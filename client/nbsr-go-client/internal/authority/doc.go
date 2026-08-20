// Package authority defines the local-only authority-provider boundary and its
// bounded manager foundation. It also contains the frozen ACP/enrollment wire,
// HTTP/2 clients, and the minimal Source Operator remote authority service
// runtime for those same codecs.
//
// BASELINE ONLY — NOT ACCEPTANCE CAPACITY: local benchmark observations are
// not capacity targets or acceptance evidence. Fixed-state hot-path checks make
// no provider calls, I/O, or wire parsing.
package authority
