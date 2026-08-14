package identity

import "fmt"

type ErrorCode uint8

const (
	CodeUnknownIdentity ErrorCode = iota + 1
	CodeInvalidKeyPurpose
	CodeInvalidIdentity
	CodeInvalidGeneration
	CodeExpiredIdentity
)

type IdentityError struct {
	Code     ErrorCode
	Resource string
}

func (e *IdentityError) Error() string {
	if e == nil {
		return "<nil>"
	}
	if e.Resource == "" {
		return fmt.Sprintf("identity error %d", e.Code)
	}
	return fmt.Sprintf("identity error %d: %s", e.Code, e.Resource)
}

func (e *IdentityError) Is(target error) bool {
	t, ok := target.(*IdentityError)
	return ok && e != nil && t != nil && e.Code == t.Code
}

var (
	ErrUnknownIdentity   = &IdentityError{Code: CodeUnknownIdentity}
	ErrInvalidKeyPurpose = &IdentityError{Code: CodeInvalidKeyPurpose}
	ErrInvalidIdentity   = &IdentityError{Code: CodeInvalidIdentity}
	ErrInvalidGeneration = &IdentityError{Code: CodeInvalidGeneration}
	ErrExpiredIdentity   = &IdentityError{Code: CodeExpiredIdentity}
)
