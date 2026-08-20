// Package authority defines the local-only authority-provider boundary, its
// bounded manager foundation, and the frozen transport-neutral ACP wire codec.
// It does not define a remote authority service or provider transport.
//
// BASELINE ONLY — NOT ACCEPTANCE CAPACITY: local benchmark observations are
// not capacity targets or acceptance evidence. Fixed-state hot-path checks make
// no provider calls, I/O, or wire parsing.
package authority
