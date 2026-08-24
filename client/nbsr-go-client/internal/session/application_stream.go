package session

import (
	"context"
	"io"
	"math/bits"
	"sync/atomic"
	"time"

	"nbsr.local/client/nbsr-go-client/internal/authority"
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

type pendingAdmission struct {
	cancel context.CancelFunc
	wire   WireApplicationStream
	stop   func() bool
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

func (stream *ApplicationStream) Read(payload []byte) (int, error) {
	state := stream.State()
	if state != ApplicationStreamAccepted {
		err := ErrStreamNotAccepted
		if state == ApplicationStreamClosed || state == ApplicationStreamFailed {
			err = ErrStreamClosed
		}
		return 0, err
	}
	return stream.wire.Read(payload)
}

// FinishWrite sends the QUIC write-side FIN while retaining accepted stream
// ownership so a response can still be read before Close removes ownership.
func (stream *ApplicationStream) FinishWrite() error {
	if stream.State() != ApplicationStreamAccepted {
		return ErrStreamClosed
	}
	return stream.wire.Close()
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
	credit, channel, opener, pendingID, admissionCtx, err := manager.reserveApplicationAdmission(ctx, generation, handle)
	if err != nil {
		return nil, err
	}
	var wire WireApplicationStream
	defer func() {
		if resultErr == nil {
			return
		}
		manager.abortApplicationAdmission(generation, handle, channel, pendingID, credit)
	}()
	wire, err = OpenAdmittedWireApplication(admissionCtx, opener, credit, func(opened WireApplicationStream) error {
		manager.mu.Lock()
		defer manager.mu.Unlock()
		entry := manager.sessions[generation]
		if entry == nil || entry.channels[handle] != channel || channel.pending[pendingID] == nil {
			return ErrStreamClosed
		}
		record := channel.pending[pendingID]
		record.wire = opened
		record.stop = context.AfterFunc(admissionCtx, func() { _ = opened.Close() })
		return nil
	})
	if err != nil {
		return nil, err
	}
	stream := newApplicationStream(manager, credit, wire)
	token := channel.authority
	owner := authority.AdmissionOwner{TSGeneration: authority.TSGeneration(generation), ChannelID: [16]byte(credit.ChannelID)}
	err = manager.authority.CommitApplication(token, owner, manager.clock.NowUnix(), func() error {
		manager.mu.Lock()
		defer manager.mu.Unlock()
		entry := manager.sessions[generation]
		if entry == nil || entry.snapshot.State != TransportCurrent || entry.channels[handle] != channel || channel.authority != token || !creditBindingMatches(entry, channel, credit) || channel.credits.epoch(credit.Epoch) == nil || channel.pending[pendingID] == nil {
			return ErrCreditBinding
		}
		if _, exists := channel.streams[stream.id]; exists {
			return ErrDuplicateStream
		}
		used := manager.sessionBytes + manager.channelBytes + manager.streamBytes
		if used > manager.limits.MaxStateBytes || applicationStreamCost > manager.limits.MaxStateBytes-used {
			return ErrStreamCapacity
		}
		record := channel.pending[pendingID]
		if admissionCtx.Err() != nil || (record.stop != nil && !record.stop()) {
			return ErrStreamClosed
		}
		record.cancel()
		delete(channel.pending, pendingID)
		manager.pendingAdmissions--
		channel.streams[stream.id] = stream
		manager.streamBytes += applicationStreamCost
		stream.state.Store(uint32(ApplicationStreamAccepted))
		return nil
	})
	if err != nil {
		return nil, authorityError(err)
	}
	return stream, nil
}

func (manager *Manager) reserveApplicationAdmission(ctx context.Context, generation corestate.TSGeneration, handle corestate.ServiceHandle) (CreditReservation, *channelEntry, ApplicationStreamOpener, uint64, context.Context, error) {
	manager.mu.Lock()
	entry := manager.sessions[generation]
	if entry == nil || entry.snapshot.State != TransportCurrent || entry.channels[handle] == nil {
		manager.mu.Unlock()
		return CreditReservation{}, nil, nil, 0, nil, ErrStreamClosed
	}
	channel := entry.channels[handle]
	opener, ok := channel.wire.(ApplicationStreamOpener)
	authorityGeneration := entry.snapshot.AuthorityGeneration
	manager.mu.Unlock()
	if !ok || opener.StreamCreditProfile() != StreamCreditProfileID {
		return CreditReservation{}, nil, nil, 0, nil, ErrProfileUnsupported
	}
	if err := manager.authority.Validate(authorityGeneration); err != nil {
		_ = manager.CloseServiceChannel(generation, handle)
		return CreditReservation{}, nil, nil, 0, nil, ErrAuthorityStale
	}
	manager.mu.Lock()
	defer manager.mu.Unlock()
	entry = manager.sessions[generation]
	if entry == nil || entry.snapshot.State != TransportCurrent || entry.snapshot.AuthorityGeneration != authorityGeneration || entry.channels[handle] != channel {
		return CreditReservation{}, nil, nil, 0, nil, ErrStreamClosed
	}
	if manager.pendingAdmissions >= manager.limits.MaxPendingAdmissions || manager.streamCountLocked()+manager.pendingAdmissions >= manager.limits.MaxStreams || manager.nextPendingAdmission == ^uint64(0) {
		return CreditReservation{}, nil, nil, 0, nil, ErrStreamCapacity
	}
	available := ^channel.credits.current.used
	if available == 0 {
		return CreditReservation{}, nil, nil, 0, nil, ErrCreditExhausted
	}
	slot := uint8(bits.TrailingZeros64(available))
	channel.credits.current.used |= uint64(1) << slot
	channel.credits.current.active++
	credit := reservationFor(entry, channel, handle, channel.credits.current.number, slot)
	manager.nextPendingAdmission++
	pendingID := manager.nextPendingAdmission
	admissionCtx, cancel := context.WithCancel(ctx)
	channel.pending[pendingID] = &pendingAdmission{cancel: cancel}
	manager.pendingAdmissions++
	return credit, channel, opener, pendingID, admissionCtx, nil
}

func (manager *Manager) abortApplicationAdmission(generation corestate.TSGeneration, handle corestate.ServiceHandle, channel *channelEntry, pendingID uint64, credit CreditReservation) {
	var wire WireApplicationStream
	manager.mu.Lock()
	entry := manager.sessions[generation]
	if entry != nil && entry.channels[handle] == channel {
		if record := channel.pending[pendingID]; record != nil {
			if record.stop != nil {
				record.stop()
			}
			record.cancel()
			wire = record.wire
			delete(channel.pending, pendingID)
			manager.pendingAdmissions--
			_ = releaseCreditAssignment(&channel.credits, credit.Epoch)
		}
	}
	manager.mu.Unlock()
	if wire != nil {
		_ = wire.Close()
	}
}

// OpenAdmittedWireApplication performs the accepted P2D same-stream exchange.
// It never returns the wire stream before the exact ACCEPT byte has arrived.
func OpenAdmittedWireApplication(ctx context.Context, opener ApplicationStreamOpener, credit CreditReservation, onOpen func(WireApplicationStream) error) (WireApplicationStream, error) {
	if ctx == nil || opener == nil || opener.StreamCreditProfile() != StreamCreditProfileID {
		return nil, ErrProfileUnsupported
	}
	wire, err := opener.OpenApplicationStream(ctx)
	if err != nil || wire == nil {
		if wire != nil {
			_ = wire.Close()
		}
		return nil, ErrTransport
	}
	fail := func(err error) (WireApplicationStream, error) {
		_ = wire.Close()
		return nil, err
	}
	if onOpen != nil {
		if err := onOpen(wire); err != nil {
			return fail(err)
		}
	}
	preface, err := encodeStreamCreditPreface(credit.ChannelID, credit.ChannelGeneration, credit.Epoch, credit.Slot, wire.StreamID())
	if err != nil {
		return fail(err)
	}
	if err := writeAll(wire, preface); err != nil {
		return fail(ErrAdmissionRejected)
	}
	decision := []byte{0xff}
	if _, err := io.ReadFull(wire, decision); err != nil || decision[0] != 0 {
		return fail(ErrAdmissionRejected)
	}
	return wire, nil
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
	opener, _ := channel.wire.(ApplicationStreamOpener)
	delete(channel.streams, stream.id)
	manager.streamBytes -= applicationStreamCost
	_ = releaseCreditAssignment(&channel.credits, stream.credit.Epoch)
	stream.state.Store(uint32(ApplicationStreamClosed))
	manager.mu.Unlock()
	closeErr := stream.wire.Close()
	if opener != nil {
		if refillEpoch, refillErr := manager.BeginCreditRefill(stream.generation, stream.handle); refillErr == nil {
			refillContext, cancelRefill := context.WithTimeout(context.Background(), 5*time.Second)
			refillErr = opener.RefillStreamCredits(refillContext, refillEpoch)
			cancelRefill()
			if refillErr == nil {
				if completeErr := manager.CompleteCreditRefill(stream.generation, stream.handle, refillEpoch); completeErr != nil {
					_ = manager.CancelCreditRefill(stream.generation, stream.handle)
				}
			} else {
				_ = manager.CancelCreditRefill(stream.generation, stream.handle)
			}
		}
	}
	return closeErr
}
