package client

import (
	"context"
	"errors"
	"net"
	"net/netip"
	"sync"
	"time"

	"nbsr.local/client/nbsr-go-client/internal/adapter/proxy"
	"nbsr.local/client/nbsr-go-client/internal/corestate"
	"nbsr.local/client/nbsr-go-client/internal/resolution"
)

type RuntimeConfig struct {
	ListenAddress     string
	SharedSyntheticIP netip.Addr
	NowUnix           uint64
	MaxConnections    int
	MaxRequestBytes   int64
}

type Runtime struct {
	store     *corestate.Store
	flows     *resolution.FlowStore
	proxy     *proxy.Server
	router    *resolution.Router
	mappingID corestate.MappingID
	address   string
	cancel    context.CancelFunc
	serveDone chan struct{}
	closed    bool
	mu        sync.Mutex
	wg        sync.WaitGroup
	closeOnce sync.Once
	closeErr  error
}

type runtimeClock uint64

func (clock runtimeClock) NowUnix() uint64 { return uint64(clock) }

func NewRuntime(config RuntimeConfig, input resolution.ResultInput, opener resolution.SecureRouteOpener) (*Runtime, error) {
	if config.ListenAddress == "" || !config.SharedSyntheticIP.IsValid() || config.NowUnix == 0 || config.MaxConnections <= 0 || config.MaxRequestBytes <= 0 || opener == nil {
		return nil, errors.New("invalid demo runtime configuration")
	}
	store, err := corestate.NewStore(corestate.Limits{
		MaxGenerations: 1, MaxMappings: 4, MaxServices: 4, MaxStreams: config.MaxConnections,
		MaxMappingBytes: 64 << 10, MaxServiceBytes: 64 << 10, MaxStreamBytes: 64 << 10,
		MaxServiceIdentityBytes: 128, MaxPolicyContextBytes: 128, MaxCanonicalNameBytes: 253,
		MaxRouteIntentBytes: 4096, MaxTargetEdgeBytes: 1024,
	}, runtimeClock(config.NowUnix), nil)
	if err != nil {
		return nil, err
	}
	registry, err := resolution.NewRegistry(store, 4)
	if err != nil {
		return nil, err
	}
	service, err := resolution.NewService(registry, config.SharedSyntheticIP)
	if err != nil {
		return nil, err
	}
	result, err := resolution.NewResult(input, config.NowUnix)
	if err != nil {
		return nil, err
	}
	answer, err := service.Publish(result, corestate.PolicyContext("demo-policy-v1"))
	if err != nil {
		return nil, err
	}
	flows, err := resolution.NewFlowStore(resolution.FlowLimits{MaxEntries: config.MaxConnections, MaxBytes: uint64(config.MaxConnections) * 16})
	if err != nil {
		_ = store.RemoveMapping(answer.MappingID)
		return nil, err
	}
	correlator, err := proxy.NewCorrelator(registry, flows)
	if err != nil {
		_ = flows.Close()
		_ = store.RemoveMapping(answer.MappingID)
		return nil, err
	}
	listener, err := net.Listen("tcp", config.ListenAddress)
	if err != nil {
		_ = flows.Close()
		_ = store.RemoveMapping(answer.MappingID)
		return nil, err
	}
	server, err := proxy.NewServer(listener, correlator, proxy.ServerLimits{MaxConnections: config.MaxConnections, MaxRequestBytes: config.MaxRequestBytes, HandshakeTimeout: 5 * time.Second})
	if err != nil {
		_ = listener.Close()
		_ = flows.Close()
		_ = store.RemoveMapping(answer.MappingID)
		return nil, err
	}
	router, err := resolution.NewRouter(store, flows, opener)
	if err != nil {
		_ = server.Close()
		_ = flows.Close()
		_ = store.RemoveMapping(answer.MappingID)
		return nil, err
	}
	return &Runtime{store: store, flows: flows, proxy: server, router: router, mappingID: answer.MappingID, address: listener.Addr().String()}, nil
}

func (runtime *Runtime) Serve(ctx context.Context) error {
	serveCtx, cancel := context.WithCancel(ctx)
	runtime.mu.Lock()
	if runtime.closed || runtime.cancel != nil {
		runtime.mu.Unlock()
		cancel()
		return errors.New("demo runtime is closed or already serving")
	}
	serveDone := make(chan struct{})
	runtime.cancel = cancel
	runtime.serveDone = serveDone
	runtime.mu.Unlock()
	defer func() {
		cancel()
		runtime.mu.Lock()
		runtime.cancel = nil
		runtime.serveDone = nil
		close(serveDone)
		runtime.mu.Unlock()
	}()
	for {
		flow, err := runtime.proxy.Accept(serveCtx)
		if err != nil {
			if serveCtx.Err() != nil {
				return serveCtx.Err()
			}
			if errors.Is(err, proxy.ErrConnectionCapacity) {
				continue
			}
			return err
		}
		runtime.wg.Add(1)
		go func() {
			defer runtime.wg.Done()
			application := &onceReadWriteCloser{ReadWriteCloser: flow.Downstream}
			defer application.Close()
			secure, openErr := runtime.router.OpenFlow(serveCtx, flow.Context.LocalFlowID)
			if openErr != nil {
				return
			}
			defer secure.Close()
			_ = forwardBounded(serveCtx, application, secure)
		}()
	}
}

func (runtime *Runtime) ProxyAddress() string            { return runtime.address }
func (runtime *Runtime) FlowUsage() resolution.FlowUsage { return runtime.flows.Usage() }
func (runtime *Runtime) ProxyUsage() proxy.ServerUsage   { return runtime.proxy.Usage() }
func (runtime *Runtime) MappingReferences() uint64 {
	mapping, err := runtime.store.LookupMapping(runtime.mappingID)
	if err != nil {
		return 0
	}
	return mapping.ActiveReferences
}

func (runtime *Runtime) stopServing() <-chan struct{} {
	runtime.mu.Lock()
	cancel := runtime.cancel
	done := runtime.serveDone
	runtime.closed = true
	runtime.mu.Unlock()
	if cancel != nil {
		cancel()
	}
	return done
}

func (runtime *Runtime) cancelServing() bool {
	runtime.mu.Lock()
	cancel := runtime.cancel
	runtime.mu.Unlock()
	if cancel == nil {
		return false
	}
	cancel()
	return true
}

func (runtime *Runtime) serving() bool {
	runtime.mu.Lock()
	defer runtime.mu.Unlock()
	return runtime.cancel != nil
}

func (runtime *Runtime) Close() error {
	runtime.closeOnce.Do(func() {
		serveDone := runtime.stopServing()
		runtime.closeErr = errors.Join(runtime.proxy.Close())
		if serveDone != nil {
			<-serveDone
		}
		runtime.wg.Wait()
		runtime.closeErr = errors.Join(runtime.closeErr, runtime.flows.Close(), runtime.store.RemoveMapping(runtime.mappingID))
	})
	return runtime.closeErr
}
