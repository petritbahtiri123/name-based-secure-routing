package corestate

import "fmt"

type ErrorCode uint8

const (
	CodeInvalidHandle ErrorCode = iota + 1
	CodeUnknownMapping
	CodeExpiredMapping
	CodeMappingConflict
	CodeUnknownService
	CodeDuplicateService
	CodeDuplicateStream
	CodeCapacityExceeded
	CodeByteCapacityExceeded
	CodeGenerationClosed
	CodeServiceClosed
	CodeHandleExhausted
	CodeMappingIDExhausted
	CodeInvalidTransition
	CodeInvalidLimits
	CodeAccountingOverflow
)

type StateError struct {
	Code     ErrorCode
	Resource string
}

func (e *StateError) Error() string {
	if e == nil {
		return "<nil>"
	}
	if e.Resource == "" {
		return fmt.Sprintf("core state error %d", e.Code)
	}
	return fmt.Sprintf("core state error %d: %s", e.Code, e.Resource)
}

func (e *StateError) Is(target error) bool {
	t, ok := target.(*StateError)
	return ok && e != nil && e.Code == t.Code
}

var (
	ErrInvalidHandle        = &StateError{Code: CodeInvalidHandle}
	ErrUnknownMapping       = &StateError{Code: CodeUnknownMapping}
	ErrExpiredMapping       = &StateError{Code: CodeExpiredMapping}
	ErrMappingConflict      = &StateError{Code: CodeMappingConflict}
	ErrUnknownService       = &StateError{Code: CodeUnknownService}
	ErrDuplicateService     = &StateError{Code: CodeDuplicateService}
	ErrDuplicateStream      = &StateError{Code: CodeDuplicateStream}
	ErrCapacityExceeded     = &StateError{Code: CodeCapacityExceeded}
	ErrByteCapacityExceeded = &StateError{Code: CodeByteCapacityExceeded}
	ErrGenerationClosed     = &StateError{Code: CodeGenerationClosed}
	ErrServiceClosed        = &StateError{Code: CodeServiceClosed}
	ErrHandleExhausted      = &StateError{Code: CodeHandleExhausted}
	ErrMappingIDExhausted   = &StateError{Code: CodeMappingIDExhausted}
	ErrInvalidTransition    = &StateError{Code: CodeInvalidTransition}
	ErrInvalidLimits        = &StateError{Code: CodeInvalidLimits}
	ErrAccountingOverflow   = &StateError{Code: CodeAccountingOverflow}
)
