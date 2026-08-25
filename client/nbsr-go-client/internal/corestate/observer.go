package corestate

type Clock interface {
	NowUnix() uint64
}

type Observer interface {
	Observe(Event)
}

type Event struct {
	Kind EventKind
}

type EventKind uint8

const (
	EventMappingInserted EventKind = iota + 1
	EventMappingRemoved
	EventServiceInserted
	EventServiceClosed
	EventServiceRemoved
	EventStreamInserted
	EventStreamTerminal
	EventStreamRemoved
	EventGenerationClosed
)

type noopObserver struct{}

func (noopObserver) Observe(Event) {}
