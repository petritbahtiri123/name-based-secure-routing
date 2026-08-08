// Package authority independently verifies the frozen RouteGrant COSE profile
// and constructs the exact F75 federated route-opening transcript.
package authority

import (
	"bytes"
	"crypto/ed25519"
	"crypto/sha256"
	"errors"

	"nbsr.local/interop/nbsr-go-peer/internal/cbor"
)

type VerifiedRouteGrant struct {
	RouteID                    [16]byte
	ServiceID                  string
	DestinationEdges           []string
	AllowedTransport           string
	AllowedPorts               []uint64
	ClientSessionKeyThumbprint [32]byte
	PolicyHash                 [32]byte
	NotBefore                  uint64
	ExpiresAt                  uint64
	Digest                     [32]byte
}

type SourceAdmissionBinding struct {
	SourceOperatorID        [32]byte
	DestinationOperatorID   [32]byte
	CanonicalName           string
	Transport               string
	Port                    uint64
	RouteGrantDigest        [32]byte
	FederationContextDigest [32]byte
	OpenedAt                uint64
}

func VerifySourceAdmission(exactCOSE []byte, authority ed25519.PublicKey, expectedKID []byte, expected SourceAdmissionBinding) error {
	payload, err := verifySign1(exactCOSE, authority, expectedKID)
	if err != nil {
		return err
	}
	decoded, err := cbor.DecodeExact(payload, cbor.DefaultLimits())
	if err != nil {
		return err
	}
	fields, ok := decoded.(map[uint64]any)
	if !ok || !keysZeroThrough(fields, 14) || fields[0] != uint64(1) || fields[1] != "nbsr-federation-source-admission" {
		return errors.New("invalid source admission profile or purpose")
	}
	source, sourceOK := fixedArray32(fields[2])
	destination, destinationOK := fixedArray32(fields[3])
	service, serviceOK := fixedArray32(fields[4])
	name, nameOK := fields[5].(string)
	protocol, protocolOK := fields[6].(uint64)
	port, portOK := fields[7].(uint64)
	routeDigest, routeOK := fixedArray32(fields[8])
	contextDigest, contextOK := fixedArray32(fields[9])
	effectiveAt, effectiveOK := fields[10].(uint64)
	validUntil, validOK := fields[11].(uint64)
	generation, generationOK := fields[12].(uint64)
	sequence, sequenceOK := fields[13].(uint64)
	dependencies, dependenciesOK := fields[14].([]any)
	if !sourceOK || !destinationOK || !serviceOK || !nameOK || !protocolOK || !portOK || !routeOK || !contextOK || !effectiveOK || !validOK || !generationOK || !sequenceOK || !dependenciesOK {
		return errors.New("malformed source admission binding")
	}
	if source != expected.SourceOperatorID || destination != expected.DestinationOperatorID || source == destination || name != expected.CanonicalName || protocol != 6 || expected.Transport != "tcp" || port != expected.Port || routeDigest != expected.RouteGrantDigest || contextDigest != expected.FederationContextDigest || expected.OpenedAt < effectiveAt || expected.OpenedAt > validUntil || effectiveAt >= validUntil || generation == 0 || sequence == 0 || service != deriveServiceID(source, name) {
		return errors.New("source admission authority mismatch")
	}
	if len(dependencies) == 0 || len(dependencies) > 256 {
		return errors.New("invalid source admission dependencies")
	}
	var previous [32]byte
	for index, item := range dependencies {
		dependency, ok := fixedArray32(item)
		if !ok || (index > 0 && bytes.Compare(previous[:], dependency[:]) >= 0) {
			return errors.New("invalid source admission dependency order")
		}
		previous = dependency
	}
	return nil
}

func verifySign1(exactCOSE []byte, authority ed25519.PublicKey, expectedKID []byte) ([]byte, error) {
	if len(exactCOSE) < 2 || exactCOSE[0] != 0xd2 {
		return nil, errors.New("attestation must be COSE_Sign1 tag 18")
	}
	decoded, err := cbor.DecodeExact(exactCOSE[1:], cbor.DefaultLimits())
	if err != nil {
		return nil, err
	}
	items, ok := decoded.([]any)
	if !ok || len(items) != 4 {
		return nil, errors.New("invalid COSE_Sign1 array")
	}
	protected, protectedOK := items[0].([]byte)
	unprotected, unprotectedOK := items[1].(map[uint64]any)
	payload, payloadOK := items[2].([]byte)
	signature, signatureOK := items[3].([]byte)
	if !protectedOK || !unprotectedOK || len(unprotected) != 0 || !payloadOK || !signatureOK || len(signature) != ed25519.SignatureSize {
		return nil, errors.New("invalid COSE_Sign1 structure")
	}
	headersValue, err := cbor.DecodeExact(protected, cbor.DefaultLimits())
	if err != nil {
		return nil, err
	}
	headers, ok := headersValue.(map[uint64]any)
	if !ok || len(headers) != 2 || headers[1] != int64(-8) || !bytes.Equal(byteValue(headers[4]), expectedKID) {
		return nil, errors.New("unsupported attestation authority")
	}
	sigStructure, err := cbor.Encode([]any{"Signature1", protected, []byte{}, payload})
	if err != nil {
		return nil, err
	}
	if len(authority) != ed25519.PublicKeySize || !ed25519.Verify(authority, sigStructure, signature) {
		return nil, errors.New("invalid attestation signature")
	}
	return payload, nil
}

func deriveServiceID(operator [32]byte, name string) [32]byte {
	digest := sha256.New()
	digest.Write([]byte("NBSR-FEDERATION-SERVICE-ID-v1\x00"))
	digest.Write(operator[:])
	digest.Write([]byte{byte(len(name) >> 8), byte(len(name))})
	digest.Write([]byte(name))
	var result [32]byte
	copy(result[:], digest.Sum(nil))
	return result
}

func VerifyRouteGrant(exactCOSE []byte, issuer ed25519.PublicKey, expectedKID []byte, openedAt uint64) (VerifiedRouteGrant, error) {
	if len(exactCOSE) < 2 || exactCOSE[0] != 0xd2 {
		return VerifiedRouteGrant{}, errors.New("RouteGrant must be COSE_Sign1 tag 18")
	}
	decoded, err := cbor.DecodeExact(exactCOSE[1:], cbor.DefaultLimits())
	if err != nil {
		return VerifiedRouteGrant{}, err
	}
	items, ok := decoded.([]any)
	if !ok || len(items) != 4 {
		return VerifiedRouteGrant{}, errors.New("invalid COSE_Sign1 array")
	}
	protected, ok := items[0].([]byte)
	if !ok {
		return VerifiedRouteGrant{}, errors.New("invalid protected headers")
	}
	unprotected, ok := items[1].(map[uint64]any)
	if !ok || len(unprotected) != 0 {
		return VerifiedRouteGrant{}, errors.New("unprotected headers forbidden")
	}
	payload, ok := items[2].([]byte)
	if !ok {
		return VerifiedRouteGrant{}, errors.New("detached payload forbidden")
	}
	signature, ok := items[3].([]byte)
	if !ok || len(signature) != ed25519.SignatureSize {
		return VerifiedRouteGrant{}, errors.New("invalid COSE signature")
	}
	headersValue, err := cbor.DecodeExact(protected, cbor.DefaultLimits())
	if err != nil {
		return VerifiedRouteGrant{}, err
	}
	headers, ok := headersValue.(map[uint64]any)
	if !ok || len(headers) != 2 || headers[1] != int64(-8) || !bytes.Equal(byteValue(headers[4]), expectedKID) {
		return VerifiedRouteGrant{}, errors.New("unsupported COSE authority")
	}
	sigStructure, err := cbor.Encode([]any{"Signature1", protected, []byte{}, payload})
	if err != nil {
		return VerifiedRouteGrant{}, err
	}
	if len(issuer) != ed25519.PublicKeySize || !ed25519.Verify(issuer, sigStructure, signature) {
		return VerifiedRouteGrant{}, errors.New("invalid RouteGrant signature")
	}
	value, err := cbor.DecodeExact(payload, cbor.DefaultLimits())
	if err != nil {
		return VerifiedRouteGrant{}, err
	}
	grant, ok := value.(map[uint64]any)
	if !ok || !keysZeroThrough(grant, 16) || grant[0] != uint64(1) {
		return VerifiedRouteGrant{}, errors.New("invalid RouteGrant payload")
	}
	routeID, ok := fixedArray16(grant[1])
	if !ok {
		return VerifiedRouteGrant{}, errors.New("invalid route ID")
	}
	service, ok := grant[3].(string)
	if !ok || service == "" || len(service) > 64 || !ascii(service) {
		return VerifiedRouteGrant{}, errors.New("invalid service ID")
	}
	destinations, ok := stringArray(grant[7], 1, 16)
	if !ok {
		return VerifiedRouteGrant{}, errors.New("invalid destination set")
	}
	transports, ok := stringArray(grant[8], 1, 1)
	if !ok || transports[0] != "tcp" {
		return VerifiedRouteGrant{}, errors.New("invalid allowed transport")
	}
	ports, ok := uintArray(grant[9], 1, 32)
	if !ok {
		return VerifiedRouteGrant{}, errors.New("invalid allowed ports")
	}
	thumbprint, ok := fixedArray32(grant[10])
	if !ok {
		return VerifiedRouteGrant{}, errors.New("invalid session key thumbprint")
	}
	notBefore, ok1 := grant[11].(uint64)
	expiresAt, ok2 := grant[12].(uint64)
	if !ok1 || !ok2 || expiresAt <= notBefore || expiresAt-notBefore > 600 || openedAt < notBefore || openedAt > expiresAt {
		return VerifiedRouteGrant{}, errors.New("RouteGrant outside validity interval")
	}
	if _, ok := fixedArray16(grant[13]); !ok {
		return VerifiedRouteGrant{}, errors.New("invalid lease ID")
	}
	if sequence, ok := grant[14].(uint64); !ok || sequence == 0 {
		return VerifiedRouteGrant{}, errors.New("invalid record sequence")
	}
	policyHash, ok := fixedArray32(grant[15])
	if !ok {
		return VerifiedRouteGrant{}, errors.New("invalid policy hash")
	}
	if _, ok := fixedArray16(grant[16]); !ok {
		return VerifiedRouteGrant{}, errors.New("invalid unique nonce")
	}
	return VerifiedRouteGrant{RouteID: routeID, ServiceID: service, DestinationEdges: destinations, AllowedTransport: transports[0], AllowedPorts: ports, ClientSessionKeyThumbprint: thumbprint, PolicyHash: policyHash, NotBefore: notBefore, ExpiresAt: expiresAt, Digest: sha256.Sum256(exactCOSE)}, nil
}

func BuildF75Transcript(sessionID, requestID [16]byte, destinationEdge string, body map[uint64]any, grant VerifiedRouteGrant) ([]byte, error) {
	if body[0] != uint64(2) {
		return nil, errors.New("F75 requires ROUTE_OPEN v2")
	}
	channel, ok := fixedArray16(body[1])
	if !ok {
		return nil, errors.New("invalid channel ID")
	}
	exactGrant, ok := body[2].([]byte)
	if !ok || sha256.Sum256(exactGrant) != grant.Digest {
		return nil, errors.New("RouteGrant digest mismatch")
	}
	edgeNonce, ok := fixedArray32(body[3])
	if !ok {
		return nil, errors.New("invalid edge nonce")
	}
	transport, ok := body[4].(string)
	if !ok || transport != grant.AllowedTransport {
		return nil, errors.New("transport mismatch")
	}
	port, ok := body[5].(uint64)
	if !ok || !containsUint(grant.AllowedPorts, port) {
		return nil, errors.New("port mismatch")
	}
	openedAt, ok := body[6].(uint64)
	if !ok || openedAt < grant.NotBefore || openedAt > grant.ExpiresAt {
		return nil, errors.New("route time mismatch")
	}
	binding, ok := body[8].(map[uint64]any)
	if !ok || len(binding) != 6 || binding[0] != uint64(1) || binding[1] != uint64(1) || binding[2] != uint64(1) || binding[3] != "nbsr-federation-dev-v1" {
		return nil, errors.New("unsupported federation binding")
	}
	routeDigest, ok := fixedArray32(binding[4])
	if !ok || routeDigest != grant.Digest {
		return nil, errors.New("binding RouteGrant digest mismatch")
	}
	contextDigest, ok := fixedArray32(binding[5])
	if !ok {
		return nil, errors.New("invalid federation context digest")
	}
	if !containsString(grant.DestinationEdges, destinationEdge) {
		return nil, errors.New("destination mismatch")
	}
	return cbor.Encode([]any{
		"NBSR-FED-ROUTE-OPEN", uint64(2), uint64(2),
		[]any{uint64(1), uint64(1), uint64(1), "nbsr-federation-dev-v1"},
		sessionID[:], requestID[:], channel[:], grant.RouteID[:], destinationEdge,
		edgeNonce[:], transport, grant.ServiceID, port, routeDigest[:], openedAt, contextDigest[:],
	})
}

func byteValue(value any) []byte { raw, _ := value.([]byte); return raw }
func keysZeroThrough(items map[uint64]any, last uint64) bool {
	if len(items) != int(last+1) {
		return false
	}
	for key := uint64(0); key <= last; key++ {
		if _, ok := items[key]; !ok {
			return false
		}
	}
	return true
}
func fixedArray16(value any) ([16]byte, bool) {
	var result [16]byte
	raw, ok := value.([]byte)
	if !ok || len(raw) != 16 {
		return result, false
	}
	copy(result[:], raw)
	return result, true
}
func fixedArray32(value any) ([32]byte, bool) {
	var result [32]byte
	raw, ok := value.([]byte)
	if !ok || len(raw) != 32 {
		return result, false
	}
	copy(result[:], raw)
	return result, true
}
func ascii(value string) bool {
	for _, item := range []byte(value) {
		if item > 0x7f {
			return false
		}
	}
	return true
}
func containsString(items []string, wanted string) bool {
	for _, item := range items {
		if item == wanted {
			return true
		}
	}
	return false
}
func containsUint(items []uint64, wanted uint64) bool {
	for _, item := range items {
		if item == wanted {
			return true
		}
	}
	return false
}
func stringArray(value any, minimum, maximum int) ([]string, bool) {
	raw, ok := value.([]any)
	if !ok || len(raw) < minimum || len(raw) > maximum {
		return nil, false
	}
	result := make([]string, len(raw))
	for i, item := range raw {
		text, ok := item.(string)
		if !ok || !ascii(text) || text == "" || (i > 0 && text <= result[i-1]) {
			return nil, false
		}
		result[i] = text
	}
	return result, true
}
func uintArray(value any, minimum, maximum int) ([]uint64, bool) {
	raw, ok := value.([]any)
	if !ok || len(raw) < minimum || len(raw) > maximum {
		return nil, false
	}
	result := make([]uint64, len(raw))
	for i, item := range raw {
		number, ok := item.(uint64)
		if !ok || number < 1 || number > 65535 || (i > 0 && number <= result[i-1]) {
			return nil, false
		}
		result[i] = number
	}
	return result, true
}
