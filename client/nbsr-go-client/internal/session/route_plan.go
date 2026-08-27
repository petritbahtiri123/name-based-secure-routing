package session

import (
	"context"
	"crypto/ed25519"
	"crypto/sha256"

	"nbsr.local/client/nbsr-go-client/internal/authority"
	"nbsr.local/client/nbsr-go-client/internal/corestate"
	"nbsr.local/client/nbsr-go-client/internal/resolution"
)

// TSProofBinding is the public representation of the proof identity selected
// by the Transport Session owner. It contains no signer or private key.
type TSProofBinding struct {
	Generation corestate.TSGeneration
	KeyID      [32]byte
	Thumbprint authority.ProofKeyThumbprint
	PublicKey  [ed25519.PublicKeySize]byte
}

// DestinationRouteView is public input for an independent destination policy
// provider. It is not a client route capability or a trust source.
type DestinationRouteView struct {
	ServiceIdentity string
	ServiceDigest   corestate.ServiceDigest
	Intent          authority.RouteIntent
	ProofThumbprint authority.ProofKeyThumbprint
	ProofPublicKey  [ed25519.PublicKeySize]byte
}

// RoutePlan composes a borrowed Mapping capability with the exact session spec
// owned and validated by Manager. Callers cannot replace its proof before the
// same plan creates the Transport Session.
type RoutePlan struct {
	manager *Manager
	route   *resolution.MappedRoute
	spec    TransportSessionSpec
	proof   TSProofBinding
}

func (manager *Manager) PlanRoute(route *resolution.MappedRoute, spec TransportSessionSpec, publicKey []byte) (*RoutePlan, error) {
	if manager == nil || route == nil || len(publicKey) != ed25519.PublicKeySize {
		return nil, ErrProofBinding
	}
	if _, err := route.Context(); err != nil {
		return nil, resolution.ErrRouteBinding
	}
	_, proof, err := manager.validateSessionSpec(spec)
	if err != nil {
		return nil, err
	}
	if sha256.Sum256(publicKey) != proof.Key.Thumbprint {
		return nil, ErrProofBinding
	}
	var public [ed25519.PublicKeySize]byte
	copy(public[:], publicKey)
	return &RoutePlan{manager: manager, route: route, spec: spec, proof: TSProofBinding{
		Generation: spec.Generation, KeyID: proof.Key.ID,
		Thumbprint: authority.ProofKeyThumbprint(proof.Key.Thumbprint), PublicKey: public,
	}}, nil
}

func (plan *RoutePlan) ProofBinding() (TSProofBinding, error) {
	if plan == nil || plan.manager == nil || plan.route == nil {
		return TSProofBinding{}, ErrProofBinding
	}
	return plan.proof, nil
}

func (plan *RoutePlan) BuildAcquireRequest(template authority.AcquireRequest) (authority.AcquireRequest, error) {
	proof, err := plan.ProofBinding()
	if err != nil {
		return authority.AcquireRequest{}, err
	}
	if template.Key.TSGeneration != 0 && template.Key.TSGeneration != authority.TSGeneration(proof.Generation) {
		return authority.AcquireRequest{}, ErrProofBinding
	}
	if template.Key.ProofThumbprint != (authority.ProofKeyThumbprint{}) && template.Key.ProofThumbprint != proof.Thumbprint {
		return authority.AcquireRequest{}, ErrProofBinding
	}
	template.Key.TSGeneration = authority.TSGeneration(proof.Generation)
	template.Key.ProofThumbprint = proof.Thumbprint
	return plan.route.BuildAcquireRequest(template)
}

func (plan *RoutePlan) CreateTransportSession(ctx context.Context) (TransportSessionSnapshot, error) {
	if plan == nil || plan.manager == nil {
		return TransportSessionSnapshot{}, ErrProofBinding
	}
	if _, err := plan.route.Context(); err != nil {
		return TransportSessionSnapshot{}, err
	}
	return plan.manager.CreateTransportSession(ctx, plan.spec)
}

func (plan *RoutePlan) DestinationRouteView() (DestinationRouteView, error) {
	proof, err := plan.ProofBinding()
	if err != nil {
		return DestinationRouteView{}, err
	}
	route, err := plan.route.Context()
	if err != nil {
		return DestinationRouteView{}, err
	}
	return DestinationRouteView{ServiceIdentity: route.ServiceIdentity, ServiceDigest: route.ServiceDigest,
		Intent: route.Intent, ProofThumbprint: proof.Thumbprint, ProofPublicKey: proof.PublicKey}, nil
}
