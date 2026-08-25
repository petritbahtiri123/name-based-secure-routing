// Package observability provides bounded, identifier-free client telemetry.
package observability

import "sync/atomic"

// Domain is a closed telemetry subsystem dimension.
type Domain uint8

const (
	DomainInvalid Domain = iota
	DomainMapping
	DomainFlow
	DomainProxy
	DomainAuthority
	DomainSession
	DomainChannel
	DomainCredit
	DomainStream
	DomainRetry
	DomainRuntime
	domainCount
)

// Kind is a closed lifecycle or decision dimension.
type Kind uint8

const (
	KindInvalid Kind = iota
	KindStarted
	KindAdmitted
	KindCoalesced
	KindRejected
	KindExhausted
	KindFailedClosed
	KindReleased
	KindExpired
	KindShutdown
	kindCount
)

// Outcome distinguishes success, expected denial, and internal failure.
type Outcome uint8

const (
	OutcomeInvalid Outcome = iota
	OutcomeSuccess
	OutcomeExpectedDenial
	OutcomeInternalFailure
	outcomeCount
)

// Event contains only closed dimensions. Identifiers and caller-controlled
// strings deliberately have no representation at this boundary.
type Event struct {
	Domain  Domain
	Kind    Kind
	Outcome Outcome
}

// Recorder accepts identifier-free events.
type Recorder interface {
	Record(Event)
}

// Collector owns fixed-size concurrent counters and no background resources.
type Collector struct {
	counts  [domainCount][kindCount][outcomeCount]atomic.Uint64
	invalid atomic.Uint64
}

// NewCollector constructs an empty collector.
func NewCollector() *Collector { return &Collector{} }

func (collector *Collector) Record(event Event) {
	if collector == nil {
		return
	}
	if event.Domain <= DomainInvalid || event.Domain >= domainCount || event.Kind <= KindInvalid || event.Kind >= kindCount || event.Outcome <= OutcomeInvalid || event.Outcome >= outcomeCount {
		collector.invalid.Add(1)
		return
	}
	collector.counts[event.Domain][event.Kind][event.Outcome].Add(1)
}

// Snapshot is an immutable value copy of all fixed counters.
type Snapshot struct {
	Counts        [domainCount][kindCount][outcomeCount]uint64
	InvalidEvents uint64
}

func (collector *Collector) Snapshot() Snapshot {
	var snapshot Snapshot
	if collector == nil {
		return snapshot
	}
	for domain := Domain(1); domain < domainCount; domain++ {
		for kind := Kind(1); kind < kindCount; kind++ {
			for outcome := Outcome(1); outcome < outcomeCount; outcome++ {
				snapshot.Counts[domain][kind][outcome] = collector.counts[domain][kind][outcome].Load()
			}
		}
	}
	snapshot.InvalidEvents = collector.invalid.Load()
	return snapshot
}

func (snapshot Snapshot) Count(domain Domain, kind Kind, outcome Outcome) uint64 {
	if domain <= DomainInvalid || domain >= domainCount || kind <= KindInvalid || kind >= kindCount || outcome <= OutcomeInvalid || outcome >= outcomeCount {
		return 0
	}
	return snapshot.Counts[domain][kind][outcome]
}

// Resource indexes one fixed aggregate usage slot.
type Resource uint8

const (
	ResourceMappings Resource = iota
	ResourceFlows
	ResourceProxyConnections
	ResourceAuthorityPending
	ResourceSessions
	ResourceChannels
	ResourceCredits
	ResourceStreams
	ResourceRetries
	resourceCount
)

// ResourceUsage reports aggregate use and configured capacity.
type ResourceUsage struct {
	Used     uint64
	Capacity uint64
}

// HealthState is the coarse local health state.
type HealthState uint8

const (
	HealthReady HealthState = iota + 1
	HealthDegraded
)

// HealthReason is a closed, privacy-safe health classification.
type HealthReason uint8

const (
	HealthNominal HealthReason = iota + 1
	HealthCapacityPressure
	HealthInternalFailure
)

// Health contains aggregate counters and fixed resource usage only.
type Health struct {
	State            HealthState
	Reason           HealthReason
	ExpectedDenials  uint64
	InternalFailures uint64
	Resources        [resourceCount]ResourceUsage
}

func (collector *Collector) Health(resources [resourceCount]ResourceUsage) Health {
	snapshot := collector.Snapshot()
	health := Health{State: HealthReady, Reason: HealthNominal, Resources: resources}
	for domain := Domain(1); domain < domainCount; domain++ {
		for kind := Kind(1); kind < kindCount; kind++ {
			health.ExpectedDenials += snapshot.Count(domain, kind, OutcomeExpectedDenial)
			health.InternalFailures += snapshot.Count(domain, kind, OutcomeInternalFailure)
		}
	}
	if health.InternalFailures != 0 || snapshot.InvalidEvents != 0 {
		health.State = HealthDegraded
		health.Reason = HealthInternalFailure
		return health
	}
	for _, usage := range resources {
		if usage.Capacity != 0 && usage.Used >= usage.Capacity {
			health.State = HealthDegraded
			health.Reason = HealthCapacityPressure
			break
		}
	}
	return health
}
