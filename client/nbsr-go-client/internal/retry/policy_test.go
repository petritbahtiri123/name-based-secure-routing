package retry

import (
	"errors"
	"math"
	"testing"
)

func validInput() Input {
	return Input{
		Class:             Retryable,
		Attempt:           1,
		MaxAttempts:       3,
		NowUnixMilli:      100,
		DeadlineUnixMilli: 10_000,
		BaseBackoffMillis: 100,
		MaxBackoffMillis:  1_000,
		JitterSample:      500,
	}
}

func TestRetryDecisionTable(t *testing.T) {
	tests := []struct {
		name string
		edit func(*Input)
		want Decision
	}{
		{"retryable retries with base backoff", func(*Input) {}, Decision{Retry: true, DelayMillis: 100}},
		{"conditional retries when condition changed", func(in *Input) { in.Class = ConditionallyRetryable; in.ConditionChanged = true }, Decision{Retry: true, DelayMillis: 100}},
		{"terminal class stops", func(in *Input) { in.Class = Terminal }, Decision{TerminalReason: ReasonTerminalClass}},
		{"unchanged condition stops", func(in *Input) { in.Class = ConditionallyRetryable }, Decision{TerminalReason: ReasonConditionUnchanged}},
		{"exact max attempt stops", func(in *Input) { in.Attempt = in.MaxAttempts }, Decision{TerminalReason: ReasonAttemptsExhausted}},
		{"exhausted attempt stops", func(in *Input) { in.Attempt = in.MaxAttempts + 1 }, Decision{TerminalReason: ReasonAttemptsExhausted}},
		{"deadline exact stops", func(in *Input) { in.NowUnixMilli = in.DeadlineUnixMilli }, Decision{TerminalReason: ReasonDeadline}},
		{"deadline past stops", func(in *Input) { in.NowUnixMilli = in.DeadlineUnixMilli + 1 }, Decision{TerminalReason: ReasonDeadline}},
		{"circuit open stops", func(in *Input) { in.CircuitOpen = true }, Decision{TerminalReason: ReasonCircuitOpen}},
		{"retry after shorter than backoff", func(in *Input) { in.RetryAfterMillis = 99 }, Decision{Retry: true, DelayMillis: 100}},
		{"retry after larger than backoff", func(in *Input) { in.RetryAfterMillis = 500 }, Decision{Retry: true, DelayMillis: 500}},
		{"zero jitter preserves backoff", func(in *Input) { in.JitterPermille = 0; in.JitterSample = 0 }, Decision{Retry: true, DelayMillis: 100}},
		{"maximum positive jitter is bounded", func(in *Input) { in.JitterPermille = 1_000; in.JitterSample = 1_000 }, Decision{Retry: true, DelayMillis: 200}},
		{"maximum negative jitter is bounded", func(in *Input) { in.JitterPermille = 1_000; in.JitterSample = 0 }, Decision{Retry: true, DelayMillis: 0}},
		{"delay clamps strictly below deadline", func(in *Input) { in.DeadlineUnixMilli = in.NowUnixMilli + 100 }, Decision{Retry: true, DelayMillis: 99}},
		{"maximum delay clamps to configured maximum", func(in *Input) { in.BaseBackoffMillis = 900; in.MaxBackoffMillis = 1_000; in.RetryAfterMillis = 10_000 }, Decision{Retry: true, DelayMillis: 1_000}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			in := validInput()
			tt.edit(&in)
			got, err := Decide(in)
			if err != nil {
				t.Fatal(err)
			}
			if got != tt.want {
				t.Fatalf("Decide(%+v) = %+v, want %+v", in, got, tt.want)
			}
		})
	}
}

func TestApplicationPayloadIsNeverRetried(t *testing.T) {
	in := validInput()
	in.ApplicationPayloadWritten = true
	got, err := Decide(in)
	if err != nil || got.Retry || got.TerminalReason != ReasonPayloadWritten {
		t.Fatalf("%#v %v", got, err)
	}
}

func TestRetryDecisionPrecedence(t *testing.T) {
	tests := []struct {
		name string
		edit func(*Input)
		want Reason
	}{
		{"payload wins over every lower-priority stop", func(in *Input) {
			in.ApplicationPayloadWritten = true
			in.Class = Terminal
			in.CircuitOpen = true
			in.DeadlineUnixMilli = in.NowUnixMilli
		}, ReasonPayloadWritten},
		{"terminal class wins over circuit and lower-priority stops", func(in *Input) {
			in.Class = Terminal
			in.CircuitOpen = true
			in.DeadlineUnixMilli = in.NowUnixMilli
		}, ReasonTerminalClass},
		{"circuit wins over condition attempt and deadline", func(in *Input) {
			in.Class = ConditionallyRetryable
			in.CircuitOpen = true
			in.Attempt = in.MaxAttempts
			in.DeadlineUnixMilli = in.NowUnixMilli
		}, ReasonCircuitOpen},
		{"condition wins over attempt and deadline", func(in *Input) {
			in.Class = ConditionallyRetryable
			in.Attempt = in.MaxAttempts
			in.DeadlineUnixMilli = in.NowUnixMilli
		}, ReasonConditionUnchanged},
		{"attempt wins over deadline", func(in *Input) {
			in.Attempt = in.MaxAttempts
			in.DeadlineUnixMilli = in.NowUnixMilli
		}, ReasonAttemptsExhausted},
		{"deadline is last terminal stop", func(in *Input) {
			in.DeadlineUnixMilli = in.NowUnixMilli
		}, ReasonDeadline},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			in := validInput()
			tt.edit(&in)
			got, err := Decide(in)
			if err != nil {
				t.Fatal(err)
			}
			if got != (Decision{TerminalReason: tt.want}) {
				t.Fatalf("Decide(%+v) = %+v, want terminal reason %d", in, got, tt.want)
			}
		})
	}
}

func TestBackoffSaturationAndArithmeticBoundaries(t *testing.T) {
	tests := []struct {
		name string
		edit func(*Input)
		want uint64
	}{
		{"low base traverses sixty-three shifts", func(in *Input) {
			in.Attempt = 64
			in.MaxAttempts = math.MaxUint32
			in.NowUnixMilli = 0
			in.DeadlineUnixMilli = math.MaxUint64
			in.BaseBackoffMillis = 1
			in.MaxBackoffMillis = math.MaxUint64
		}, uint64(1) << 63},
		{"next shift saturates uint64 without wrapping", func(in *Input) {
			in.Attempt = 65
			in.MaxAttempts = math.MaxUint32
			in.NowUnixMilli = 0
			in.DeadlineUnixMilli = math.MaxUint64
			in.BaseBackoffMillis = 1
			in.MaxBackoffMillis = math.MaxUint64
		}, math.MaxUint64 - 1},
		{"configured maximum clamps exponential growth", func(in *Input) {
			in.Attempt = 20
			in.MaxAttempts = math.MaxUint32
			in.BaseBackoffMillis = 1
			in.MaxBackoffMillis = 1_000
		}, 1_000},
		{"jittered backoff wins over shorter retry after", func(in *Input) {
			in.Attempt = 2
			in.JitterPermille = 1_000
			in.JitterSample = 1_000
			in.RetryAfterMillis = 300
		}, 400},
		{"long retry after wins after jitter and is bounded", func(in *Input) {
			in.Attempt = 2
			in.JitterPermille = 1_000
			in.JitterSample = 1_000
			in.RetryAfterMillis = 10_000
		}, 1_000},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			in := validInput()
			tt.edit(&in)
			got, err := Decide(in)
			if err != nil {
				t.Fatal(err)
			}
			if !got.Retry || got.DelayMillis != tt.want || got.TerminalReason != ReasonNone {
				t.Fatalf("Decide(%+v) = %+v, want retry delay %d", in, got, tt.want)
			}
		})
	}
}

func TestInvalidRetryInputsAreTyped(t *testing.T) {
	tests := []struct {
		name string
		edit func(*Input)
	}{
		{"unknown class", func(in *Input) { in.Class = 0 }},
		{"zero attempt", func(in *Input) { in.Attempt = 0 }},
		{"zero max attempts", func(in *Input) { in.MaxAttempts = 0 }},
		{"zero base backoff", func(in *Input) { in.BaseBackoffMillis = 0 }},
		{"zero max backoff", func(in *Input) { in.MaxBackoffMillis = 0 }},
		{"base exceeds maximum", func(in *Input) { in.BaseBackoffMillis = 101; in.MaxBackoffMillis = 100 }},
		{"jitter exceeds permille", func(in *Input) { in.JitterPermille = 1_001 }},
		{"sample exceeds permille", func(in *Input) { in.JitterSample = 1_001 }},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			in := validInput()
			tt.edit(&in)
			if _, err := Decide(in); !errors.Is(err, ErrInvalidInput) {
				t.Fatalf("Decide(%+v) error = %v, want ErrInvalidInput", in, err)
			}
		})
	}
}

func TestTenThousandDecisionsArePureAndFinite(t *testing.T) {
	in := validInput()
	for i := 0; i < 10_000; i++ {
		in.Attempt = uint32(i%3 + 1)
		got, err := Decide(in)
		if err != nil {
			t.Fatal(err)
		}
		if got.Retry != (in.Attempt < in.MaxAttempts) {
			t.Fatalf("attempt %d: %+v", in.Attempt, got)
		}
	}
}
