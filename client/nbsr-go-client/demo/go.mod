module nbsr.local/client/nbsr-go-client/demo

go 1.26.5

require (
	nbsr.local/client/nbsr-go-client v0.0.0
	nbsr.local/interop/nbsr-go-peer v0.0.0
)

require (
	github.com/quic-go/quic-go v0.61.0 // indirect
	golang.org/x/crypto v0.54.0 // indirect
	golang.org/x/net v0.56.0 // indirect
	golang.org/x/sys v0.47.0 // indirect
	golang.org/x/text v0.40.0 // indirect
)

replace nbsr.local/client/nbsr-go-client => ..

replace nbsr.local/interop/nbsr-go-peer => ../../../interop/nbsr-go-peer
