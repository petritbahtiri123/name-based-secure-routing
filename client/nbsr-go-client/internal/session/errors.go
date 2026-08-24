package session

import "fmt"

type ErrorCode uint8

const (
	CodeInvalidLimits ErrorCode = iota + 1
	CodeInvalidSession
	CodeAuthorityStale
	CodeProofBinding
	CodeGenerationCapacity
	CodeGenerationClosed
	CodeGenerationNotCurrent
	CodeSessionCapacity
	CodeChannelCapacity
	CodePendingCapacity
	CodeServiceBinding
	CodeChannelBinding
	CodeDuplicateChannel
	CodeChannelClosed
	CodeTransport
	CodeCreditClosed
	CodeCreditBinding
	CodeCreditConsumed
	CodeCreditExhausted
	CodeCreditMalformed
	CodeCreditStaleEpoch
	CodeEpochCapacity
	CodeRefillPending
	CodeRefillNotDue
)

type Error struct {
	Code     ErrorCode
	Resource string
}

func (e *Error) Error() string {
	if e == nil {
		return "<nil>"
	}
	if e.Resource == "" {
		return fmt.Sprintf("session error %d", e.Code)
	}
	return fmt.Sprintf("session error %d: %s", e.Code, e.Resource)
}
func (e *Error) Is(target error) bool {
	t, ok := target.(*Error)
	return ok && e != nil && t != nil && e.Code == t.Code
}

var (
	ErrInvalidLimits        = &Error{Code: CodeInvalidLimits}
	ErrInvalidSession       = &Error{Code: CodeInvalidSession}
	ErrAuthorityStale       = &Error{Code: CodeAuthorityStale}
	ErrProofBinding         = &Error{Code: CodeProofBinding}
	ErrGenerationCapacity   = &Error{Code: CodeGenerationCapacity}
	ErrGenerationClosed     = &Error{Code: CodeGenerationClosed}
	ErrGenerationNotCurrent = &Error{Code: CodeGenerationNotCurrent}
	ErrSessionCapacity      = &Error{Code: CodeSessionCapacity}
	ErrChannelCapacity      = &Error{Code: CodeChannelCapacity}
	ErrPendingCapacity      = &Error{Code: CodePendingCapacity}
	ErrServiceBinding       = &Error{Code: CodeServiceBinding}
	ErrChannelBinding       = &Error{Code: CodeChannelBinding}
	ErrDuplicateChannel     = &Error{Code: CodeDuplicateChannel}
	ErrChannelClosed        = &Error{Code: CodeChannelClosed}
	ErrTransport            = &Error{Code: CodeTransport}
	ErrCreditClosed         = &Error{Code: CodeCreditClosed}
	ErrCreditBinding        = &Error{Code: CodeCreditBinding}
	ErrCreditConsumed       = &Error{Code: CodeCreditConsumed}
	ErrCreditExhausted      = &Error{Code: CodeCreditExhausted}
	ErrCreditMalformed      = &Error{Code: CodeCreditMalformed}
	ErrCreditStaleEpoch     = &Error{Code: CodeCreditStaleEpoch}
	ErrEpochCapacity        = &Error{Code: CodeEpochCapacity}
	ErrRefillPending        = &Error{Code: CodeRefillPending}
	ErrRefillNotDue         = &Error{Code: CodeRefillNotDue}
)
