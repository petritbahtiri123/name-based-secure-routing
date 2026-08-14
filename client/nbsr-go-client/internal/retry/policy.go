package retry

import "math"

// Class describes whether an operation's pre-payload failure can be retried.
type Class uint8

const (
	Retryable Class = iota + 1
	ConditionallyRetryable
	Terminal
)

type Input struct {
	Class                     Class
	Attempt                   uint32
	MaxAttempts               uint32
	NowUnixMilli              uint64
	DeadlineUnixMilli         uint64
	BaseBackoffMillis         uint64
	MaxBackoffMillis          uint64
	JitterPermille            uint16
	JitterSample              uint16
	RetryAfterMillis          uint64
	ConditionChanged          bool
	CircuitOpen               bool
	ApplicationPayloadWritten bool
}

type Decision struct {
	Retry          bool
	DelayMillis    uint64
	TerminalReason Reason
}

type Reason uint8

const (
	ReasonNone Reason = iota
	ReasonTerminalClass
	ReasonConditionUnchanged
	ReasonAttemptsExhausted
	ReasonDeadline
	ReasonCircuitOpen
	ReasonPayloadWritten
)

// Decide returns one bounded retry decision. It is pure: callers perform any
// delay themselves, after applying their own cancellation and lifecycle rules.
func Decide(in Input) (Decision, error) {
	if err := validate(in); err != nil {
		return Decision{}, err
	}
	if in.ApplicationPayloadWritten {
		return terminal(ReasonPayloadWritten), nil
	}
	if in.Class == Terminal {
		return terminal(ReasonTerminalClass), nil
	}
	if in.CircuitOpen {
		return terminal(ReasonCircuitOpen), nil
	}
	if in.Class == ConditionallyRetryable && !in.ConditionChanged {
		return terminal(ReasonConditionUnchanged), nil
	}
	if in.Attempt >= in.MaxAttempts {
		return terminal(ReasonAttemptsExhausted), nil
	}
	if in.NowUnixMilli >= in.DeadlineUnixMilli {
		return terminal(ReasonDeadline), nil
	}

	delay := jitteredBackoff(in.BaseBackoffMillis, in.MaxBackoffMillis, in.Attempt, in.JitterPermille, in.JitterSample)
	retryAfter := min(in.RetryAfterMillis, in.MaxBackoffMillis)
	delay = max(delay, retryAfter)
	remaining := in.DeadlineUnixMilli - in.NowUnixMilli
	delay = min(delay, remaining-1)
	return Decision{Retry: true, DelayMillis: delay}, nil
}

func validate(in Input) error {
	if in.Class != Retryable && in.Class != ConditionallyRetryable && in.Class != Terminal {
		return ErrInvalidInput
	}
	if in.Attempt == 0 || in.MaxAttempts == 0 || in.BaseBackoffMillis == 0 || in.MaxBackoffMillis == 0 || in.BaseBackoffMillis > in.MaxBackoffMillis || in.JitterPermille > 1_000 || in.JitterSample > 1_000 {
		return ErrInvalidInput
	}
	return nil
}

func terminal(reason Reason) Decision {
	return Decision{TerminalReason: reason}
}

func jitteredBackoff(base, limit uint64, attempt uint32, permille, sample uint16) uint64 {
	backoff := exponentialBackoff(base, limit, attempt-1)
	center := int64(sample)*2 - 1_000
	factor := uint64(center)
	negative := center < 0
	if negative {
		factor = uint64(-center)
	}
	adjustment := scaledProduct(backoff, factor*uint64(permille), 1_000_000)
	if negative {
		if adjustment >= backoff {
			return 0
		}
		return backoff - adjustment
	}
	return min(saturatingAdd(backoff, adjustment), limit)
}

func exponentialBackoff(base, limit uint64, exponent uint32) uint64 {
	value := base
	for exponent > 0 && value < limit {
		if value > limit-value {
			return limit
		}
		value *= 2
		exponent--
	}
	return min(value, limit)
}

func scaledProduct(value, factor, divisor uint64) uint64 {
	quotient, remainder := value/divisor, value%divisor
	return quotient*factor + (remainder*factor)/divisor
}

func saturatingAdd(a, b uint64) uint64 {
	if math.MaxUint64-a < b {
		return math.MaxUint64
	}
	return a + b
}

func min(a, b uint64) uint64 {
	if a < b {
		return a
	}
	return b
}

func max(a, b uint64) uint64 {
	if a > b {
		return a
	}
	return b
}
