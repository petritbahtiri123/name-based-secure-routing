package corestate

type TSGeneration uint64
type ServiceHandle uint32
type MappingID uint64
type StreamID uint64
type LocalFlowID uint64
type AuthorityGeneration uint64
type CreditStateRef uint64
type ChannelID [16]byte
type ServiceDigest [32]byte
type RouteGrantDigest [32]byte
type PolicyContext string

const InvalidServiceHandle ServiceHandle = 0

type ServiceState uint8

const (
	ServiceActive ServiceState = iota + 1
	ServiceClosed
)

type StreamState uint8

const (
	StreamActive StreamState = iota + 1
	StreamCancelled
	StreamFinished
)

type TerminalReason uint8

const (
	TerminalNone TerminalReason = iota
	TerminalCancelled
	TerminalCompleted
	TerminalFailed
)

type MappingSpec struct {
	ServiceIdentity string
	ExpiresAtUnix   uint64
	PolicyContext   PolicyContext
}

type MappingSnapshot struct {
	MappingSpec
	ID               MappingID
	ActiveReferences uint64
	AccountedBytes   uint64
}

type ServiceSpec struct {
	Generation          TSGeneration
	ChannelID           ChannelID
	ChannelGeneration   uint64
	ServiceIdentity     string
	ServiceDigest       ServiceDigest
	RouteGrantDigest    RouteGrantDigest
	AuthorityGeneration AuthorityGeneration
	CreditState         CreditStateRef
}

type ServiceSnapshot struct {
	ServiceSpec
	Handle         ServiceHandle
	State          ServiceState
	ActiveStreams  uint64
	AccountedBytes uint64
}

type StreamSpec struct {
	Generation  TSGeneration
	Handle      ServiceHandle
	StreamID    StreamID
	LocalFlowID LocalFlowID
}

type StreamSnapshot struct {
	StreamSpec
	State          StreamState
	TerminalReason TerminalReason
	AccountedBytes uint64
}

type Usage struct {
	Mappings, Services, Streams             int
	MappingBytes, ServiceBytes, StreamBytes uint64
}

type MappingRegistry interface {
	AddMapping(MappingSpec) (MappingSnapshot, error)
	LookupMapping(MappingID) (MappingSnapshot, error)
	AcquireMapping(MappingID) (MappingSnapshot, error)
	ReleaseMapping(MappingID) error
	RemoveMapping(MappingID) error
	ExpireMappings() (int, error)
}

type ServiceRegistry interface {
	AddService(ServiceSpec) (ServiceSnapshot, error)
	LookupService(TSGeneration, ServiceHandle) (ServiceSnapshot, error)
	CloseService(TSGeneration, ServiceHandle) error
	RemoveService(TSGeneration, ServiceHandle) error
}

type StreamRegistry interface {
	InsertStream(StreamSpec) error
	LookupStream(TSGeneration, ServiceHandle, StreamID) (StreamSnapshot, error)
	CancelStream(TSGeneration, ServiceHandle, StreamID) error
	FinishStream(TSGeneration, ServiceHandle, StreamID, TerminalReason) error
	RemoveStream(TSGeneration, ServiceHandle, StreamID) error
}
