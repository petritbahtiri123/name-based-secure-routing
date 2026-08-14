package authority

import (
	"context"
	cryptorand "crypto/rand"
	"io"
)

type cryptoRequestIDSource struct{ reader io.Reader }

func NewCryptoRequestIDSource(reader io.Reader) (RequestIDSource, error) {
	if reader == nil {
		reader = cryptorand.Reader
	}
	return cryptoRequestIDSource{reader: reader}, nil
}

func (source cryptoRequestIDSource) NewRequestID() (RequestID, error) {
	var id RequestID
	if _, err := io.ReadFull(source.reader, id[:]); err != nil {
		return RequestID{}, &AuthorityError{Code: CodeInvalidAuthority, Resource: "request ID"}
	}
	if id == (RequestID{}) {
		return RequestID{}, &AuthorityError{Code: CodeInvalidAuthority, Resource: "request ID"}
	}
	return id, nil
}

// invokeProvider is deliberately called only after a pending operation has
// been published and the manager mutex released. Providers are reentrant
// callbacks and must never observe the manager lock.
func (m *Manager) invokeProvider(ctx context.Context, operation pendingOperation, acquire AcquireRequest, renew RenewRequest) (ProviderGrant, error) {
	if operation == pendingRenew {
		return m.provider.Renew(ctx, renew)
	}
	return m.provider.Acquire(ctx, acquire)
}
