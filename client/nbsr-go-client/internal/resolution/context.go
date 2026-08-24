package resolution

import (
	"crypto/sha256"
	"strings"

	"nbsr.local/client/nbsr-go-client/internal/authority"
	"nbsr.local/client/nbsr-go-client/internal/corestate"
)

type ResultInput struct {
	PresentationName string
	ServiceIdentity  string
	Intent           authority.RouteIntent
	RecordExpiresAt  uint64
	SafetyExpiresAt  uint64
}

type Result struct {
	CanonicalName   CanonicalName
	ServiceDigest   corestate.ServiceDigest
	ServiceIdentity string
	Intent          authority.RouteIntent
	ExpiresAtUnix   uint64
}

func NewResult(input ResultInput, now uint64) (Result, error) {
	name, err := CanonicalizePresentationName(input.PresentationName)
	if err != nil || now == 0 || input.ServiceIdentity == "" || input.ServiceIdentity != input.Intent.ServiceIdentity || !validRouteIntent(input.Intent) {
		return Result{}, ErrInvalidResolution
	}
	expires := input.RecordExpiresAt
	if expires == 0 || input.Intent.ExpiresAt < expires {
		expires = input.Intent.ExpiresAt
	}
	if input.SafetyExpiresAt != 0 && input.SafetyExpiresAt < expires {
		expires = input.SafetyExpiresAt
	}
	if expires <= now {
		return Result{}, ErrInvalidResolution
	}
	intent := input.Intent
	intent.Canonical = append([]byte(nil), input.Intent.Canonical...)
	intent.TargetEdges = append([]string(nil), input.Intent.TargetEdges...)
	return Result{
		CanonicalName: name, ServiceDigest: DigestCanonicalName(name),
		ServiceIdentity: strings.Clone(input.ServiceIdentity), Intent: intent, ExpiresAtUnix: expires,
	}, nil
}

func validRouteIntent(intent authority.RouteIntent) bool {
	if len(intent.Canonical) == 0 || authority.RouteIntentDigest(sha256.Sum256(intent.Canonical)) != intent.Digest ||
		intent.ServiceIdentity == "" || intent.SourceOperator == "" || intent.SourceEdge == "" || intent.TargetOperator == "" ||
		len(intent.TargetEdges) == 0 || intent.Transport == "" || intent.Port == 0 || intent.RecordSequence == 0 ||
		intent.PolicyHash == (authority.PolicyDigest{}) || intent.RouteID == ([16]byte{}) || intent.LeaseID == ([16]byte{}) || intent.ExpiresAt == 0 {
		return false
	}
	for _, edge := range intent.TargetEdges {
		if edge == "" {
			return false
		}
	}
	return true
}

func (result Result) MappingSpec(policy corestate.PolicyContext) corestate.MappingSpec {
	intent := result.Intent
	return corestate.MappingSpec{
		CanonicalName: result.CanonicalName.String(), ServiceIdentity: strings.Clone(result.ServiceIdentity), ServiceDigest: result.ServiceDigest,
		RouteIntent: corestate.RouteIntentSnapshot{
			Canonical: append([]byte(nil), intent.Canonical...), Digest: [32]byte(intent.Digest), SourceOperator: strings.Clone(intent.SourceOperator),
			SourceEdge: strings.Clone(intent.SourceEdge), TargetOperator: strings.Clone(intent.TargetOperator), TargetEdges: append([]string(nil), intent.TargetEdges...),
			Transport: strings.Clone(intent.Transport), Port: intent.Port, RecordSequence: intent.RecordSequence, PolicyHash: [32]byte(intent.PolicyHash),
			RouteID: intent.RouteID, LeaseID: intent.LeaseID, ExpiresAt: intent.ExpiresAt,
		},
		ExpiresAtUnix: result.ExpiresAtUnix, PolicyContext: policy,
	}
}

func (name CanonicalName) String() string { return string(name) }
