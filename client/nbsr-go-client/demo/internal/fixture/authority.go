package fixture

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"errors"
	"fmt"
	"io"
	"log"
	"math/big"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"sync"
	"time"

	"nbsr.local/client/nbsr-go-client/internal/authority"
	"nbsr.local/client/nbsr-go-client/internal/identity"
	"nbsr.local/client/nbsr-go-client/internal/resolution"
	"nbsr.local/client/nbsr-go-client/internal/session"
)

const Classification = "DEMO FIXTURE — NOT PRODUCTION AUTHORITY"
const fixedNow uint64 = 1_893_456_000

type Mutation uint8

const (
	MutateServiceDigest Mutation = iota + 1
	MutateServiceIdentity
	MutateSigner
	MutateKID
	MutateKIDPurpose
	MutateExpired
	MutateNotYetValid
	MutateStaleGeneration
	MutateMalformedResponse
)

type Option func(*options)
type options struct {
	mutation     Mutation
	block        bool
	routeRequest *authority.AcquireRequest
	runtimeView  *session.DestinationRouteView
}

func WithMutation(value Mutation) Option { return func(o *options) { o.mutation = value } }
func WithDecisionBlock() Option          { return func(o *options) { o.block = true } }
func WithRouteInputs(request authority.AcquireRequest, view session.DestinationRouteView) Option {
	return func(o *options) { o.routeRequest = &request; o.runtimeView = &view }
}

type Authority struct {
	request    authority.AcquireRequest
	grant      []byte
	generation authority.AuthorityGeneration
	block      bool
	mutation   Mutation
	release    <-chan struct{}
}

func (a *Authority) CurrentAuthorityGeneration(context.Context, string, string) (authority.AuthorityGeneration, error) {
	return a.generation, nil
}
func (a *Authority) DecideAuthority(ctx context.Context, request authority.VerifiedACPRequest) (authority.ACPDecision, error) {
	if err := ctx.Err(); err != nil {
		return authority.ACPDecision{}, err
	}
	if a.block && request.Operation() != authority.ACPOperationFreshness {
		select {
		case <-ctx.Done():
			return authority.ACPDecision{}, ctx.Err()
		case <-a.release:
			return authority.ACPDecision{}, context.Canceled
		}
	}
	if a.mutation == MutateStaleGeneration && request.Operation() != authority.ACPOperationFreshness {
		return authority.ACPDecision{Status: authority.ACPResultStatusStaleGeneration, AuthorityGeneration: a.generation}, nil
	}
	if request.Operation() == authority.ACPOperationFreshness {
		return authority.ACPDecision{Status: authority.ACPResultStatusSuccess, AuthorityGeneration: a.generation, Artifact: []byte("demo-freshness-v1")}, nil
	}
	got, ok := request.Acquire()
	if !ok || got.Key != a.request.Key || !sameIntent(got.Intent, a.request.Intent) {
		return authority.ACPDecision{Status: authority.ACPResultStatusPolicyDenied, AuthorityGeneration: a.generation}, nil
	}
	return authority.ACPDecision{Status: authority.ACPResultStatusSuccess, AuthorityGeneration: a.generation, Artifact: append([]byte(nil), a.grant...)}, nil
}

type Server struct {
	authority    *Authority
	endpoint     string
	clientTLS    *tls.Config
	deviceSigner identity.Signer
	issuers      *authority.StaticIssuerResolver
	checkpoint   authority.CheckpointClaims
	runtime      *authority.SourceOperatorRuntime
	http         *http.Server
	listener     net.Listener
	store        *authority.FileIdempotencyStore
	runtimeView  *session.DestinationRouteView
	routeIssuer  authority.IssuerRecord
	mu           sync.Mutex
	lastTLS      tls.ConnectionState
	closeOnce    sync.Once
	release      chan struct{}
}

func Start(runtimeDir string, opts ...Option) (*Server, error) {
	return StartAt(runtimeDir, "127.0.0.1:0", opts...)
}

func StartAt(runtimeDir, listenAddress string, opts ...Option) (*Server, error) {
	var cfg options
	for _, apply := range opts {
		apply(&cfg)
	}
	host, _, splitErr := net.SplitHostPort(listenAddress)
	address := net.ParseIP(host)
	if splitErr != nil || address == nil || !address.IsLoopback() {
		return nil, errors.New("demo ACP listener must be loopback")
	}
	if err := os.MkdirAll(runtimeDir, 0o700); err != nil {
		return nil, err
	}
	request, deviceSigner, deviceRecord, err := makeRequest()
	if err != nil {
		return nil, err
	}
	if cfg.routeRequest != nil {
		input := *cfg.routeRequest
		request.Intent = input.Intent
		request.Key.IntentDigest = input.Key.IntentDigest
		request.Key.ServiceDigest = input.Key.ServiceDigest
		request.Key.SourceOperator = input.Key.SourceOperator
		request.Key.SourceEdge = input.Key.SourceEdge
		request.Key.TargetOperator = input.Key.TargetOperator
		request.Key.TargetEdgeSetDigest = input.Key.TargetEdgeSetDigest
		request.Key.Transport = input.Key.Transport
		request.Key.Port = input.Key.Port
		request.Key.TSGeneration = input.Key.TSGeneration
		request.Key.ProofThumbprint = input.Key.ProofThumbprint
		request.Key.PolicyHash = input.Key.PolicyHash
	}
	routePublic, routePrivate, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		return nil, err
	}
	routeKID := []byte("nbsr-demo-route-grant-v1")
	grantInput := authority.DemoRouteGrantInput{Key: request.Key, Intent: request.Intent, NotBefore: fixedNow - 1, Nonce: [16]byte{9}, KID: routeKID}
	issuerPurpose := uint16(1)
	issuerPublic := routePublic
	switch cfg.mutation {
	case MutateServiceDigest:
		grantInput.Key.ServiceDigest[0] ^= 1
	case MutateServiceIdentity:
		grantInput.Intent.ServiceIdentity = "wrong.demo.service"
	case MutateSigner:
		_, other, e := ed25519.GenerateKey(rand.Reader)
		if e != nil {
			return nil, e
		}
		routePrivate = other
	case MutateKID:
		grantInput.KID = []byte("unknown-demo-route-grant-v1")
	case MutateKIDPurpose:
		issuerPurpose = 2
	case MutateExpired:
		grantInput.NotBefore, grantInput.Intent.ExpiresAt = fixedNow-601, fixedNow-1
	case MutateNotYetValid:
		grantInput.NotBefore, grantInput.Intent.ExpiresAt = fixedNow+1, fixedNow+301
	}
	grant, err := authority.SignDemoRouteGrant(context.Background(), grantInput, routePrivate)
	if err != nil {
		return nil, err
	}
	if cfg.mutation == MutateMalformedResponse {
		grant = []byte{0xd2, 0x01}
	}
	var routeKey [32]byte
	copy(routeKey[:], issuerPublic)

	acpPublic, acpPrivate, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		return nil, err
	}
	acpSigner := &operatorSigner{kid: []byte("nbsr-demo-acp-result-v1"), purpose: 15, private: acpPrivate}
	var acpKey [32]byte
	copy(acpKey[:], acpPublic)
	routeIssuer := authority.IssuerRecord{KID: append([]byte(nil), routeKID...), PublicKey: routeKey, Purpose: issuerPurpose, Profile: request.Key.Profile, SourceOperator: request.Key.SourceOperator, Generation: uint64(grantInput.Key.AuthorityGeneration), NotBefore: fixedNow - 10, ExpiresAt: fixedNow + 600}
	acpIssuer := authority.IssuerRecord{KID: append([]byte(nil), acpSigner.kid...), PublicKey: acpKey, Purpose: 15, Profile: request.Key.Profile, SourceOperator: request.Key.SourceOperator, Generation: uint64(request.Key.AuthorityGeneration), NotBefore: fixedNow - 10, ExpiresAt: fixedNow + 600}
	issuers, err := authority.NewStaticIssuerResolver([]authority.IssuerRecord{routeIssuer, acpIssuer})
	if err != nil {
		return nil, err
	}
	store, err := authority.NewFileIdempotencyStore(authority.FileIdempotencyStoreConfig{Path: filepath.Join(runtimeDir, "acp-idempotency.cbor"), DeploymentMode: authority.IdempotencyDeploymentSingleNode, ReplicaCount: 1, MaxEntries: 64, MaxBytes: 4 << 20, CleanupGraceSeconds: 1, NowUnix: func() uint64 { return fixedNow }})
	if err != nil {
		return nil, err
	}
	release := make(chan struct{})
	authz := &Authority{request: request, grant: grant, generation: request.Key.AuthorityGeneration, block: cfg.block, mutation: cfg.mutation, release: release}
	runtime, err := authority.NewSourceOperatorRuntime(authority.SourceOperatorRuntimeConfig{SourceOperator: request.Key.SourceOperator, Profile: request.Key.Profile, ReplicaCount: 1, RequestKeys: staticDeviceResolver{record: deviceRecord}, Authority: authz, Bootstrap: denyBootstrap{}, Enrollment: denyEnrollment{}, ACPResultSigner: acpSigner, EnrollmentResultSigner: &operatorSigner{kid: []byte("nbsr-demo-enrollment-result-v1"), purpose: 16, private: acpPrivate}, Idempotency: store, NowUnix: func() uint64 { return fixedNow }})
	if err != nil {
		_ = store.Close()
		return nil, err
	}
	cert, roots, err := generateTLS(runtimeDir)
	if err != nil {
		_ = runtime.Close()
		_ = store.Close()
		return nil, err
	}
	listener, err := net.Listen("tcp", listenAddress)
	if err != nil {
		return nil, err
	}
	var runtimeView *session.DestinationRouteView
	if cfg.runtimeView != nil {
		view := *cfg.runtimeView
		runtimeView = &view
	}
	s := &Server{authority: authz, endpoint: "https://" + listener.Addr().String(), clientTLS: &tls.Config{RootCAs: roots, ServerName: "nbsr-demo-acp", MinVersion: tls.VersionTLS13, MaxVersion: tls.VersionTLS13, NextProtos: []string{"h2"}}, deviceSigner: deviceSigner, issuers: issuers, checkpoint: authority.CheckpointClaims{SourceOperator: request.Key.SourceOperator, Profile: request.Key.Profile, Generation: request.Key.AuthorityGeneration, IssuedAt: fixedNow - 1, FreshUntil: fixedNow + 300, Digest: authority.CheckpointDigest{7}}, runtime: runtime, listener: listener, store: store, runtimeView: runtimeView, routeIssuer: routeIssuer, release: release}
	httpServer, err := authority.NewSourceOperatorHTTPServer(listener.Addr().String(), runtime, &tls.Config{Certificates: []tls.Certificate{cert}})
	if err != nil {
		return nil, err
	}
	httpServer.Handler = http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.TLS != nil {
			s.mu.Lock()
			s.lastTLS = *r.TLS
			s.mu.Unlock()
		}
		runtime.ServeHTTP(w, r)
	})
	httpServer.ErrorLog = log.New(io.Discard, "", 0)
	s.http = httpServer
	go func() { _ = httpServer.ServeTLS(listener, "", "") }()
	return s, nil
}

func (s *Server) Close() {
	if s == nil {
		return
	}
	s.closeOnce.Do(func() {
		close(s.release)
		_ = s.http.Close()
		_ = s.runtime.Close()
		_ = s.store.Close()
	})
}
func (s *Server) Endpoint() string { return s.endpoint }
func (s *Server) AcquireRequest() authority.AcquireRequest {
	r := s.authority.request
	r.Intent.Canonical = append([]byte(nil), r.Intent.Canonical...)
	r.Intent.TargetEdges = append([]string(nil), r.Intent.TargetEdges...)
	return r
}
func (s *Server) ClientTLSConfig() *tls.Config                 { return s.clientTLS.Clone() }
func (s *Server) DeviceSigner() identity.Signer                { return s.deviceSigner }
func (s *Server) Issuers() *authority.StaticIssuerResolver     { return s.issuers }
func (s *Server) CheckpointClaims() authority.CheckpointClaims { return s.checkpoint }
func (s *Server) NowUnix() uint64                              { return fixedNow }
func (s *Server) LastTLS() tls.ConnectionState                 { s.mu.Lock(); defer s.mu.Unlock(); return s.lastTLS }

func (s *Server) PublicRuntimeAdmissionConfig(edgeNonce [32]byte) ([]byte, error) {
	if s == nil || s.runtimeView == nil || edgeNonce == ([32]byte{}) || len(s.runtimeView.Intent.TargetEdges) != 1 {
		return nil, errors.New("runtime admission configuration unavailable")
	}
	view := *s.runtimeView
	return []byte(fmt.Sprintf(
		"NBSR-RUNTIME-ADMISSION-v1\nsource_operator=%s\nsource_edge=%s\ndestination_operator=%s\ndestination_edge=%s\nservice_identity=%s\nservice_digest=%x\ntransport=%s\nport=%d\nrecord_sequence=%d\npolicy_hash=%x\nnow=%d\nproof_thumbprint=%x\nproof_public_key=%x\nedge_nonce=%x\nissuer_kid=%s\nissuer_public_key=%x\n",
		view.Intent.SourceOperator, view.Intent.SourceEdge, view.Intent.TargetOperator, view.Intent.TargetEdges[0],
		view.ServiceIdentity, view.ServiceDigest, view.Intent.Transport, view.Intent.Port,
		view.Intent.RecordSequence, view.Intent.PolicyHash, fixedNow,
		view.ProofThumbprint, view.ProofPublicKey, edgeNonce, s.routeIssuer.KID, s.routeIssuer.PublicKey,
	)), nil
}

func makeRequest() (authority.AcquireRequest, identity.Signer, authority.DeviceACPRequestKey, error) {
	public, private, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		return authority.AcquireRequest{}, nil, authority.DeviceACPRequestKey{}, err
	}
	thumb := sha256.Sum256(public)
	id := sha256.Sum256([]byte("nbsr-demo-device-v1"))
	keyID := sha256.Sum256([]byte("nbsr-demo-device-acp-key-v1"))
	ref := identity.KeyRef{ID: keyID, Purpose: identity.PurposeDeviceACPRequest, Generation: 1, Thumbprint: thumb}
	signer, err := identity.NewMemorySigner(ref, private)
	if err != nil {
		return authority.AcquireRequest{}, nil, authority.DeviceACPRequestKey{}, err
	}
	canonical := []byte("demo route intent for service-a.nbsr.test")
	intent := authority.RouteIntent{Canonical: canonical, Digest: authority.RouteIntentDigest(sha256.Sum256(canonical)), ServiceIdentity: "nbsr-demo-service-a-v1", SourceOperator: "source.operator", SourceEdge: "source.edge", TargetOperator: "destination.operator", TargetEdges: []string{"destination.edge"}, Transport: "tcp", Port: 8080, RecordSequence: 1, PolicyHash: authority.PolicyDigest(sha256.Sum256([]byte("demo-policy-v1"))), RouteID: [16]byte{1}, LeaseID: [16]byte{2}, ExpiresAt: fixedNow + 300}
	name, err := resolution.CanonicalizePresentationName("service-a.nbsr.test")
	if err != nil {
		return authority.AcquireRequest{}, nil, authority.DeviceACPRequestKey{}, err
	}
	serviceDigest := authority.ServiceDigest(resolution.DigestCanonicalName(name))
	key := authority.AuthorityKey{IntentDigest: intent.Digest, ServiceDigest: serviceDigest, SourceOperator: intent.SourceOperator, SourceEdge: intent.SourceEdge, TargetOperator: intent.TargetOperator, TargetEdgeSetDigest: authority.TargetEdgeSetDigest(intent.TargetEdges), Profile: "nbsr-federation-dev-v1", Transport: "tcp", Port: 8080, DeviceID: id, DeviceGeneration: 1, TSGeneration: 2, ProofThumbprint: authority.ProofKeyThumbprint(sha256.Sum256([]byte("demo-proof-v1"))), PolicyHash: intent.PolicyHash, PolicyGeneration: 1, AuthorityGeneration: 7}
	device := identity.DeviceIdentity{ID: id, SourceOperatorID: key.SourceOperator, CredentialGeneration: 1, CredentialNotBefore: fixedNow - 10, CredentialExpiresAt: fixedNow + 600, SigningKey: ref}
	request := authority.AcquireRequest{Key: key, Intent: intent, Device: device, RequestID: authority.RequestID{1}, DeadlineUnix: fixedNow + 30}
	var pub [32]byte
	copy(pub[:], public)
	record := authority.DeviceACPRequestKey{KID: keyID, PublicKey: pub, Purpose: identity.PurposeDeviceACPRequest, KeyGeneration: 1, DeviceID: id, CredentialGeneration: 1, CredentialNotBefore: device.CredentialNotBefore, CredentialExpiresAt: device.CredentialExpiresAt, SourceOperator: key.SourceOperator, Thumbprint: thumb, NotBefore: fixedNow - 10, ExpiresAt: fixedNow + 600}
	return request, signer, record, nil
}

type staticDeviceResolver struct{ record authority.DeviceACPRequestKey }

func (r staticDeviceResolver) ResolveDeviceACPRequestKey(_ context.Context, kid []byte, _ uint64) (authority.DeviceACPRequestKey, error) {
	if !bytes.Equal(kid, r.record.KID[:]) {
		return authority.DeviceACPRequestKey{}, authority.ErrUnknownIdentity
	}
	return r.record, nil
}

type operatorSigner struct {
	kid     []byte
	purpose uint16
	private ed25519.PrivateKey
}

func (s *operatorSigner) KID() []byte     { return append([]byte(nil), s.kid...) }
func (s *operatorSigner) Purpose() uint16 { return s.purpose }
func (s *operatorSigner) Sign(ctx context.Context, b []byte) ([]byte, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return ed25519.Sign(s.private, b), nil
}

type denyBootstrap struct{}

func (denyBootstrap) AuthorizeInitialEnrollment(context.Context, *http.Request) (authority.BootstrapAuthorization, error) {
	return authority.BootstrapAuthorization{}, authority.ErrBootstrapUnauthorized
}

type denyEnrollment struct{}

func (denyEnrollment) DecideInitialEnrollment(context.Context, authority.BootstrapAuthorization, authority.VerifiedEnrollmentRequest) (authority.EnrollmentDecision, error) {
	return authority.EnrollmentDecision{Status: authority.EnrollmentStatusRejected}, nil
}
func sameIntent(a, b authority.RouteIntent) bool {
	return a.Digest == b.Digest && a.ServiceIdentity == b.ServiceIdentity && a.SourceOperator == b.SourceOperator && a.SourceEdge == b.SourceEdge && a.TargetOperator == b.TargetOperator && a.Transport == b.Transport && a.Port == b.Port && a.RecordSequence == b.RecordSequence && a.PolicyHash == b.PolicyHash && a.RouteID == b.RouteID && a.LeaseID == b.LeaseID && a.ExpiresAt == b.ExpiresAt && len(a.TargetEdges) == len(b.TargetEdges) && len(a.TargetEdges) == 1 && a.TargetEdges[0] == b.TargetEdges[0]
}

func generateTLS(dir string) (tls.Certificate, *x509.CertPool, error) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		return tls.Certificate{}, nil, err
	}
	serial, _ := rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 120))
	now := time.Now()
	template := x509.Certificate{SerialNumber: serial, Subject: pkix.Name{CommonName: "nbsr-demo-acp"}, DNSNames: []string{"nbsr-demo-acp"}, NotBefore: now.Add(-time.Minute), NotAfter: now.Add(time.Hour), KeyUsage: x509.KeyUsageDigitalSignature | x509.KeyUsageKeyEncipherment, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}, BasicConstraintsValid: true}
	der, err := x509.CreateCertificate(rand.Reader, &template, &template, &key.PublicKey, key)
	if err != nil {
		return tls.Certificate{}, nil, err
	}
	certPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})
	keyPEM := pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(key)})
	certPath, keyPath := filepath.Join(dir, "acp-cert.pem"), filepath.Join(dir, "acp-key.pem")
	if err = os.WriteFile(certPath, certPEM, 0o644); err != nil {
		return tls.Certificate{}, nil, err
	}
	if err = os.WriteFile(keyPath, keyPEM, 0o600); err != nil {
		return tls.Certificate{}, nil, err
	}
	pair, err := tls.X509KeyPair(certPEM, keyPEM)
	if err != nil {
		return tls.Certificate{}, nil, err
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(certPEM) {
		return tls.Certificate{}, nil, errors.New("failed to trust demo certificate")
	}
	return pair, roots, nil
}
