package authority

import (
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/retry"
)

// BASELINE ONLY — NOT ACCEPTANCE CAPACITY. These benchmarks measure local
// fixed-state operations; they make no provider calls, I/O, or wire parsing.
func BenchmarkBaselineOnlyValidityCheck(b *testing.B) {
	authority := testAuthority(testKey(1), testGrant(1), 200)
	b.ReportAllocs()
	b.ResetTimer()
	for range b.N {
		if !authority.valid() {
			b.Fatal("valid authority rejected")
		}
	}
}

func BenchmarkBaselineOnlyCacheLookup(b *testing.B) {
	m, reservation, snapshot := task11BenchmarkReservation(b)
	b.ReportAllocs()
	b.ResetTimer()
	for range b.N {
		if err := m.ValidateForNewWork(reservation, snapshot, 99); err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkBaselineOnlyGenerationCheck(b *testing.B) {
	m, _, snapshot := task11BenchmarkReservation(b)
	b.ReportAllocs()
	b.ResetTimer()
	for range b.N {
		if err := m.ValidateStillCurrent(snapshot); err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkBaselineOnlyFreshnessLookup(b *testing.B) {
	m := task11Manager(b)
	b.ReportAllocs()
	b.ResetTimer()
	for range b.N {
		if _, err := m.CaptureGeneration(); err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkBaselineOnlyRetryDecision(b *testing.B) {
	in := retry.Input{Class: retry.Retryable, Attempt: 1, MaxAttempts: 3, NowUnixMilli: 1, DeadlineUnixMilli: 1_001, BaseBackoffMillis: 100, MaxBackoffMillis: 1_000, JitterPermille: 100, JitterSample: 500}
	b.ReportAllocs()
	b.ResetTimer()
	for range b.N {
		decision, err := retry.Decide(in)
		if err != nil || !decision.Retry {
			b.Fatalf("Decide = %+v, %v", decision, err)
		}
	}
}

func task11BenchmarkReservation(b *testing.B) (*Manager, Reservation, GenerationSnapshot) {
	b.Helper()
	m := task11Manager(b)
	key := testKey(1)
	reservation, err := m.reserveVerified(testAuthority(key, testGrant(1), 200))
	if err != nil {
		b.Fatal(err)
	}
	return m, reservation, GenerationSnapshot{generation: key.AuthorityGeneration}
}
