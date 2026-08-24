package resolution

import (
	"crypto/sha256"
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/authority"
)

func validIntent() authority.RouteIntent {
	canonical := []byte("canonical route intent")
	return authority.RouteIntent{
		Canonical: canonical, Digest: authority.RouteIntentDigest(sha256.Sum256(canonical)),
		ServiceIdentity: "service.api", SourceOperator: "source.operator", SourceEdge: "source.edge",
		TargetOperator: "target.operator", TargetEdges: []string{"target.edge"}, Transport: "tcp", Port: 443,
		RecordSequence: 1, PolicyHash: authority.PolicyDigest{1}, RouteID: [16]byte{1}, LeaseID: [16]byte{2}, ExpiresAt: 200,
	}
}

func TestNewResultDerivesDigestAndEarliestExpiry(t *testing.T) {
	got, err := NewResult(ResultInput{PresentationName: "API.Example.", ServiceIdentity: "service.api", Intent: validIntent(), RecordExpiresAt: 180, SafetyExpiresAt: 150}, 100)
	if err != nil {
		t.Fatal(err)
	}
	if got.CanonicalName != "api.example" || got.ServiceDigest != sha256.Sum256([]byte("api.example")) || got.ExpiresAtUnix != 150 {
		t.Fatalf("result = %+v", got)
	}
}

func TestNewResultRejectsIdentityDigestAndExpiryMismatch(t *testing.T) {
	tests := []struct {
		name  string
		input ResultInput
	}{
		{"identity", ResultInput{PresentationName: "api.example", ServiceIdentity: "other.service", Intent: validIntent(), RecordExpiresAt: 180}},
		{"intent digest", func() ResultInput {
			v := validIntent()
			v.Digest[0]++
			return ResultInput{PresentationName: "api.example", ServiceIdentity: "service.api", Intent: v, RecordExpiresAt: 180}
		}()},
		{"expired", ResultInput{PresentationName: "api.example", ServiceIdentity: "service.api", Intent: validIntent(), RecordExpiresAt: 100}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if _, err := NewResult(test.input, 100); err == nil {
				t.Fatal("invalid resolution result accepted")
			}
		})
	}
}

func TestNewResultOwnsMutableIntentInput(t *testing.T) {
	intent := validIntent()
	result, err := NewResult(ResultInput{PresentationName: "api.example", ServiceIdentity: "service.api", Intent: intent, RecordExpiresAt: 180}, 100)
	if err != nil {
		t.Fatal(err)
	}
	intent.Canonical[0] ^= 0xff
	intent.TargetEdges[0] = "changed.edge"
	if string(result.Intent.Canonical) != "canonical route intent" || result.Intent.TargetEdges[0] != "target.edge" {
		t.Fatal("result aliases caller-owned RouteIntent")
	}
}

func TestResultMappingSpecPreservesResolutionProvenance(t *testing.T) {
	result, err := NewResult(ResultInput{PresentationName: "api.example", ServiceIdentity: "service.api", Intent: validIntent(), RecordExpiresAt: 180}, 100)
	if err != nil {
		t.Fatal(err)
	}
	spec := result.MappingSpec("policy")
	if spec.CanonicalName != "api.example" || spec.ServiceDigest != result.ServiceDigest || spec.ServiceIdentity != "service.api" ||
		spec.ExpiresAtUnix != 180 || spec.RouteIntent.Digest != [32]byte(result.Intent.Digest) || spec.RouteIntent.Port != 443 {
		t.Fatalf("mapping spec = %+v", spec)
	}
}
