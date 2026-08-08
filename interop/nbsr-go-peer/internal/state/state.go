// Package state implements the independent source peer's monotonic admission
// sequence. Any invalid transition is terminal and cannot enable payload.
package state

import "errors"

type phase uint8

const (
	newPhase phase = iota
	helloSentPhase
	helloAcceptedPhase
	routeSentPhase
	routeAcceptedPhase
	streamSentPhase
	payloadAllowedPhase
	failedPhase
)

type Source struct {
	phase           phase
	sessionID       [16]byte
	helloRequestID  [16]byte
	routeRequestID  [16]byte
	streamRequestID [16]byte
	channelID       [16]byte
	routeID         [16]byte
	service         string
	transport       string
	port            uint16
	streamID        uint64
}

func NewSource(session, helloRequest, routeRequest, streamRequest, channel, route [16]byte, service, transport string, port uint16) *Source {
	return &Source{phase: newPhase, sessionID: session, helloRequestID: helloRequest, routeRequestID: routeRequest, streamRequestID: streamRequest, channelID: channel, routeID: route, service: service, transport: transport, port: port}
}

func (source *Source) transition(expected, next phase) error {
	if source.phase != expected {
		source.phase = failedPhase
		return errors.New("invalid or replayed state transition")
	}
	source.phase = next
	return nil
}

func (source *Source) HelloSent() error { return source.transition(newPhase, helloSentPhase) }

func (source *Source) EdgeHelloAccepted(session, request [16]byte) error {
	if source.phase != helloSentPhase || session != source.sessionID || request != source.helloRequestID {
		source.phase = failedPhase
		return errors.New("EDGE_HELLO correlation mismatch")
	}
	source.phase = helloAcceptedPhase
	return nil
}

func (source *Source) RouteSent(service, transport string, port uint16) error {
	if source.phase != helloAcceptedPhase || service != source.service || transport != source.transport || port != source.port {
		source.phase = failedPhase
		return errors.New("route authority binding mismatch")
	}
	source.phase = routeSentPhase
	return nil
}

func (source *Source) RouteAccepted(session, request, channel, route [16]byte) error {
	if source.phase != routeSentPhase || session != source.sessionID || request != source.routeRequestID || channel != source.channelID || route != source.routeID {
		source.phase = failedPhase
		return errors.New("ROUTE_ACCEPT correlation mismatch")
	}
	source.phase = routeAcceptedPhase
	return nil
}

func (source *Source) StreamSent(streamID uint64) error {
	if source.phase != routeAcceptedPhase || streamID < 4 || streamID > (1<<62)-1 || streamID%4 != 0 {
		source.phase = failedPhase
		return errors.New("invalid application stream")
	}
	source.streamID = streamID
	source.phase = streamSentPhase
	return nil
}

func (source *Source) StreamAccepted(session, request [16]byte, streamID uint64, channel, route [16]byte) error {
	if source.phase != streamSentPhase || session != source.sessionID || request != source.streamRequestID || streamID != source.streamID || channel != source.channelID || route != source.routeID {
		source.phase = failedPhase
		return errors.New("STREAM_ACCEPT correlation mismatch")
	}
	source.phase = payloadAllowedPhase
	return nil
}

func (source *Source) PayloadAllowed() bool { return source.phase == payloadAllowedPhase }

// NextStream returns an already accepted Service Channel to its route-accepted
// state while replacing only the per-stream correlation authority. It cannot
// create a route or inherit payload authority from the previous stream.
func (source *Source) NextStream(request [16]byte) error {
	if source.phase != payloadAllowedPhase || request == [16]byte{} || request == source.streamRequestID {
		source.phase = failedPhase
		return errors.New("next stream requires a distinct accepted-stream correlation")
	}
	source.streamRequestID = request
	source.streamID = 0
	source.phase = routeAcceptedPhase
	return nil
}
