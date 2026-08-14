package retry

import "fmt"

type ErrorCode uint8

const (
	CodeInvalidInput ErrorCode = iota + 1
)

type RetryError struct {
	Code     ErrorCode
	Resource string
}

func (e *RetryError) Error() string {
	if e == nil {
		return "<nil>"
	}
	if e.Resource == "" {
		return fmt.Sprintf("retry error %d", e.Code)
	}
	return fmt.Sprintf("retry error %d: %s", e.Code, e.Resource)
}

func (e *RetryError) Is(target error) bool {
	t, ok := target.(*RetryError)
	return ok && e != nil && t != nil && e.Code == t.Code
}

var ErrInvalidInput = &RetryError{Code: CodeInvalidInput}
