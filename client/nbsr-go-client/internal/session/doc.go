// Package session owns bounded production-client Transport Session and Service
// Channel lifecycle state.
//
// A Transport Session is keyed by its complete reuse context and bound to one
// sealed authority generation plus one generation-specific TS proof key. At
// most two generations exist for a reuse key, and only one may be CURRENT; a
// caller must explicitly mark the old generation DRAINING before constructing
// its successor. This package deliberately does not choose rotation policy.
//
// Service Channel creation is two phase. The manager captures the TS and
// authority context, releases its mutex for wire I/O, then revalidates both
// contexts before consuming the single-use grant and publishing the channel.
// ServiceHandle is a nonzero, monotonically allocated local alias. The existing
// channel_id remains the independent wire identity and is never derived from or
// replaced by ServiceHandle.
//
// The package owns no Stream Credit or Application Stream state.
package session
