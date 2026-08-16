package authority

import (
	"context"
	"crypto/sha256"
	"errors"
)

const (
	routeGrantIssuerPurpose  uint16 = 1
	maxRouteGrantLifetime           = uint64(600)
	maxStaticIssuers                = 64
	maxUnixTime                     = uint64(253_402_300_799)
	maxRouteGrantTargetEdges        = 16
)

// VerificationContext binds a provider candidate to the already validated
// local authority request and its current checkpoint.  No caller-controlled
// field is trusted until VerifyRouteGrant compares it to the signed payload.
type VerificationContext struct {
	Key        AuthorityKey
	Intent     RouteIntent
	Checkpoint VerifiedCheckpoint
	NowUnix    uint64
}

type StaticIssuerResolver struct{ records []IssuerRecord }

func NewStaticIssuerResolver(records []IssuerRecord) (*StaticIssuerResolver, error) {
	if len(records) == 0 || len(records) > maxStaticIssuers {
		return nil, ErrInvalidAuthority
	}
	copied := make([]IssuerRecord, len(records))
	for index, record := range records {
		if len(record.KID) < 1 || len(record.KID) > 64 || !validPublicKey(record.PublicKey) || record.Purpose == 0 || record.Profile == "" || record.SourceOperator == "" || record.Generation == 0 || record.NotBefore >= record.ExpiresAt {
			return nil, ErrInvalidAuthority
		}
		copied[index] = record
		copied[index].KID = append([]byte(nil), record.KID...)
	}
	for left := range copied {
		for right := left + 1; right < len(copied); right++ {
			if sameKID(copied[left].KID, copied[right].KID) && copied[left].Profile == copied[right].Profile && copied[left].SourceOperator == copied[right].SourceOperator {
				return nil, ErrInvalidAuthority
			}
		}
	}
	return &StaticIssuerResolver{records: copied}, nil
}

func (resolver *StaticIssuerResolver) ResolveRouteGrantIssuer(_ context.Context, kid []byte, profile, sourceOperator string, now uint64) (IssuerRecord, error) {
	expectedPurpose := uint16(routeGrantIssuerPurpose)
	return resolver.resolveIssuerByPurpose(kid, profile, sourceOperator, now, expectedPurpose)
}

func (resolver *StaticIssuerResolver) ResolveEnrollmentResultIssuer(_ context.Context, kid []byte, profile, sourceOperator string, now uint64) (IssuerRecord, error) {
	expectedPurpose, err := EnrollmentResultSigningPurpose()
	if err != nil {
		return IssuerRecord{}, err
	}
	return resolver.resolveIssuerByPurpose(kid, profile, sourceOperator, now, expectedPurpose)
}

func (resolver *StaticIssuerResolver) resolveIssuerByPurpose(kid []byte, profile, sourceOperator string, now uint64, expectedPurpose uint16) (IssuerRecord, error) {
	if resolver == nil || len(kid) < 1 || len(kid) > 64 || profile == "" || sourceOperator == "" || now == 0 {
		return IssuerRecord{}, ErrUnknownIdentity
	}
	for _, record := range resolver.records {
		if !sameKID(record.KID, kid) || record.Profile != profile || record.SourceOperator != sourceOperator {
			continue
		}
		if record.Purpose != expectedPurpose {
			return IssuerRecord{}, ErrInvalidKeyPurpose
		}
		if record.Revoked {
			return IssuerRecord{}, ErrRevoked
		}
		if now < record.NotBefore || now >= record.ExpiresAt {
			return IssuerRecord{}, ErrExpired
		}
		return copyIssuerRecord(record), nil
	}
	return IssuerRecord{}, errNoStaticIssuer
}

func copyIssuerRecord(record IssuerRecord) IssuerRecord {
	record.KID = append([]byte(nil), record.KID...)
	return record
}

func NewVerifier(issuers IssuerResolver) (*Verifier, error) {
	if isNilDependency(issuers) {
		return nil, ErrInvalidAuthority
	}
	return &Verifier{issuers: issuers}, nil
}

func (verifier *Verifier) VerifyRouteGrant(ctx context.Context, candidate ProviderGrant, verification VerificationContext) (VerifiedAuthority, error) {
	if verifier == nil || isNilDependency(verifier.issuers) || ctx == nil {
		return VerifiedAuthority{}, ErrInvalidAuthority
	}
	if len(candidate.ExactRouteGrant) == 0 || len(candidate.ExactRouteGrant) > defaultCBORLimits().maxInputBytes || candidate.Profile == "" || candidate.AuthorityGeneration == 0 || candidate.Checkpoint == (CheckpointDigest{}) {
		return VerifiedAuthority{}, ErrInvalidAuthority
	}
	if len(verification.Intent.Canonical) == 0 || len(verification.Intent.Canonical) > defaultCBORLimits().maxInputBytes || len(verification.Intent.TargetEdges) == 0 || len(verification.Intent.TargetEdges) > maxRouteGrantTargetEdges {
		return VerifiedAuthority{}, ErrInvalidAuthority
	}
	// Issuer resolvers are callbacks. Freeze every mutable value used after the
	// callback before parsing, verifying, or deriving the sealed digest.
	candidate.ExactRouteGrant = append([]byte(nil), candidate.ExactRouteGrant...)
	verification.Intent.Canonical = append([]byte(nil), verification.Intent.Canonical...)
	verification.Intent.TargetEdges = append([]string(nil), verification.Intent.TargetEdges...)
	if err := verifyContext(verification, candidate); err != nil {
		return VerifiedAuthority{}, err
	}
	sign1, err := parseRouteGrantSign1(candidate.ExactRouteGrant)
	if err != nil {
		return VerifiedAuthority{}, err
	}
	issuer, err := verifier.issuers.ResolveRouteGrantIssuer(ctx, sign1.kid, candidate.Profile, verification.Key.SourceOperator, verification.NowUnix)
	if err != nil {
		return VerifiedAuthority{}, normalizeIssuerError(err)
	}
	if err := validateResolvedIssuer(issuer, sign1.kid, candidate.Profile, verification); err != nil {
		return VerifiedAuthority{}, err
	}
	if err := sign1.verify(issuer.PublicKey); err != nil {
		return VerifiedAuthority{}, err
	}
	grant, err := decodeCBORExact(sign1.payload, defaultCBORLimits())
	if err != nil {
		return VerifiedAuthority{}, ErrInvalidAuthority
	}
	fields, ok := grant.(map[uint64]any)
	if !ok || !keysZeroThrough(fields, 16) || fields[0] != uint64(1) {
		return VerifiedAuthority{}, ErrInvalidAuthority
	}
	if err := verifyRouteGrantFields(fields, verification); err != nil {
		return VerifiedAuthority{}, err
	}
	return sealAuthority(verification.Key, RouteGrantDigest(sha256.Sum256(candidate.ExactRouteGrant)), verification.Intent.ExpiresAt, candidate.Checkpoint, candidate.AuthorityGeneration), nil
}

func verifyContext(verification VerificationContext, candidate ProviderGrant) error {
	hasWorkload := verification.Key.WorkloadDigest != ([32]byte{})
	if verification.NowUnix == 0 || !validUnixTime(verification.NowUnix) || validateAuthorityKey(verification.Key, hasWorkload) != nil || len(verification.Intent.Canonical) == 0 || !validTextID(verification.Intent.ServiceIdentity) || !validTextID(verification.Intent.SourceOperator) || !validTextID(verification.Intent.SourceEdge) || !validTextID(verification.Intent.TargetOperator) || !validTextIDs(verification.Intent.TargetEdges) || verification.Intent.Transport == "" || verification.Intent.Port == 0 || verification.Intent.RecordSequence == 0 || verification.Intent.RouteID == ([16]byte{}) || verification.Intent.LeaseID == ([16]byte{}) || verification.Intent.PolicyHash == (PolicyDigest{}) || verification.Intent.ExpiresAt == 0 || !validUnixTime(verification.Intent.ExpiresAt) {
		return ErrInvalidAuthority
	}
	if RouteIntentDigest(sha256.Sum256(verification.Intent.Canonical)) != verification.Intent.Digest {
		return ErrInvalidAuthority
	}
	if verification.Key.IntentDigest != verification.Intent.Digest {
		return ErrBindingMismatch
	}
	if verification.Key.SourceOperator != verification.Intent.SourceOperator || verification.Key.SourceEdge != verification.Intent.SourceEdge || verification.Key.TargetOperator != verification.Intent.TargetOperator || verification.Key.Transport != verification.Intent.Transport || verification.Key.Port != verification.Intent.Port || verification.Key.PolicyHash != verification.Intent.PolicyHash || verification.Key.TargetEdgeSetDigest != targetEdgeSetDigest(verification.Intent.TargetEdges) {
		return ErrBindingMismatch
	}
	checkpoint := verification.Checkpoint
	if !checkpoint.valid() || checkpoint.sourceOperator() != verification.Key.SourceOperator || checkpoint.profile() != verification.Key.Profile || checkpoint.Generation() != verification.Key.AuthorityGeneration || verification.NowUnix >= checkpoint.FreshUntil() || candidate.Checkpoint != checkpoint.Digest() {
		return ErrStaleFreshness
	}
	if candidate.Profile != verification.Key.Profile {
		return ErrBindingMismatch
	}
	if candidate.AuthorityGeneration != verification.Key.AuthorityGeneration {
		return ErrStaleGeneration
	}
	return nil
}

func normalizeIssuerError(err error) error {
	for _, allowed := range []error{ErrUnknownIdentity, ErrInvalidKeyPurpose, ErrInvalidAuthority, ErrExpired, ErrRevoked} {
		if errors.Is(err, allowed) {
			return allowed
		}
	}
	return ErrUnknownIdentity
}

func validateResolvedIssuer(issuer IssuerRecord, kid []byte, profile string, verification VerificationContext) error {
	if len(issuer.KID) < 1 || len(issuer.KID) > 64 || !sameKID(issuer.KID, kid) || !validPublicKey(issuer.PublicKey) || issuer.Profile != profile || issuer.Profile != verification.Key.Profile || issuer.SourceOperator != verification.Key.SourceOperator || issuer.Generation != uint64(verification.Key.AuthorityGeneration) || issuer.NotBefore >= issuer.ExpiresAt {
		return ErrUnknownIdentity
	}
	if issuer.Purpose != routeGrantIssuerPurpose {
		return ErrInvalidKeyPurpose
	}
	if issuer.Revoked {
		return ErrRevoked
	}
	if verification.NowUnix < issuer.NotBefore || verification.NowUnix >= issuer.ExpiresAt {
		return ErrExpired
	}
	return nil
}

func verifyRouteGrantFields(fields map[uint64]any, verification VerificationContext) error {
	if !keysZeroThrough(fields, 16) {
		return ErrInvalidAuthority
	}
	routeID, routeIDOK := fixed16(fields[1])
	serviceDigest, serviceDigestOK := fixed32(fields[2])
	service, serviceOK := fields[3].(string)
	sourceOperator, sourceOperatorOK := fields[4].(string)
	sourceEdge, sourceEdgeOK := fields[5].(string)
	targetOperator, targetOperatorOK := fields[6].(string)
	edges, edgesOK := sortedStrings(fields[7], 1, maxRouteGrantTargetEdges)
	transports, transportsOK := sortedStrings(fields[8], 1, 1)
	ports, portsOK := sortedPorts(fields[9], 1, 32)
	proof, proofOK := fixed32(fields[10])
	notBefore, notBeforeOK := fields[11].(uint64)
	expiresAt, expiresAtOK := fields[12].(uint64)
	leaseID, leaseIDOK := fixed16(fields[13])
	recordSequence, recordSequenceOK := fields[14].(uint64)
	policyHash, policyHashOK := fixed32(fields[15])
	_, nonceOK := fixed16(fields[16])
	if !routeIDOK || !serviceDigestOK || !serviceOK || !sourceOperatorOK || !sourceEdgeOK || !targetOperatorOK || !edgesOK || !transportsOK || !portsOK || !proofOK || !notBeforeOK || !expiresAtOK || !leaseIDOK || !recordSequenceOK || !policyHashOK || !nonceOK || !validTextID(service) || !validTextID(sourceOperator) || !validTextID(sourceEdge) || !validTextID(targetOperator) || !validTextIDs(edges) || !validUnixTime(notBefore) || !validUnixTime(expiresAt) {
		return ErrInvalidAuthority
	}
	intent, key := verification.Intent, verification.Key
	if serviceDigest != [32]byte(key.ServiceDigest) || service != intent.ServiceIdentity || sourceOperator != key.SourceOperator || sourceEdge != key.SourceEdge || targetOperator != key.TargetOperator || !sameStrings(edges, intent.TargetEdges) || len(transports) != 1 || transports[0] != "tcp" || transports[0] != key.Transport || transports[0] != intent.Transport || !containsPort(ports, uint64(intent.Port)) || routeID != intent.RouteID || leaseID != intent.LeaseID || recordSequence != intent.RecordSequence || policyHash != [32]byte(key.PolicyHash) || policyHash != [32]byte(intent.PolicyHash) || proof != [32]byte(key.ProofThumbprint) {
		return ErrBindingMismatch
	}
	if expiresAt <= notBefore || expiresAt-notBefore > maxRouteGrantLifetime || intent.ExpiresAt != expiresAt || verification.NowUnix < notBefore || verification.NowUnix >= expiresAt {
		return ErrExpired
	}
	return nil
}

func sealAuthority(key AuthorityKey, digest RouteGrantDigest, expiresAt uint64, checkpoint CheckpointDigest, generation AuthorityGeneration) VerifiedAuthority {
	return VerifiedAuthority{seal: verifiedAuthority{key: key, grantDigest: digest, expiresAt: expiresAt, checkpoint: checkpoint, authorityGeneration: generation}}
}

func (authority VerifiedAuthority) valid() bool {
	hasWorkload := authority.seal.key.WorkloadDigest != ([32]byte{})
	return validateAuthorityKey(authority.seal.key, hasWorkload) == nil && authority.seal.grantDigest != (RouteGrantDigest{}) && authority.seal.expiresAt != 0 && authority.seal.checkpoint != (CheckpointDigest{}) && authority.seal.authorityGeneration == authority.seal.key.AuthorityGeneration
}
func (authority VerifiedAuthority) Key() AuthorityKey             { return authority.seal.key }
func (authority VerifiedAuthority) GrantDigest() RouteGrantDigest { return authority.seal.grantDigest }
func (authority VerifiedAuthority) ExpiresAt() uint64             { return authority.seal.expiresAt }
func (authority VerifiedAuthority) Checkpoint() CheckpointDigest  { return authority.seal.checkpoint }
func (authority VerifiedAuthority) AuthorityGeneration() AuthorityGeneration {
	return authority.seal.authorityGeneration
}

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
func fixed16(value any) ([16]byte, bool) {
	var result [16]byte
	raw, ok := value.([]byte)
	if !ok || len(raw) != len(result) {
		return result, false
	}
	copy(result[:], raw)
	return result, true
}
func fixed32(value any) ([32]byte, bool) {
	var result [32]byte
	raw, ok := value.([]byte)
	if !ok || len(raw) != len(result) {
		return result, false
	}
	copy(result[:], raw)
	return result, true
}
func asciiString(value string) bool {
	for _, item := range []byte(value) {
		if item > 0x7f {
			return false
		}
	}
	return true
}
func validUnixTime(value uint64) bool { return value <= maxUnixTime }
func validTextID(value string) bool {
	if len(value) == 0 || len(value) > 64 || value[0] < 'a' || value[0] > 'z' {
		return false
	}
	separator := false
	for index := 1; index < len(value); index++ {
		item := value[index]
		if (item >= 'a' && item <= 'z') || (item >= '0' && item <= '9') {
			separator = false
			continue
		}
		if item == '.' || item == '_' || item == '-' {
			if separator || index == len(value)-1 {
				return false
			}
			separator = true
			continue
		}
		return false
	}
	return !separator
}
func validTextIDs(values []string) bool {
	if len(values) == 0 || len(values) > maxRouteGrantTargetEdges {
		return false
	}
	for _, value := range values {
		if !validTextID(value) {
			return false
		}
	}
	return true
}
func sortedStrings(value any, minimum, maximum int) ([]string, bool) {
	raw, ok := value.([]any)
	if !ok || len(raw) < minimum || len(raw) > maximum {
		return nil, false
	}
	result := make([]string, len(raw))
	for index, item := range raw {
		text, ok := item.(string)
		if !ok || text == "" || !asciiString(text) || (index > 0 && text <= result[index-1]) {
			return nil, false
		}
		result[index] = text
	}
	return result, true
}
func sortedPorts(value any, minimum, maximum int) ([]uint64, bool) {
	raw, ok := value.([]any)
	if !ok || len(raw) < minimum || len(raw) > maximum {
		return nil, false
	}
	result := make([]uint64, len(raw))
	for index, item := range raw {
		port, ok := item.(uint64)
		if !ok || port == 0 || port > 65535 || (index > 0 && port <= result[index-1]) {
			return nil, false
		}
		result[index] = port
	}
	return result, true
}
func sameStrings(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}
func containsPort(ports []uint64, wanted uint64) bool {
	for _, port := range ports {
		if port == wanted {
			return true
		}
	}
	return false
}
