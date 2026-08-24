package main

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"os"
	"path/filepath"
	"runtime"
	"sync"
	"sync/atomic"
	"time"

	"nbsr.local/client/nbsr-go-client/streamclient"
	"nbsr.local/interop/nbsr-go-peer/internal/authority"
	"nbsr.local/interop/nbsr-go-peer/internal/cbor"
	"nbsr.local/interop/nbsr-go-peer/internal/core"
	"nbsr.local/interop/nbsr-go-peer/internal/perfclock"
	"nbsr.local/interop/nbsr-go-peer/internal/state"
	"nbsr.local/interop/nbsr-go-peer/internal/streamcredit"
	"nbsr.local/interop/nbsr-go-peer/internal/transport"
)

const maxBenchmarkPayload = 1 << 20

type config struct {
	ReadinessPath              string  `json:"readiness_path"`
	F75Package                 string  `json:"f75_package"`
	LocalAttestationPackage    string  `json:"local_attestation_package"`
	SafePayload                string  `json:"safe_payload"`
	BenchmarkSamples           int     `json:"benchmark_samples,omitempty"`
	OfferedRate                float64 `json:"offered_rate,omitempty"`
	RuntimeSeriesPath          string  `json:"runtime_series_path,omitempty"`
	RuntimeSamplingCadenceMS   int     `json:"runtime_sampling_cadence_ms,omitempty"`
	LifecycleAuthorityDir      string  `json:"lifecycle_authority_dir,omitempty"`
	LifecycleConnections       int     `json:"lifecycle_connections,omitempty"`
	LifecycleServices          int     `json:"lifecycle_services,omitempty"`
	LifecycleStreamsPerService int     `json:"lifecycle_streams_per_service,omitempty"`
	LifecycleConcurrent        bool    `json:"lifecycle_concurrent,omitempty"`
	LifecycleConnectionOffset  int     `json:"lifecycle_connection_offset,omitempty"`
	LifecycleReportConnections bool    `json:"lifecycle_report_connections,omitempty"`
	StreamCreditProfile        string  `json:"stream_credit_profile,omitempty"`
}

func isCreditMutation(value string) bool {
	return value == "malformed_credit_preface" || value == "credit_profile_mismatch" || value == "credit_legacy_downgrade" || value == "credit_wrong_channel" || value == "credit_replay"
}

func runMutatedCreditCase(ctx context.Context, peer *transport.Peer, configuration config, channelID [16]byte, mutation string) (result, error) {
	if mutation == "credit_replay" {
		first, err := peer.OpenApplication(ctx)
		if err != nil {
			return result{}, err
		}
		preface, err := streamcredit.EncodePreface(channelID, 1, 1, 0, uint64(first.StreamID()))
		if err != nil {
			return result{}, err
		}
		if _, err = first.Write(preface); err != nil {
			return result{}, err
		}
		decision := []byte{0xff}
		if _, err = io.ReadFull(first, decision); err != nil || decision[0] != 0 {
			return result{}, errors.New("initial replay setup admission rejected")
		}
		if _, err = first.Write([]byte(configuration.SafePayload)); err != nil {
			return result{}, err
		}
		if err = first.Close(); err != nil {
			return result{}, err
		}
		echo := make([]byte, len(configuration.SafePayload))
		if _, err = io.ReadFull(first, echo); err != nil {
			return result{}, err
		}
		second, err := peer.OpenApplication(ctx)
		if err != nil {
			return result{}, err
		}
		replayed, err := streamcredit.EncodePreface(channelID, 1, 1, 0, uint64(second.StreamID()))
		if err != nil {
			return result{}, err
		}
		if _, err = second.Write(replayed); err != nil {
			return result{}, err
		}
		if _, err = io.ReadFull(second, decision); err != nil {
			return result{}, fmt.Errorf("replayed credit rejected: %w", err)
		}
		return result{}, errors.New("replayed credit unexpectedly answered")
	}
	application, err := peer.OpenApplication(ctx)
	if err != nil {
		return result{}, err
	}
	streamID := uint64(application.StreamID())
	preface, err := streamcredit.EncodePreface(channelID, 1, 1, 0, streamID)
	if err != nil {
		return result{}, err
	}
	switch mutation {
	case "malformed_credit_preface":
		preface = []byte{0x02, 0xbf, 0xff}
	case "credit_profile_mismatch":
		preface[3] = 0x02
	case "credit_legacy_downgrade":
		preface = []byte(configuration.SafePayload)
	case "credit_wrong_channel":
		wrongChannel := channelID
		wrongChannel[0] ^= 1
		preface, err = streamcredit.EncodePreface(wrongChannel, 1, 1, 0, streamID)
		if err != nil {
			return result{}, err
		}
	default:
		return result{}, errors.New("unsupported credit mutation")
	}
	if _, err := application.Write(preface); err != nil {
		return result{}, fmt.Errorf("stream-credit preface write: %w", err)
	}
	decision := []byte{0xff}
	if _, err := io.ReadFull(application, decision); err != nil {
		return result{}, fmt.Errorf("stream-credit admission rejected: %w", err)
	}
	if decision[0] == 0 {
		return result{}, errors.New("invalid stream-credit case unexpectedly accepted")
	}
	return result{}, errors.New("stream-credit admission rejected")
}

func (value config) validate() error {
	if value.ReadinessPath == "" || value.F75Package == "" || value.LocalAttestationPackage == "" || value.SafePayload == "" || len(value.SafePayload) > maxBenchmarkPayload {
		return errors.New("configuration fields are missing or out of bounds")
	}
	if value.BenchmarkSamples < 0 || value.BenchmarkSamples > 10_000_000 {
		return errors.New("benchmark sample count is out of bounds")
	}
	if value.StreamCreditProfile != "" {
		if value.StreamCreditProfile != streamcredit.ProfileID {
			return errors.New("unsupported stream-credit profile")
		}
		if value.BenchmarkSamples < 1 || value.BenchmarkSamples > 128 || value.OfferedRate != 0 || value.LifecycleAuthorityDir != "" {
			return errors.New("stream-credit interop mode requires 1 to 128 bounded operations")
		}
	}
	if value.BenchmarkSamples > 100_000 && value.OfferedRate == 0 {
		return errors.New("large benchmark sample count requires streaming open-loop mode")
	}
	if value.OfferedRate < 0 || math.IsNaN(value.OfferedRate) || math.IsInf(value.OfferedRate, 0) {
		return errors.New("offered rate is out of bounds")
	}
	if (value.RuntimeSeriesPath == "") != (value.RuntimeSamplingCadenceMS == 0) {
		return errors.New("incomplete runtime sampling configuration")
	}
	if value.RuntimeSeriesPath != "" && (value.OfferedRate <= 0 || value.RuntimeSamplingCadenceMS != 1000) {
		return errors.New("runtime sampling requires open-loop load and a 1000 ms cadence")
	}
	if value.LifecycleAuthorityDir == "" {
		if value.LifecycleConnections != 0 || value.LifecycleServices != 0 {
			return errors.New("incomplete lifecycle configuration")
		}
		return nil
	}
	if value.LifecycleConnections < 1 || value.LifecycleServices < 1 || value.LifecycleServices > 32 || value.LifecycleStreamsPerService < 1 || value.LifecycleStreamsPerService > 64 {
		return errors.New("lifecycle configuration is out of bounds")
	}
	return nil
}

type result struct {
	Status               string          `json:"status"`
	Messages             []string        `json:"messages"`
	CoreVersion          uint64          `json:"core_version"`
	RouteOpenBodyVersion uint64          `json:"route_open_body_version"`
	FederationProfile    string          `json:"federation_profile"`
	PayloadSHA256        string          `json:"payload_sha256"`
	BenchmarkSamples     int             `json:"benchmark_samples,omitempty"`
	Samples              []sample        `json:"samples,omitempty"`
	GoRuntime            *goRuntimeStats `json:"go_runtime,omitempty"`
}

type goRuntimeStats struct {
	HeapAllocBytes         uint64 `json:"heap_alloc_bytes"`
	HeapSysBytes           uint64 `json:"heap_sys_bytes"`
	HeapIdleBytes          uint64 `json:"heap_idle_bytes"`
	HeapInuseBytes         uint64 `json:"heap_inuse_bytes"`
	HeapReleasedBytes      uint64 `json:"heap_released_bytes"`
	TotalAllocBytes        uint64 `json:"total_alloc_bytes"`
	Mallocs                uint64 `json:"mallocs"`
	Frees                  uint64 `json:"frees"`
	GCCycles               uint32 `json:"gc_cycles"`
	TotalGCPauseNS         uint64 `json:"total_gc_pause_ns"`
	MaximumRecentGCPauseNS uint64 `json:"maximum_recent_gc_pause_ns"`
}

type goRuntimeSample struct {
	ObservedAtNS      int64  `json:"observed_at_ns"`
	ProcessedRequests uint64 `json:"processed_requests"`
	HeapAllocBytes    uint64 `json:"heap_alloc_bytes"`
	HeapSysBytes      uint64 `json:"heap_sys_bytes"`
	HeapIdleBytes     uint64 `json:"heap_idle_bytes"`
	HeapInuseBytes    uint64 `json:"heap_inuse_bytes"`
	HeapReleasedBytes uint64 `json:"heap_released_bytes"`
	NumGC             uint32 `json:"num_gc"`
	TotalAllocBytes   uint64 `json:"total_alloc_bytes"`
	Mallocs           uint64 `json:"mallocs"`
	Frees             uint64 `json:"frees"`
	TotalGCPauseNS    uint64 `json:"total_gc_pause_ns"`
}

func startRuntimeSampler(path string, cadence time.Duration, processed *atomic.Uint64) (func() error, error) {
	if path == "" || cadence <= 0 || processed == nil {
		return nil, errors.New("invalid runtime sampler configuration")
	}
	file, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return nil, err
	}
	stop := make(chan struct{})
	done := make(chan error, 1)
	var once sync.Once
	var stopErr error
	go func() {
		ticker := time.NewTicker(cadence)
		defer ticker.Stop()
		encoder := json.NewEncoder(file)
		for {
			select {
			case observed := <-ticker.C:
				var stats runtime.MemStats
				runtime.ReadMemStats(&stats)
				sample := goRuntimeSample{
					ObservedAtNS: observed.UnixNano(), ProcessedRequests: processed.Load(),
					HeapAllocBytes: stats.HeapAlloc, HeapSysBytes: stats.HeapSys,
					HeapIdleBytes: stats.HeapIdle, HeapInuseBytes: stats.HeapInuse, HeapReleasedBytes: stats.HeapReleased,
					NumGC: stats.NumGC, TotalAllocBytes: stats.TotalAlloc, Mallocs: stats.Mallocs, Frees: stats.Frees,
					TotalGCPauseNS: stats.PauseTotalNs,
				}
				if err := encoder.Encode(sample); err != nil {
					_ = file.Close()
					done <- err
					return
				}
			case <-stop:
				done <- file.Close()
				return
			}
		}
	}()
	return func() error {
		once.Do(func() {
			close(stop)
			stopErr = <-done
		})
		return stopErr
	}, nil
}

type sample struct {
	SampleID                int    `json:"sample_id"`
	Success                 bool   `json:"success"`
	TransportHandshakeNS    *int64 `json:"transport_handshake_ns"`
	HelloRTTNS              *int64 `json:"hello_rtt_ns"`
	SourceAdmissionNS       *int64 `json:"source_admission_ns"`
	DestinationAdmissionNS  *int64 `json:"destination_admission_ns"`
	RouteOpenRTTNS          *int64 `json:"route_open_rtt_ns"`
	ChannelBindingNS        *int64 `json:"channel_binding_ns"`
	StreamOpenRTTNS         int64  `json:"stream_open_rtt_ns"`
	TTFABNS                 int64  `json:"ttfab_ns"`
	RequestLatencyNS        int64  `json:"request_latency_ns"`
	ApplicationProcessingNS *int64 `json:"application_processing_ns"`
	TotalScenarioNS         int64  `json:"total_scenario_ns"`
	BytesTransmitted        int    `json:"bytes_transmitted"`
	BytesReceived           int    `json:"bytes_received"`
	ScheduledNS             int64  `json:"scheduled_ns"`
	StartedNS               int64  `json:"started_ns"`
	CompletedNS             int64  `json:"completed_ns"`
	StartLatenessNS         int64  `json:"start_lateness_ns"`
	ServiceLatencyNS        int64  `json:"service_latency_ns"`
}

func measured(value int64) *int64 { return &value }

func runtimeDelta(start runtime.MemStats, end runtime.MemStats) *goRuntimeStats {
	maximum := uint64(0)
	for _, pause := range end.PauseNs {
		maximum = max(maximum, pause)
	}
	return &goRuntimeStats{
		HeapAllocBytes: end.HeapAlloc, HeapSysBytes: end.HeapSys,
		HeapIdleBytes: end.HeapIdle, HeapInuseBytes: end.HeapInuse, HeapReleasedBytes: end.HeapReleased,
		TotalAllocBytes: end.TotalAlloc - start.TotalAlloc,
		Mallocs:         end.Mallocs - start.Mallocs, Frees: end.Frees - start.Frees,
		GCCycles: end.NumGC - start.NumGC, TotalGCPauseNS: end.PauseTotalNs - start.PauseTotalNs,
		MaximumRecentGCPauseNS: maximum,
	}
}

func waitUntilQPC(origin int64, scheduledNS int64) {
	for {
		remaining := time.Duration(scheduledNS - perfclock.Since(origin))
		if remaining <= 0 {
			return
		}
		if remaining > 20*time.Millisecond {
			time.Sleep(remaining - 20*time.Millisecond)
		} else {
			runtime.Gosched()
		}
	}
}

func loadConfig(path string) (config, error) {
	file, err := os.Open(path)
	if err != nil {
		return config{}, err
	}
	defer file.Close()
	decoder := json.NewDecoder(io.LimitReader(file, maxBenchmarkPayload+64*1024))
	decoder.DisallowUnknownFields()
	var value config
	if err := decoder.Decode(&value); err != nil {
		return config{}, err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return config{}, errors.New("configuration must contain one JSON object")
	}
	if err := value.validate(); err != nil {
		return config{}, err
	}
	return value, nil
}

func lifecycleIDs(index int) (request, channel, route [16]byte) {
	request[0], channel[0], route[0] = 0x70, 0x40, 0x20
	binary.BigEndian.PutUint64(request[8:], uint64(index))
	binary.BigEndian.PutUint64(channel[8:], uint64(index))
	binary.BigEndian.PutUint64(route[8:], uint64(index))
	return
}

func sequence(start byte) [16]byte {
	var value [16]byte
	for index := range value {
		value[index] = start + byte(index)
	}
	return value
}
func repeated32(value byte) (result [32]byte) {
	for index := range result {
		result[index] = value
	}
	return
}
func specialRequest(last byte) [16]byte { value := sequence(0); value[15] = last; return value }
func benchmarkStreamRequest(index uint64) [16]byte {
	value := sequence(0)
	value[15] = 0x11
	binary.BigEndian.PutUint64(value[8:16], binary.BigEndian.Uint64(value[8:16])+index)
	return value
}
func mustRead(path string) ([]byte, error) { return os.ReadFile(filepath.Clean(path)) }
func loadPublicKey(path string) (ed25519.PublicKey, error) {
	raw, err := mustRead(path)
	if err != nil {
		return nil, err
	}
	decoded, err := hex.DecodeString(string(bytes.TrimSpace(raw)))
	if err != nil || len(decoded) != ed25519.PublicKeySize {
		return nil, errors.New("invalid Ed25519 public key")
	}
	return ed25519.PublicKey(decoded), nil
}

func run(ctx context.Context, configuration config) (result, error) {
	mutation := os.Getenv("NBSR_INTEROP_TEST_MUTATION")
	allowedMutations := map[string]bool{"": true, "unsupported_alpn": true, "wrong_peer_identity": true, "wrong_ca": true, "payload_before_admission": true, "malformed_cbor": true, "noncanonical_cbor": true, "over_limit_cbor": true, "wrong_core_version": true, "wrong_session": true, "wrong_request": true, "wrong_channel": true, "wrong_transport": true, "wrong_port": true, "wrong_route_grant_digest": true, "wrong_federation_context_digest": true, "wrong_proof_signature": true, "wrong_service": true, "expired_authority": true, "revoked_authority": true, "unsupported_federation_version": true, "unsupported_profile": true, "downgrade_v1": true, "transcript_substitution": true, "replay": true, "wrong_stream": true, "malformed_credit_preface": true, "credit_profile_mismatch": true, "credit_legacy_downgrade": true, "credit_wrong_channel": true, "credit_replay": true}
	if !allowedMutations[mutation] {
		return result{}, errors.New("unsupported test mutation")
	}
	ready, err := transport.LoadReadiness(configuration.ReadinessPath)
	if err != nil {
		return result{}, err
	}
	if mutation == "unsupported_alpn" {
		ready.ALPN = "unsupported"
	}
	if mutation == "wrong_peer_identity" {
		ready.ServerName = "wrong.edge"
	}
	if mutation == "wrong_ca" {
		ready.CADER = ready.ClientCertDER
	}
	peer, err := transport.Dial(ctx, ready)
	if err != nil {
		return result{}, err
	}
	defer peer.Close()
	if mutation == "payload_before_admission" {
		application, openErr := peer.OpenApplication(ctx)
		if openErr != nil {
			return result{}, openErr
		}
		if _, writeErr := application.Write([]byte(configuration.SafePayload)); writeErr != nil {
			return result{}, writeErr
		}
		return result{}, errors.New("test payload attempted before admission")
	}
	sessionID, helloRequest, routeRequest, streamRequest := sequence(0x10), sequence(0), specialRequest(0x10), specialRequest(0x11)
	channelID, routeID := sequence(0x40), sequence(0x20)
	machine := state.NewSource(sessionID, helloRequest, routeRequest, streamRequest, channelID, routeID, "service.example", "tcp", 8443)
	sessionPublic, err := loadPublicKey(filepath.Join(filepath.Dir(configuration.F75Package), "core-v0.2", "keys", "test-only-session-ed25519-public.hex"))
	if err != nil {
		return result{}, err
	}
	clientNonce, edgeNonce := sequence32(0x60), sequence32(0x80)
	clientBody := map[uint64]any{0: uint64(1), 1: "nbsr12df4x56n2df4x56n2df4x56n2df4x56n2df4x56n2df4x56n2dfsk5743r", 2: "source.edge", 3: "nbsr1g3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zqel9ufg", 4: "destination.edge", 5: clientNonce[:], 6: []byte(sessionPublic), 7: uint64(1_893_456_000)}
	if mutation == "malformed_cbor" {
		if err := peer.SendRawControl([]byte{0xbf, 0xff}); err != nil {
			return result{}, err
		}
		return result{}, errors.New("malformed CBOR sent for rejection")
	}
	if mutation == "noncanonical_cbor" {
		canonical, encodeErr := cbor.Encode(map[uint64]any{0: uint64(2), 1: uint64(core.ClientHello), 2: helloRequest[:], 3: sessionID[:], 4: uint64(1), 5: clientBody})
		if encodeErr != nil {
			return result{}, encodeErr
		}
		index := bytes.Index(canonical, []byte{0x00, 0x02})
		if index < 0 {
			return result{}, errors.New("canonical version encoding absent")
		}
		noncanonical := append(append(append([]byte{}, canonical[:index+1]...), 0x18, 0x02), canonical[index+2:]...)
		if err := peer.SendRawControl(noncanonical); err != nil {
			return result{}, err
		}
		return result{}, errors.New("non-canonical CBOR sent for rejection")
	}
	if mutation == "over_limit_cbor" {
		overLimit := append([]byte{0x98, 0x81}, make([]byte, 129)...)
		if err := peer.SendRawControl(overLimit); err != nil {
			return result{}, err
		}
		return result{}, errors.New("over-limit CBOR sent for rejection")
	}
	if mutation == "wrong_core_version" {
		wire, encodeErr := cbor.Encode(map[uint64]any{0: uint64(3), 1: uint64(core.ClientHello), 2: helloRequest[:], 3: sessionID[:], 4: uint64(1), 5: clientBody})
		if encodeErr != nil {
			return result{}, encodeErr
		}
		if err := peer.SendRawControl(wire); err != nil {
			return result{}, err
		}
		return result{}, errors.New("unsupported Core version sent for rejection")
	}
	if err := peer.SendEnvelope(core.Envelope{ProtocolVersion: 2, MessageType: core.ClientHello, RequestID: helloRequest, SessionID: sessionID, Sequence: 1, Body: clientBody}); err != nil {
		return result{}, err
	}
	if err := machine.HelloSent(); err != nil {
		return result{}, err
	}
	edge, err := peer.ReceiveEnvelope()
	if err != nil {
		return result{}, err
	}
	if edge.MessageType != core.EdgeHello || edge.SessionID != sessionID || edge.RequestID != helloRequest || edge.Body[1] != "source.edge" || edge.Body[2] != "destination.edge" || !bytes.Equal(edge.Body[3].([]byte), clientNonce[:]) || !bytes.Equal(edge.Body[4].([]byte), edgeNonce[:]) || !bytes.Equal(edge.Body[5].([]byte), sha256Bytes(sessionPublic)) {
		return result{}, errors.New("EDGE_HELLO authority or correlation mismatch")
	}
	if err := machine.EdgeHelloAccepted(edge.SessionID, edge.RequestID); err != nil {
		return result{}, err
	}

	bodyWire, err := mustRead(filepath.Join(configuration.F75Package, "route-open-body.cbor"))
	if err != nil {
		return result{}, err
	}
	decoded, err := cbor.DecodeExact(bodyWire, cbor.DefaultLimits())
	if err != nil {
		return result{}, err
	}
	routeBody := decoded.(map[uint64]any)
	issuerPublic, err := loadPublicKey(filepath.Join(filepath.Dir(configuration.F75Package), "core-v0.2", "keys", "test-only-route-grant-ed25519-public.hex"))
	if err != nil {
		return result{}, err
	}
	exactGrant := routeBody[2].([]byte)
	grant, err := authority.VerifyRouteGrant(exactGrant, issuerPublic, []byte("nbsr-test-route-grant-key"), 1_893_456_000)
	if err != nil {
		return result{}, err
	}
	federationContext, err := mustRead(filepath.Join(configuration.F75Package, "federation-context.cbor"))
	if err != nil {
		return result{}, err
	}
	sourceAttestation, err := mustRead(filepath.Join(configuration.LocalAttestationPackage, "source.cose"))
	if err != nil {
		return result{}, err
	}
	sourceAuthority, err := hex.DecodeString("f80cccdce4ae1c07ae208a2adf99a310ae4207e0306fa0236110b06827bbb8d0")
	if err != nil {
		return result{}, err
	}
	if err := authority.VerifySourceAdmission(sourceAttestation, ed25519.PublicKey(sourceAuthority), []byte("local-source"), authority.SourceAdmissionBinding{
		SourceOperatorID: repeated32('S'), DestinationOperatorID: repeated32('D'),
		CanonicalName: "service.example", Transport: "tcp", Port: 8443,
		RouteGrantDigest: grant.Digest, FederationContextDigest: sha256.Sum256(federationContext),
		OpenedAt: 1_893_456_000,
	}); err != nil {
		return result{}, fmt.Errorf("source federation admission: %w", err)
	}
	transcript, err := authority.BuildF75Transcript(sessionID, routeRequest, "destination.edge", routeBody, grant)
	if err != nil {
		return result{}, err
	}
	proof := routeBody[7].([]byte)
	if !ed25519.Verify(sessionPublic, transcript, proof) {
		return result{}, errors.New("invalid F75 proof signature")
	}
	routeSession, routeRequestID := sessionID, routeRequest
	if mutation == "wrong_session" {
		routeSession[0] ^= 1
	}
	if mutation == "wrong_request" {
		routeRequestID[0] ^= 1
	}
	if mutation == "wrong_channel" {
		changed := append([]byte(nil), routeBody[1].([]byte)...)
		changed[0] ^= 1
		routeBody[1] = changed
	}
	if mutation == "wrong_transport" {
		routeBody[4] = "udp"
	}
	if mutation == "wrong_port" {
		routeBody[5] = uint64(443)
	}
	if mutation == "wrong_route_grant_digest" {
		binding := routeBody[8].(map[uint64]any)
		changed := append([]byte(nil), binding[4].([]byte)...)
		changed[0] ^= 1
		binding[4] = changed
	}
	if mutation == "wrong_federation_context_digest" {
		binding := routeBody[8].(map[uint64]any)
		changed := append([]byte(nil), binding[5].([]byte)...)
		changed[0] ^= 1
		binding[5] = changed
	}
	if mutation == "wrong_proof_signature" || mutation == "transcript_substitution" {
		changed := append([]byte(nil), proof...)
		changed[0] ^= 1
		routeBody[7] = changed
	}
	if mutation == "wrong_service" {
		changed := append([]byte(nil), exactGrant...)
		changed[len(changed)/2] ^= 1
		routeBody[2] = changed
	}
	if mutation == "unsupported_federation_version" {
		routeBody[8].(map[uint64]any)[2] = uint64(2)
	}
	if mutation == "unsupported_profile" {
		routeBody[8].(map[uint64]any)[3] = "unsupported"
	}
	if mutation == "downgrade_v1" {
		routeBody[0] = uint64(1)
		delete(routeBody, 8)
	}
	if err := machine.RouteSent(grant.ServiceID, grant.AllowedTransport, uint16(routeBody[5].(uint64))); err != nil {
		return result{}, err
	}
	if err := peer.SendEnvelope(core.Envelope{ProtocolVersion: 2, MessageType: core.RouteOpen, RequestID: routeRequestID, SessionID: routeSession, Sequence: 2, Body: routeBody}); err != nil {
		return result{}, err
	}
	if mutation != "" && mutation != "replay" && !isCreditMutation(mutation) {
		_, receiveErr := peer.ReceiveEnvelope()
		if receiveErr == nil {
			return result{}, errors.New("mutated route was unexpectedly answered")
		}
		return result{}, fmt.Errorf("mutated route rejected: %w", receiveErr)
	}
	routeAccepted, err := peer.ReceiveEnvelope()
	if err != nil {
		return result{}, err
	}
	if routeAccepted.MessageType != core.RouteAccept || routeAccepted.SessionID != sessionID || routeAccepted.RequestID != routeRequest {
		return result{}, errors.New("ROUTE_ACCEPT correlation mismatch")
	}
	if err := machine.RouteAccepted(routeAccepted.SessionID, routeAccepted.RequestID, bytes16(routeAccepted.Body[1]), bytes16(routeAccepted.Body[2])); err != nil {
		return result{}, err
	}
	if !bytes.Equal(routeAccepted.Body[3].([]byte), grant.Digest[:]) {
		return result{}, errors.New("ROUTE_ACCEPT digest mismatch")
	}
	if mutation == "replay" {
		if err := peer.SendEnvelope(core.Envelope{ProtocolVersion: 2, MessageType: core.RouteOpen, RequestID: routeRequest, SessionID: sessionID, Sequence: 2, Body: routeBody}); err != nil {
			return result{}, err
		}
		_, replayErr := peer.ReceiveEnvelope()
		if replayErr == nil {
			return result{}, errors.New("replayed ROUTE_OPEN accepted")
		}
		return result{}, fmt.Errorf("replayed ROUTE_OPEN rejected: %w", replayErr)
	}
	exporterContext, err := cbor.Encode([]any{"NBSR-SERVICE-CHANNEL-CONTEXT-v2", uint64(2), sessionID[:], "source.edge", "destination.edge", channelID[:], routeID[:], grant.Digest[:], grant.ServiceID, "tcp", uint64(8443), grant.PolicyHash[:], clientNonce[:], edgeNonce[:]})
	if err != nil {
		return result{}, err
	}
	exporter, err := peer.ExportKeyingMaterial(exporterContext)
	if err != nil || len(exporter) != 32 {
		return result{}, errors.New("live WP4 exporter failed")
	}
	if configuration.StreamCreditProfile != "" {
		if mutation != "" {
			return runMutatedCreditCase(ctx, peer, configuration, channelID, mutation)
		}
		serviceDigest := sha256.Sum256([]byte(grant.ServiceID))
		owner, ownerErr := streamclient.NewOwnedChannel(ctx, streamclient.OwnedChannelConfig{
			Now: 1_893_456_000, ExpiresAt: 1_893_457_000, TSGeneration: 1, ChannelGeneration: 1, AuthorityGeneration: 1,
			ChannelID: channelID, DeviceID: repeated32('C'), PolicyDigest: grant.PolicyHash, ServiceDigest: serviceDigest,
			RouteGrantDigest: grant.Digest, ProofThumbprint: repeated32('P'), SourceOperator: "source.edge",
			Gateway: "destination.edge", ServiceIdentity: grant.ServiceID, Profile: configuration.StreamCreditProfile, Transport: "quic",
			Open: func(ctx context.Context) (streamclient.Wire, uint64, error) {
				wire, openErr := peer.OpenApplication(ctx)
				if openErr != nil {
					return nil, 0, openErr
				}
				return wire, uint64(wire.StreamID()), nil
			},
			Refill: func(refillContext context.Context, epoch uint64) error {
				return peer.RefillStreamCredits(refillContext, channelID, epoch)
			},
		})
		if ownerErr != nil {
			return result{}, fmt.Errorf("production stream owner: %w", ownerErr)
		}
		defer owner.Close()
		var digest [32]byte
		for index := 0; index < configuration.BenchmarkSamples; index++ {
			application, admissionErr := owner.Open(ctx)
			if admissionErr != nil {
				return result{}, fmt.Errorf("stream-credit admission rejected: %w", admissionErr)
			}
			if _, err := application.Write([]byte(configuration.SafePayload)); err != nil {
				return result{}, fmt.Errorf("credited application write: %w", err)
			}
			if err := application.FinishWrite(); err != nil {
				return result{}, fmt.Errorf("credited application finish-write: %w", err)
			}
			echo := make([]byte, len(configuration.SafePayload))
			if _, err := io.ReadFull(application, echo); err != nil {
				return result{}, fmt.Errorf("credited application echo: %w", err)
			}
			if !bytes.Equal(echo, []byte(configuration.SafePayload)) {
				return result{}, errors.New("credited application payload echo mismatch")
			}
			if err := application.Close(); err != nil {
				return result{}, fmt.Errorf("credited application finish: %w", err)
			}
			digest = sha256.Sum256(echo)
		}
		return result{Status: "PASS", Messages: []string{"CLIENT_HELLO", "EDGE_HELLO", "ROUTE_OPEN", "ROUTE_ACCEPT", "STREAM_CREDIT_PREFACE", "STREAM_CREDIT_ACCEPT"}, CoreVersion: 2, RouteOpenBodyVersion: 2, FederationProfile: streamcredit.ProfileID, PayloadSHA256: hex.EncodeToString(digest[:]), BenchmarkSamples: configuration.BenchmarkSamples}, nil
	}

	samples := configuration.BenchmarkSamples
	if samples == 0 {
		samples = 1
	}
	observedSamples := make([]sample, 0, samples)
	var echo []byte
	var runtimeStart runtime.MemStats
	runtime.ReadMemStats(&runtimeStart)
	var processed atomic.Uint64
	stopRuntimeSampler := func() error { return nil }
	if configuration.RuntimeSeriesPath != "" {
		stopRuntimeSampler, err = startRuntimeSampler(
			configuration.RuntimeSeriesPath,
			time.Duration(configuration.RuntimeSamplingCadenceMS)*time.Millisecond,
			&processed,
		)
		if err != nil {
			return result{}, err
		}
		defer func() { _ = stopRuntimeSampler() }()
	}
	scheduleClockOrigin := perfclock.Now()
	for index := 0; index < samples; index++ {
		var scheduledNS, startedNS, startLatenessNS int64
		if configuration.OfferedRate > 0 {
			scheduledNS = int64(float64(index) / configuration.OfferedRate * 1_000_000_000)
			waitUntilQPC(scheduleClockOrigin, scheduledNS)
			startedNS = perfclock.Since(scheduleClockOrigin)
			startLatenessNS = max(0, startedNS-scheduledNS)
		}
		totalStarted := perfclock.Now()
		request := benchmarkStreamRequest(uint64(index))
		if index > 0 {
			if err := machine.NextStream(request); err != nil {
				return result{}, err
			}
		}
		application, err := peer.OpenApplication(ctx)
		if err != nil {
			return result{}, err
		}
		streamID := uint64(4 + 4*index)
		if uint64(application.StreamID()) != streamID {
			return result{}, errors.New("application stream ID mismatch")
		}
		streamBody := map[uint64]any{0: uint64(1), 1: streamID, 2: channelID[:], 3: routeID[:], 4: grant.Digest[:], 5: "tcp", 6: uint64(8443)}
		if mutation == "wrong_stream" {
			streamBody[1] = streamID + 4
		}
		if err := machine.StreamSent(streamID); err != nil {
			return result{}, err
		}
		streamStarted := perfclock.Now()
		if err := peer.SendEnvelope(core.Envelope{ProtocolVersion: 2, MessageType: core.StreamOpen, RequestID: request, SessionID: sessionID, Sequence: uint64(3 + index), Body: streamBody}); err != nil {
			return result{}, err
		}
		if mutation == "wrong_stream" {
			_, receiveErr := peer.ReceiveEnvelope()
			if receiveErr == nil {
				return result{}, errors.New("wrong stream correlation accepted")
			}
			return result{}, fmt.Errorf("wrong stream correlation rejected: %w", receiveErr)
		}
		streamAccepted, err := peer.ReceiveEnvelope()
		if err != nil {
			return result{}, err
		}
		if streamAccepted.MessageType != core.StreamAccept {
			return result{}, errors.New("STREAM_ACCEPT missing")
		}
		if err := machine.StreamAccepted(streamAccepted.SessionID, streamAccepted.RequestID, streamAccepted.Body[1].(uint64), bytes16(streamAccepted.Body[2]), bytes16(streamAccepted.Body[3])); err != nil {
			return result{}, err
		}
		streamNS := perfclock.Since(streamStarted)
		if !machine.PayloadAllowed() {
			return result{}, errors.New("payload gate remained closed")
		}
		requestStarted := perfclock.Now()
		if _, err := application.Write([]byte(configuration.SafePayload)); err != nil {
			return result{}, fmt.Errorf("application write: %w", err)
		}
		if err := application.Close(); err != nil {
			return result{}, fmt.Errorf("application finish: %w", err)
		}
		echo = make([]byte, len(configuration.SafePayload))
		if _, err := io.ReadFull(application, echo); err != nil {
			return result{}, fmt.Errorf("application echo: %w", err)
		}
		serviceNS := perfclock.Since(requestStarted)
		requestNS := serviceNS
		completedNS := int64(0)
		if configuration.OfferedRate > 0 {
			completedNS = perfclock.Since(scheduleClockOrigin)
			requestNS = completedNS - scheduledNS
		}
		if string(echo) != configuration.SafePayload {
			return result{}, errors.New("application payload echo mismatch")
		}
		entry := sample{SampleID: index, Success: true, StreamOpenRTTNS: streamNS, TTFABNS: requestNS, RequestLatencyNS: requestNS, TotalScenarioNS: perfclock.Since(totalStarted), BytesTransmitted: len(echo), BytesReceived: len(echo), ScheduledNS: scheduledNS, StartedNS: startedNS, CompletedNS: completedNS, StartLatenessNS: startLatenessNS, ServiceLatencyNS: serviceNS}
		if configuration.OfferedRate > 0 {
			if err := json.NewEncoder(os.Stdout).Encode(entry); err != nil {
				return result{}, err
			}
		} else {
			observedSamples = append(observedSamples, entry)
		}
		processed.Store(uint64(index + 1))
	}
	if err := stopRuntimeSampler(); err != nil {
		return result{}, err
	}
	digest := sha256.Sum256(echo)
	var runtimeEnd runtime.MemStats
	runtime.ReadMemStats(&runtimeEnd)
	return result{Status: "PASS", Messages: []string{"CLIENT_HELLO", "EDGE_HELLO", "ROUTE_OPEN", "ROUTE_ACCEPT", "STREAM_OPEN", "STREAM_ACCEPT"}, CoreVersion: 2, RouteOpenBodyVersion: 2, FederationProfile: "nbsr-federation-dev-v1", PayloadSHA256: hex.EncodeToString(digest[:]), BenchmarkSamples: samples, Samples: observedSamples, GoRuntime: runtimeDelta(runtimeStart, runtimeEnd)}, nil
}

func runLifecycle(ctx context.Context, configuration config) (result, error) {
	ready, err := transport.LoadReadiness(configuration.ReadinessPath)
	if err != nil {
		return result{}, err
	}
	sessionPublic, err := loadPublicKey(filepath.Join(filepath.Dir(configuration.F75Package), "core-v0.2", "keys", "test-only-session-ed25519-public.hex"))
	if err != nil {
		return result{}, err
	}
	issuerPublic, err := loadPublicKey(filepath.Join(filepath.Dir(configuration.F75Package), "core-v0.2", "keys", "test-only-route-grant-ed25519-public.hex"))
	if err != nil {
		return result{}, err
	}
	sourceAuthority, err := hex.DecodeString("f80cccdce4ae1c07ae208a2adf99a310ae4207e0306fa0236110b06827bbb8d0")
	if err != nil {
		return result{}, err
	}
	sessionID, helloRequest := sequence(0x10), sequence(0)
	clientNonce, edgeNonce := sequence32(0x60), sequence32(0x80)
	clientBody := map[uint64]any{0: uint64(1), 1: "nbsr12df4x56n2df4x56n2df4x56n2df4x56n2df4x56n2df4x56n2dfsk5743r", 2: "source.edge", 3: "nbsr1g3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zqel9ufg", 4: "destination.edge", 5: clientNonce[:], 6: []byte(sessionPublic), 7: uint64(1_893_456_000)}
	observed := make([]sample, 0, configuration.LifecycleConnections*configuration.LifecycleServices)
	for connectionOrdinal := 0; connectionOrdinal < configuration.LifecycleConnections; connectionOrdinal++ {
		coldStarted := perfclock.Now()
		handshakeStarted := perfclock.Now()
		peer, dialErr := transport.Dial(ctx, ready)
		if dialErr != nil {
			return result{}, dialErr
		}
		handshakeNS := perfclock.Since(handshakeStarted)
		if configuration.LifecycleReportConnections {
			if err := os.WriteFile(filepath.Join(configuration.LifecycleAuthorityDir, fmt.Sprintf("connection-%d.connected", configuration.LifecycleConnectionOffset+connectionOrdinal)), []byte("connected\n"), 0o600); err != nil {
				return result{}, err
			}
		}
		helloStarted := perfclock.Now()
		if err := peer.SendEnvelope(core.Envelope{ProtocolVersion: 2, MessageType: core.ClientHello, RequestID: helloRequest, SessionID: sessionID, Sequence: 1, Body: clientBody}); err != nil {
			return result{}, err
		}
		edge, err := peer.ReceiveEnvelope()
		if err != nil {
			return result{}, err
		}
		helloNS := perfclock.Since(helloStarted)
		if edge.MessageType != core.EdgeHello || edge.SessionID != sessionID || edge.RequestID != helloRequest || edge.Body[1] != "source.edge" || edge.Body[2] != "destination.edge" || !bytes.Equal(edge.Body[3].([]byte), clientNonce[:]) || !bytes.Equal(edge.Body[4].([]byte), edgeNonce[:]) || !bytes.Equal(edge.Body[5].([]byte), sha256Bytes(sessionPublic)) {
			return result{}, errors.New("EDGE_HELLO authority or correlation mismatch")
		}
		type concurrentMetric struct {
			service, localStream, ordinal int
			scenarioStarted               int64
			sourceAdmissionNS, routeNS    int64
			bindingNS, streamNS           int64
		}
		type concurrentResult struct {
			ordinal, requestNS int
			error              error
		}
		concurrentStart := make(chan struct{})
		concurrentResults := make(chan concurrentResult, configuration.LifecycleServices*configuration.LifecycleStreamsPerService)
		concurrentMetrics := make([]concurrentMetric, 0, configuration.LifecycleServices*configuration.LifecycleStreamsPerService)
		for serviceIndex := 0; serviceIndex < configuration.LifecycleServices; serviceIndex++ {
			scenarioStarted := perfclock.Now()
			directory := filepath.Join(configuration.LifecycleAuthorityDir, fmt.Sprintf("%02d", serviceIndex))
			nameRaw, err := mustRead(filepath.Join(directory, "name.txt"))
			if err != nil {
				return result{}, err
			}
			serviceName := string(bytes.TrimSpace(nameRaw))
			routeRequest, channelID, routeID := lifecycleIDs(serviceIndex)
			firstStreamOrdinal := serviceIndex * configuration.LifecycleStreamsPerService
			streamRequest := benchmarkStreamRequest(uint64(firstStreamOrdinal))
			machine := state.NewSource(sessionID, helloRequest, routeRequest, streamRequest, channelID, routeID, serviceName, "tcp", 8443)
			if err := machine.HelloSent(); err != nil {
				return result{}, err
			}
			if err := machine.EdgeHelloAccepted(edge.SessionID, edge.RequestID); err != nil {
				return result{}, err
			}
			bodyWire, err := mustRead(filepath.Join(directory, "route-open-body.cbor"))
			if err != nil {
				return result{}, err
			}
			decoded, err := cbor.DecodeExact(bodyWire, cbor.DefaultLimits())
			if err != nil {
				return result{}, err
			}
			routeBody := decoded.(map[uint64]any)
			exactGrant := routeBody[2].([]byte)
			grant, err := authority.VerifyRouteGrant(exactGrant, issuerPublic, []byte("nbsr-test-route-grant-key"), 1_893_456_000)
			if err != nil {
				return result{}, err
			}
			federationContext, err := mustRead(filepath.Join(directory, "federation-context.cbor"))
			if err != nil {
				return result{}, err
			}
			sourceAttestation, err := mustRead(filepath.Join(directory, "source.cose"))
			if err != nil {
				return result{}, err
			}
			sourceAdmissionStarted := perfclock.Now()
			if err := authority.VerifySourceAdmission(sourceAttestation, ed25519.PublicKey(sourceAuthority), []byte("local-source"), authority.SourceAdmissionBinding{
				SourceOperatorID: repeated32('S'), DestinationOperatorID: repeated32('D'), CanonicalName: serviceName, Transport: "tcp", Port: 8443,
				RouteGrantDigest: grant.Digest, FederationContextDigest: sha256.Sum256(federationContext), OpenedAt: 1_893_456_000,
			}); err != nil {
				return result{}, fmt.Errorf("source federation admission: %w", err)
			}
			transcript, err := authority.BuildF75Transcript(sessionID, routeRequest, "destination.edge", routeBody, grant)
			if err != nil || !ed25519.Verify(sessionPublic, transcript, routeBody[7].([]byte)) {
				return result{}, errors.New("invalid F75 proof signature")
			}
			sourceAdmissionNS := perfclock.Since(sourceAdmissionStarted)
			if err := machine.RouteSent(grant.ServiceID, grant.AllowedTransport, uint16(routeBody[5].(uint64))); err != nil {
				return result{}, err
			}
			routeStarted := perfclock.Now()
			routeSequence := 2 + serviceIndex*(1+configuration.LifecycleStreamsPerService)
			if err := peer.SendEnvelope(core.Envelope{ProtocolVersion: 2, MessageType: core.RouteOpen, RequestID: routeRequest, SessionID: sessionID, Sequence: uint64(routeSequence), Body: routeBody}); err != nil {
				return result{}, err
			}
			routeAccepted, err := peer.ReceiveEnvelope()
			if err != nil {
				return result{}, err
			}
			routeNS := perfclock.Since(routeStarted)
			if err := machine.RouteAccepted(routeAccepted.SessionID, routeAccepted.RequestID, bytes16(routeAccepted.Body[1]), bytes16(routeAccepted.Body[2])); err != nil {
				return result{}, err
			}
			bindingStarted := perfclock.Now()
			exporterContext, err := cbor.Encode([]any{"NBSR-SERVICE-CHANNEL-CONTEXT-v2", uint64(2), sessionID[:], "source.edge", "destination.edge", channelID[:], routeID[:], grant.Digest[:], grant.ServiceID, "tcp", uint64(8443), grant.PolicyHash[:], clientNonce[:], edgeNonce[:]})
			if err != nil {
				return result{}, err
			}
			if exporter, err := peer.ExportKeyingMaterial(exporterContext); err != nil || len(exporter) != 32 {
				return result{}, errors.New("live WP4 exporter failed")
			}
			bindingNS := perfclock.Since(bindingStarted)
			if configuration.LifecycleConcurrent {
				for localStream := 0; localStream < configuration.LifecycleStreamsPerService; localStream++ {
					streamOrdinal := firstStreamOrdinal + localStream
					streamRequest = benchmarkStreamRequest(uint64(streamOrdinal))
					if localStream > 0 {
						if err := machine.NextStream(streamRequest); err != nil {
							return result{}, err
						}
					}
					application, err := peer.OpenApplication(ctx)
					if err != nil {
						return result{}, err
					}
					streamID := uint64(4 + 4*streamOrdinal)
					if uint64(application.StreamID()) != streamID {
						return result{}, errors.New("application stream ID mismatch")
					}
					streamBody := map[uint64]any{0: uint64(1), 1: streamID, 2: channelID[:], 3: routeID[:], 4: grant.Digest[:], 5: "tcp", 6: uint64(8443)}
					if err := machine.StreamSent(streamID); err != nil {
						return result{}, err
					}
					streamStarted := perfclock.Now()
					if err := peer.SendEnvelope(core.Envelope{ProtocolVersion: 2, MessageType: core.StreamOpen, RequestID: streamRequest, SessionID: sessionID, Sequence: uint64(routeSequence + 1 + localStream), Body: streamBody}); err != nil {
						return result{}, err
					}
					streamAccepted, err := peer.ReceiveEnvelope()
					if err != nil {
						return result{}, err
					}
					streamNS := perfclock.Since(streamStarted)
					if err := machine.StreamAccepted(streamAccepted.SessionID, streamAccepted.RequestID, streamAccepted.Body[1].(uint64), bytes16(streamAccepted.Body[2]), bytes16(streamAccepted.Body[3])); err != nil || !machine.PayloadAllowed() {
						return result{}, errors.New("stream payload gate remained closed")
					}
					concurrentMetrics = append(concurrentMetrics, concurrentMetric{serviceIndex, localStream, streamOrdinal, scenarioStarted, sourceAdmissionNS, routeNS, bindingNS, streamNS})
					go func(ordinal int) {
						<-concurrentStart
						started := perfclock.Now()
						if _, err := application.Write([]byte(configuration.SafePayload)); err != nil {
							concurrentResults <- concurrentResult{ordinal: ordinal, error: err}
							return
						}
						if err := application.Close(); err != nil {
							concurrentResults <- concurrentResult{ordinal: ordinal, error: err}
							return
						}
						echo := make([]byte, len(configuration.SafePayload))
						if _, err := io.ReadFull(application, echo); err != nil || string(echo) != configuration.SafePayload {
							concurrentResults <- concurrentResult{ordinal: ordinal, error: errors.New("concurrent application echo failed")}
							return
						}
						concurrentResults <- concurrentResult{ordinal: ordinal, requestNS: int(perfclock.Since(started))}
					}(streamOrdinal)
				}
				continue
			}
			for localStream := 0; localStream < configuration.LifecycleStreamsPerService; localStream++ {
				streamOrdinal := firstStreamOrdinal + localStream
				streamRequest = benchmarkStreamRequest(uint64(streamOrdinal))
				if localStream > 0 {
					if err := machine.NextStream(streamRequest); err != nil {
						return result{}, err
					}
				}
				application, err := peer.OpenApplication(ctx)
				if err != nil {
					return result{}, err
				}
				streamID := uint64(4 + 4*streamOrdinal)
				if uint64(application.StreamID()) != streamID {
					return result{}, errors.New("application stream ID mismatch")
				}
				streamBody := map[uint64]any{0: uint64(1), 1: streamID, 2: channelID[:], 3: routeID[:], 4: grant.Digest[:], 5: "tcp", 6: uint64(8443)}
				if err := machine.StreamSent(streamID); err != nil {
					return result{}, err
				}
				streamStarted := perfclock.Now()
				if err := peer.SendEnvelope(core.Envelope{ProtocolVersion: 2, MessageType: core.StreamOpen, RequestID: streamRequest, SessionID: sessionID, Sequence: uint64(routeSequence + 1 + localStream), Body: streamBody}); err != nil {
					return result{}, err
				}
				streamAccepted, err := peer.ReceiveEnvelope()
				if err != nil {
					return result{}, err
				}
				streamNS := perfclock.Since(streamStarted)
				if err := machine.StreamAccepted(streamAccepted.SessionID, streamAccepted.RequestID, streamAccepted.Body[1].(uint64), bytes16(streamAccepted.Body[2]), bytes16(streamAccepted.Body[3])); err != nil || !machine.PayloadAllowed() {
					return result{}, errors.New("stream payload gate remained closed")
				}
				requestStarted := perfclock.Now()
				if _, err := application.Write([]byte(configuration.SafePayload)); err != nil {
					return result{}, err
				}
				if err := application.Close(); err != nil {
					return result{}, err
				}
				echo := make([]byte, len(configuration.SafePayload))
				if _, err := io.ReadFull(application, echo); err != nil {
					return result{}, err
				}
				requestNS := perfclock.Since(requestStarted)
				if string(echo) != configuration.SafePayload {
					return result{}, errors.New("application payload echo mismatch")
				}
				totalNS := perfclock.Since(scenarioStarted)
				if serviceIndex == 0 && localStream == 0 {
					totalNS = perfclock.Since(coldStarted)
				}
				entry := sample{SampleID: len(observed), Success: true, StreamOpenRTTNS: streamNS, TTFABNS: totalNS, RequestLatencyNS: requestNS, TotalScenarioNS: totalNS, BytesTransmitted: len(echo), BytesReceived: len(echo)}
				if localStream == 0 {
					entry.SourceAdmissionNS, entry.RouteOpenRTTNS, entry.ChannelBindingNS = measured(sourceAdmissionNS), measured(routeNS), measured(bindingNS)
				}
				if serviceIndex == 0 && localStream == 0 {
					entry.TransportHandshakeNS, entry.HelloRTTNS = measured(handshakeNS), measured(helloNS)
				}
				observed = append(observed, entry)
			}
		}
		if configuration.LifecycleConcurrent {
			close(concurrentStart)
			requestLatencies := make([]int64, configuration.LifecycleServices*configuration.LifecycleStreamsPerService)
			for range concurrentMetrics {
				completed := <-concurrentResults
				if completed.error != nil {
					return result{}, completed.error
				}
				requestLatencies[completed.ordinal] = int64(completed.requestNS)
			}
			for _, metric := range concurrentMetrics {
				totalNS := perfclock.Since(metric.scenarioStarted)
				if metric.service == 0 && metric.localStream == 0 {
					totalNS = perfclock.Since(coldStarted)
				}
				entry := sample{SampleID: len(observed), Success: true, StreamOpenRTTNS: metric.streamNS, TTFABNS: totalNS, RequestLatencyNS: requestLatencies[metric.ordinal], TotalScenarioNS: totalNS, BytesTransmitted: len(configuration.SafePayload), BytesReceived: len(configuration.SafePayload)}
				if metric.localStream == 0 {
					entry.SourceAdmissionNS, entry.RouteOpenRTTNS, entry.ChannelBindingNS = measured(metric.sourceAdmissionNS), measured(metric.routeNS), measured(metric.bindingNS)
				}
				if metric.service == 0 && metric.localStream == 0 {
					entry.TransportHandshakeNS, entry.HelloRTTNS = measured(handshakeNS), measured(helloNS)
				}
				observed = append(observed, entry)
			}
		}
		if err := os.WriteFile(filepath.Join(configuration.LifecycleAuthorityDir, fmt.Sprintf("connection-%d.ack", configuration.LifecycleConnectionOffset+connectionOrdinal)), []byte("complete\n"), 0o600); err != nil {
			return result{}, err
		}
		if err := peer.Close(); err != nil {
			return result{}, err
		}
	}
	return result{Status: "PASS", Messages: []string{"CLIENT_HELLO", "EDGE_HELLO", "ROUTE_OPEN", "ROUTE_ACCEPT", "STREAM_OPEN", "STREAM_ACCEPT"}, CoreVersion: 2, RouteOpenBodyVersion: 2, FederationProfile: "nbsr-federation-dev-v1", BenchmarkSamples: len(observed), Samples: observed}, nil
}

func sequence32(start byte) [32]byte {
	var value [32]byte
	for index := range value {
		value[index] = start + byte(index)
	}
	return value
}
func sha256Bytes(value []byte) []byte { digest := sha256.Sum256(value); return digest[:] }
func bytes16(value any) [16]byte      { var output [16]byte; copy(output[:], value.([]byte)); return output }

func main() {
	if len(os.Args) != 3 || os.Args[1] != "--config" {
		fmt.Fprintln(os.Stderr, "usage: nbsr-go-peer --config PATH")
		os.Exit(64)
	}
	configuration, err := loadConfig(os.Args[2])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(65)
	}
	processDeadline := 15 * time.Second
	if configuration.BenchmarkSamples > 0 {
		processDeadline = 2 * time.Hour
	}
	ctx, cancel := context.WithTimeout(context.Background(), processDeadline)
	defer cancel()
	var observed result
	if configuration.LifecycleAuthorityDir != "" {
		observed, err = runLifecycle(ctx, configuration)
	} else {
		observed, err = run(ctx, configuration)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if err := json.NewEncoder(os.Stdout).Encode(observed); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
