package authority

import "fmt"

type ErrorCode uint8

const (
	CodeUnknownIdentity ErrorCode = iota + 1
	CodeInvalidKeyPurpose
	CodeInvalidAuthority
	CodeSignatureFailure
	CodeBindingMismatch
	CodeExpired
	CodeRevoked
	CodeStaleFreshness
	CodeStaleGeneration
	CodeGenerationRollback
	CodeCacheCapacity
	CodePendingCapacity
	CodeWaiterCapacity
	CodeRequestConflict
	CodeRequestAmbiguous
	CodeProviderUnavailable
	CodePolicyDenied
	CodeTerminalEnrollment
	CodeInvalidLimits
	CodeInvalidTransition
	CodeClosed
	CodeNotReady
	CodeAccountingOverflow
	CodeStoragePathRejected
	CodeStorageBusy
	CodeStorageUnsupported
	CodeBootstrapUnauthorized
)

type AuthorityError struct {
	Code     ErrorCode
	Resource string
}

func (e *AuthorityError) Error() string {
	if e == nil {
		return "<nil>"
	}
	if e.Resource == "" {
		return fmt.Sprintf("authority error %d", e.Code)
	}
	return fmt.Sprintf("authority error %d: %s", e.Code, e.Resource)
}

func (e *AuthorityError) Is(target error) bool {
	t, ok := target.(*AuthorityError)
	return ok && e != nil && t != nil && e.Code == t.Code
}

var (
	ErrUnknownIdentity       = &AuthorityError{Code: CodeUnknownIdentity}
	ErrInvalidKeyPurpose     = &AuthorityError{Code: CodeInvalidKeyPurpose}
	ErrInvalidAuthority      = &AuthorityError{Code: CodeInvalidAuthority}
	ErrSignatureFailure      = &AuthorityError{Code: CodeSignatureFailure}
	ErrBindingMismatch       = &AuthorityError{Code: CodeBindingMismatch}
	ErrExpired               = &AuthorityError{Code: CodeExpired}
	ErrRevoked               = &AuthorityError{Code: CodeRevoked}
	ErrStaleFreshness        = &AuthorityError{Code: CodeStaleFreshness}
	ErrStaleGeneration       = &AuthorityError{Code: CodeStaleGeneration}
	ErrGenerationRollback    = &AuthorityError{Code: CodeGenerationRollback}
	ErrCacheCapacity         = &AuthorityError{Code: CodeCacheCapacity}
	ErrPendingCapacity       = &AuthorityError{Code: CodePendingCapacity}
	ErrWaiterCapacity        = &AuthorityError{Code: CodeWaiterCapacity}
	ErrRequestConflict       = &AuthorityError{Code: CodeRequestConflict}
	ErrRequestAmbiguous      = &AuthorityError{Code: CodeRequestAmbiguous}
	ErrProviderUnavailable   = &AuthorityError{Code: CodeProviderUnavailable}
	ErrPolicyDenied          = &AuthorityError{Code: CodePolicyDenied}
	ErrTerminalEnrollment    = &AuthorityError{Code: CodeTerminalEnrollment}
	ErrInvalidLimits         = &AuthorityError{Code: CodeInvalidLimits}
	ErrInvalidTransition     = &AuthorityError{Code: CodeInvalidTransition}
	ErrClosed                = &AuthorityError{Code: CodeClosed}
	ErrNotReady              = &AuthorityError{Code: CodeNotReady}
	ErrAccountingOverflow    = &AuthorityError{Code: CodeAccountingOverflow}
	ErrStoragePathRejected   = &AuthorityError{Code: CodeStoragePathRejected}
	ErrStorageBusy           = &AuthorityError{Code: CodeStorageBusy}
	ErrStorageUnsupported    = &AuthorityError{Code: CodeStorageUnsupported}
	ErrBootstrapUnauthorized = &AuthorityError{Code: CodeBootstrapUnauthorized}
)
