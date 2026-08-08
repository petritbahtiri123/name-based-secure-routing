package state

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"nbsr.example/federation-verifier/internal/strictjson"
	"sort"
	"strconv"
	"strings"
)

type Event struct {
	AuthorityExpansion     bool     `json:"authority_expansion"`
	Compromised            bool     `json:"compromised"`
	Dependencies           []string `json:"dependencies"`
	Generation             uint64   `json:"generation"`
	Key                    string   `json:"key"`
	ObjectDigest           string   `json:"object_digest"`
	ObjectKind             string   `json:"object_kind"`
	Operation              string   `json:"operation"`
	OperatorID             string   `json:"operator_id"`
	OutageTrigger          *string  `json:"outage_trigger"`
	PeerOperatorID         string   `json:"peer_operator_id"`
	PreviousDigest         *string  `json:"previous_digest"`
	RecoveryOf             *string  `json:"recovery_of"`
	ReplayDigest           *string  `json:"replay_digest"`
	RequiresPriorAuthority bool     `json:"requires_prior_authority"`
	Sequence               uint64   `json:"sequence"`
	ServiceID              string   `json:"service_id"`
	SourceFreshAt          *uint64  `json:"source_fresh_at"`
	StaticPolicyDigest     *string  `json:"static_policy_digest"`
	Terminal               bool     `json:"terminal"`
	ValidUntil             *uint64  `json:"valid_until"`
	ValidationFailures     []string `json:"validation_failures"`
}
type Wrapped struct {
	EvaluationTime uint64 `json:"evaluation_time"`
	Event          Event  `json:"federation_event"`
	ID             string `json:"id"`
}
type Scenario struct {
	Enforcement, ExpectedReason, ExpectedResult, ID, ResultingDigest string
	Mutation                                                         bool
	Input                                                            ScenarioInput
	Ordinal                                                          int
	Dependencies, EmittedEvidence                                    []string
	Effects                                                          any
}
type ScenarioInput struct{ Artifact, FixedNonce, Operation, PreState, VectorID string }

func (s *Scenario) UnmarshalJSON(b []byte) error {
	type w struct {
		Dependencies   []string `json:"dependencies"`
		Effects        any      `json:"effects"`
		Emitted        []string `json:"emitted_evidence"`
		Enforcement    string   `json:"enforcement"`
		EvaluationTime uint64   `json:"evaluation_time"`
		ExpectedReason string   `json:"expected_reason"`
		ExpectedResult string   `json:"expected_result"`
		ID             string   `json:"id"`
		Input          struct {
			Artifact   string `json:"artifact"`
			FixedNonce string `json:"fixed_nonce"`
			Operation  string `json:"operation"`
			PreState   string `json:"pre_state"`
			VectorID   string `json:"vector_id"`
		} `json:"input"`
		Mutation bool   `json:"mutation"`
		Ordinal  int    `json:"ordinal"`
		Digest   string `json:"resulting_state_digest"`
	}
	var x w
	if e := strictjson.Decode(b, &x); e != nil {
		return e
	}
	s.Enforcement = x.Enforcement
	s.ExpectedReason = x.ExpectedReason
	s.ExpectedResult = x.ExpectedResult
	s.ID = x.ID
	s.ResultingDigest = x.Digest
	s.Mutation = x.Mutation
	s.Ordinal = x.Ordinal
	s.Dependencies = x.Dependencies
	s.EmittedEvidence = x.Emitted
	s.Effects = x.Effects
	s.Input = ScenarioInput{x.Input.Artifact, x.Input.FixedNonce, x.Input.Operation, x.Input.PreState, x.Input.VectorID}
	return nil
}

type Document struct {
	Authority         string     `json:"authority"`
	EventVectors      []Wrapped  `json:"event_vectors"`
	FormatVersion     int        `json:"format_version"`
	Scenarios         []Scenario `json:"scenarios"`
	Task6Oracle       any        `json:"task6_oracle"`
	Task6OraclePath   string     `json:"task6_oracle_path"`
	Task6OracleSHA256 string     `json:"task6_oracle_sha256"`
}
type Accepted struct {
	Dependencies []string `json:"dependencies"`
	Digest       string   `json:"digest"`
	Fresh        *uint64  `json:"fresh"`
	Generation   uint64   `json:"generation"`
	Key          string   `json:"key"`
	Kind         string   `json:"kind"`
	Operator     string   `json:"operator"`
	Peer         string   `json:"peer"`
	Sequence     uint64   `json:"sequence"`
	Service      string   `json:"service"`
	Terminal     bool     `json:"terminal"`
	ValidUntil   *uint64  `json:"valid_until"`
}
type Static struct {
	Activated uint64   `json:"activated"`
	Digest    string   `json:"digest"`
	Expires   uint64   `json:"expires"`
	Operators []string `json:"operators"`
	Scope     string   `json:"scope"`
	Service   string   `json:"service"`
	Triggers  []string `json:"triggers"`
}
type State struct {
	Accepted   []Accepted `json:"accepted"`
	Pending    []any      `json:"pending"`
	Quarantine [][]any    `json:"quarantine"`
	Replay     [][]any    `json:"replay"`
	Static     []Static   `json:"static"`
	Tombstones []string   `json:"tombstones"`
}
type Result struct {
	Outcome, Reason, Enforcement string
	Mutation                     bool
	Evidence                     []string
}

func Initial() State {
	return State{Accepted: []Accepted{}, Pending: []any{}, Quarantine: [][]any{}, Replay: [][]any{}, Static: []Static{{1899999000, strings.Repeat("50", 32), 1900001000, []string{strings.Repeat("41", 32), strings.Repeat("42", 32)}, "static:route", strings.Repeat("53", 32), []string{"control-outage"}}}, Tombstones: []string{}}
}
func Digest(s State) string { b := stable(s); h := sha256.Sum256(b); return hex.EncodeToString(h[:]) }
func Decide(s *State, e Event, now uint64) Result {
	r := func(o, reason, enf string, mut bool) Result { return Result{o, reason, enf, mut, nil} }
	if len(e.ValidationFailures) > 0 {
		return r("REJECT", e.ValidationFailures[0], "DENY_NEW_USE", false)
	}
	if e.ObjectKind == "replay-rejection" {
		return r("REJECT", "ERR_REPLAY", "DENY_NEW_USE", false)
	}
	if e.Compromised {
		return r("REJECT", "ERR_REVOKED", "TERMINATE_ACTIVE_USE", false)
	}
	if e.RequiresPriorAuthority && len(s.Accepted) == 0 {
		return r("REJECT", "ERR_AUTHORITY", "DENY_NEW_USE", false)
	}
	if e.RecoveryOf != nil && !contains(s.Tombstones, *e.RecoveryOf) && !quarantined(s.Quarantine, *e.RecoveryOf) {
		return r("REJECT", "ERR_RECOVERY_INVALID", "DENY_NEW_USE", false)
	}
	if e.ReplayDigest != nil && replayed(s.Replay, *e.ReplayDigest) {
		return r("REJECT", "ERR_REPLAY", "DENY_NEW_USE", false)
	}
	if e.Operation == "existing_context" {
		if e.SourceFreshAt == nil {
			return r("REJECT", "ERR_FRESHNESS", "DRAIN", false)
		}
		if *e.SourceFreshAt > now {
			return r("REJECT", "ERR_FRESHNESS", "DENY_NEW_USE", false)
		}
		age := now - *e.SourceFreshAt
		if age <= 300 {
			return r("ACCEPT", "NONE", "NONE", false)
		}
		if age <= 900 {
			return r("RESTRICTED", "ERR_FRESHNESS", "REAUTHENTICATE", false)
		}
		return r("REJECT", "ERR_OUTAGE_POLICY", "DRAIN", false)
	}
	if e.Operation == "static_recovery" {
		for _, p := range s.Static {
			if e.StaticPolicyDigest != nil && p.Digest == *e.StaticPolicyDigest && p.Scope == e.Key && p.Service == e.ServiceID && contains(p.Operators, e.OperatorID) && contains(p.Operators, e.PeerOperatorID) && e.OutageTrigger != nil && contains(p.Triggers, *e.OutageTrigger) {
				if now >= p.Activated && now < p.Expires {
					return r("RESTRICTED", "ERR_OUTAGE_POLICY", "DENY_NEW_USE", false)
				}
			}
		}
		return r("REJECT", "ERR_RECOVERY_INVALID", "DENY_NEW_USE", false)
	}
	idx := -1
	for i, x := range s.Accepted {
		if x.Key == e.Key {
			idx = i
			break
		}
	}
	if e.PreviousDigest != nil && (idx < 0 || s.Accepted[idx].Digest != *e.PreviousDigest) {
		return r("REJECT", "ERR_CONTINUITY", "DENY_NEW_USE", false)
	}
	if idx >= 0 {
		old := s.Accepted[idx]
		if e.Generation < old.Generation || e.Generation == old.Generation && e.Sequence < old.Sequence {
			return r("REJECT", "ERR_ROLLBACK", "DENY_NEW_USE", false)
		}
		if e.Generation == old.Generation && e.Sequence == old.Sequence {
			if e.ObjectDigest == old.Digest {
				if old.Terminal {
					return r("REJECT", "ERR_TERMINAL_STATE", "DENY_NEW_USE", false)
				}
				return r("ACCEPT", "NONE", "NONE", false)
			}
			addQuarantine(s, e.Key, old.Digest, e.ObjectDigest)
			return r("QUARANTINE", "ERR_EQUIVOCATION", "DENY_NEW_USE", true)
		}
	}
	if contains(s.Tombstones, e.Key) {
		return r("REJECT", "ERR_TERMINAL_STATE", "DENY_NEW_USE", false)
	}
	a := Accepted{e.Dependencies, e.ObjectDigest, e.SourceFreshAt, e.Generation, e.Key, e.ObjectKind, e.OperatorID, e.PeerOperatorID, e.Sequence, e.ServiceID, e.Terminal, e.ValidUntil}
	if idx >= 0 {
		s.Accepted = append(s.Accepted[:idx], s.Accepted[idx+1:]...)
	}
	s.Accepted = append(s.Accepted, a)
	sort.Slice(s.Accepted, func(i, j int) bool { return s.Accepted[i].Key < s.Accepted[j].Key })
	if e.Terminal && !contains(s.Tombstones, e.Key) {
		s.Tombstones = append(s.Tombstones, e.Key)
		sort.Strings(s.Tombstones)
	}
	if e.ReplayDigest != nil {
		s.Replay = append(s.Replay, []any{*e.ReplayDigest, now})
		sort.Slice(s.Replay, func(i, j int) bool { return fmt.Sprint(s.Replay[i]) < fmt.Sprint(s.Replay[j]) })
	}
	z := r("ACCEPT", "NONE", "NONE", true)
	z.Evidence = []string{e.ObjectDigest}
	return z
}
func Verify(raw []byte) (int, []string, error) {
	var d Document
	if e := strictjson.Decode(raw, &d); e != nil {
		return 0, nil, e
	}
	if len(d.EventVectors) != 43 || len(d.Scenarios) != 43 {
		return 0, nil, fmt.Errorf("state counts")
	}
	s := Initial()
	div := []string{}
	for i, w := range d.EventVectors {
		sc := d.Scenarios[i]
		pre := Digest(s)
		if pre != sc.Input.PreState {
			div = append(div, fmt.Sprintf("state %s pre-digest got %s want %s", sc.ID, pre, sc.Input.PreState))
		}
		g := Decide(&s, w.Event, w.EvaluationTime)
		dig := Digest(s)
		if g.Outcome != sc.ExpectedResult || g.Reason != sc.ExpectedReason || g.Enforcement != sc.Enforcement || g.Mutation != sc.Mutation || dig != sc.ResultingDigest {
			div = append(div, fmt.Sprintf("state %s got %s/%s/%s/%v/%s want %s/%s/%s/%v/%s", sc.ID, g.Outcome, g.Reason, g.Enforcement, g.Mutation, dig, sc.ExpectedResult, sc.ExpectedReason, sc.Enforcement, sc.Mutation, sc.ResultingDigest))
		}
	}
	return len(d.Scenarios), div, nil
}
func addQuarantine(s *State, key, a, b string) {
	vals := []string{a, b}
	sort.Strings(vals)
	for i, q := range s.Quarantine {
		if q[0] == key {
			old := q[1].([]any)
			m := map[string]bool{}
			for _, x := range old {
				m[x.(string)] = true
			}
			m[b] = true
			xs := []string{}
			for x := range m {
				xs = append(xs, x)
			}
			sort.Strings(xs)
			z := make([]any, len(xs))
			for j, x := range xs {
				z[j] = x
			}
			s.Quarantine[i][1] = z
			return
		}
	}
	s.Quarantine = append(s.Quarantine, []any{key, []any{vals[0], vals[1]}})
	sort.Slice(s.Quarantine, func(i, j int) bool { return s.Quarantine[i][0].(string) < s.Quarantine[j][0].(string) })
}
func contains(a []string, x string) bool {
	for _, q := range a {
		if q == x {
			return true
		}
	}
	return false
}
func quarantined(q [][]any, k string) bool {
	for _, x := range q {
		if x[0] == k {
			return true
		}
	}
	return false
}
func replayed(q [][]any, k string) bool {
	for _, x := range q {
		if x[0] == k {
			return true
		}
	}
	return false
}
func stable(v any) []byte { var b bytes.Buffer; writeStable(&b, reflectJSON(v)); return b.Bytes() }
func reflectJSON(v any) any {
	b, _ := json.Marshal(v)
	var x any
	dec := json.NewDecoder(bytes.NewReader(b))
	dec.UseNumber()
	_ = dec.Decode(&x)
	return x
}
func writeStable(b *bytes.Buffer, v any) {
	switch x := v.(type) {
	case nil:
		b.WriteString("null")
	case bool:
		if x {
			b.WriteString("true")
		} else {
			b.WriteString("false")
		}
	case string:
		q, _ := json.Marshal(x)
		b.Write(q)
	case json.Number:
		b.WriteString(x.String())
	case float64:
		b.WriteString(strconv.FormatFloat(x, 'f', -1, 64))
	case []any:
		b.WriteByte('[')
		for i, q := range x {
			if i > 0 {
				b.WriteByte(',')
			}
			writeStable(b, q)
		}
		b.WriteByte(']')
	case map[string]any:
		ks := make([]string, 0, len(x))
		for k := range x {
			ks = append(ks, k)
		}
		sort.Strings(ks)
		b.WriteByte('{')
		for i, k := range ks {
			if i > 0 {
				b.WriteByte(',')
			}
			q, _ := json.Marshal(k)
			b.Write(q)
			b.WriteByte(':')
			writeStable(b, x[k])
		}
		b.WriteByte('}')
	}
}
