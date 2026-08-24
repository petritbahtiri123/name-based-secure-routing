package session

import (
	"context"
	"io"
	"sync/atomic"

	"nbsr.local/client/nbsr-go-client/internal/corestate"
)

const applicationStreamCost uint64 = 80

type ApplicationStreamState uint32

const (
	ApplicationStreamPendingAdmission ApplicationStreamState = iota + 1
	ApplicationStreamAccepted
	ApplicationStreamClosed
	ApplicationStreamFailed
)

type WireApplicationStream interface {
	io.Reader
	io.Writer
	StreamID() corestate.StreamID
	Close() error
}

type ApplicationStreamOpener interface {
	StreamCreditProfile() string
	OpenApplicationStream(context.Context) (WireApplicationStream, error)
	RefillStreamCredits(context.Context, uint64) error
}

type ApplicationStream struct {
	manager    *Manager
	generation corestate.TSGeneration
	handle     corestate.ServiceHandle
	id         corestate.StreamID
	credit     CreditReservation
	wire       WireApplicationStream
	state      atomic.Uint32
}

func newApplicationStream(manager *Manager, credit CreditReservation, wire WireApplicationStream) *ApplicationStream {
	stream := &ApplicationStream{manager: manager, generation: credit.Generation, handle: credit.Handle, id: wire.StreamID(), credit: credit, wire: wire}
	stream.state.Store(uint32(ApplicationStreamPendingAdmission))
	return stream
}

func (stream *ApplicationStream) StreamID() corestate.StreamID { return stream.id }
func (stream *ApplicationStream) State() ApplicationStreamState {
	return ApplicationStreamState(stream.state.Load())
}
func (stream *ApplicationStream) Write(payload []byte) (int, error) {
	state := stream.State()
	if state != ApplicationStreamAccepted {
		if state == ApplicationStreamClosed || state == ApplicationStreamFailed {
			return 0, ErrStreamClosed
		}
		return 0, ErrStreamNotAccepted
	}
	return stream.wire.Write(payload)
}
func (stream *ApplicationStream) Close() error {
	if stream.manager == nil {
		previous := ApplicationStreamState(stream.state.Swap(uint32(ApplicationStreamClosed)))
		if previous == ApplicationStreamClosed {
			return nil
		}
		return stream.wire.Close()
	}
	return stream.manager.closeApplicationStream(stream)
}

func (manager *Manager) OpenApplicationStream(ctx context.Context, generation corestate.TSGeneration, handle corestate.ServiceHandle) (_ *ApplicationStream, resultErr error) {
	if ctx == nil || handle == corestate.InvalidServiceHandle {
		return nil, ErrStreamClosed
	}
	credit, err := manager.ReserveStreamCredit(generation, handle)
	if err != nil {
		return nil, err
	}
	manager.mu.Lock()
	entry := manager.sessions[generation]
	if entry == nil || entry.snapshot.State != TransportCurrent || entry.channels[handle] == nil || !creditBindingMatches(entry, entry.channels[handle], credit) {
		manager.mu.Unlock()
		return nil, ErrCreditBinding
	}
	channel := entry.channels[handle]
	opener, ok := channel.wire.(ApplicationStreamOpener)
	if !ok || opener.StreamCreditProfile() != StreamCreditProfileID {
		manager.mu.Unlock()
		return nil, ErrProfileUnsupported
	}
	if manager.pendingAdmissions >= manager.limits.MaxPendingAdmissions || manager.streamCountLocked()+manager.pendingAdmissions >= manager.limits.MaxStreams {
		manager.mu.Unlock()
		return nil, ErrStreamCapacity
	}
	manager.pendingAdmissions++
	authorityGeneration := entry.snapshot.AuthorityGeneration
	manager.mu.Unlock()
	if refillEpoch, refillErr := manager.BeginCreditRefill(generation, handle); refillErr == nil {
		if refillErr = opener.RefillStreamCredits(ctx, refillEpoch); refillErr == nil {
			if completeErr := manager.CompleteCreditRefill(generation, handle, refillEpoch); completeErr != nil {
				_ = manager.CancelCreditRefill(generation, handle)
			}
		} else {
			_ = manager.CancelCreditRefill(generation, handle)
		}
	}

	committed := false
	var wire WireApplicationStream
	defer func() {
		if committed {
			return
		}
		manager.mu.Lock()
		manager.pendingAdmissions--
		currentEntry := manager.sessions[generation]
		if currentEntry != nil && currentEntry.channels[handle] == channel {
			_ = releaseCreditAssignment(&channel.credits, credit.Epoch)
		}
		manager.mu.Unlock()
		if wire != nil {
			_ = wire.Close()
		}
	}()

	wire, err = opener.OpenApplicationStream(ctx)
	if err != nil || wire == nil {
		return nil, ErrTransport
	}
	stream := newApplicationStream(manager, credit, wire)
	preface, err := encodeStreamCreditPreface(credit.ChannelID, credit.ChannelGeneration, credit.Epoch, credit.Slot, stream.id)
	if err != nil {
		return nil, err
	}
	if err := writeAll(wire, preface); err != nil {
		return nil, ErrAdmissionRejected
	}
	decision := []byte{0xff}
	if _, err := io.ReadFull(wire, decision); err != nil || decision[0] != 0 {
		return nil, ErrAdmissionRejected
	}
	if err := manager.authority.Validate(authorityGeneration); err != nil {
		return nil, ErrAuthorityStale
	}
	manager.mu.Lock()
	currentEntry := manager.sessions[generation]
	if currentEntry == nil || currentEntry != entry || currentEntry.snapshot.State != TransportCurrent || currentEntry.snapshot.AuthorityGeneration != authorityGeneration || currentEntry.channels[handle] != channel || !creditBindingMatches(currentEntry, channel, credit) || channel.credits.epoch(credit.Epoch) == nil {
		manager.mu.Unlock()
		return nil, ErrCreditBinding
	}
	if _, exists := channel.streams[stream.id]; exists {
		manager.mu.Unlock()
		return nil, ErrDuplicateStream
	}
	used := manager.sessionBytes + manager.channelBytes + manager.streamBytes
	if used > manager.limits.MaxStateBytes || applicationStreamCost > manager.limits.MaxStateBytes-used {
		manager.mu.Unlock()
		return nil, ErrStreamCapacity
	}
	manager.pendingAdmissions--
	channel.streams[stream.id] = stream
	manager.streamBytes += applicationStreamCost
	stream.state.Store(uint32(ApplicationStreamAccepted))
	committed = true
	manager.mu.Unlock()
	return stream, nil
}

func writeAll(writer io.Writer, value []byte) error {
	for len(value) != 0 {
		n, err := writer.Write(value)
		if err != nil {
			return err
		}
		if n <= 0 || n > len(value) {
			return io.ErrShortWrite
		}
		value = value[n:]
	}
	return nil
}

func (manager *Manager) closeApplicationStream(stream *ApplicationStream) error {
	manager.mu.Lock()
	entry := manager.sessions[stream.generation]
	if entry == nil || entry.channels[stream.handle] == nil || entry.channels[stream.handle].streams[stream.id] != stream {
		manager.mu.Unlock()
		stream.state.Store(uint32(ApplicationStreamClosed))
		return nil
	}
	channel := entry.channels[stream.handle]
	delete(channel.streams, stream.id)
	manager.streamBytes -= applicationStreamCost
	_ = releaseCreditAssignment(&channel.credits, stream.credit.Epoch)
	stream.state.Store(uint32(ApplicationStreamClosed))
	manager.mu.Unlock()
	return stream.wire.Close()
}
