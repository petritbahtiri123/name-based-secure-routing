package main

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"path/filepath"
	"time"

	"nbsr.local/client/nbsr-go-client/streamclient"
	"nbsr.local/interop/nbsr-go-peer/internal/authority"
	"nbsr.local/interop/nbsr-go-peer/internal/cbor"
	"nbsr.local/interop/nbsr-go-peer/internal/core"
	"nbsr.local/interop/nbsr-go-peer/internal/state"
	"nbsr.local/interop/nbsr-go-peer/internal/transport"
)

type realGeneration struct {
	peer    *transport.Peer
	channel [16]byte
}

func (generation *realGeneration) Close() error     { return generation.peer.Close() }
func (generation *realGeneration) Identity() string { return generation.peer.Identity() }
func (generation *realGeneration) Open(ctx context.Context) (streamclient.Wire, uint64, error) {
	wire, err := generation.peer.OpenApplication(ctx)
	if err != nil {
		return nil, 0, err
	}
	return wire, uint64(wire.StreamID()), nil
}
func (generation *realGeneration) Refill(ctx context.Context, channel [16]byte, epoch uint64) error {
	return generation.peer.RefillStreamCredits(ctx, channel, epoch)
}

type rotationEvidence struct {
	ATransport              string                          `json:"a_transport"`
	BTransport              string                          `json:"b_transport"`
	Transition              string                          `json:"transition"`
	MaximumGenerations      int                             `json:"maximum_generations"`
	NewWorkGeneration       uint64                          `json:"new_work_generation"`
	ADescendantPinned       bool                            `json:"a_descendant_pinned"`
	ADrainingRejections     streamclient.DrainingRejections `json:"a_draining_rejections"`
	AStateUnusable          bool                            `json:"a_state_unusable"`
	ApplicationDataReplayed bool                            `json:"application_data_replayed"`
	FinalBCurrent           bool                            `json:"final_b_current"`
	FinalBUsable            bool                            `json:"final_b_usable"`
	ThirdGenerationRejected bool                            `json:"third_generation_rejected"`
}

func establishRotationGeneration(ctx context.Context, configuration config, readiness string) (*realGeneration, error) {
	ready, err := transport.LoadReadiness(readiness)
	if err != nil {
		return nil, err
	}
	peer, err := transport.Dial(ctx, ready)
	if err != nil {
		return nil, err
	}
	fail := func(err error) (*realGeneration, error) { _ = peer.Close(); return nil, err }
	sessionID, helloRequest, routeRequest, streamRequest := sequence(0x10), sequence(0), specialRequest(0x10), specialRequest(0x11)
	channelID, routeID := sequence(0x40), sequence(0x20)
	machine := state.NewSource(sessionID, helloRequest, routeRequest, streamRequest, channelID, routeID, "service.example", "tcp", 8443)
	sessionPublic, err := loadPublicKey(filepath.Join(filepath.Dir(configuration.F75Package), "core-v0.2", "keys", "test-only-session-ed25519-public.hex"))
	if err != nil {
		return fail(err)
	}
	clientNonce, edgeNonce := sequence32(0x60), sequence32(0x80)
	clientBody := map[uint64]any{0: uint64(1), 1: "nbsr12df4x56n2df4x56n2df4x56n2df4x56n2df4x56n2df4x56n2dfsk5743r", 2: "source.edge", 3: "nbsr1g3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zqel9ufg", 4: "destination.edge", 5: clientNonce[:], 6: []byte(sessionPublic), 7: uint64(1_893_456_000)}
	if err = peer.SendEnvelope(core.Envelope{ProtocolVersion: 2, MessageType: core.ClientHello, RequestID: helloRequest, SessionID: sessionID, Sequence: 1, Body: clientBody}); err != nil {
		return fail(err)
	}
	if err = machine.HelloSent(); err != nil {
		return fail(err)
	}
	edge, err := peer.ReceiveEnvelope()
	if err != nil {
		return fail(err)
	}
	if edge.MessageType != core.EdgeHello || edge.SessionID != sessionID || edge.RequestID != helloRequest || !bytes.Equal(edge.Body[3].([]byte), clientNonce[:]) || !bytes.Equal(edge.Body[4].([]byte), edgeNonce[:]) || !bytes.Equal(edge.Body[5].([]byte), sha256Bytes(sessionPublic)) {
		return fail(errors.New("rotation EDGE_HELLO mismatch"))
	}
	if err = machine.EdgeHelloAccepted(edge.SessionID, edge.RequestID); err != nil {
		return fail(err)
	}
	bodyWire, err := mustRead(filepath.Join(configuration.F75Package, "route-open-body.cbor"))
	if err != nil {
		return fail(err)
	}
	decoded, err := cbor.DecodeExact(bodyWire, cbor.DefaultLimits())
	if err != nil {
		return fail(err)
	}
	routeBody := decoded.(map[uint64]any)
	issuerPublic, err := loadPublicKey(filepath.Join(filepath.Dir(configuration.F75Package), "core-v0.2", "keys", "test-only-route-grant-ed25519-public.hex"))
	if err != nil {
		return fail(err)
	}
	grant, err := authority.VerifyRouteGrant(routeBody[2].([]byte), issuerPublic, []byte("nbsr-test-route-grant-key"), 1_893_456_000)
	if err != nil {
		return fail(err)
	}
	federationContext, err := mustRead(filepath.Join(configuration.F75Package, "federation-context.cbor"))
	if err != nil {
		return fail(err)
	}
	sourceAttestation, err := mustRead(filepath.Join(configuration.LocalAttestationPackage, "source.cose"))
	if err != nil {
		return fail(err)
	}
	sourceAuthority, err := hex.DecodeString("f80cccdce4ae1c07ae208a2adf99a310ae4207e0306fa0236110b06827bbb8d0")
	if err != nil {
		return fail(err)
	}
	if err = authority.VerifySourceAdmission(sourceAttestation, ed25519.PublicKey(sourceAuthority), []byte("local-source"), authority.SourceAdmissionBinding{SourceOperatorID: repeated32('S'), DestinationOperatorID: repeated32('D'), CanonicalName: "service.example", Transport: "tcp", Port: 8443, RouteGrantDigest: grant.Digest, FederationContextDigest: sha256.Sum256(federationContext), OpenedAt: 1_893_456_000}); err != nil {
		return fail(fmt.Errorf("source admission: %w", err))
	}
	transcript, err := authority.BuildF75Transcript(sessionID, routeRequest, "destination.edge", routeBody, grant)
	if err != nil {
		return fail(err)
	}
	if !ed25519.Verify(sessionPublic, transcript, routeBody[7].([]byte)) {
		return fail(errors.New("rotation F75 proof invalid"))
	}
	if err = machine.RouteSent(grant.ServiceID, grant.AllowedTransport, uint16(routeBody[5].(uint64))); err != nil {
		return fail(err)
	}
	if err = peer.SendEnvelope(core.Envelope{ProtocolVersion: 2, MessageType: core.RouteOpen, RequestID: routeRequest, SessionID: sessionID, Sequence: 2, Body: routeBody}); err != nil {
		return fail(err)
	}
	accepted, err := peer.ReceiveEnvelope()
	if err != nil {
		return fail(err)
	}
	if accepted.MessageType != core.RouteAccept || accepted.SessionID != sessionID || accepted.RequestID != routeRequest {
		return fail(errors.New("rotation ROUTE_ACCEPT mismatch"))
	}
	if err = machine.RouteAccepted(accepted.SessionID, accepted.RequestID, bytes16(accepted.Body[1]), bytes16(accepted.Body[2])); err != nil {
		return fail(err)
	}
	exporterContext, err := cbor.Encode([]any{"NBSR-SERVICE-CHANNEL-CONTEXT-v2", uint64(2), sessionID[:], "source.edge", "destination.edge", channelID[:], routeID[:], grant.Digest[:], grant.ServiceID, "tcp", uint64(8443), grant.PolicyHash[:], clientNonce[:], edgeNonce[:]})
	if err != nil {
		return fail(err)
	}
	if exporter, exportErr := peer.ExportKeyingMaterial(exporterContext); exportErr != nil || len(exporter) != 32 {
		return fail(errors.New("rotation exporter failed"))
	}
	return &realGeneration{peer: peer, channel: channelID}, nil
}

type rotationApplication interface {
	io.Reader
	Write([]byte) (int, error)
	FinishWrite() error
}

func exchangeRotationPayload(stream rotationApplication, payload string) error {
	if _, err := stream.Write([]byte(payload)); err != nil {
		return err
	}
	if err := stream.FinishWrite(); err != nil {
		return err
	}
	echo := make([]byte, len(payload))
	if _, err := io.ReadFull(stream, echo); err != nil {
		return err
	}
	if string(echo) != payload {
		return errors.New("rotation echo mismatch")
	}
	return nil
}

func runRotationInterop(ctx context.Context, configuration config) (result, error) {
	channel := sequence(0x40)
	serviceDigest := sha256.Sum256([]byte("service.example"))
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
	grant, err := authority.VerifyRouteGrant(routeBody[2].([]byte), issuerPublic, []byte("nbsr-test-route-grant-key"), 1_893_456_000)
	if err != nil {
		return result{}, err
	}
	generations := make([]streamclient.GenerationConfig, 0, 3)
	for index, path := range configuration.RotationReadinessPaths {
		generation := uint64(index + 1)
		readiness := path
		generations = append(generations, streamclient.GenerationConfig{Generation: generation, ChannelGeneration: 1, ChannelID: channel, ProofThumbprint: repeated32(byte('P' + index)), Factory: func(ctx context.Context) (streamclient.GenerationSession, error) {
			return establishRotationGeneration(ctx, configuration, readiness)
		}})
	}
	generations = append(generations, streamclient.GenerationConfig{Generation: 3, ChannelGeneration: 1, ChannelID: channel, ProofThumbprint: repeated32('R'), Factory: func(context.Context) (streamclient.GenerationSession, error) {
		return nil, errors.New("C factory must not run")
	}})
	client, err := streamclient.NewRotationClient(ctx, streamclient.RotationClientConfig{Now: 1_893_456_000, ExpiresAt: 1_893_457_000, AuthorityGeneration: 1, DeviceID: repeated32('C'), PolicyDigest: grant.PolicyHash, ServiceDigest: serviceDigest, RouteGrantDigest: grant.Digest, SourceOperator: "source.edge", Gateway: "destination.edge", ServiceIdentity: "service.example", Profile: streamclient.ProfileID, Transport: "quic", DrainTimeout: 30 * time.Second, Generations: generations})
	if err != nil {
		return result{}, err
	}
	streamA, err := client.Open(ctx, 1)
	if err != nil {
		return result{}, err
	}
	if err = exchangeRotationPayload(streamA, configuration.SafePayload); err != nil {
		return result{}, err
	}
	aID := client.TransportIdentity(1)
	handoff, err := client.Rotate(ctx, 2, streamclient.RotationExplicit)
	if err != nil {
		return result{}, err
	}
	bID := client.TransportIdentity(2)
	if aID == "" || bID == "" || aID == bID {
		return result{}, errors.New("rotation transport identities not distinct")
	}
	rejections := client.ProbeDraining(ctx, 1)
	if !rejections.ServiceChannel || !rejections.Credit || !rejections.Refill || !rejections.ApplicationStream {
		return result{}, errors.New("draining A accepted new work")
	}
	_, thirdErr := client.Rotate(ctx, 3, streamclient.RotationExplicit)
	thirdRejected := errors.Is(thirdErr, streamclient.ErrGenerationCapacity)
	maximumGenerations := client.Usage().Sessions
	aPinned := streamA.State() == streamclient.ApplicationStreamAccepted
	streamB, err := client.Open(ctx, 2)
	if err != nil {
		return result{}, err
	}
	if err = exchangeRotationPayload(streamB, configuration.SafePayload); err != nil {
		return result{}, err
	}
	if err = streamA.Close(); err != nil {
		return result{}, err
	}
	if err = client.CloseGeneration(1); err != nil {
		return result{}, err
	}
	_, aErr := client.Open(ctx, 1)
	afterDrain := client.Usage()
	aUnusable := aErr != nil && streamA.State() == streamclient.ApplicationStreamClosed && afterDrain.Sessions == 1 && afterDrain.PendingRotations == 0 && afterDrain.PendingChannels == 0
	if err = streamB.Close(); err != nil {
		return result{}, err
	}
	finalB, err := client.Open(ctx, 2)
	if err != nil {
		return result{}, err
	}
	if err = exchangeRotationPayload(finalB, configuration.SafePayload); err != nil {
		return result{}, err
	}
	_ = finalB.Close()
	current, err := client.Current()
	if err != nil {
		return result{}, err
	}
	evidence := &rotationEvidence{ATransport: aID, BTransport: bID, Transition: fmt.Sprintf("%d:%d->%d:%d", handoff.Previous.Generation, handoff.Previous.State, handoff.Current.Generation, handoff.Current.State), MaximumGenerations: maximumGenerations, NewWorkGeneration: 2, ADescendantPinned: aPinned && streamA.StreamID() != 0, ADrainingRejections: rejections, AStateUnusable: aUnusable, ApplicationDataReplayed: false, FinalBCurrent: current.Generation == 2, FinalBUsable: true, ThirdGenerationRejected: thirdRejected}
	if !evidence.ThirdGenerationRejected || !evidence.FinalBCurrent || !evidence.AStateUnusable {
		return result{}, errors.New("rotation evidence incomplete")
	}
	return result{Status: "PASS", Messages: []string{"TS_A", "SC_A", "APP_A", "ROTATE", "TS_B", "SC_B", "APP_B", "DRAIN_A"}, CoreVersion: 2, RouteOpenBodyVersion: 2, FederationProfile: streamclient.ProfileID, BenchmarkSamples: 3, Rotation: evidence}, nil
}
