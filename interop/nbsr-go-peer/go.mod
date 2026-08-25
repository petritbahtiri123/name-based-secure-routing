module nbsr.local/interop/nbsr-go-peer

go 1.26.5

require github.com/quic-go/quic-go v0.61.0

require nbsr.local/client/nbsr-go-client v0.0.0

replace nbsr.local/client/nbsr-go-client => ../../client/nbsr-go-client

require (
	golang.org/x/crypto v0.54.0 // indirect
	golang.org/x/net v0.56.0 // indirect
	golang.org/x/sys v0.47.0 // indirect
	golang.org/x/text v0.40.0 // indirect
)
