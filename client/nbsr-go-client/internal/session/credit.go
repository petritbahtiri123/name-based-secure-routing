package session

import (
	"math/bits"

	"nbsr.local/client/nbsr-go-client/internal/corestate"
)

const (
	StreamCreditCount        = 64
	StreamCreditLowWatermark = 16
)

type CreditReservation struct {
	Generation          corestate.TSGeneration
	Handle              corestate.ServiceHandle
	ChannelID           corestate.ChannelID
	ChannelGeneration   uint64
	AuthorityGeneration corestate.AuthorityGeneration
	Epoch               uint64
	Slot                uint8
}

type CreditSnapshot struct {
	CurrentEpoch  uint64
	DrainingEpoch uint64
	Available     uint8
	RefillPending bool
}

type creditEpoch struct {
	number uint64
	used   uint64
	active uint8
}

type creditWindow struct {
	current       creditEpoch
	draining      *creditEpoch
	pendingRefill uint64
}

func newCreditWindow() creditWindow {
	return creditWindow{current: creditEpoch{number: 1}}
}

func (manager *Manager) CreditSnapshot(generation corestate.TSGeneration, handle corestate.ServiceHandle) (CreditSnapshot, error) {
	manager.mu.Lock()
	entry := manager.sessions[generation]
	if entry == nil || entry.channels[handle] == nil {
		manager.mu.Unlock()
		return CreditSnapshot{}, ErrCreditClosed
	}
	channel := entry.channels[handle]
	authorityGeneration := entry.snapshot.AuthorityGeneration
	manager.mu.Unlock()
	if err := manager.authority.Validate(authorityGeneration); err != nil {
		_ = manager.CloseServiceChannel(generation, handle)
		return CreditSnapshot{}, ErrCreditClosed
	}
	manager.mu.Lock()
	defer manager.mu.Unlock()
	entry = manager.sessions[generation]
	if entry == nil || entry.channels[handle] != channel {
		return CreditSnapshot{}, ErrCreditClosed
	}
	return channel.credits.snapshot(), nil
}

func (manager *Manager) ReserveStreamCredit(generation corestate.TSGeneration, handle corestate.ServiceHandle) (CreditReservation, error) {
	manager.mu.Lock()
	entry := manager.sessions[generation]
	if entry == nil || entry.snapshot.State != TransportCurrent {
		manager.mu.Unlock()
		return CreditReservation{}, ErrCreditClosed
	}
	channel := entry.channels[handle]
	if channel == nil {
		manager.mu.Unlock()
		return CreditReservation{}, ErrCreditClosed
	}
	authorityGeneration := entry.snapshot.AuthorityGeneration
	manager.mu.Unlock()
	if err := manager.authority.Validate(authorityGeneration); err != nil {
		_ = manager.CloseServiceChannel(generation, handle)
		return CreditReservation{}, ErrCreditClosed
	}
	manager.mu.Lock()
	defer manager.mu.Unlock()
	entry = manager.sessions[generation]
	if entry == nil || entry.snapshot.State != TransportCurrent || entry.snapshot.AuthorityGeneration != authorityGeneration || entry.channels[handle] != channel {
		return CreditReservation{}, ErrCreditClosed
	}
	available := ^channel.credits.current.used
	if available == 0 {
		return CreditReservation{}, ErrCreditExhausted
	}
	slot := uint8(bits.TrailingZeros64(available))
	channel.credits.current.used |= uint64(1) << slot
	channel.credits.current.active++
	return reservationFor(entry, channel, handle, channel.credits.current.number, slot), nil
}

// ReserveSpecificStreamCredit validates externally supplied credit coordinates.
// It exists for deterministic replay/binding checks; normal callers allocate via
// ReserveStreamCredit.
func (manager *Manager) ReserveSpecificStreamCredit(reservation CreditReservation) (CreditReservation, error) {
	manager.mu.Lock()
	defer manager.mu.Unlock()
	if reservation.Epoch == 0 || reservation.Slot >= StreamCreditCount {
		return CreditReservation{}, ErrCreditMalformed
	}
	entry := manager.sessions[reservation.Generation]
	if entry == nil {
		return CreditReservation{}, ErrCreditBinding
	}
	channel := entry.channels[reservation.Handle]
	if channel == nil || !creditBindingMatches(entry, channel, reservation) {
		return CreditReservation{}, ErrCreditBinding
	}
	epoch := channel.credits.epoch(reservation.Epoch)
	if epoch == nil {
		return CreditReservation{}, ErrCreditStaleEpoch
	}
	bit := uint64(1) << reservation.Slot
	if epoch.used&bit != 0 {
		return CreditReservation{}, ErrCreditConsumed
	}
	epoch.used |= bit
	epoch.active++
	return reservation, nil
}

func (manager *Manager) BeginCreditRefill(generation corestate.TSGeneration, handle corestate.ServiceHandle) (uint64, error) {
	manager.mu.Lock()
	defer manager.mu.Unlock()
	window, err := manager.creditWindowLocked(generation, handle)
	if err != nil {
		return 0, err
	}
	if window.draining != nil {
		return 0, ErrEpochCapacity
	}
	if window.pendingRefill != 0 {
		return 0, ErrRefillPending
	}
	if StreamCreditCount-bits.OnesCount64(window.current.used) > StreamCreditLowWatermark {
		return 0, ErrRefillNotDue
	}
	if window.current.number == ^uint64(0) {
		return 0, ErrEpochCapacity
	}
	window.pendingRefill = window.current.number + 1
	return window.pendingRefill, nil
}

func (manager *Manager) CompleteCreditRefill(generation corestate.TSGeneration, handle corestate.ServiceHandle, epoch uint64) error {
	manager.mu.Lock()
	defer manager.mu.Unlock()
	window, err := manager.creditWindowLocked(generation, handle)
	if err != nil {
		return err
	}
	if window.draining != nil {
		return ErrEpochCapacity
	}
	if epoch == 0 || window.pendingRefill != epoch || epoch != window.current.number+1 {
		return ErrCreditStaleEpoch
	}
	draining := window.current
	if draining.active != 0 {
		window.draining = &draining
	}
	window.current = creditEpoch{number: epoch}
	window.pendingRefill = 0
	return nil
}

func (manager *Manager) CancelCreditRefill(generation corestate.TSGeneration, handle corestate.ServiceHandle) error {
	manager.mu.Lock()
	defer manager.mu.Unlock()
	window, err := manager.creditWindowLocked(generation, handle)
	if err != nil {
		return err
	}
	if window.pendingRefill == 0 {
		return ErrCreditStaleEpoch
	}
	window.pendingRefill = 0
	return nil
}

func (manager *Manager) creditWindowLocked(generation corestate.TSGeneration, handle corestate.ServiceHandle) (*creditWindow, error) {
	entry := manager.sessions[generation]
	if entry == nil || entry.snapshot.State != TransportCurrent || entry.channels[handle] == nil {
		return nil, ErrCreditClosed
	}
	return &entry.channels[handle].credits, nil
}

func (window *creditWindow) epoch(number uint64) *creditEpoch {
	if window.current.number == number {
		return &window.current
	}
	if window.draining != nil && window.draining.number == number {
		return window.draining
	}
	return nil
}

func (window *creditWindow) snapshot() CreditSnapshot {
	snapshot := CreditSnapshot{CurrentEpoch: window.current.number, Available: uint8(StreamCreditCount - bits.OnesCount64(window.current.used)), RefillPending: window.pendingRefill != 0}
	if window.draining != nil {
		snapshot.DrainingEpoch = window.draining.number
	}
	return snapshot
}

func reservationFor(entry *transportEntry, channel *channelEntry, handle corestate.ServiceHandle, epoch uint64, slot uint8) CreditReservation {
	return CreditReservation{Generation: channel.snapshot.Generation, Handle: handle, ChannelID: channel.snapshot.ChannelID, ChannelGeneration: channel.snapshot.ChannelGeneration, AuthorityGeneration: channel.snapshot.AuthorityGeneration, Epoch: epoch, Slot: slot}
}

func creditBindingMatches(entry *transportEntry, channel *channelEntry, reservation CreditReservation) bool {
	return entry.snapshot.Generation == reservation.Generation && channel.snapshot.Generation == reservation.Generation && channel.snapshot.Handle == reservation.Handle && channel.snapshot.ChannelID == reservation.ChannelID && channel.snapshot.ChannelGeneration == reservation.ChannelGeneration && channel.snapshot.AuthorityGeneration == reservation.AuthorityGeneration
}

func releaseCreditAssignment(window *creditWindow, epoch uint64) error {
	value := window.epoch(epoch)
	if value == nil || value.active == 0 {
		return ErrCreditStaleEpoch
	}
	value.active--
	if window.draining == value && value.active == 0 {
		window.draining = nil
	}
	return nil
}
