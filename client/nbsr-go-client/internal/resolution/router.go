package resolution

import (
	"context"
	"crypto/sha256"
	"errors"
	"io"
	"sync"

	"nbsr.local/client/nbsr-go-client/internal/authority"
	"nbsr.local/client/nbsr-go-client/internal/corestate"
)

var ErrRouteBinding = errors.New("route binding mismatch")

type mappingOwner interface {
	AcquireMapping(corestate.MappingID) (corestate.MappingSnapshot, error)
	ReleaseMapping(corestate.MappingID) error
}

type flowConsumer interface {
	Consume(corestate.LocalFlowID) (corestate.MappingID, error)
}

type RouteContext struct {
	MappingID       corestate.MappingID
	CanonicalName   string
	ServiceIdentity string
	ServiceDigest   corestate.ServiceDigest
	Intent          authority.RouteIntent
	PolicyContext   corestate.PolicyContext
}

// MappedRoute is a capability for one Mapping reference acquired by Router.
// Its fields are intentionally private: RouteContext is informational and is
// not evidence that a live Mapping exists.
type MappedRoute struct {
	mu     sync.RWMutex
	route  *RouteContext
	active bool
}

func (route *MappedRoute) Context() (RouteContext, error) {
	if route == nil {
		return RouteContext{}, ErrRouteBinding
	}
	route.mu.RLock()
	defer route.mu.RUnlock()
	if !route.active || route.route == nil {
		return RouteContext{}, ErrRouteBinding
	}
	return cloneRouteContext(*route.route), nil
}

func (route *MappedRoute) invalidate() {
	if route == nil {
		return
	}
	route.mu.Lock()
	route.active = false
	route.mu.Unlock()
}

// BuildAcquireRequest binds only Mapping-owned identity and policy fields.
// Session-owned proof fields are bound by the session route plan.
func (route *MappedRoute) BuildAcquireRequest(template authority.AcquireRequest) (authority.AcquireRequest, error) {
	context, err := route.Context()
	if err != nil {
		return authority.AcquireRequest{}, err
	}
	return buildAcquireRequest(context, template)
}

type SecureRouteOpener interface {
	OpenVerifiedRoute(context.Context, *MappedRoute) (io.ReadWriteCloser, error)
}

type Router struct {
	mappings mappingOwner
	flows    flowConsumer
	opener   SecureRouteOpener
}

func NewRouter(mappings mappingOwner, flows flowConsumer, opener SecureRouteOpener) (*Router, error) {
	if mappings == nil || flows == nil || opener == nil {
		return nil, ErrRouteBinding
	}
	return &Router{mappings: mappings, flows: flows, opener: opener}, nil
}

func (router *Router) OpenFlow(ctx context.Context, flow corestate.LocalFlowID) (*RoutedStream, error) {
	if ctx == nil || flow == 0 {
		return nil, ErrRouteBinding
	}
	mappingID, err := router.flows.Consume(flow)
	if err != nil {
		return nil, err
	}
	mapping, err := router.mappings.AcquireMapping(mappingID)
	if err != nil {
		return nil, err
	}
	routeContext, err := routeContext(mapping)
	if err != nil {
		_ = router.mappings.ReleaseMapping(mappingID)
		return nil, err
	}
	route := &MappedRoute{route: &routeContext, active: true}
	downstream, err := router.opener.OpenVerifiedRoute(ctx, route)
	if err != nil || downstream == nil {
		route.invalidate()
		_ = router.mappings.ReleaseMapping(mappingID)
		if err == nil {
			err = ErrRouteBinding
		}
		return nil, err
	}
	return &RoutedStream{ReadWriteCloser: downstream, release: func() error {
		route.invalidate()
		return router.mappings.ReleaseMapping(mappingID)
	}}, nil
}

func routeContext(mapping corestate.MappingSnapshot) (RouteContext, error) {
	intent := mapping.RouteIntent
	if mapping.ID == 0 || mapping.ServiceIdentity == "" || mapping.ServiceDigest == (corestate.ServiceDigest{}) ||
		corestate.ServiceDigest(sha256.Sum256([]byte(mapping.CanonicalName))) != mapping.ServiceDigest ||
		len(intent.Canonical) == 0 || sha256.Sum256(intent.Canonical) != intent.Digest || mapping.ExpiresAtUnix > intent.ExpiresAt {
		return RouteContext{}, ErrRouteBinding
	}
	return RouteContext{
		MappingID: mapping.ID, CanonicalName: mapping.CanonicalName, ServiceIdentity: mapping.ServiceIdentity, ServiceDigest: mapping.ServiceDigest, PolicyContext: mapping.PolicyContext,
		Intent: authority.RouteIntent{
			Canonical: append([]byte(nil), intent.Canonical...), Digest: authority.RouteIntentDigest(intent.Digest), ServiceIdentity: mapping.ServiceIdentity,
			SourceOperator: intent.SourceOperator, SourceEdge: intent.SourceEdge, TargetOperator: intent.TargetOperator,
			TargetEdges: append([]string(nil), intent.TargetEdges...), Transport: intent.Transport, Port: intent.Port,
			RecordSequence: intent.RecordSequence, PolicyHash: authority.PolicyDigest(intent.PolicyHash), RouteID: intent.RouteID,
			LeaseID: intent.LeaseID, ExpiresAt: intent.ExpiresAt,
		},
	}, nil
}

func buildAcquireRequest(route RouteContext, template authority.AcquireRequest) (authority.AcquireRequest, error) {
	if route.MappingID == 0 || route.ServiceIdentity == "" || route.ServiceDigest == (corestate.ServiceDigest{}) || !validRouteIntent(route.Intent) {
		return authority.AcquireRequest{}, ErrRouteBinding
	}
	request := template
	request.Intent = route.Intent
	request.Intent.Canonical = append([]byte(nil), route.Intent.Canonical...)
	request.Intent.TargetEdges = append([]string(nil), route.Intent.TargetEdges...)
	request.Key.IntentDigest = route.Intent.Digest
	request.Key.ServiceDigest = authority.ServiceDigest(route.ServiceDigest)
	request.Key.SourceOperator = route.Intent.SourceOperator
	request.Key.SourceEdge = route.Intent.SourceEdge
	request.Key.TargetOperator = route.Intent.TargetOperator
	request.Key.TargetEdgeSetDigest = authority.TargetEdgeSetDigest(route.Intent.TargetEdges)
	request.Key.Transport = route.Intent.Transport
	request.Key.Port = route.Intent.Port
	request.Key.PolicyHash = route.Intent.PolicyHash
	if request.Workload != nil {
		workload := *request.Workload
		request.Workload = &workload
	}
	return request, nil
}

type RoutedStream struct {
	io.ReadWriteCloser
	once    sync.Once
	release func() error
	err     error
}

func (stream *RoutedStream) CloseWrite() error {
	if writer, ok := stream.ReadWriteCloser.(interface{ CloseWrite() error }); ok {
		return writer.CloseWrite()
	}
	return ErrRouteBinding
}

func (stream *RoutedStream) Close() error {
	stream.once.Do(func() {
		stream.err = errors.Join(stream.ReadWriteCloser.Close(), stream.release())
	})
	return stream.err
}
