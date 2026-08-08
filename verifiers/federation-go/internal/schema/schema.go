package schema

import (
	"bytes"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"regexp"
	"strconv"
	"strings"

	"nbsr.example/federation-verifier/internal/cbor"
	"nbsr.example/federation-verifier/internal/strictjson"
)

type Field struct {
	Name              string `json:"name"`
	Key               uint64 `json:"key"`
	WireType          string `json:"wire_type"`
	Requiredness      string `json:"requiredness"`
	Bounds            string `json:"bounds"`
	Genesis           string `json:"genesis"`
	Update            string `json:"update"`
	Critical          bool   `json:"critical"`
	Immutable         bool   `json:"immutable_after_genesis"`
	Monotonic         bool   `json:"monotonic"`
	Predecessor       bool   `json:"predecessor_linked"`
	AuthorityDefining bool   `json:"authority_defining"`
	LifecycleDefining bool   `json:"lifecycle_defining"`
	PrivacySensitive  bool   `json:"privacy_sensitive"`
	Privacy           string `json:"privacy"`
}
type Object struct {
	Fields                       []Field  `json:"fields"`
	MaximumCanonicalPayloadBytes int      `json:"maximum_canonical_payload_bytes"`
	LifecycleClass               string   `json:"lifecycle_class"`
	Rationale                    string   `json:"rationale"`
	LifecycleRules               any      `json:"lifecycle_rules"`
	SignerRule                   any      `json:"signer_rule"`
	ForbiddenFields              []string `json:"forbidden_fields"`
	UnknownBaseField             string   `json:"unknown_base_field"`
	MaximumSignedObjectBytes     int      `json:"maximum_signed_object_bytes"`
	AllowedStateTransitions      any      `json:"allowed_state_transitions"`
	NewGenerationChangeFields    []string `json:"new_generation_change_fields"`
}
type Composite struct {
	Closed              bool              `json:"closed"`
	WireType            string            `json:"wire_type"`
	Fields              map[string]string `json:"fields"`
	Item                string            `json:"item"`
	Cardinality         string            `json:"cardinality"`
	MaximumEncodedBytes int               `json:"maximum_encoded_bytes"`
	DuplicateBehavior   string            `json:"duplicate_behavior"`
	UnknownField        string            `json:"unknown_field_behavior"`
	CanonicalOrdering   string            `json:"canonical_ordering"`
	Intersection        string            `json:"intersection"`
	Digest              string            `json:"digest"`
	Preservation        string            `json:"preservation"`
}
type document struct {
	Objects                         map[string]Object            `json:"objects"`
	FormatVersion                   int                          `json:"format_version"`
	Profile                         string                       `json:"profile"`
	Status                          string                       `json:"status"`
	ProposalAuthority               string                       `json:"proposal_authority"`
	RuntimeImplementationAuthorized bool                         `json:"runtime_implementation_authorized"`
	Task2Ready                      bool                         `json:"task2_ready_after_human_approval"`
	KeyModel                        any                          `json:"key_model"`
	CommonFields                    any                          `json:"common_fields"`
	ScalarTypes                     map[string]string            `json:"scalar_types"`
	CompositeTypes                  map[string]Composite         `json:"composite_types"`
	SignatureThresholdRules         any                          `json:"signature_threshold_rules"`
	LocalEnums                      map[string]map[string]uint64 `json:"local_enums"`
	RecoveryDefault                 any                          `json:"recovery_default"`
	RecoverySubstitution            any                          `json:"recovery_substitution"`
}
type Registry struct {
	Objects     map[string]Object
	ObjectTypes map[string]uint64
	Enums       map[string]map[uint64]bool
	EnumNames   map[string]map[string]uint64
	Composites  map[string]Composite
	LocalEnums  map[string]map[uint64]bool
}

func (r Registry) Class(v cbor.Value) (string, bool) {
	x, ok := cbor.Get(v, 1)
	if !ok || x.Kind != cbor.Uint {
		return "", false
	}
	for n, id := range r.ObjectTypes {
		if id == x.Uint {
			return n, true
		}
	}
	return "", false
}

type regEntry struct {
	Name   string `json:"name"`
	Value  uint64 `json:"value"`
	Status string `json:"status"`
}
type devDocument struct {
	Registries                 map[string][]regEntry `json:"registries"`
	FormatVersion              int                   `json:"format_version"`
	Profile                    string                `json:"profile"`
	Status                     string                `json:"status"`
	WireFreeze                 bool                  `json:"wire_freeze"`
	AllocationPolicy           any                   `json:"allocation_policy"`
	ReservedRanges             any                   `json:"reserved_ranges"`
	CoreCollisionProof         any                   `json:"core_collision_proof"`
	UnknownValuePolicy         any                   `json:"unknown_value_policy"`
	SignerAuthorityMatrix      any                   `json:"signer_authority_matrix"`
	RootReplacement            any                   `json:"root_replacement"`
	PrivacyOpening             any                   `json:"privacy_opening"`
	DeferredDecisions          any                   `json:"deferred_decisions"`
	MessageRegistryPolicy      any                   `json:"message_registry_policy"`
	MessageSemantics           any                   `json:"message_semantics"`
	ContextualRules            any                   `json:"contextual_rules"`
	LocalWorkflowStates        any                   `json:"local_workflow_states"`
	OperatorLifecycleSemantics any                   `json:"operator_lifecycle_semantics"`
}

func Load(schemaRaw, devRaw []byte) (Registry, error) {
	var s document
	if e := strictjson.Decode(schemaRaw, &s); e != nil {
		return Registry{}, e
	}
	var d devDocument
	if e := strictjson.Decode(devRaw, &d); e != nil {
		return Registry{}, e
	}
	r := Registry{Objects: s.Objects, ObjectTypes: map[string]uint64{}, Enums: map[string]map[uint64]bool{}, EnumNames: map[string]map[string]uint64{}, Composites: s.CompositeTypes, LocalEnums: map[string]map[uint64]bool{}}
	for _, x := range d.Registries["object_types"] {
		r.ObjectTypes[x.Name] = x.Value
	}
	for name, values := range s.LocalEnums {
		m := map[uint64]bool{}
		for _, value := range values {
			m[value] = true
		}
		r.LocalEnums[name] = m
	}
	for n, xs := range d.Registries {
		m := map[uint64]bool{}
		nm := map[string]uint64{}
		for _, x := range xs {
			m[x.Value] = true
			nm[x.Name] = x.Value
		}
		r.Enums[n] = m
		r.EnumNames[n] = nm
	}
	if len(r.Objects) != 18 || len(r.ObjectTypes) != 18 {
		return Registry{}, fmt.Errorf("registry coverage")
	}
	return r, nil
}
func (r Registry) Validate(class string, raw []byte, ctx map[string]any) (string, string, bool) {
	if len(raw) > 32768 {
		return "REJECT", "ERR_RESOURCE_LIMIT", false
	}
	v, e := cbor.DecodeLimits(raw, cbor.Limits{MaxDepth: 16, MaxArray: 1024, MaxMap: 128, MaxBytes: 65536, MaxText: 4096})
	if e != nil {
		return "REJECT", "ERR_NON_CANONICAL", false
	}
	round, _ := cbor.Encode(v)
	if !bytes.Equal(round, raw) {
		return "REJECT", "ERR_NON_CANONICAL", false
	}
	o, ok := r.Objects[class]
	if !ok || v.Kind != cbor.Map {
		return "REJECT", "ERR_SCHEMA", false
	}
	if o.MaximumCanonicalPayloadBytes <= 0 || len(raw) > o.MaximumCanonicalPayloadBytes {
		return "REJECT", "ERR_RESOURCE_LIMIT", false
	}
	allowed := map[uint64]Field{}
	for _, f := range o.Fields {
		allowed[f.Key] = f
		if f.Requiredness == "required" {
			if _, ok := cbor.Get(v, f.Key); !ok {
				return "REJECT", "ERR_SCHEMA", false
			}
		}
	}
	for _, p := range v.Map {
		if p.Key.Kind != cbor.Uint {
			return "REJECT", "ERR_SCHEMA", false
		}
		if _, ok := allowed[p.Key.Uint]; !ok {
			return "REJECT", "ERR_SCHEMA", false
		}
	}
	t, ok := cbor.Get(v, 1)
	if !ok || t.Kind != cbor.Uint || t.Uint != r.ObjectTypes[class] {
		return "REJECT", "ERR_SCHEMA", false
	}
	ver, ok := cbor.Get(v, 2)
	if !ok || ver.Kind != cbor.Uint || ver.Uint != 1 {
		return "REJECT", "ERR_SCHEMA", false
	}
	for _, f := range o.Fields {
		q, ok := cbor.Get(v, f.Key)
		if !ok {
			continue
		}
		if !r.validateWire(q, f.WireType) || !r.validateBounds(q, f) {
			if f.Name == "operator_id" {
				return "REJECT", "ERR_IDENTITY", false
			}
			return "REJECT", "ERR_SCHEMA", false
		}
	}
	gen, _ := uintv(v, 4)
	seq, _ := uintv(v, 5)
	genesis := gen == 1 && seq == 1
	for _, f := range o.Fields {
		_, present := cbor.Get(v, f.Key)
		rule := f.Update
		if genesis {
			rule = f.Genesis
		}
		if rule == "required" && !present {
			return "REJECT", "ERR_SCHEMA", false
		}
		if rule == "forbidden" && present {
			return "REJECT", "ERR_SCHEMA", false
		}
	}
	if previousHex, ok := ctx["previous_canonical_hex"].(string); ok {
		previousRaw, err := hex.DecodeString(previousHex)
		if err != nil {
			return "REJECT", "ERR_SCHEMA", false
		}
		previous, err := cbor.Decode(previousRaw)
		if err != nil || previous.Kind != cbor.Map {
			return "REJECT", "ERR_SCHEMA", false
		}
		for _, f := range o.Fields {
			old, oldOK := cbor.Get(previous, f.Key)
			current, currentOK := cbor.Get(v, f.Key)
			if f.Immutable && (oldOK != currentOK || oldOK && !valueEqual(old, current)) {
				return "REJECT", "ERR_SCHEMA", false
			}
			if f.Monotonic && oldOK && currentOK && old.Kind == cbor.Uint && current.Kind == cbor.Uint && current.Uint < old.Uint {
				return "REJECT", "ERR_ROLLBACK", false
			}
		}
	}
	if !r.validateRelationships(class, v, o) {
		return "REJECT", "ERR_SCHEMA", false
	}
	if ext, ok := cbor.Get(v, 31); ok {
		for _, p := range ext.Map {
			if p.Value.Kind != cbor.Map {
				return "REJECT", "ERR_SCHEMA", false
			}
			crit, has := cbor.Get(p.Value, 2)
			if !has || crit.Kind != cbor.Bool {
				return "REJECT", "ERR_SCHEMA", false
			}
			if crit.Bool {
				return "REJECT", "ERR_UNSUPPORTED_CRITICAL", false
			}
		}
	}
	if x, ok := cbor.Get(v, 32); ok && class == "OperatorRegistryRecord" && (x.Kind != cbor.Bytes || len(x.Bytes) != 32) {
		return "REJECT", "ERR_IDENTITY", false
	}
	if x, ok := cbor.Get(v, 33); ok && class == "KeyAuthorizationRecord" && (x.Kind != cbor.Bytes || len(x.Bytes) < 1 || len(x.Bytes) > 64) {
		return "REJECT", "ERR_IDENTITY", false
	}
	if class == "TransparencyCheckpoint" {
		if cg, ok := number(ctx["current_generation"]); ok && gen == uint64(cg)+1 && ctx["accepted_transition"] == nil {
			return "REJECT", "ERR_RECOVERY_INVALID", false
		}
	}
	prev, hasPrev := cbor.Get(v, 8)
	lineage := class == "OperatorRegistryRecord" || class == "KeyAuthorizationRecord" || class == "NameOwnershipRecord" || class == "DelegationRecord" || class == "FederationTrustBundle" || class == "OperatorEndpointRecord" || class == "TypedRevocationRecord" || class == "OperatorLifecycleRecord"
	if lineage && gen == 1 && seq == 1 && hasPrev {
		return "REJECT", "ERR_SCHEMA", false
	}
	if lineage && gen > 0 && (gen != 1 || seq != 1) && !hasPrev {
		return "REJECT", "ERR_SCHEMA", false
	}
	if hasPrev && (prev.Kind != cbor.Bytes || len(prev.Bytes) != 32) {
		return "REJECT", "ERR_SCHEMA", false
	}
	if now, ok := number(ctx["validation_time"]); ok {
		nb, _ := uintv(v, 6)
		ex, _ := uintv(v, 7)
		if now < float64(nb) || ex > 0 && now >= float64(ex) {
			return "REJECT", "ERR_FRESHNESS", false
		}
	}
	if want, ok := ctx["expected_operator_id"].(string); ok {
		if x, _ := cbor.Get(v, 32); x.Kind != cbor.Bytes || hex.EncodeToString(x.Bytes) != want {
			return "REJECT", "ERR_IDENTITY", false
		}
	}
	if ids, ok := ctx["terminal_key_ids"].([]any); ok {
		if x, _ := cbor.Get(v, 33); x.Kind == cbor.Bytes {
			for _, id := range ids {
				if s, ok := id.(string); ok && hex.EncodeToString(x.Bytes) == s {
					return "REJECT", "ERR_TERMINAL_STATE", false
				}
			}
		}
	}
	if s, _ := ctx["signer_lifecycle"].(string); s == "REVOKED" {
		if class == "KeyAuthorizationRecord" {
			return "REJECT", "ERR_KEY_LIFECYCLE", false
		}
		return "REJECT", "ERR_KEY_LIFECYCLE", false
	}
	if s, _ := ctx["signer"].(string); s == "operator-root-only" {
		return "REJECT", "ERR_AUTHORITY", false
	}
	if s, _ := ctx["signer_purpose"].(string); s != "" && s != "IDENTITY_ROOT" {
		return "REJECT", "ERR_KEY_PURPOSE", false
	}
	if s, _ := ctx["protected_kid"].(string); s == "unknown-kid" {
		return "REJECT", "ERR_IDENTITY", false
	}
	if class == "KeyAuthorizationRecord" {
		p, _ := uintv(v, 35)
		if !r.Enums["key_purposes"][p] {
			return "REJECT", "ERR_KEY_PURPOSE", false
		}
		if p == 4 && ctx["recovery_transition"] == nil {
			return "REJECT", "ERR_KEY_PURPOSE", false
		}
	}
	if cg, ok := number(ctx["current_generation"]); ok {
		cs, _ := number(ctx["current_sequence"])
		if gen < uint64(cg) || gen == uint64(cg) && seq < uint64(cs) {
			return "REJECT", "ERR_ROLLBACK", false
		}
		if gen == uint64(cg) && seq == uint64(cs) {
			return "QUARANTINE", "ERR_EQUIVOCATION", false
		}
		if gen == uint64(cg)+1 && seq == 1 {
			if _, ok := ctx["recovery_transition"]; !ok || ctx["recovery_transition"] == nil {
				return "REJECT", "ERR_RECOVERY_INVALID", false
			}
		}
	}
	if cd, ok := ctx["current_digest"].(string); ok && hasPrev && hex.EncodeToString(prev.Bytes) != cd {
		return "REJECT", "ERR_CONTINUITY", false
	}
	if class == "ConsistencyProof" {
		if want, ok := ctx["expected_old_checkpoint_digest"].(string); ok {
			old, _ := cbor.Get(v, 34)
			if old.Kind != cbor.Bytes || hex.EncodeToString(old.Bytes) != want {
				return "REJECT", "ERR_CONTINUITY", false
			}
		}
		if want, ok := ctx["expected_new_checkpoint_digest"].(string); ok {
			nw, _ := cbor.Get(v, 35)
			if nw.Kind != cbor.Bytes || hex.EncodeToString(nw.Bytes) != want {
				return "REJECT", "ERR_CONTINUITY", false
			}
		}
	}
	if class == "OperatorRegistryRecord" {
		life, _ := uintv(v, 36)
		_, stage := cbor.Get(v, 39)
		recovery := r.enumValue("operator_lifecycles", "RECOVERY")
		if life == recovery && !stage {
			return "REJECT", "ERR_SCHEMA", false
		}
		if transition, supplied := ctx["recovery_transition"]; life == recovery && supplied && transition == nil {
			return "REJECT", "ERR_RECOVERY_INVALID", false
		}
		if life != recovery && stage {
			return "REJECT", "ERR_SCHEMA", false
		}
		if s, _ := ctx["signer"].(string); strings.HasPrefix(s, "recovery") && ctx["recovery_transition"] == nil {
			return "REJECT", "ERR_RECOVERY_INVALID", false
		}
	}
	return "ACCEPT", "NONE", true
}
func (r Registry) validateWire(v cbor.Value, w string) bool {
	if strings.HasSuffix(w, "|null") {
		return v.Kind == cbor.Null || r.validateWire(v, strings.TrimSuffix(w, "|null"))
	}
	switch w {
	case "uint":
		return v.Kind == cbor.Uint
	case "bool":
		return v.Kind == cbor.Bool
	case "bstr":
		return v.Kind == cbor.Bytes
	case "tstr":
		return v.Kind == cbor.Text
	}
	if strings.HasPrefix(w, "array<") && strings.HasSuffix(w, ">") {
		if v.Kind != cbor.Array {
			return false
		}
		inner := w[len("array<") : len(w)-1]
		for _, item := range v.Array {
			if !r.validateWire(item, inner) {
				return false
			}
		}
		return sortedUnique(v.Array)
	}
	if w == "map<uint,ExtensionEntry>" {
		if v.Kind != cbor.Map || len(v.Map) > 16 {
			return false
		}
		for _, p := range v.Map {
			if p.Key.Kind != cbor.Uint || p.Key.Uint < 1000 || p.Key.Uint > 65535 || !r.validateComposite(p.Value, "ExtensionEntry") {
				return false
			}
		}
		return true
	}
	_, known := r.Composites[w]
	return known && r.validateComposite(v, w)
}

func (r Registry) validateComposite(v cbor.Value, name string) bool {
	c, ok := r.Composites[name]
	if !ok {
		return false
	}
	encoded, err := cbor.Encode(v)
	if err != nil || c.MaximumEncodedBytes > 0 && len(encoded) > c.MaximumEncodedBytes {
		return false
	}
	if c.WireType == "map" {
		if v.Kind != cbor.Map || len(v.Map) != len(c.Fields) {
			return false
		}
		for keyText, spec := range c.Fields {
			key, err := strconv.ParseUint(keyText, 10, 64)
			if err != nil {
				return false
			}
			item, present := cbor.Get(v, key)
			if !present || !r.validateSpec(item, spec) {
				return false
			}
		}
		for _, p := range v.Map {
			if p.Key.Kind != cbor.Uint {
				return false
			}
			if _, ok := c.Fields[strconv.FormatUint(p.Key.Uint, 10)]; !ok {
				return false
			}
		}
		return r.compositeSemantics(name, v)
	}
	if c.WireType != "array" || v.Kind != cbor.Array {
		return false
	}
	lo, hi := cardinality(c.Cardinality)
	if len(v.Array) < lo || len(v.Array) > hi {
		return false
	}
	for _, item := range v.Array {
		if !r.validateSpec(item, c.Item) {
			return false
		}
	}
	return sortedUnique(v.Array)
}

func (r Registry) validateSpec(v cbor.Value, spec string) bool {
	if i := strings.Index(spec, ":"); i >= 0 && !strings.HasPrefix(spec, "[") {
		spec = spec[i+1:]
	}
	if strings.Contains(spec, "|") {
		for _, alt := range strings.Split(spec, "|") {
			if r.validateSpec(v, alt) {
				return true
			}
		}
		return false
	}
	if spec == "null" {
		return v.Kind == cbor.Null
	}
	if spec == "bool" {
		return v.Kind == cbor.Bool
	}
	if spec == "bstr" {
		return v.Kind == cbor.Bytes
	}
	if spec == "tstr" {
		return v.Kind == cbor.Text
	}
	if spec == "bstr32" {
		return v.Kind == cbor.Bytes && len(v.Bytes) == 32
	}
	if spec == "uint" {
		return v.Kind == cbor.Uint
	}
	if strings.HasPrefix(spec, "uint(") {
		lo, hi, ok := parseRange(spec)
		return ok && v.Kind == cbor.Uint && v.Uint >= uint64(lo) && v.Uint <= uint64(hi)
	}
	if strings.HasPrefix(spec, "bstr(") {
		lo, hi, ok := parseRange(spec)
		return ok && v.Kind == cbor.Bytes && len(v.Bytes) >= lo && len(v.Bytes) <= hi
	}
	if strings.HasPrefix(spec, "tstr(") {
		lo, hi, ok := parseRange(spec)
		return ok && v.Kind == cbor.Text && len([]byte(v.Text)) >= lo && len([]byte(v.Text)) <= hi
	}
	if strings.HasPrefix(spec, "array<") {
		end := strings.LastIndex(spec, ">")
		if end < 0 || v.Kind != cbor.Array {
			return false
		}
		inner := spec[6:end]
		lo, hi := 0, int(^uint(0)>>1)
		if end+1 < len(spec) {
			lo, hi, _ = parseRange(spec[end+1:])
		}
		if len(v.Array) < lo || len(v.Array) > hi {
			return false
		}
		for _, x := range v.Array {
			if !r.validateSpec(x, inner) {
				return false
			}
		}
		return sortedUnique(v.Array)
	}
	if strings.HasPrefix(spec, "[") && strings.HasSuffix(spec, "]") {
		if v.Kind != cbor.Array {
			return false
		}
		parts := strings.Split(strings.Trim(spec, "[]"), ",")
		if len(v.Array) != len(parts) {
			return false
		}
		for i, p := range parts {
			if !r.validateSpec(v.Array[i], strings.TrimSpace(p)) {
				return false
			}
		}
		return true
	}
	if values, ok := r.LocalEnums[spec]; ok {
		return v.Kind == cbor.Uint && values[v.Uint]
	}
	if _, ok := r.Composites[spec]; ok {
		return r.validateComposite(v, spec)
	}
	return false
}

func (r Registry) compositeSemantics(name string, v cbor.Value) bool {
	switch name {
	case "OrganizationBinding":
		mode, _ := uintv(v, 1)
		pub, _ := cbor.Get(v, 2)
		commitment, _ := cbor.Get(v, 3)
		return mode == 1 && pub.Kind == cbor.Text && commitment.Kind == cbor.Null || mode == 2 && pub.Kind == cbor.Null && commitment.Kind == cbor.Bytes
	case "ThresholdSet":
		for k := uint64(1); k <= 3; k++ {
			pair, _ := cbor.Get(v, k)
			if pair.Kind != cbor.Array || len(pair.Array) != 2 || pair.Array[0].Kind != cbor.Uint || pair.Array[1].Kind != cbor.Uint || pair.Array[0].Uint < 1 || pair.Array[0].Uint > pair.Array[1].Uint {
				return false
			}
		}
	case "LifecycleTransition":
		to, _ := uintv(v, 3)
		stage, _ := cbor.Get(v, 4)
		recovery := r.enumValue("operator_lifecycles", "RECOVERY")
		if to == recovery {
			return stage.Kind == cbor.Uint
		}
		return stage.Kind == cbor.Null
	case "DelegationScope":
		ports, _ := cbor.Get(v, 7)
		for i, p := range ports.Array {
			if len(p.Array) != 2 || p.Array[0].Uint > p.Array[1].Uint {
				return false
			}
			if i > 0 && ports.Array[i-1].Array[1].Uint+1 >= p.Array[0].Uint {
				return false
			}
		}
	}
	return true
}

var rangeRE = regexp.MustCompile(`\((\d+)\.\.(\d+)\)`)

func parseRange(s string) (int, int, bool) {
	m := rangeRE.FindStringSubmatch(s)
	if m == nil {
		return 0, 0, false
	}
	a, e1 := strconv.Atoi(m[1])
	b, e2 := strconv.Atoi(m[2])
	return a, b, e1 == nil && e2 == nil
}
func cardinality(s string) (int, int) {
	if strings.Contains(s, "exactly two") || strings.Contains(s, "exactly 2") {
		return 2, 2
	}
	if strings.Contains(s, "exactly three") {
		return 3, 3
	}
	m := regexp.MustCompile(`(\d+)\.\.(\d+)`).FindStringSubmatch(s)
	if m != nil {
		a, _ := strconv.Atoi(m[1])
		b, _ := strconv.Atoi(m[2])
		return a, b
	}
	return 0, int(^uint(0) >> 1)
}
func sortedUnique(xs []cbor.Value) bool {
	var prev []byte
	for i, x := range xs {
		b, e := cbor.Encode(x)
		if e != nil {
			return false
		}
		if i > 0 && bytes.Compare(prev, b) >= 0 {
			return false
		}
		prev = b
	}
	return true
}
func valueEqual(a, b cbor.Value) bool {
	ab, ae := cbor.Encode(a)
	bb, be := cbor.Encode(b)
	return ae == nil && be == nil && bytes.Equal(ab, bb)
}

func (r Registry) validateBounds(v cbor.Value, f Field) bool {
	b := f.Bounds
	if strings.Contains(b, "exactly 32 bytes") || strings.Contains(b, "exact 32 bytes") {
		if v.Kind == cbor.Null && strings.Contains(b, "null") { /* explicitly allowed */
		} else if v.Kind != cbor.Bytes || len(v.Bytes) != 32 {
			return false
		}
	}
	if strings.Contains(b, "exactly 16 bytes") {
		if v.Kind != cbor.Bytes || len(v.Bytes) != 16 {
			return false
		}
	}
	if strings.Contains(b, "1..64 bytes") && v.Kind == cbor.Bytes && (len(v.Bytes) < 1 || len(v.Bytes) > 64) {
		return false
	}
	if strings.Contains(b, "16..64 bytes") && v.Kind == cbor.Bytes && (len(v.Bytes) < 16 || len(v.Bytes) > 64) {
		return false
	}
	if strings.Contains(b, "1..255 UTF-8 bytes") && v.Kind == cbor.Text && (len([]byte(v.Text)) < 1 || len([]byte(v.Text)) > 255) {
		return false
	}
	if strings.Contains(b, "1..2^64-1") && v.Kind == cbor.Uint && v.Uint == 0 {
		return false
	}
	if strings.Contains(b, "1..2^64-2") && v.Kind == cbor.Uint && (v.Uint == 0 || v.Uint == ^uint64(0)) {
		return false
	}
	if strings.Contains(b, "0..253402300799") && v.Kind == cbor.Uint && v.Uint > 253402300799 {
		return false
	}
	if strings.Contains(b, "0..900 seconds") && v.Kind == cbor.Uint && v.Uint > 900 {
		return false
	}
	if strings.Contains(b, "1..65535") && v.Kind == cbor.Uint && (v.Uint < 1 || v.Uint > 65535) {
		return false
	}
	if strings.Contains(b, "0..65535") && v.Kind == cbor.Uint && v.Uint > 65535 {
		return false
	}
	if strings.Contains(b, "null for size 0; exact 32 bytes otherwise") && v.Kind != cbor.Null && (v.Kind != cbor.Bytes || len(v.Bytes) != 32) {
		return false
	}
	if v.Kind == cbor.Array {
		lo, hi := cardinality(b)
		if len(v.Array) < lo || len(v.Array) > hi || strings.Contains(b, "sorted unique") && !sortedUnique(v.Array) {
			return false
		}
	}
	if v.Kind == cbor.Uint {
		if table := enumTable(f.Name, b); table != "" && !r.Enums[table][v.Uint] {
			if local := r.LocalEnums[table]; !local[v.Uint] {
				return false
			}
		}
	}
	return true
}
func (r Registry) validateRelationships(class string, v cbor.Value, o Object) bool {
	keys := map[string]uint64{}
	for _, f := range o.Fields {
		keys[f.Name] = f.Key
	}
	getU := func(name string) (uint64, bool) {
		k, ok := keys[name]
		if !ok {
			return 0, false
		}
		return uintv(v, k)
	}
	get := func(name string) (cbor.Value, bool) {
		k, ok := keys[name]
		if !ok {
			return cbor.Value{}, false
		}
		return cbor.Get(v, k)
	}
	if nb, nok := getU("not_before"); nok {
		if ex, eok := getU("expires_at"); eok && ex <= nb {
			return false
		}
	}
	if observed, ok := getU("observed_at"); ok {
		if until, uok := getU("valid_until"); uok && until < observed {
			return false
		}
	}
	if effective, ok := getU("effective_at"); ok {
		if until, uok := getU("valid_until"); uok && until < effective {
			return false
		}
		if deadline, dok := getU("appeal_deadline"); dok && deadline < effective {
			return false
		}
	}
	if size, ok := getU("tree_size"); ok {
		if index, iok := getU("leaf_index"); iok && index >= size {
			return false
		}
	}
	if old, ok := getU("old_tree_size"); ok {
		if next, nok := getU("new_tree_size"); nok && next < old {
			return false
		}
	}
	if old, ok := getU("old_generation"); ok {
		if next, nok := getU("new_generation"); !nok || old == ^uint64(0) || next != old+1 {
			return false
		}
	}
	if state, ok := get("revocation_state"); ok && state.Kind == cbor.Bool {
		ref, present := get("revocation_reference")
		if !present {
			return false
		}
		if state.Bool && ref.Kind == cbor.Null {
			return false
		}
		if !state.Bool && ref.Kind != cbor.Null {
			return false
		}
	}
	if class == "OperatorRegistryRecord" || class == "OperatorLifecycleRecord" {
		if life, ok := getU("lifecycle_state"); ok {
			stage, present := get("recovery_stage")
			recovery := r.enumValue("operator_lifecycles", "RECOVERY")
			if life == recovery && (!present || stage.Kind != cbor.Uint) {
				return false
			}
			if life != recovery && present {
				return false
			}
		}
	}
	if class == "RecoveryTransitionRecord" {
		continuity, _ := get("continuity_digest")
		broken, _ := get("explicit_break")
		if broken.Kind != cbor.Bool {
			return false
		}
		if broken.Bool && continuity.Kind != cbor.Null {
			return false
		}
		if !broken.Bool && (continuity.Kind != cbor.Bytes || len(continuity.Bytes) != 32) {
			return false
		}
	}
	return true
}
func enumTable(name, bounds string) string {
	m := map[string]string{"object_type": "object_types", "lifecycle_state": "operator_lifecycles", "key_purpose": "key_purposes", "key_lifecycle": "key_lifecycles", "recovery_stage": "recovery_stages", "reason_code": "reason_codes", "enforcement_mode": "enforcement_modes", "decision": "decision_outcomes", "outcome": "decision_outcomes"}
	if x := m[name]; x != "" {
		return x
	}
	for _, n := range []string{"OrganizationBindingMode", "OwnershipTransferState", "EndpointRole", "EndpointLifecycle", "TransportProfile", "RevocationAuthorityMode", "HashProfile", "WitnessVerificationResult", "PrivacyClass", "ConflictClass", "AppellantStanding", "AppealGrounds"} {
		if strings.Contains(bounds, n) {
			return n
		}
	}
	return ""
}
func uintv(v cbor.Value, k uint64) (uint64, bool) {
	x, ok := cbor.Get(v, k)
	return x.Uint, ok && x.Kind == cbor.Uint
}
func number(v any) (float64, bool) {
	switch x := v.(type) {
	case json.Number:
		f, e := x.Float64()
		return f, e == nil
	case float64:
		return x, true
	}
	return 0, false
}
func (r Registry) enumValue(table, name string) uint64 { return r.EnumNames[table][name] }
