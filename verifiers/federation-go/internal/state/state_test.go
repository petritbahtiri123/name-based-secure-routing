package state

import "testing"

func baseEvent() Event {
	return Event{Dependencies: []string{}, Generation: 1, Key: "terminal", ObjectDigest: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", ObjectKind: "terminal", Operation: "apply", OperatorID: "4141414141414141414141414141414141414141414141414141414141414141", PeerOperatorID: "4242424242424242424242424242424242424242424242424242424242424242", Sequence: 1, ServiceID: "5353535353535353535353535353535353535353535353535353535353535353", Terminal: true, ValidationFailures: []string{}}
}
func TestTerminalReplayCannotResurrect(t *testing.T) {
	s := Initial()
	e := baseEvent()
	if g := Decide(&s, e, 1900000000); g.Outcome != "ACCEPT" {
		t.Fatal(g)
	}
	before := Digest(s)
	g := Decide(&s, e, 1900000001)
	if g.Reason != "ERR_TERMINAL_STATE" || g.Mutation || Digest(s) != before {
		t.Fatalf("terminal replay %#v", g)
	}
}
func TestFutureFreshnessFailsClosed(t *testing.T) {
	s := Initial()
	future := uint64(200)
	e := baseEvent()
	e.Terminal = false
	e.Operation = "existing_context"
	e.SourceFreshAt = &future
	g := Decide(&s, e, 100)
	if g.Reason != "ERR_FRESHNESS" || g.Mutation {
		t.Fatalf("future freshness %#v", g)
	}
}
