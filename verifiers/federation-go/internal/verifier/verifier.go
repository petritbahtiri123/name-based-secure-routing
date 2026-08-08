package verifier

import (
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"nbsr.example/federation-verifier/internal/capability"
	"nbsr.example/federation-verifier/internal/cbor"
	"nbsr.example/federation-verifier/internal/cose"
	"nbsr.example/federation-verifier/internal/identity"
	"nbsr.example/federation-verifier/internal/packageverify"
	"nbsr.example/federation-verifier/internal/precedence"
	"nbsr.example/federation-verifier/internal/schema"
	"nbsr.example/federation-verifier/internal/state"
	"nbsr.example/federation-verifier/internal/strictjson"
	"nbsr.example/federation-verifier/internal/threshold"
)

type Result struct {
	Outcome, Reason, Enforcement string
	Mutation                     bool
	StateDigest                  string
}
type Summary struct {
	Static, Signed, Threshold, Capability, Precedence, State int
	ManifestArtifacts, SchemaClasses                         int
	Divergences                                              []string
}

func VerifyAll(pkg, repo string) (Summary, error) {
	m, files, e := packageverify.Verify(pkg, repo)
	if e != nil {
		return Summary{}, e
	}
	read := func(p string) ([]byte, error) { return os.ReadFile(filepath.Join(repo, filepath.FromSlash(p))) }
	sr, e := read("docs/protocol/registries/federation-v0.1-schema-proposal.json")
	if e != nil {
		return Summary{}, e
	}
	dr, e := read("docs/protocol/registries/federation-v0.1-development.json")
	if e != nil {
		return Summary{}, e
	}
	reg, e := schema.Load(sr, dr)
	if e != nil {
		return Summary{}, e
	}
	s := Summary{ManifestArtifacts: len(m.Artifacts), SchemaClasses: len(reg.Objects)}
	var d []string
	s.Static, d, e = VerifyStatic(files["static-vectors.json"], reg)
	if e != nil {
		return s, e
	}
	s.Divergences = append(s.Divergences, d...)
	s.Signed, d, e = VerifySigned(files["signed-vectors.json"], reg)
	if e != nil {
		return s, e
	}
	s.Divergences = append(s.Divergences, d...)
	s.Threshold, d, e = threshold.VerifyDocument(files["threshold-vectors.json"])
	if e != nil {
		return s, e
	}
	s.Divergences = append(s.Divergences, d...)
	s.Capability, d, e = capability.VerifyDocument(files["capability-vectors.json"])
	if e != nil {
		return s, e
	}
	s.Divergences = append(s.Divergences, d...)
	s.Precedence, d, e = precedence.Verify(files["error-precedence.json"])
	if e != nil {
		return s, e
	}
	s.Divergences = append(s.Divergences, d...)
	s.State, d, e = state.Verify(files["stateful-scenarios.json"])
	if e != nil {
		return s, e
	}
	s.Divergences = append(s.Divergences, d...)
	if len(s.Divergences) > 0 {
		return s, fmt.Errorf("%d conformance divergences", len(s.Divergences))
	}
	return s, nil
}

type staticDoc struct {
	Vectors            []staticVector `json:"vectors"`
	ObjectCoverage     any            `json:"object_coverage"`
	Authority          string         `json:"authority"`
	FormatVersion      int            `json:"format_version"`
	SchemaOracle       any            `json:"schema_oracle"`
	SchemaOracleCount  int            `json:"schema_oracle_count"`
	SchemaOraclePath   string         `json:"schema_oracle_path"`
	SchemaOracleSHA256 string         `json:"schema_oracle_sha256"`
}
type staticVector struct {
	Canonical           string         `json:"canonical_cbor_hex"`
	Expected            string         `json:"expected"`
	ExpectedReason      string         `json:"expected_reason"`
	FixedContext        map[string]any `json:"fixed_context"`
	ID                  string         `json:"id"`
	ObjectClass         string         `json:"object_class"`
	PayloadSHA256       string         `json:"payload_sha256"`
	Case                string         `json:"case"`
	Dependencies        []string       `json:"dependencies"`
	Mutation            bool           `json:"mutation"`
	MutationOf          any            `json:"mutation_of"`
	Provenance          string         `json:"provenance"`
	ResourceExpectation string         `json:"resource_expectation"`
}
type signedDoc struct {
	Vectors            []signedVector      `json:"vectors"`
	Authority          string              `json:"authority"`
	FormatVersion      int                 `json:"format_version"`
	ObjectCoverage     any                 `json:"object_coverage"`
	TrustedSigners     []trustedSigner     `json:"trusted_signers"`
	SignerRequirements []signerRequirement `json:"signer_requirements"`
	AuthorityState     authorityState      `json:"authority_state"`
}
type authorityState struct {
	EvaluationTime uint64 `json:"evaluation_time"`
	Generation     uint64 `json:"generation"`
	Sequence       uint64 `json:"sequence"`
}
type trustedSigner struct {
	AuthorityClass   uint64 `json:"authority_class"`
	ExpiresAt        uint64 `json:"expires_at"`
	Generation       uint64 `json:"generation"`
	GenesisPublicKey string `json:"genesis_public_key"`
	KeyLifecycle     uint64 `json:"key_lifecycle"`
	KeyPurpose       uint64 `json:"key_purpose"`
	Kid              string `json:"kid"`
	NotBefore        uint64 `json:"not_before"`
	OperatorID       string `json:"operator_id"`
	RecordID         string `json:"record_id"`
	Revoked          bool   `json:"revoked"`
	Sequence         uint64 `json:"sequence"`
	SigningPublicKey string `json:"signing_public_key"`
	SubjectID        string `json:"subject_id"`
}
type signerRequirement struct {
	AuthorityClass uint64 `json:"authority_class"`
	KeyPurpose     uint64 `json:"key_purpose"`
	ObjectClass    string `json:"object_class"`
	RequirementID  string `json:"requirement_id"`
	SubjectField   uint64 `json:"subject_field"`
}
type signedVector struct {
	COSE              string         `json:"cose_sign1_hex"`
	ExpectedX         string         `json:"expected"`
	ReasonX           string         `json:"expected_reason"`
	IDx               string         `json:"id"`
	Kidx              string         `json:"kid_hex"`
	PayloadX          string         `json:"payload_sha256"`
	ObjectClass       string         `json:"object_class"`
	Case              string         `json:"case"`
	Dependencies      []string       `json:"dependencies"`
	FixedContext      map[string]any `json:"fixed_context"`
	Mutation          bool           `json:"mutation"`
	ThresholdEnvelope any            `json:"threshold_envelope"`
}

func VerifyStatic(raw []byte, r schema.Registry) (int, []string, error) {
	var d staticDoc
	if e := strictjson.Decode(raw, &d); e != nil {
		return 0, nil, e
	}
	div := []string{}
	for _, v := range d.Vectors {
		b, e := hex.DecodeString(v.Canonical)
		if e != nil {
			return 0, nil, e
		}
		h := sha256.Sum256(b)
		decoded, de := cbor.Decode(b)
		derived, ok := r.Class(decoded)
		if de != nil || !ok {
			derived = ""
		}
		out, reason, _ := r.Validate(derived, b, v.FixedContext)
		if hex.EncodeToString(h[:]) != v.PayloadSHA256 {
			div = append(div, fmt.Sprintf("static %s payload digest oracle mismatch", v.ID))
		}
		if derived != "" && derived != v.ObjectClass {
			div = append(div, fmt.Sprintf("static %s object class oracle mismatch got %s want %s", v.ID, derived, v.ObjectClass))
		}
		if out != v.Expected || reason != v.ExpectedReason {
			div = append(div, fmt.Sprintf("static %s got %s/%s want %s/%s", v.ID, out, reason, v.Expected, v.ExpectedReason))
		}
	}
	return len(d.Vectors), div, nil
}
func VerifySigned(raw []byte, regs ...schema.Registry) (int, []string, error) {
	var d signedDoc
	if e := strictjson.Decode(raw, &d); e != nil {
		return 0, nil, e
	}
	signersByKid := map[string]trustedSigner{}
	seenSigningKeys := map[string]bool{}
	for i, signer := range d.TrustedSigners {
		kid, e := hex.DecodeString(signer.Kid)
		_, recordReason := validateSignerRecord(signer, kid, d.AuthorityState.EvaluationTime, d.AuthorityState)
		if signer.RecordID == "" || signersByKid[signer.Kid].RecordID != "" || seenSigningKeys[signer.SigningPublicKey] || (i > 0 && d.TrustedSigners[i-1].RecordID >= signer.RecordID) || e != nil || recordReason != "NONE" {
			return 0, nil, fmt.Errorf("invalid trusted signer inventory")
		}
		signersByKid[signer.Kid] = signer
		seenSigningKeys[signer.SigningPublicKey] = true
	}
	requirements := map[string]signerRequirement{}
	for i, requirement := range d.SignerRequirements {
		if requirement.RequirementID == "" || requirements[requirement.RequirementID].RequirementID != "" || (i > 0 && d.SignerRequirements[i-1].RequirementID >= requirement.RequirementID) {
			return 0, nil, fmt.Errorf("invalid signer requirement inventory")
		}
		requirements[requirement.RequirementID] = requirement
	}
	div := []string{}
	for _, v := range d.Vectors {
		out, reason := "ACCEPT", "NONE"
		if !canonicalHexRange(v.COSE, 1, 1<<20) {
			out, reason = "REJECT", "ERR_PARSE"
		} else {
			rawC, e := hex.DecodeString(v.COSE)
			s, e := cose.Parse(rawC)
			if e != nil {
				out, reason = "REJECT", "ERR_PARSE"
			} else {
				h := sha256.Sum256(s.Payload)
				record, recordOK := signersByKid[hex.EncodeToString(s.Kid)]
				if !recordOK {
					out, reason = "REJECT", "ERR_IDENTITY"
				} else {
					pub, signerReason := validateSignerRecord(record, s.Kid, signedNow(v.FixedContext), d.AuthorityState)
					if signerReason != "NONE" {
						out, reason = "REJECT", signerReason
					} else if e = s.Verify(pub, s.Payload, s.Kid); e != nil {
						out, reason = "REJECT", "ERR_SIGNATURE_INVALID"
					} else if len(regs) > 0 {
						pv, pe := cbor.Decode(s.Payload)
						class, cok := regs[0].Class(pv)
						if pe != nil || !cok {
							out, reason = "REJECT", "ERR_SCHEMA"
						} else if requirement, ok := deriveSignerRequirement(class, pv, requirements); !ok {
							out, reason = "REJECT", "ERR_AUTHORITY"
						} else if _, signerReason = validateSigner(record, requirement, class, s.Kid, signedNow(v.FixedContext), d.AuthorityState, pv); signerReason != "NONE" {
							out, reason = "REJECT", signerReason
						} else {
							out, reason, _ = regs[0].Validate(class, s.Payload, v.FixedContext)
							if class != v.ObjectClass {
								div = append(div, fmt.Sprintf("signed %s object class oracle mismatch", v.IDx))
							}
						}
					}
				}
				if hex.EncodeToString(h[:]) != v.PayloadX {
					div = append(div, fmt.Sprintf("signed %s payload digest oracle mismatch", v.IDx))
				}
				if hex.EncodeToString(s.Kid) != v.Kidx {
					div = append(div, fmt.Sprintf("signed %s kid oracle mismatch", v.IDx))
				}
			}
		}
		if out != v.ExpectedX || reason != v.ReasonX {
			div = append(div, fmt.Sprintf("signed %s got %s/%s want %s/%s", v.IDx, out, reason, v.ExpectedX, v.ReasonX))
		}
	}
	return len(d.Vectors), div, nil
}
func validateSignerRecord(record trustedSigner, coseKid []byte, now uint64, state authorityState) (ed25519.PublicKey, string) {
	if !canonicalHex(record.GenesisPublicKey, ed25519.PublicKeySize) || !canonicalHex(record.SigningPublicKey, ed25519.PublicKeySize) || !canonicalHex(record.OperatorID, sha256.Size) || !canonicalHexRange(record.Kid, 1, 64) {
		return nil, "ERR_IDENTITY"
	}
	if record.SubjectID != "" && !canonicalHex(record.SubjectID, 32) {
		return nil, "ERR_IDENTITY"
	}
	genesis, e1 := hex.DecodeString(record.GenesisPublicKey)
	signing, e2 := hex.DecodeString(record.SigningPublicKey)
	kid, e3 := hex.DecodeString(record.Kid)
	claimed, e4 := hex.DecodeString(record.OperatorID)
	if e1 != nil || e2 != nil || e3 != nil || e4 != nil || len(genesis) != ed25519.PublicKeySize || len(signing) != ed25519.PublicKeySize || len(kid) < 1 || len(kid) > 64 || len(claimed) != sha256.Size {
		return nil, "ERR_IDENTITY"
	}
	derived, e := identity.OperatorID(genesis)
	if e != nil || !equal(derived[:], claimed) || !equal(kid, coseKid) {
		return nil, "ERR_IDENTITY"
	}
	if state.EvaluationTime > 253402300799 || now != state.EvaluationTime || state.Generation < 1 || state.Sequence < 1 || record.Generation != state.Generation || record.Sequence != state.Sequence {
		return nil, "ERR_REPLAY"
	}
	if record.Revoked {
		return nil, "ERR_REVOKED"
	}
	if record.KeyLifecycle != 2 {
		return nil, "ERR_KEY_LIFECYCLE"
	}
	if record.NotBefore > 253402300799 || record.ExpiresAt > 253402300799 || record.ExpiresAt <= record.NotBefore || now < record.NotBefore || now >= record.ExpiresAt {
		return nil, "ERR_FRESHNESS"
	}
	return ed25519.PublicKey(signing), "NONE"
}
func validateSigner(record trustedSigner, requirement signerRequirement, actualClass string, coseKid []byte, now uint64, state authorityState, payload cbor.Value) (ed25519.PublicKey, string) {
	pub, reason := validateSignerRecord(record, coseKid, now, state)
	if reason != "NONE" {
		return nil, reason
	}
	if requirement.ObjectClass != actualClass {
		return nil, "ERR_AUTHORITY"
	}
	if record.KeyPurpose != requirement.KeyPurpose {
		return nil, "ERR_KEY_PURPOSE"
	}
	if record.AuthorityClass != requirement.AuthorityClass {
		return nil, "ERR_AUTHORITY"
	}
	if requirement.SubjectField == 0 {
		if record.SubjectID != "" {
			return nil, "ERR_IDENTITY"
		}
	} else {
		if !canonicalHex(record.SubjectID, 32) {
			return nil, "ERR_IDENTITY"
		}
		subject, ok := cbor.Get(payload, requirement.SubjectField)
		expected, _ := hex.DecodeString(record.SubjectID)
		if !ok || subject.Kind != cbor.Bytes || !equal(subject.Bytes, expected) {
			return nil, "ERR_IDENTITY"
		}
	}
	if actualClass == "KeyAuthorizationRecord" {
		authority, ok := cbor.Get(payload, 37)
		if !ok || authority.Kind != cbor.Map {
			return nil, "ERR_IDENTITY"
		}
		class, cok := cbor.Get(authority, 1)
		actor, aok := cbor.Get(authority, 2)
		nestedKid, kok := cbor.Get(authority, 3)
		operator, ook := cbor.Get(authority, 4)
		subject, _ := hex.DecodeString(record.SubjectID)
		if !cok || class.Kind != cbor.Uint || class.Uint != requirement.AuthorityClass || !aok || actor.Kind != cbor.Bytes || !equal(actor.Bytes, subject) || !kok || nestedKid.Kind != cbor.Bytes || !equal(nestedKid.Bytes, coseKid) || !ook || operator.Kind != cbor.Bytes || !equal(operator.Bytes, subject) {
			return nil, "ERR_IDENTITY"
		}
	}
	return pub, "NONE"
}
func deriveSignerRequirement(class string, payload cbor.Value, requirements map[string]signerRequirement) (signerRequirement, bool) {
	id := ""
	expected := signerRequirement{}
	switch class {
	case "OperatorRegistryRecord":
		id = "operator-registrar"
		expected = signerRequirement{AuthorityClass: 3, KeyPurpose: 3, ObjectClass: class, RequirementID: id, SubjectField: 0}
	case "KeyAuthorizationRecord":
		auth, ok := cbor.Get(payload, 37)
		if !ok || auth.Kind != cbor.Map {
			return signerRequirement{}, false
		}
		authority, ok := cbor.Get(auth, 1)
		if !ok || authority.Kind != cbor.Uint {
			return signerRequirement{}, false
		}
		if authority.Uint == 1 {
			id = "key-identity-root"
			expected = signerRequirement{AuthorityClass: 1, KeyPurpose: 1, ObjectClass: class, RequirementID: id, SubjectField: 32}
		} else if authority.Uint == 2 {
			id = "key-recovery"
			expected = signerRequirement{AuthorityClass: 2, KeyPurpose: 2, ObjectClass: class, RequirementID: id, SubjectField: 32}
		} else {
			return signerRequirement{}, false
		}
	case "TransparencyCheckpoint":
		id = "checkpoint-log"
		expected = signerRequirement{AuthorityClass: 5, KeyPurpose: 8, ObjectClass: class, RequirementID: id, SubjectField: 32}
	case "ConsistencyProof":
		id = "consistency-log"
		expected = signerRequirement{AuthorityClass: 5, KeyPurpose: 8, ObjectClass: class, RequirementID: id, SubjectField: 32}
	default:
		return signerRequirement{}, false
	}
	actual, ok := requirements[id]
	return actual, ok && actual == expected
}
func canonicalHex(value string, size int) bool {
	return len(value) == size*2 && value == strings.ToLower(value) && allHex(value)
}
func canonicalHexRange(value string, min, max int) bool {
	return len(value)%2 == 0 && len(value)/2 >= min && len(value)/2 <= max && value == strings.ToLower(value) && allHex(value)
}
func allHex(value string) bool {
	for _, c := range value {
		if !(c >= '0' && c <= '9' || c >= 'a' && c <= 'f') {
			return false
		}
	}
	return true
}
func signedNow(ctx map[string]any) uint64 {
	v, ok := ctx["evaluation_time"].(json.Number)
	if !ok {
		return 0
	}
	n, e := v.Int64()
	if e != nil || n < 0 {
		return 0
	}
	return uint64(n)
}
func equal(a, b []byte) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}
