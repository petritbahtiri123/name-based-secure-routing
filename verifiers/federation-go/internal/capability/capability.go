package capability

import (
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"nbsr.example/federation-verifier/internal/cbor"
	"nbsr.example/federation-verifier/internal/cose"
	"nbsr.example/federation-verifier/internal/strictjson"
)

type Vector struct {
	Agreed          []uint64 `json:"agreed_capabilities"`
	Session         string   `json:"authenticated_session_digest"`
	Transcript      string   `json:"authenticated_transcript_digest"`
	SetDigest       string   `json:"capability_set_digest"`
	Case            string   `json:"case"`
	Dependencies    []string `json:"dependencies"`
	Enforcement     string   `json:"enforcement"`
	Expected        string   `json:"expected_outcome"`
	Reason          string   `json:"expected_reason"`
	FixedTime       uint64   `json:"fixed_time"`
	ID              string   `json:"id"`
	Mutation        bool     `json:"mutation"`
	Offer           string   `json:"offer_cbor_hex"`
	OfferSign1      string   `json:"offer_sign1_hex"`
	Offered         []uint64 `json:"offered_capabilities"`
	Profile         string   `json:"profile"`
	Core            string   `json:"selected_core"`
	Federation      string   `json:"selected_federation"`
	Selection       string   `json:"selection_cbor_hex"`
	SelectionSign1  string   `json:"selection_sign1_hex"`
	SignedThreshold string   `json:"signed_threshold_signature_context_hex"`
	ThresholdSign1  string   `json:"threshold_evidence_sign1_hex"`
	ThresholdDigest string   `json:"threshold_signature_context_digest"`
	ReplaySourceID  string   `json:"replay_source_id"`
}
type Document struct {
	Authority          string   `json:"authority"`
	FixedPrivateKey    string   `json:"fixed_private_key_hex"`
	FormatVersion      int      `json:"format_version"`
	RequiredCapability any      `json:"required_capability"`
	Vectors            []Vector `json:"vectors"`
}
type Decision struct{ Outcome, Reason string }

func VerifyDocument(raw []byte) (int, []string, error) {
	var d Document
	if e := strictjson.Decode(raw, &d); e != nil {
		return 0, nil, e
	}
	seed, se := hex.DecodeString(d.FixedPrivateKey)
	if se != nil || len(seed) != ed25519.SeedSize {
		return 0, nil, fmt.Errorf("invalid fixed Ed25519 seed")
	}
	pub := ed25519.NewKeyFromSeed(seed).Public().(ed25519.PublicKey)
	div := []string{}
	for _, v := range d.Vectors {
		g := evaluate(v, pub)
		if g.Outcome != v.Expected || g.Reason != v.Reason {
			div = append(div, fmt.Sprintf("capability %s got %s/%s want %s/%s", v.ID, g.Outcome, g.Reason, v.Expected, v.Reason))
		}
	}
	return len(d.Vectors), div, nil
}
func evaluate(v Vector, pub ed25519.PublicKey) Decision {
	rej := func(r string) Decision { return Decision{"REJECT", r} }
	offerRaw, e := hex.DecodeString(v.Offer)
	if e != nil {
		return rej("ERR_SCHEMA")
	}
	selRaw, e := hex.DecodeString(v.Selection)
	if e != nil {
		return rej("ERR_SCHEMA")
	}
	offer, e := cbor.Decode(offerRaw)
	if e != nil || offer.Kind != cbor.Map {
		return rej("ERR_SCHEMA")
	}
	sel, e := cbor.Decode(selRaw)
	if e != nil || sel.Kind != cbor.Map {
		return rej("ERR_SCHEMA")
	}
	off, ok := uints(offer, 1)
	if !ok || !sorted(off) {
		return rej("ERR_SCHEMA")
	}
	ag, ok := uints(sel, 1)
	if !ok || !sorted(ag) {
		return rej("ERR_SCHEMA")
	}
	session, ok := digestText(sel, 5)
	if !ok {
		return rej("ERR_SCHEMA")
	}
	osession, ok := digestText(offer, 2)
	if !ok || session != osession {
		return rej("ERR_REPLAY")
	}
	core, _ := text(sel, 2)
	fed, _ := text(sel, 3)
	profile, _ := text(sel, 4)
	if core != "core-v0.2" || fed != "federation-v0.1" || profile != "federation-v0.1-development" {
		return rej("ERR_VERSION")
	}
	if !contains(off, 6) {
		return rej("ERR_UNSUPPORTED_CRITICAL")
	}
	if !contains(ag, 6) {
		return rej("ERR_DOWNGRADE")
	}
	for _, x := range off {
		if x != 6 {
			return rej("ERR_UNSUPPORTED_CRITICAL")
		}
	}
	for _, x := range ag {
		if x != 6 {
			return rej("ERR_UNSUPPORTED_CRITICAL")
		}
	}
	oraw, _ := hex.DecodeString(v.OfferSign1)
	sraw, _ := hex.DecodeString(v.SelectionSign1)
	os, e := cose.Parse(oraw)
	if e != nil {
		return rej("ERR_SIGNATURE_INVALID")
	}
	ss, e := cose.Parse(sraw)
	if e != nil {
		return rej("ERR_SIGNATURE_INVALID")
	}
	if e = os.Verify(pub, offerRaw, []byte("cap-offer")); e != nil {
		return rej("ERR_SIGNATURE_INVALID")
	}
	if e = ss.Verify(pub, selRaw, []byte("cap-select")); e != nil {
		return rej("ERR_SIGNATURE_INVALID")
	}
	capv := cbor.Value{Kind: cbor.Array}
	for _, x := range ag {
		capv.Array = append(capv.Array, cbor.Value{Kind: cbor.Uint, Uint: x})
	}
	cb, _ := cbor.Encode(capv)
	ch := sha256.Sum256(cb)
	if hex.EncodeToString(ch[:]) != v.SetDigest {
		return rej("ERR_DOWNGRADE")
	}
	th := sha256.Sum256(append(append([]byte{}, offerRaw...), selRaw...))
	if hex.EncodeToString(th[:]) != v.Transcript {
		return rej("ERR_REPLAY")
	}
	// Derive the threshold signature context from the authenticated wire
	// transcript. The vector's threshold digest is an oracle only and never
	// participates in the decision.
	sessionBytes, e := hex.DecodeString(session)
	if e != nil || len(sessionBytes) != sha256.Size {
		return rej("ERR_REPLAY")
	}
	contextInput := make([]byte, 0, sha256.Size*3+len("threshold-evidence-v1"))
	contextInput = append(contextInput, ch[:]...)
	contextInput = append(contextInput, th[:]...)
	contextInput = append(contextInput, sessionBytes...)
	contextInput = append(contextInput, []byte("threshold-evidence-v1")...)
	expectedContext := sha256.Sum256(contextInput)
	signed, e := hex.DecodeString(v.SignedThreshold)
	if e != nil || !equalBytes(signed, expectedContext[:]) {
		return rej("ERR_REPLAY")
	}
	teRaw, _ := hex.DecodeString(v.ThresholdSign1)
	te, e := cose.Parse(teRaw)
	if e != nil {
		return rej("ERR_SIGNATURE_INVALID")
	}
	if e = te.Verify(pub, signed, []byte("threshold-context")); e != nil {
		return rej("ERR_REPLAY")
	}
	return Decision{"ACCEPT", "NONE"}
}
func equalBytes(a, b []byte) bool {
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
func uints(v cbor.Value, k uint64) ([]uint64, bool) {
	x, ok := cbor.Get(v, k)
	if !ok || x.Kind != cbor.Array {
		return nil, false
	}
	a := make([]uint64, len(x.Array))
	for i, q := range x.Array {
		if q.Kind != cbor.Uint {
			return nil, false
		}
		a[i] = q.Uint
	}
	return a, true
}
func text(v cbor.Value, k uint64) (string, bool) {
	x, ok := cbor.Get(v, k)
	return x.Text, ok && x.Kind == cbor.Text
}
func digestText(v cbor.Value, k uint64) (string, bool) {
	x, ok := cbor.Get(v, k)
	if !ok {
		return "", false
	}
	if x.Kind == cbor.Text {
		return x.Text, true
	}
	if x.Kind == cbor.Bytes {
		return string(x.Bytes), true
	}
	return "", false
}
func sorted(a []uint64) bool {
	for i := 1; i < len(a); i++ {
		if a[i-1] >= a[i] {
			return false
		}
	}
	return true
}
func contains(a []uint64, x uint64) bool {
	for _, q := range a {
		if q == x {
			return true
		}
	}
	return false
}
func equalU(a, b []uint64) bool {
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
