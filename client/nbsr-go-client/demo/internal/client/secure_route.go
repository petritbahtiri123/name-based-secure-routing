package client

import (
	"context"
	"errors"
	"io"
	"sync"

	"nbsr.local/client/nbsr-go-client/internal/authority"
	"nbsr.local/client/nbsr-go-client/internal/corestate"
	"nbsr.local/client/nbsr-go-client/internal/resolution"
	"nbsr.local/client/nbsr-go-client/internal/session"
)

type RoutePlanner interface {
	PlanRoute(*resolution.MappedRoute) (*session.RoutePlan, error)
}

type SessionRoutePlanner struct {
	manager *session.Manager
	spec    session.TransportSessionSpec
	public  []byte
}

func NewSessionRoutePlanner(manager *session.Manager, spec session.TransportSessionSpec, proof *TSProofOwner) (*SessionRoutePlanner, error) {
	if manager == nil || proof == nil || spec.Generation == 0 || spec.Proof.Key != proof.KeyRef() || uint64(spec.Generation) != proof.KeyRef().Generation {
		return nil, session.ErrProofBinding
	}
	return &SessionRoutePlanner{manager: manager, spec: spec, public: proof.PublicKey()}, nil
}

func (planner *SessionRoutePlanner) PlanRoute(route *resolution.MappedRoute) (*session.RoutePlan, error) {
	if planner == nil || planner.manager == nil {
		return nil, session.ErrInvalidSession
	}
	return planner.manager.PlanRoute(route, planner.spec, planner.public)
}

type SecureRouteOpenerConfig struct {
	Authority       *AuthorityClient
	Sessions        *session.Manager
	Planner         RoutePlanner
	AcquireTemplate authority.AcquireRequest
	ChannelID       corestate.ChannelID
}

type SecureRouteOpener struct {
	authority  *AuthorityClient
	sessions   *session.Manager
	planner    RoutePlanner
	template   authority.AcquireRequest
	channelID  corestate.ChannelID
	mu         sync.Mutex
	generation corestate.TSGeneration
	handle     corestate.ServiceHandle
	closed     bool
}

func NewSecureRouteOpener(config SecureRouteOpenerConfig) (*SecureRouteOpener, error) {
	if config.Authority == nil || config.Sessions == nil || config.Planner == nil || config.ChannelID == (corestate.ChannelID{}) {
		return nil, session.ErrInvalidSession
	}
	return &SecureRouteOpener{
		authority: config.Authority,
		sessions:  config.Sessions,
		planner:   config.Planner,
		template:  config.AcquireTemplate,
		channelID: config.ChannelID,
	}, nil
}

func (opener *SecureRouteOpener) OpenVerifiedRoute(ctx context.Context, mapped *resolution.MappedRoute) (_ io.ReadWriteCloser, resultErr error) {
	if ctx == nil || mapped == nil || opener == nil {
		return nil, session.ErrInvalidSession
	}
	plan, err := opener.planner.PlanRoute(mapped)
	if err != nil {
		return nil, err
	}
	request, err := plan.BuildAcquireRequest(opener.template)
	if err != nil {
		return nil, err
	}
	reservation, err := opener.authority.AcquireRoute(ctx, request)
	if err != nil {
		return nil, err
	}
	consumed := false
	defer func() {
		if resultErr != nil && !consumed {
			_ = opener.authority.Manager().Release(reservation)
		}
	}()
	transport, err := plan.CreateTransportSession(ctx)
	if err != nil {
		return nil, err
	}
	proof, err := plan.ProofBinding()
	if err != nil {
		_ = opener.sessions.CloseTransportSession(transport.Generation)
		return nil, err
	}
	route, err := mapped.Context()
	if err != nil {
		_ = opener.sessions.CloseTransportSession(transport.Generation)
		return nil, err
	}
	channel, err := opener.sessions.CreateServiceChannel(ctx, session.ServiceChannelRequest{
		Generation: transport.Generation, ChannelID: opener.channelID, ServiceIdentity: route.ServiceIdentity,
		ServiceDigest: route.ServiceDigest, RouteGrantDigest: corestate.RouteGrantDigest(reservation.RouteGrantDigest()),
		AuthorityGeneration: corestate.AuthorityGeneration(reservation.AuthorityGeneration()), ProofThumbprint: proof.Thumbprint, Reservation: reservation,
	})
	if err != nil {
		_ = opener.sessions.CloseTransportSession(transport.Generation)
		return nil, err
	}
	consumed = true
	application, err := opener.sessions.OpenApplicationStream(ctx, transport.Generation, channel.Handle)
	if err != nil {
		_ = opener.sessions.CloseServiceChannel(transport.Generation, channel.Handle)
		_ = opener.sessions.CloseTransportSession(transport.Generation)
		return nil, err
	}
	opener.mu.Lock()
	if opener.closed {
		opener.mu.Unlock()
		_ = application.Close()
		_ = opener.sessions.CloseServiceChannel(transport.Generation, channel.Handle)
		_ = opener.sessions.CloseTransportSession(transport.Generation)
		return nil, session.ErrInvalidSession
	}
	opener.generation, opener.handle = transport.Generation, channel.Handle
	opener.mu.Unlock()
	return &ownedSecureRoute{stream: application}, nil
}

type ownedSecureRoute struct {
	stream *session.ApplicationStream
	once   sync.Once
	err    error
}

func (route *ownedSecureRoute) Read(payload []byte) (int, error)  { return route.stream.Read(payload) }
func (route *ownedSecureRoute) Write(payload []byte) (int, error) { return route.stream.Write(payload) }
func (route *ownedSecureRoute) CloseWrite() error                 { return route.stream.FinishWrite() }
func (route *ownedSecureRoute) Close() error {
	route.once.Do(func() {
		route.err = route.stream.Close()
	})
	return route.err
}

func (opener *SecureRouteOpener) Close() error {
	if opener == nil {
		return nil
	}
	opener.mu.Lock()
	if opener.closed {
		opener.mu.Unlock()
		return nil
	}
	opener.closed = true
	generation, handle := opener.generation, opener.handle
	opener.generation, opener.handle = 0, corestate.InvalidServiceHandle
	opener.mu.Unlock()
	if generation == 0 {
		return nil
	}
	return errors.Join(opener.sessions.CloseServiceChannel(generation, handle), opener.sessions.CloseTransportSession(generation))
}

var _ resolution.SecureRouteOpener = (*SecureRouteOpener)(nil)
