package state_test

import (
	"testing"

	"nbsr.local/interop/nbsr-go-peer/internal/state"
)

func IDs() (session, helloRequest, routeRequest, streamRequest, channel, route [16]byte) {
	for index := 0; index < 16; index++ {
		session[index] = byte(0x10 + index)
		helloRequest[index] = byte(index)
		routeRequest[index] = byte(0x30 + index)
		streamRequest[index] = byte(0x50 + index)
		channel[index] = byte(0x40 + index)
		route[index] = byte(0x20 + index)
	}
	return
}

func TestSourceStateAllowsPayloadOnlyAfterCorrelatedAccepts(t *testing.T) {
	session, hello, routeRequest, streamRequest, channel, route := IDs()
	peer := state.NewSource(session, hello, routeRequest, streamRequest, channel, route, "service.example", "tcp", 8443)
	if peer.PayloadAllowed() {
		t.Fatal("payload allowed in NEW")
	}
	if err := peer.HelloSent(); err != nil {
		t.Fatal(err)
	}
	if err := peer.EdgeHelloAccepted(session, hello); err != nil {
		t.Fatal(err)
	}
	if err := peer.RouteSent("service.example", "tcp", 8443); err != nil {
		t.Fatal(err)
	}
	if err := peer.RouteAccepted(session, routeRequest, channel, route); err != nil {
		t.Fatal(err)
	}
	if err := peer.StreamSent(4); err != nil {
		t.Fatal(err)
	}
	if peer.PayloadAllowed() {
		t.Fatal("payload allowed before STREAM_ACCEPT")
	}
	if err := peer.StreamAccepted(session, streamRequest, 4, channel, route); err != nil {
		t.Fatal(err)
	}
	if !peer.PayloadAllowed() {
		t.Fatal("payload not allowed after correlated STREAM_ACCEPT")
	}
}

func TestWrongCorrelationAndReplayFailWithoutOpeningPayload(t *testing.T) {
	session, hello, routeRequest, streamRequest, channel, route := IDs()
	wrong := session
	wrong[0] ^= 1
	peer := state.NewSource(session, hello, routeRequest, streamRequest, channel, route, "service.example", "tcp", 8443)
	if err := peer.HelloSent(); err != nil {
		t.Fatal(err)
	}
	if err := peer.EdgeHelloAccepted(wrong, hello); err == nil {
		t.Fatal("accepted wrong session")
	}
	if peer.PayloadAllowed() {
		t.Fatal("payload allowed after wrong correlation")
	}

	peer = state.NewSource(session, hello, routeRequest, streamRequest, channel, route, "service.example", "tcp", 8443)
	_ = peer.HelloSent()
	_ = peer.EdgeHelloAccepted(session, hello)
	_ = peer.RouteSent("service.example", "tcp", 8443)
	_ = peer.RouteAccepted(session, routeRequest, channel, route)
	_ = peer.StreamSent(4)
	if err := peer.StreamAccepted(session, streamRequest, 8, channel, route); err == nil {
		t.Fatal("accepted wrong stream")
	}
	if peer.PayloadAllowed() {
		t.Fatal("payload allowed after wrong stream")
	}
	if err := peer.StreamAccepted(session, streamRequest, 4, channel, route); err == nil {
		t.Fatal("terminal failure resurrected")
	}
}

func TestEveryAcceptCorrelationAndTransitionMustMatch(t *testing.T) {
	session, hello, routeRequest, streamRequest, channel, route := IDs()
	mutations := []struct {
		name  string
		apply func(*[16]byte, *[16]byte, *[16]byte, *[16]byte, *uint64)
	}{
		{"request", func(_ *[16]byte, request *[16]byte, _ *[16]byte, _ *[16]byte, _ *uint64) { request[0] ^= 1 }},
		{"channel", func(_ *[16]byte, _ *[16]byte, value *[16]byte, _ *[16]byte, _ *uint64) { value[0] ^= 1 }},
		{"route", func(_ *[16]byte, _ *[16]byte, _ *[16]byte, value *[16]byte, _ *uint64) { value[0] ^= 1 }},
		{"stream", func(_ *[16]byte, _ *[16]byte, _ *[16]byte, _ *[16]byte, value *uint64) { *value = 8 }},
	}
	for _, mutation := range mutations {
		t.Run(mutation.name, func(t *testing.T) {
			peer := state.NewSource(session, hello, routeRequest, streamRequest, channel, route, "service.example", "tcp", 8443)
			_ = peer.HelloSent()
			_ = peer.EdgeHelloAccepted(session, hello)
			_ = peer.RouteSent("service.example", "tcp", 8443)
			_ = peer.RouteAccepted(session, routeRequest, channel, route)
			_ = peer.StreamSent(4)
			gotSession, gotRequest, gotChannel, gotRoute, gotStream := session, streamRequest, channel, route, uint64(4)
			mutation.apply(&gotSession, &gotRequest, &gotChannel, &gotRoute, &gotStream)
			if err := peer.StreamAccepted(gotSession, gotRequest, gotStream, gotChannel, gotRoute); err == nil || peer.PayloadAllowed() {
				t.Fatal("mismatched accept enabled payload")
			}
		})
	}
}

func TestRouteServiceTransportAndPortAreImmutableAuthority(t *testing.T) {
	session, hello, routeRequest, streamRequest, channel, route := IDs()
	for _, binding := range []struct {
		service, transport string
		port               uint16
	}{
		{"other.example", "tcp", 8443}, {"service.example", "udp", 8443}, {"service.example", "tcp", 443},
	} {
		peer := state.NewSource(session, hello, routeRequest, streamRequest, channel, route, "service.example", "tcp", 8443)
		_ = peer.HelloSent()
		_ = peer.EdgeHelloAccepted(session, hello)
		if err := peer.RouteSent(binding.service, binding.transport, binding.port); err == nil || peer.PayloadAllowed() {
			t.Fatal("mismatched route authority advanced state")
		}
	}
}

func TestAcceptedChannelCanAuthorizeASecondIndependentStream(t *testing.T) {
	session, hello, routeRequest, streamRequest, channel, route := IDs()
	peer := state.NewSource(session, hello, routeRequest, streamRequest, channel, route, "service.example", "tcp", 8443)
	_ = peer.HelloSent()
	_ = peer.EdgeHelloAccepted(session, hello)
	_ = peer.RouteSent("service.example", "tcp", 8443)
	_ = peer.RouteAccepted(session, routeRequest, channel, route)
	_ = peer.StreamSent(4)
	_ = peer.StreamAccepted(session, streamRequest, 4, channel, route)
	nextRequest := streamRequest
	nextRequest[15]++
	if err := peer.NextStream(nextRequest); err != nil {
		t.Fatal(err)
	}
	if peer.PayloadAllowed() {
		t.Fatal("next stream inherited payload authority")
	}
	if err := peer.StreamSent(8); err != nil {
		t.Fatal(err)
	}
	if err := peer.StreamAccepted(session, nextRequest, 8, channel, route); err != nil {
		t.Fatal(err)
	}
	if !peer.PayloadAllowed() {
		t.Fatal("second accepted stream did not open payload gate")
	}
}

func TestNextStreamCannotBypassPriorStreamAcceptance(t *testing.T) {
	session, hello, routeRequest, streamRequest, channel, route := IDs()
	peer := state.NewSource(session, hello, routeRequest, streamRequest, channel, route, "service.example", "tcp", 8443)
	if err := peer.NextStream(streamRequest); err == nil {
		t.Fatal("next stream bypassed accepted route and stream")
	}
}
