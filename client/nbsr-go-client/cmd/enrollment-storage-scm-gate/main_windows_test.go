//go:build windows

package main

import "testing"

func TestGateFixtureAndMarkersAreDeterministic(t *testing.T) {
	first := enrollmentFixture()
	second := enrollmentFixture()
	if first != second {
		t.Fatal("enrollment fixture is not deterministic")
	}
	if first.ID == ([32]byte{}) || first.SigningKey.ID == ([32]byte{}) || first.SigningKey.Thumbprint == ([32]byte{}) {
		t.Fatal("enrollment fixture contains a zero identity field")
	}
	for _, marker := range []string{"store.json", "load-1.json", "load-2.json"} {
		if !validMarker(marker) {
			t.Fatalf("validMarker(%q) = false", marker)
		}
	}
	for _, marker := range []string{"", `..\outside.json`, "not-json.txt"} {
		if validMarker(marker) {
			t.Fatalf("validMarker(%q) = true", marker)
		}
	}
}
