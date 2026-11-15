package authority

import (
	"context"
	"crypto/tls"
	"errors"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"sync"
	"syscall"
	"testing"
	"time"
)

type diagnosticTransport struct {
	err   error
	calls int
}

func (d *diagnosticTransport) RoundTrip(*http.Request) (*http.Response, error) {
	d.calls++
	return nil, d.err
}
func TestDiagnosticDoesNotChangeTransportOutcome(t *testing.T) {
	for _, tc := range []struct {
		name string
		err  error
		want TransportDiagnostic
	}{{"deadline", context.DeadlineExceeded, TransportDeadline}, {"EOF", io.EOF, TransportEOF}} {
		for _, mode := range []string{"nil", "buffered", "unread", "full", "closed"} {
			t.Run(tc.name+"/"+mode, func(t *testing.T) {
				var ch chan TransportDiagnostic
				if mode != "nil" {
					ch = make(chan TransportDiagnostic, 1)
				}
				if mode == "unread" {
					ch = make(chan TransportDiagnostic)
				}
				if mode == "full" {
					ch <- TransportOther
				}
				if mode == "closed" {
					close(ch)
				}
				c, err := newBoundedHTTP2Client("https://localhost", &tls.Config{}, HTTPProviderOptions{MaxAttempts: 1, AttemptTimeout: 2 * time.Second})
				if err != nil {
					t.Fatal(err)
				}
				defer c.Close()
				d := &diagnosticTransport{err: tc.err}
				c.client.Transport = d
				c.diagnostics = ch
				_, err = c.Post(context.Background(), "/acp/authority", []byte{1}, 10, 130, func() uint64 { return 100 })
				if !errors.Is(err, ErrRequestAmbiguous) || d.calls != 1 || c.attemptTimeout != 2*time.Second {
					t.Fatalf("outcome changed: %v calls=%d", err, d.calls)
				}
				if mode == "buffered" {
					select {
					case got := <-ch:
						if got != tc.want {
							t.Fatalf("kind=%v", got)
						}
					default:
						t.Fatal("missing hint")
					}
				}
			})
		}
	}
}

type hostileDiagnosticError struct{}

func (hostileDiagnosticError) Error() string   { panic("Error invoked") }
func (hostileDiagnosticError) Is(error) bool   { panic("Is invoked") }
func (hostileDiagnosticError) As(any) bool     { panic("As invoked") }
func (hostileDiagnosticError) Unwrap() error   { panic("Unwrap invoked") }
func (hostileDiagnosticError) Timeout() bool   { panic("Timeout invoked") }
func (hostileDiagnosticError) Temporary() bool { panic("Temporary invoked") }
func TestDiagnosticClassificationNoCustomMethods(t *testing.T) {
	cycle := &url.Error{}
	cycle.Err = cycle
	for _, tc := range []struct {
		name string
		err  error
		want TransportDiagnostic
	}{
		{"cancel", context.Canceled, TransportCanceled}, {"unexpectedEOF", io.ErrUnexpectedEOF, TransportEOF},
		{"wrappedDeadline", &url.Error{Err: &net.OpError{Err: context.DeadlineExceeded}}, TransportDeadline},
		{"networkTimeout", &net.OpError{Err: &os.SyscallError{Err: syscall.ETIMEDOUT}}, TransportNetworkTimeout},
		{"osDeadline", os.ErrDeadlineExceeded, TransportNetworkTimeout},
		{"networkOther", &net.OpError{Err: errors.New("private detail")}, TransportNetworkOther},
		{"other", errors.New("private detail"), TransportOther}, {"customMethods", hostileDiagnosticError{}, TransportOther},
		{"cyclic", cycle, TransportOther}, {"nilPointer", (*net.OpError)(nil), TransportOther},
	} {
		t.Run(tc.name, func(t *testing.T) {
			ch := make(chan TransportDiagnostic, 1)
			emitTransportDiagnostic(ch, tc.err)
			select {
			case got := <-ch:
				if got != tc.want {
					t.Fatalf("kind %d want %d", got, tc.want)
				}
			default:
				t.Fatal("hint absent")
			}
		})
	}
}
func TestDiagnosticConcurrentSendersAndReceiver(t *testing.T) {
	ch := make(chan TransportDiagnostic, 4)
	done := make(chan struct{})
	var received sync.WaitGroup
	received.Add(1)
	go func() {
		defer received.Done()
		for {
			select {
			case k := <-ch:
				if k != TransportEOF {
					t.Errorf("unexpected kind %d", k)
				}
			case <-done:
				return
			}
		}
	}()
	var senders sync.WaitGroup
	for i := 0; i < 8; i++ {
		senders.Add(1)
		go func() {
			defer senders.Done()
			for j := 0; j < 100; j++ {
				emitTransportDiagnostic(ch, io.EOF)
			}
		}()
	}
	senders.Wait()
	close(done)
	received.Wait() // Diagnostic channel is not closed while active.
}
