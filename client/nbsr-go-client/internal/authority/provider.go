package authority

import (
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
