package authority

type Observer interface{ Observe(Event) }

type Event struct {
	Kind   EventKind
	Result ErrorCode
}

type EventKind uint8

const (
	EventAcquireRequested EventKind = iota + 1
	EventAcquireCoalesced
	EventAcquireResult
	EventRenewalRequested
	EventRenewalResult
	EventFreshnessAccepted
	EventFreshnessRejected
	EventFreshnessExpired
	EventGenerationAdvanced
	EventAuthorityInvalidated
	EventCacheHit
	EventCacheMiss
	EventCacheFull
	EventAmbiguousQuarantine
	EventRollbackFloorUpdated
	EventRollbackFloorRejected
	EventRetryDecision
)

type noopObserver struct{}

func (noopObserver) Observe(Event) {}
