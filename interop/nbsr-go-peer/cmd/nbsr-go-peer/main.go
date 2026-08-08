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
	"os"
	"path/filepath"
	"time"

	"nbsr.local/interop/nbsr-go-peer/internal/authority"
	"nbsr.local/interop/nbsr-go-peer/internal/cbor"
	"nbsr.local/interop/nbsr-go-peer/internal/core"
	"nbsr.local/interop/nbsr-go-peer/internal/state"
	"nbsr.local/interop/nbsr-go-peer/internal/transport"
)

type config struct {
	ReadinessPath           string `json:"readiness_path"`
	F75Package              string `json:"f75_package"`
	LocalAttestationPackage string `json:"local_attestation_package"`
	SafePayload             string `json:"safe_payload"`
	BenchmarkSamples        int    `json:"benchmark_samples,omitempty"`
}

type result struct {
	Status               string   `json:"status"`
	Messages             []string `json:"messages"`
	CoreVersion          uint64   `json:"core_version"`
	RouteOpenBodyVersion uint64   `json:"route_open_body_version"`
	FederationProfile    string   `json:"federation_profile"`
	PayloadSHA256        string   `json:"payload_sha256"`
	BenchmarkSamples     int      `json:"benchmark_samples,omitempty"`
	Samples              []sample `json:"samples,omitempty"`
}

type sample struct {
	SampleID         int   `json:"sample_id"`
	StreamOpenRTTNS  int64 `json:"stream_open_rtt_ns"`
	RequestLatencyNS int64 `json:"request_latency_ns"`
	TotalScenarioNS  int64 `json:"total_scenario_ns"`
	BytesTransmitted int   `json:"bytes_transmitted"`
	BytesReceived    int   `json:"bytes_received"`
}

func loadConfig(path string) (config, error) {
	file, err := os.Open(path)
	if err != nil {
		return config{}, err
	}
	defer file.Close()
	decoder := json.NewDecoder(io.LimitReader(file, 16*1024))
	decoder.DisallowUnknownFields()
	var value config
	if err := decoder.Decode(&value); err != nil {
		return config{}, err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return config{}, errors.New("configuration must contain one JSON object")
	}
	if value.ReadinessPath == "" || value.F75Package == "" || value.LocalAttestationPackage == "" || value.SafePayload == "" || len(value.SafePayload) > 4096 {
		return config{}, errors.New("configuration fields are missing or out of bounds")
	}
	if value.BenchmarkSamples < 0 || value.BenchmarkSamples > 100_000 {
		return config{}, errors.New("benchmark sample count is out of bounds")
	}
	return value, nil
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
	allowedMutations := map[string]bool{"": true, "unsupported_alpn": true, "wrong_peer_identity": true, "wrong_ca": true, "payload_before_admission": true, "malformed_cbor": true, "noncanonical_cbor": true, "over_limit_cbor": true, "wrong_core_version": true, "wrong_session": true, "wrong_request": true, "wrong_channel": true, "wrong_transport": true, "wrong_port": true, "wrong_route_grant_digest": true, "wrong_federation_context_digest": true, "wrong_proof_signature": true, "wrong_service": true, "expired_authority": true, "revoked_authority": true, "unsupported_federation_version": true, "unsupported_profile": true, "downgrade_v1": true, "transcript_substitution": true, "replay": true, "wrong_stream": true}
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
	if mutation != "" && mutation != "replay" {
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

	samples := configuration.BenchmarkSamples
	if samples == 0 {
		samples = 1
	}
	observedSamples := make([]sample, 0, samples)
	var echo []byte
	for index := 0; index < samples; index++ {
		totalStarted := time.Now()
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
		streamStarted := time.Now()
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
		streamNS := time.Since(streamStarted).Nanoseconds()
		if !machine.PayloadAllowed() {
			return result{}, errors.New("payload gate remained closed")
		}
		requestStarted := time.Now()
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
		requestNS := time.Since(requestStarted).Nanoseconds()
		if string(echo) != configuration.SafePayload {
			return result{}, errors.New("application payload echo mismatch")
		}
		observedSamples = append(observedSamples, sample{index, streamNS, requestNS, time.Since(totalStarted).Nanoseconds(), len(echo), len(echo)})
	}
	digest := sha256.Sum256(echo)
	return result{Status: "PASS", Messages: []string{"CLIENT_HELLO", "EDGE_HELLO", "ROUTE_OPEN", "ROUTE_ACCEPT", "STREAM_OPEN", "STREAM_ACCEPT"}, CoreVersion: 2, RouteOpenBodyVersion: 2, FederationProfile: "nbsr-federation-dev-v1", PayloadSHA256: hex.EncodeToString(digest[:]), BenchmarkSamples: samples, Samples: observedSamples}, nil
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
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	observed, err := run(ctx, configuration)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if err := json.NewEncoder(os.Stdout).Encode(observed); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
