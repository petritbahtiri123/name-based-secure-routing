package session

import (
	"context"

	"nbsr.local/client/nbsr-go-client/internal/authority"
	"nbsr.local/client/nbsr-go-client/internal/corestate"
	"nbsr.local/client/nbsr-go-client/internal/identity"
)

type Transport interface{ Close() error }

type WireChannel interface {
	ChannelID() corestate.ChannelID
	ChannelGeneration() uint64
	Close() error
}

type Connector interface {
	Connect(context.Context, TransportSessionAttempt) (Transport, error)
}

type ChannelOpener interface {
	Open(context.Context, Transport, ServiceChannelAttempt) (WireChannel, error)
}

type Clock interface{ NowUnix() uint64 }

type Limits struct {
	MaxReuseKeys, MaxSessions, MaxChannels                       int
	MaxPendingSessions, MaxPendingChannels, MaxWaitersPerChannel int
	MaxReuseKeyBytes, MaxServiceIdentityBytes                    int
	MaxStateBytes                                                uint64
}

func (limits Limits) validate() error {
	if limits.MaxReuseKeys <= 0 || limits.MaxSessions <= 0 || limits.MaxChannels <= 0 ||
		limits.MaxPendingSessions <= 0 || limits.MaxPendingChannels <= 0 || limits.MaxWaitersPerChannel <= 0 ||
		limits.MaxReuseKeyBytes <= 0 || limits.MaxServiceIdentityBytes <= 0 || limits.MaxStateBytes == 0 {
		return ErrInvalidLimits
	}
	return nil
}

type ReuseKey struct {
	SourceOperator, Gateway, Profile, Transport string
	DeviceID                                    [32]byte
	DeviceGeneration                            uint64
	PolicyDigest                                [32]byte
	PolicyGeneration                            uint64
}

type TransportState uint8

const (
	TransportCurrent TransportState = iota + 1
	TransportDraining
)

type TransportSessionSpec struct {
	Generation corestate.TSGeneration
	ReuseKey   ReuseKey
	Proof      identity.TSProofKey
}

type TransportSessionAttempt struct {
	Generation          corestate.TSGeneration
	ReuseKey            ReuseKey
	ProofKey            identity.KeyRef
	AuthorityGeneration authority.AuthorityGeneration
}

type TransportSessionSnapshot struct {
	Generation          corestate.TSGeneration
	ReuseKey            ReuseKey
	State               TransportState
	ProofThumbprint     [32]byte
	AuthorityGeneration authority.AuthorityGeneration
}

type ServiceChannelRequest struct {
	Generation          corestate.TSGeneration
	ChannelID           corestate.ChannelID
	ServiceIdentity     string
	ServiceDigest       corestate.ServiceDigest
	RouteGrantDigest    corestate.RouteGrantDigest
	AuthorityGeneration corestate.AuthorityGeneration
	ProofThumbprint     authority.ProofKeyThumbprint
	Reservation         authority.Reservation
}

type ServiceChannelAttempt struct {
	Generation      corestate.TSGeneration
	ChannelID       corestate.ChannelID
	ServiceIdentity string
	ServiceDigest   corestate.ServiceDigest
	RouteGrant      corestate.RouteGrantDigest
	ExactRouteGrant []byte
	ProofThumbprint authority.ProofKeyThumbprint
}

type ServiceChannelSnapshot struct {
	Generation          corestate.TSGeneration
	Handle              corestate.ServiceHandle
	ChannelID           corestate.ChannelID
	ChannelGeneration   uint64
	ServiceIdentity     string
	ServiceDigest       corestate.ServiceDigest
	RouteGrantDigest    corestate.RouteGrantDigest
	AuthorityGeneration corestate.AuthorityGeneration
}

type Usage struct {
	ReuseKeys, Sessions, Channels, PendingSessions, PendingChannels, ChannelWaiters int
	SessionBytes, ChannelBytes, StateBytes                                          uint64
}
