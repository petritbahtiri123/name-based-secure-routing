// Package retry computes finite local retry decisions from caller-supplied
// values. It performs no I/O, starts no goroutines, sleeps never, and has no
// authority or application-payload dependencies, including no
// authority-provider operations.
package retry
