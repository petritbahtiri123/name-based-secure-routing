// Package authority defines the local-only authority-provider boundary and
// its bounded manager foundation. It does not define ACP wire behavior, a
// remote authority service, provider transport, or an authority-control-plane
// wire format.
//
// BASELINE ONLY — NOT ACCEPTANCE CAPACITY: local benchmark observations are
// not capacity targets or acceptance evidence. Fixed-state hot-path checks make
// no provider calls, I/O, or wire parsing.
package authority
