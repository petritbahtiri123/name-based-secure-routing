package strictjson

import (
	"strings"
	"testing"
)

type sample struct {
	Value int `json:"value"`
}

func TestJSONDepthBound(t *testing.T) {
	at := strings.Repeat("[", 96) + "0" + strings.Repeat("]", 96)
	if err := Validate([]byte(at)); err != nil {
		t.Fatalf("accepted boundary rejected: %v", err)
	}
	over := "[" + at + "]"
	if err := Validate([]byte(over)); err == nil || !strings.Contains(err.Error(), "depth") {
		t.Fatalf("over-depth input not rejected correctly: %v", err)
	}
}

func TestRejectsDuplicateAndUnknownKeys(t *testing.T) {
	for _, raw := range []string{`{"value":1,"value":2}`, `{"value":1,"extra":2}`} {
		var got sample
		if err := Decode([]byte(raw), &got); err == nil {
			t.Fatalf("accepted %s", raw)
		}
	}
}

func TestJSONSafeIntegerBoundary(t *testing.T) {
	if err := Validate([]byte(`{"value":9007199254740991}`)); err != nil {
		t.Fatalf("safe integer boundary rejected: %v", err)
	}
	for _, raw := range []string{`{"value":9007199254740992}`, `{"value":-9007199254740992}`} {
		if err := Validate([]byte(raw)); err == nil {
			t.Fatalf("unsafe integer accepted: %s", raw)
		}
	}
}
