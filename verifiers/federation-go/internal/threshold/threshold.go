package threshold

import (
	"bytes"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"

	"nbsr.example/federation-verifier/internal/cbor"
	"nbsr.example/federation-verifier/internal/cose"
	"nbsr.example/federation-verifier/internal/strictjson"
)

type Authority struct {
	AuthorityClass       uint64   `json:"authority_class"`
	KeyPurpose           uint64   `json:"key_purpose"`
	NotBefore            uint64   `json:"not_before"`
	Revoked              bool     `json:"revoked"`
	EligiblePolicyGroups []string `json:"eligible_policy_groups"`
	AuthorityIDx         string   `json:"authority_id"`
	OrganizationIDx      string   `json:"organization_id"`
	PublicKeyx           string   `json:"public_key"`
	Kidx                 string   `json:"kid"`
	ExpiresAtx           uint64   `json:"expires_at"`
}
type Context struct {
	Accepted                  []Authority `json:"accepted_authority_registry"`
	AgreedFederation          any         `json:"agreed_federation_version"`
	AgreedProfile             string      `json:"agreed_profile_id"`
	AuthenticatedCapabilities any         `json:"authenticated_capabilities"`
	SessionDigest             string      `json:"authenticated_session_transcript_digest"`
	Agreement                 any         `json:"capability_agreement_authenticated"`
	ExpectedRequestID         string      `json:"expected_request_event_transition_id"`
	Negotiated                any         `json:"negotiated_capabilities"`
	Now                       uint64      `json:"now"`
	SelectedCore              any         `json:"selected_core_version"`
	SingleSign1Fallback       any         `json:"single_sign1_fallback"`
}
type Vector struct {
	Canonical           string   `json:"canonical_cbor_hex"`
	ExpectedDecision    string   `json:"expected_decision"`
	ExpectedReason      string   `json:"expected_reason"`
	ExpectedMutation    bool     `json:"expected_mutation"`
	Enforcement         string   `json:"enforcement"`
	ID                  string   `json:"id"`
	Name                string   `json:"name"`
	Context             Context  `json:"validation_context"`
	Dependencies        []string `json:"dependencies"`
	FixedTime           uint64   `json:"fixed_time"`
	Provenance          string   `json:"provenance"`
	ResourceExpectation string   `json:"resource_expectation"`
	SHA256              string   `json:"sha256"`
	CollectorInputOrder any      `json:"collector_input_order"`
	Note                any      `json:"note"`
}
type Document struct {
	Authority     string   `json:"authority"`
	FormatVersion int      `json:"format_version"`
	OracleCount   int      `json:"oracle_count"`
	OraclePath    string   `json:"oracle_path"`
	OracleSHA256  string   `json:"oracle_sha256"`
	Vectors       []Vector `json:"vectors"`
}
type Decision struct {
	Outcome, Reason string
	Mutation        bool
}
type policySpec struct{ need, eligible, minOrg, class, purpose uint64 }

var approved = map[string]policySpec{
	"registrar-v1:registry": {1, 1, 1, 3, 3}, "ordinary-witness-v1:witness": {2, 3, 2, 6, 9}, "high-risk-witness-v1:witness": {3, 5, 3, 6, 9},
	"global-trust-v1:governance": {3, 5, 3, 4, 13}, "high-risk-global-root-v1:governance": {4, 5, 4, 4, 13},
	"operator-recovery-v1:recovery": {2, 3, 2, 2, 2}, "operator-recovery-v1:registry": {1, 1, 1, 3, 3}, "operator-recovery-v1:witness": {2, 3, 2, 6, 9},
	"deny-only-emergency-v1:emergency": {2, 5, 2, 4, 12}, "conflict-decision-v1:conflict": {2, 3, 2, 11, 13}, "conflict-decision-v1:witness": {2, 3, 2, 6, 9},
	"appeal-decision-v1:appeal": {2, 3, 2, 12, 13}, "appeal-decision-v1:witness": {2, 3, 2, 6, 9},
}

func VerifyDocument(raw []byte) (int, []string, error) {
	var d Document
	if e := strictjson.Decode(raw, &d); e != nil {
		return 0, nil, e
	}
	div := []string{}
	for _, v := range d.Vectors {
		b, e := hex.DecodeString(v.Canonical)
		if e != nil {
			return 0, nil, e
		}
		got := Evaluate(b, v.Context)
		if got.Outcome != v.ExpectedDecision || got.Reason != v.ExpectedReason || got.Mutation != v.ExpectedMutation {
			div = append(div, fmt.Sprintf("threshold %s got %s/%s/%v want %s/%s/%v", v.ID, got.Outcome, got.Reason, got.Mutation, v.ExpectedDecision, v.ExpectedReason, v.ExpectedMutation))
		}
	}
	return len(d.Vectors), div, nil
}

func Evaluate(raw []byte, ctx Context) Decision {
	rej := func(r string) Decision { return Decision{"REJECT", r, false} }
	if len(raw) > 65536 {
		return rej("ERR_RESOURCE_LIMIT")
	}
	v, e := cbor.DecodeLimits(raw, cbor.Limits{MaxDepth: 8, MaxArray: 128, MaxMap: 64, MaxBytes: 65536, MaxText: 256})
	if e != nil {
		if bytes.Contains([]byte(e.Error()), []byte("limit")) {
			return rej("ERR_RESOURCE_LIMIT")
		}
		return rej("ERR_NON_CANONICAL")
	}
	if v.Kind != cbor.Map {
		return rej("ERR_SCHEMA")
	}
	if !keys(v, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10) {
		return rej("ERR_SCHEMA")
	}
	version, ok := u(v, 1)
	if !ok || version != 1 {
		return rej("ERR_VERSION")
	}
	profile, ok := textv(v, 2)
	if !ok || profile != "nbsr-federation-dev-v1" {
		return rej("ERR_VERSION")
	}
	obj, ok := u(v, 3)
	if !ok || obj < 1 || obj > 18 {
		return rej("ERR_SCHEMA")
	}
	digest, ok := bstr(v, 4, 32, 32)
	if !ok {
		return rej("ERR_SCHEMA")
	}
	policy, ok := cbor.Get(v, 5)
	if !ok || policy.Kind != cbor.Map || !keys(policy, 1, 2, 3, 4, 5, 6, 7, 8, 9) {
		return rej("ERR_SCHEMA")
	}
	scope, ok := bstr(v, 6, 32, 32)
	if !ok {
		return rej("ERR_SCHEMA")
	}
	lineage, ok := cbor.Get(v, 7)
	if !ok || !lineageOK(lineage) {
		return rej("ERR_SCHEMA")
	}
	auth, ok := cbor.Get(v, 8)
	if !ok || !authOK(auth) {
		return rej("ERR_SCHEMA")
	}
	groups, ok := cbor.Get(v, 9)
	if !ok || groups.Kind != cbor.Array {
		return rej("ERR_SCHEMA")
	}
	if len(groups.Array) > 4 {
		return rej("ERR_RESOURCE_LIMIT")
	}
	total := 0
	for _, g := range groups.Array {
		if g.Kind != cbor.Map {
			return rej("ERR_SCHEMA")
		}
		s, _ := cbor.Get(g, 2)
		if s.Kind != cbor.Array {
			return rej("ERR_SCHEMA")
		}
		if len(s.Array) > 5 {
			return rej("ERR_RESOURCE_LIMIT")
		}
		total += len(s.Array)
	}
	if total > 16 {
		return rej("ERR_RESOURCE_LIMIT")
	}
	if ext, ok := cbor.Get(v, 10); ok {
		if r := extensions(ext); r != "" {
			if r == "ERR_SCHEMA" && hasCritical(ext) {
				r = "ERR_UNSUPPORTED_CRITICAL"
			}
			return rej(r)
		}
	}
	if ext, ok := cbor.Get(policy, 8); ok {
		if r := extensions(ext); r != "" {
			return rej(r)
		}
	}
	pver, ok := u(policy, 1)
	if !ok || pver != 1 {
		return rej("ERR_SCHEMA")
	}
	pid, ok := bstr(policy, 2, 32, 32)
	if !ok {
		return rej("ERR_SCHEMA")
	}
	nullPolicy := policy
	nullPolicy.Map = append([]cbor.Pair(nil), policy.Map...)
	for i := range nullPolicy.Map {
		if nullPolicy.Map[i].Key.Kind == cbor.Uint && nullPolicy.Map[i].Key.Uint == 2 {
			nullPolicy.Map[i].Value = cbor.Value{Kind: cbor.Null}
		}
	}
	pb, _ := cbor.Encode(nullPolicy)
	ph := sha256.Sum256(pb)
	if !bytes.Equal(pid, ph[:]) {
		return rej("ERR_AUTHORITY")
	}
	pname, ok := textv(policy, 3)
	if !ok || len(pname) < 1 || len(pname) > 64 {
		return rej("ERR_SCHEMA")
	}
	deny, ok := boolv(policy, 4)
	if !ok {
		return rej("ERR_SCHEMA")
	}
	reqs, ok := cbor.Get(policy, 5)
	if !ok || reqs.Kind != cbor.Array || len(reqs.Array) < 1 || len(reqs.Array) > 4 {
		return rej("ERR_SCHEMA")
	}
	classes, ok := uintArray(policy, 6)
	if !ok || !sortedUniqueU(classes) {
		return rej("ERR_SCHEMA")
	}
	msgs, ok := uintArray(policy, 7)
	if !ok || !sortedUniqueU(msgs) {
		return rej("ERR_SCHEMA")
	}
	effects, ok := textArray(policy, 9)
	if !ok || !sortedUniqueS(effects) {
		return rej("ERR_SCHEMA")
	}
	if !containsU(classes, obj) {
		return rej("ERR_AUTHORITY")
	}
	msg, _ := u(auth, 1)
	if !containsU(msgs, msg) {
		return rej("ERR_REPLAY")
	}
	effect, _ := textv(auth, 7)
	if !containsS(effects, effect) {
		if deny {
			return rej("ERR_POLICY_EXPANSION")
		}
		return rej("ERR_AUTHORITY")
	}
	if deny && effect != "deny" {
		return rej("ERR_POLICY_EXPANSION")
	}
	if f, ok := ctx.SingleSign1Fallback.(bool); ok && f {
		return rej("ERR_DOWNGRADE")
	}
	core, cok := num(ctx.SelectedCore)
	fed, fok := num(ctx.AgreedFederation)
	agreement, aok := ctx.Agreement.(bool)
	if !cok || !fok || core != 2 || fed != 1 || ctx.AgreedProfile != "nbsr-federation-dev-v1" {
		return rej("ERR_VERSION")
	}
	if !aok || !agreement {
		return rej("ERR_DOWNGRADE")
	}
	neg, nok := stringsAny(ctx.Negotiated)
	aut, auok := stringsAny(ctx.AuthenticatedCapabilities)
	if !nok || !auok {
		return rej("ERR_SCHEMA")
	}
	if !containsS(neg, "THRESHOLD_EVIDENCE") || !containsS(aut, "THRESHOLD_EVIDENCE") {
		if containsS(neg, "THRESHOLD_EVIDENCE") != containsS(aut, "THRESHOLD_EVIDENCE") {
			return rej("ERR_DOWNGRADE")
		}
		return rej("ERR_UNSUPPORTED_CRITICAL")
	}
	reqid, ok := bstr(auth, 2, 16, 64)
	if !ok {
		return rej("ERR_SCHEMA")
	}
	if hex.EncodeToString(reqid) != ctx.ExpectedRequestID {
		return rej("ERR_REPLAY")
	}
	nb, nok := u(auth, 3)
	ex, xok := u(auth, 4)
	if !nok || !xok || ex < nb {
		return rej("ERR_SCHEMA")
	}
	if ctx.Now < nb || ctx.Now >= ex {
		return rej("ERR_FRESHNESS")
	}
	ctxDigest, ok := bstr(auth, 5, 32, 32)
	if !ok {
		return rej("ERR_SCHEMA")
	}
	ev, ok := u(auth, 6)
	if !ok || ev != 1 {
		return rej("ERR_SCHEMA")
	}
	pre := cbor.Value{Kind: cbor.Map}
	for _, p := range auth.Map {
		if p.Key.Kind == cbor.Uint && (p.Key.Uint == 1 || p.Key.Uint == 2 || p.Key.Uint == 3 || p.Key.Uint == 4 || p.Key.Uint == 6 || p.Key.Uint == 7) {
			pre.Map = append(pre.Map, p)
		}
	}
	preb, _ := cbor.Encode(pre)
	ch := sha256.Sum256(preb)
	if !bytes.Equal(ctxDigest, ch[:]) {
		return rej("ERR_REPLAY")
	}
	if len(groups.Array) != len(reqs.Array) {
		if len(groups.Array) == 0 {
			return Decision{"PENDING", "ERR_EVIDENCE_MISSING", false}
		}
		return Decision{"PENDING", "ERR_WITNESS_THRESHOLD", false}
	}
	seenGlobal := map[string]bool{}
	for i, req := range reqs.Array {
		if req.Kind != cbor.Map || !keys(req, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11) {
			return rej("ERR_SCHEMA")
		}
		if ext, ok := cbor.Get(req, 11); ok {
			if r := extensions(ext); r != "" {
				return rej(r)
			}
		}
		gid, ok := textv(req, 1)
		if !ok || gid == "" || len(gid) > 32 {
			return rej("ERR_SCHEMA")
		}
		need, nok := u(req, 2)
		eligible, eok := u(req, 3)
		minOrg, mok := u(req, 7)
		if !nok || !eok || !mok || need < 1 || need > 5 || eligible < need || eligible > 5 || minOrg < 1 || minOrg > need {
			return rej("ERR_SCHEMA")
		}
		spec, exists := approved[pname+":"+gid]
		if !exists || spec.need != need || spec.eligible != eligible || spec.minOrg != minOrg {
			return rej("ERR_AUTHORITY")
		}
		acls, ok := uintArray(req, 4)
		if !ok || !sortedUniqueU(acls) {
			return rej("ERR_SCHEMA")
		}
		if len(acls) != 1 || acls[0] != spec.class {
			return rej("ERR_AUTHORITY")
		}
		purposes, ok := uintArray(req, 8)
		if !ok || !sortedUniqueU(purposes) {
			return rej("ERR_SCHEMA")
		}
		if len(purposes) != 1 || purposes[0] != spec.purpose {
			return rej("ERR_AUTHORITY")
		}
		classCounts, ccok := classCount(req)
		if !ccok || len(classCounts) != 1 || classCounts[spec.class] != need {
			return rej("ERR_AUTHORITY")
		}
		eligibleIDs, ok := bytesArray(req, 6)
		if !ok || !sortedUniqueB(eligibleIDs) {
			return rej("ERR_SCHEMA")
		}
		if len(eligibleIDs) > 0 {
			trusted := eligibleFor(ctx.Accepted, pname+":"+gid)
			if !equalByteSets(eligibleIDs, trusted) {
				return rej("ERR_AUTHORITY")
			}
		}
		rdeny, ok := boolv(req, 9)
		if !ok {
			return rej("ERR_SCHEMA")
		}
		if rdeny && effect != "deny" {
			return rej("ERR_POLICY_EXPANSION")
		}
		rscope, ok := bstr(req, 10, 32, 32)
		if !ok {
			return rej("ERR_SCHEMA")
		}
		if !bytes.Equal(rscope, scope) {
			return rej("ERR_SCOPE")
		}
		group := groups.Array[i]
		if !keys(group, 1, 2) {
			return rej("ERR_SCHEMA")
		}
		actualID, ok := textv(group, 1)
		if !ok || actualID != gid {
			return rej("ERR_AUTHORITY")
		}
		signers, _ := cbor.Get(group, 2)
		if len(signers.Array) == 0 {
			return Decision{"PENDING", "ERR_EVIDENCE_MISSING", false}
		}
		validIDs := map[string]bool{}
		orgs := map[string]bool{}
		var prevTuple string
		for _, s := range signers.Array {
			if s.Kind != cbor.Map || !keys(s, 1, 2, 3, 4, 5, 6, 7, 8) {
				return rej("ERR_SCHEMA")
			}
			if ext, ok := cbor.Get(s, 8); ok {
				if r := extensions(ext); r != "" {
					return rej(r)
				}
			}
			class, cok := u(s, 1)
			aidRaw, _ := cbor.Get(s, 2)
			kidRaw, _ := cbor.Get(s, 4)
			orgRaw, _ := cbor.Get(s, 5)
			if aidRaw.Kind == cbor.Bytes && len(aidRaw.Bytes) > 64 || kidRaw.Kind == cbor.Bytes && len(kidRaw.Bytes) > 64 || orgRaw.Kind == cbor.Bytes && len(orgRaw.Bytes) > 64 {
				return rej("ERR_RESOURCE_LIMIT")
			}
			aid, aok := bstr(s, 2, 1, 64)
			purpose, pok := u(s, 3)
			kid, kok := bstr(s, 4, 1, 64)
			org, ook := nullableBytes(s, 5, 1, 64)
			sd, dok := bstr(s, 6, 32, 32)
			coseBytes, sok := bstr(s, 7, 1, 65536)
			if !cok || !aok || !pok || !kok || !ook || !dok || !sok {
				return rej("ERR_SCHEMA")
			}
			tuple := fmt.Sprintf("%020d:%x:%020d:%x", class, aid, purpose, kid)
			if prevTuple != "" && tuple <= prevTuple {
				return rej("ERR_AUTHORITY")
			}
			prevTuple = tuple
			aidKey := hex.EncodeToString(aid)
			if seenGlobal[aidKey] || validIDs[aidKey] {
				return rej("ERR_AUTHORITY")
			}
			if !containsU(acls, class) {
				return rej("ERR_AUTHORITY")
			}
			if !containsU(purposes, purpose) {
				return rej("ERR_KEY_PURPOSE")
			}
			if len(eligibleIDs) > 0 && !containsB(eligibleIDs, aid) {
				return rej("ERR_AUTHORITY")
			}
			record, rr := resolve(ctx.Accepted, class, aid, purpose, kid)
			if rr != "" {
				return rej(rr)
			}
			if record.Revoked {
				return rej("ERR_REVOKED")
			}
			if ctx.Now < record.NotBefore || ctx.Now >= record.ExpiresAtx {
				return rej("ERR_FRESHNESS")
			}
			trustedOrg, _ := hex.DecodeString(record.OrganizationIDx)
			if !bytes.Equal(org, trustedOrg) {
				return rej("ERR_AUTHORITY")
			}
			if !bytes.Equal(sd, digest) {
				return rej("ERR_SIGNATURE_INVALID")
			}
			capBind := binding(ctx)
			sigctx := cbor.Value{Kind: cbor.Map, Map: []cbor.Pair{pair(1, cbor.Value{Kind: cbor.Text, Text: "NBSR-FEDERATION-THRESHOLD-SIGNATURE-v1"}), pair(2, cbor.Value{Kind: cbor.Uint, Uint: 1}), pair(3, cbor.Value{Kind: cbor.Text, Text: "nbsr-federation-dev-v1"}), pair(4, cbor.Value{Kind: cbor.Uint, Uint: obj}), pair(5, cbor.Value{Kind: cbor.Bytes, Bytes: digest}), pair(6, cbor.Value{Kind: cbor.Bytes, Bytes: pid}), pair(7, cbor.Value{Kind: cbor.Text, Text: gid}), pair(8, cbor.Value{Kind: cbor.Bytes, Bytes: scope}), pair(9, lineage), pair(10, auth), pair(11, cbor.Value{Kind: cbor.Uint, Uint: 6}), pair(12, cbor.Value{Kind: cbor.Bytes, Bytes: capBind})}}
			sigraw, _ := cbor.Encode(sigctx)
			cs, e := cose.Parse(coseBytes)
			if e != nil {
				return rej("ERR_NON_CANONICAL")
			}
			pk, _ := hex.DecodeString(record.PublicKeyx)
			sp, e := cbor.Decode(cs.Payload)
			if e != nil || sp.Kind != cbor.Map || !keys(sp, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12) {
				return rej("ERR_SCHEMA")
			}
			cap, ok := u(sp, 11)
			if !ok || cap != 6 {
				return rej("ERR_DOWNGRADE")
			}
			bind, ok := bstr(sp, 12, 32, 32)
			if !ok {
				return rej("ERR_SCHEMA")
			}
			if !bytes.Equal(bind, capBind) {
				return rej("ERR_REPLAY")
			}
			pd, ok := bstr(sp, 5, 32, 32)
			if !ok || !bytes.Equal(pd, digest) {
				return rej("ERR_SIGNATURE_INVALID")
			}
			sev, ok := u(sp, 2)
			if !ok || sev != 1 {
				return rej("ERR_SCHEMA")
			}
			sa, ok := cbor.Get(sp, 10)
			if !ok || !authOK(sa) {
				return rej("ERR_SCHEMA")
			}
			sx, ok := u(sa, 6)
			if !ok || sx != 1 {
				return rej("ERR_SCHEMA")
			}
			if e = cs.Verify(ed25519.PublicKey(pk), cs.Payload, kid); e != nil {
				return rej("ERR_SIGNATURE_INVALID")
			}
			if !bytes.Equal(cs.Payload, sigraw) {
				return rej("ERR_REPLAY")
			}
			validIDs[aidKey] = true
			seenGlobal[aidKey] = true
			orgs[record.OrganizationIDx] = true
		}
		if uint64(len(validIDs)) < need {
			return Decision{"PENDING", "ERR_WITNESS_THRESHOLD", false}
		}
		if uint64(len(validIDs)) > eligible {
			return rej("ERR_AUTHORITY")
		}
		if uint64(len(orgs)) < minOrg {
			return Decision{"REJECT", "ERR_WITNESS_THRESHOLD", false}
		}
	}
	return Decision{"ACCEPT", "NONE", false}
}

func keys(v cbor.Value, allowed ...uint64) bool {
	a := map[uint64]bool{}
	for _, k := range allowed {
		a[k] = true
	}
	for _, p := range v.Map {
		if p.Key.Kind != cbor.Uint || !a[p.Key.Uint] {
			return false
		}
	}
	return true
}
func u(v cbor.Value, k uint64) (uint64, bool) {
	x, ok := cbor.Get(v, k)
	return x.Uint, ok && x.Kind == cbor.Uint
}
func textv(v cbor.Value, k uint64) (string, bool) {
	x, ok := cbor.Get(v, k)
	return x.Text, ok && x.Kind == cbor.Text
}
func boolv(v cbor.Value, k uint64) (bool, bool) {
	x, ok := cbor.Get(v, k)
	return x.Bool, ok && x.Kind == cbor.Bool
}
func bstr(v cbor.Value, k uint64, min, max int) ([]byte, bool) {
	x, ok := cbor.Get(v, k)
	return x.Bytes, ok && x.Kind == cbor.Bytes && len(x.Bytes) >= min && len(x.Bytes) <= max
}
func nullableBytes(v cbor.Value, k uint64, min, max int) ([]byte, bool) {
	x, ok := cbor.Get(v, k)
	if !ok {
		return nil, false
	}
	if x.Kind == cbor.Null {
		return nil, true
	}
	return x.Bytes, x.Kind == cbor.Bytes && len(x.Bytes) >= min && len(x.Bytes) <= max
}
func lineageOK(v cbor.Value) bool {
	if v.Kind != cbor.Map || !keys(v, 1, 2, 3) {
		return false
	}
	for _, k := range []uint64{1, 2} {
		x, _ := cbor.Get(v, k)
		if x.Kind != cbor.Uint && x.Kind != cbor.Null {
			return false
		}
	}
	x, _ := cbor.Get(v, 3)
	return x.Kind == cbor.Null || x.Kind == cbor.Bytes && len(x.Bytes) == 32
}
func authOK(v cbor.Value) bool { return v.Kind == cbor.Map && keys(v, 1, 2, 3, 4, 5, 6, 7) }
func extensions(v cbor.Value) string {
	if v.Kind != cbor.Array || len(v.Array) > 16 {
		return "ERR_SCHEMA"
	}
	for _, x := range v.Array {
		if x.Kind != cbor.Map || !keys(x, 1, 2, 3) {
			return "ERR_SCHEMA"
		}
		ver, ok := u(x, 1)
		if !ok || ver != 1 {
			return "ERR_SCHEMA"
		}
		crit, ok := boolv(x, 2)
		if !ok {
			return "ERR_SCHEMA"
		}
		b, ok := bstr(x, 3, 0, 4096)
		_ = b
		if !ok {
			return "ERR_SCHEMA"
		}
		if crit {
			return "ERR_UNSUPPORTED_CRITICAL"
		}
	}
	return ""
}
func hasCritical(v cbor.Value) bool {
	if v.Kind == cbor.Map {
		if x, ok := cbor.Get(v, 2); ok && x.Kind == cbor.Bool && x.Bool {
			return true
		}
		for _, p := range v.Map {
			if hasCritical(p.Value) {
				return true
			}
		}
	}
	if v.Kind == cbor.Array {
		for _, x := range v.Array {
			if hasCritical(x) {
				return true
			}
		}
	}
	return false
}
func classCount(v cbor.Value) (map[uint64]uint64, bool) {
	x, ok := cbor.Get(v, 5)
	if !ok || x.Kind != cbor.Array {
		return nil, false
	}
	m := map[uint64]uint64{}
	var last uint64
	for i, p := range x.Array {
		if p.Kind != cbor.Array || len(p.Array) != 2 || p.Array[0].Kind != cbor.Uint || p.Array[1].Kind != cbor.Uint {
			return nil, false
		}
		if i > 0 && p.Array[0].Uint <= last {
			return nil, false
		}
		last = p.Array[0].Uint
		m[last] = p.Array[1].Uint
	}
	return m, true
}
func eligibleFor(rs []Authority, group string) [][]byte {
	out := [][]byte{}
	seen := map[string]bool{}
	for _, r := range rs {
		if containsS(r.EligiblePolicyGroups, group) && !seen[r.AuthorityIDx] {
			b, e := hex.DecodeString(r.AuthorityIDx)
			if e == nil {
				out = append(out, b)
				seen[r.AuthorityIDx] = true
			}
		}
	}
	sort.Slice(out, func(i, j int) bool { return bytes.Compare(out[i], out[j]) < 0 })
	return out
}
func equalByteSets(a, b [][]byte) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if !bytes.Equal(a[i], b[i]) {
			return false
		}
	}
	return true
}
func uintArray(v cbor.Value, k uint64) ([]uint64, bool) {
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
func textArray(v cbor.Value, k uint64) ([]string, bool) {
	x, ok := cbor.Get(v, k)
	if !ok || x.Kind != cbor.Array {
		return nil, false
	}
	a := make([]string, len(x.Array))
	for i, q := range x.Array {
		if q.Kind != cbor.Text {
			return nil, false
		}
		a[i] = q.Text
	}
	return a, true
}
func bytesArray(v cbor.Value, k uint64) ([][]byte, bool) {
	x, ok := cbor.Get(v, k)
	if !ok || x.Kind != cbor.Array {
		return nil, false
	}
	a := make([][]byte, len(x.Array))
	for i, q := range x.Array {
		if q.Kind != cbor.Bytes || len(q.Bytes) == 0 {
			return nil, false
		}
		a[i] = q.Bytes
	}
	return a, true
}
func sortedUniqueU(a []uint64) bool {
	for i := 1; i < len(a); i++ {
		if a[i-1] >= a[i] {
			return false
		}
	}
	return true
}
func sortedUniqueS(a []string) bool {
	for i := 1; i < len(a); i++ {
		if a[i-1] >= a[i] {
			return false
		}
	}
	return true
}
func sortedUniqueB(a [][]byte) bool {
	for i := 1; i < len(a); i++ {
		if bytes.Compare(a[i-1], a[i]) >= 0 {
			return false
		}
	}
	return true
}
func containsU(a []uint64, x uint64) bool {
	for _, q := range a {
		if q == x {
			return true
		}
	}
	return false
}
func containsS(a []string, x string) bool {
	for _, q := range a {
		if q == x {
			return true
		}
	}
	return false
}
func containsB(a [][]byte, x []byte) bool {
	for _, q := range a {
		if bytes.Equal(q, x) {
			return true
		}
	}
	return false
}
func resolve(rs []Authority, class uint64, aid []byte, purpose uint64, kid []byte) (Authority, string) {
	matches := []Authority{}
	for _, r := range rs {
		if r.AuthorityClass == class && r.AuthorityIDx == hex.EncodeToString(aid) && r.KeyPurpose == purpose && r.Kidx == hex.EncodeToString(kid) {
			matches = append(matches, r)
		}
	}
	if len(matches) != 1 {
		if len(matches) == 0 {
			for _, r := range rs {
				if r.Kidx == hex.EncodeToString(kid) && r.KeyPurpose != purpose {
					return Authority{}, "ERR_KEY_PURPOSE"
				}
			}
		}
		return Authority{}, "ERR_IDENTITY"
	}
	return matches[0], ""
}
func binding(ctx Context) []byte {
	session, _ := hex.DecodeString(ctx.SessionDigest)
	pre := cbor.Value{Kind: cbor.Map, Map: []cbor.Pair{pair(1, cbor.Value{Kind: cbor.Text, Text: "NBSR-FEDERATION-CAPABILITY-SESSION-BINDING-v1"}), pair(2, cbor.Value{Kind: cbor.Uint, Uint: 2}), pair(3, cbor.Value{Kind: cbor.Uint, Uint: 1}), pair(4, cbor.Value{Kind: cbor.Text, Text: "nbsr-federation-dev-v1"}), pair(5, cbor.Value{Kind: cbor.Array, Array: []cbor.Value{{Kind: cbor.Uint, Uint: 6}}}), pair(6, cbor.Value{Kind: cbor.Bytes, Bytes: session})}}
	b, _ := cbor.Encode(pre)
	h := sha256.Sum256(b)
	return h[:]
}
func num(v any) (uint64, bool) {
	switch x := v.(type) {
	case json.Number:
		n, e := x.Int64()
		return uint64(n), e == nil && n >= 0
	case float64:
		return uint64(x), x >= 0 && x == float64(uint64(x))
	}
	return 0, false
}
func stringsAny(v any) ([]string, bool) {
	a, ok := v.([]any)
	if !ok {
		if s, ok := v.([]string); ok {
			return s, true
		}
		return nil, false
	}
	out := make([]string, len(a))
	for i, x := range a {
		s, ok := x.(string)
		if !ok {
			return nil, false
		}
		out[i] = s
	}
	return out, true
}
func pair(k uint64, v cbor.Value) cbor.Pair {
	return cbor.Pair{Key: cbor.Value{Kind: cbor.Uint, Uint: k}, Value: v}
}

var _ = json.Number("")
var _ = sort.Ints
