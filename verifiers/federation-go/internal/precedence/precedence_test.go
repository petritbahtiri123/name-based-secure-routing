package precedence

import "testing"

func TestSelectSimultaneousDefects(t *testing.T) {
	got, err := Select([]string{"ERR_FRESHNESS", "ERR_SCHEMA", "ERR_RESOURCE_LIMIT", "ERR_SIGNATURE_INVALID"})
	if err != nil || got != "ERR_RESOURCE_LIMIT" {
		t.Fatalf("got %q, %v", got, err)
	}
	got, err = Select([]string{"ERR_LOCAL_POLICY", "ERR_ROLLBACK", "ERR_AUTHORITY"})
	if err != nil || got != "ERR_AUTHORITY" {
		t.Fatalf("got %q, %v", got, err)
	}
}
