package adapter

import (
	"context"
	"io"

	"nbsr.local/client/nbsr-go-client/internal/resolution"
)

type LocalPeer struct {
	ProcessID uint64
}

type CapturedFlow struct {
	Context    resolution.FlowContext
	Transport  string
	Port       uint16
	Peer       LocalPeer
	Downstream io.ReadWriteCloser
}

type FlowSource interface {
	Accept(context.Context) (CapturedFlow, error)
	Close() error
}
