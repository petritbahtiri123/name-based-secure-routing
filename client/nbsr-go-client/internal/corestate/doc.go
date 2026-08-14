// Package corestate provides bounded, ephemeral client core-state foundations.
//
// A ServiceHandle is a local-only lookup handle; channel_id remains the wire identity and is never replaced by a ServiceHandle. Store implements separate
// mapping, service, and stream registries. Configured entry and byte limits
// bound the logical state in those registries: logical bytes are not heap bytes
// and are not an allocation limit.
//
// Callers drive teardown through the registry lifecycle operations so closed
// generations, services, and streams release their associated state. The
// state is ephemeral and has no persistence or recovery role. This package has
// no network behavior: it does not establish connections, send or receive
// protocol messages, authenticate peers, or make authorization decisions.
package corestate
