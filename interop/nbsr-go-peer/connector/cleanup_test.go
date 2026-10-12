//go:build connector_development

package connector

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"
)

// The callback provider is an explicitly simulated close backend, not a socket.
func cleanupFixture(t *testing.T) (*Coordinator, *CleanupPeer, *[]func(error)) {
	t.Helper()
	c, p, _, _ := fixtureSetup(t)
	if err := c.Begin(fixtureRequest(t)); err != nil {
		t.Fatal(err)
	}
	callbacks := []func(error){}
	wrapped, err := NewCleanupPeer(p, func(done func(error)) { callbacks = append(callbacks, done) })
	if err != nil {
		t.Fatal(err)
	}
	c.peer = wrapped
	return c, wrapped, &callbacks
}
func retained(t *testing.T, c *Coordinator) {
	t.Helper()
	if c.peer == nil || c.Owner() == nil || c.Owner().Eligible {
		t.Fatal("cleanup lost owner or retained eligibility")
	}
}

func TestAsyncCleanupWaitCancellationRetainsOwner(t *testing.T) {
	c, p, callbacks := cleanupFixture(t)
	if !errors.Is(c.Close(), ErrCleanupPending) {
		t.Fatal("unconfirmed cleanup not pending")
	}
	retained(t, c)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if !errors.Is(p.WaitCleanup(ctx), context.Canceled) {
		t.Fatal("wait cancellation hidden")
	}
	retained(t, c)
	if !errors.Is(c.Close(), ErrCleanupPending) || len(*callbacks) != 1 {
		t.Fatal("duplicate close attempt")
	}
	if c.Connect(&fixtureDialer{}) == nil {
		t.Fatal("replacement before cleanup")
	}
	(*callbacks)[0](nil)
	if err := p.WaitCleanup(context.Background()); err != nil {
		t.Fatal(err)
	}
	retained(t, c) // Callback does not mutate the serialized coordinator.
	if err := c.Close(); err != nil {
		t.Fatal(err)
	}
	if c.peer != nil || c.Owner() != nil {
		t.Fatal("confirmed cleanup not released")
	}
}

func TestAsyncCleanupWaitDeadlineAndLateCompletion(t *testing.T) {
	c, p, callbacks := cleanupFixture(t)
	_ = c.Close()
	ctx, cancel := context.WithDeadline(context.Background(), time.Unix(0, 0))
	defer cancel()
	if !errors.Is(p.WaitCleanup(ctx), context.DeadlineExceeded) {
		t.Fatal("deadline did not expire")
	}
	retained(t, c)
	(*callbacks)[0](nil)
	if err := c.Close(); err != nil {
		t.Fatal(err)
	}
	// Duplicate late completions cannot restore/remove a different coordinator.
	replacement, _, _, _ := fixtureSetup(t)
	if err := replacement.Begin(fixtureRequest(t)); err != nil {
		t.Fatal(err)
	}
	owner := *replacement.Owner()
	(*callbacks)[0](errors.New("late duplicate"))
	(*callbacks)[0](nil)
	if *replacement.Owner() != owner {
		t.Fatal("late callback touched replacement")
	}
}

func TestAsyncCleanupFailedCloseRequiresExplicitRetry(t *testing.T) {
	c, p, callbacks := cleanupFixture(t)
	_ = c.Close()
	failure := errors.New("explicit fixture failure")
	(*callbacks)[0](failure)
	if !errors.Is(p.WaitCleanup(context.Background()), failure) || !errors.Is(c.Close(), failure) {
		t.Fatal("failure hidden")
	}
	retained(t, c)
	(*callbacks)[0](nil)
	if !errors.Is(c.Close(), failure) || len(*callbacks) != 1 {
		t.Fatal("duplicate failure became success or retried")
	}
	if !errors.Is(p.RetryCleanup(), ErrCleanupPending) || len(*callbacks) != 2 {
		t.Fatal("explicit retry did not start once")
	}
	if p.RetryCleanup() == nil || len(*callbacks) != 2 {
		t.Fatal("parallel cleanup attempt")
	}
	(*callbacks)[0](nil)
	if !errors.Is(c.Close(), ErrCleanupPending) {
		t.Fatal("stale completion released retry")
	}
	(*callbacks)[1](nil)
	if err := c.Close(); err != nil {
		t.Fatal(err)
	}
	if c.Owner() != nil || c.peer != nil {
		t.Fatal("confirmed retry leaked owner")
	}
	if p.RetryCleanup() == nil || len(*callbacks) != 2 {
		t.Fatal("retried confirmed cleanup")
	}
}

func TestAsyncCleanupWaitUsesNotificationAndDuplicateCallbackIsSafe(t *testing.T) {
	c, p, callbacks := cleanupFixture(t)
	_ = c.Close()
	result := make(chan error, 1)
	started := make(chan struct{})
	go func() { close(started); result <- p.WaitCleanup(context.Background()) }()
	<-started
	var group sync.WaitGroup
	for i := 0; i < 8; i++ {
		group.Add(1)
		go func() { defer group.Done(); (*callbacks)[0](nil) }()
	}
	group.Wait()
	if err := <-result; err != nil {
		t.Fatal(err)
	}
	if err := c.Close(); err != nil {
		t.Fatal(err)
	}
	if len(*callbacks) != 1 {
		t.Fatal("multiple operations")
	}
}

func TestAsyncCleanupPendingAttemptCannotResumeProof(t *testing.T) {
	c, base, _, _ := fixtureSetup(t)
	base.dropAccept = true
	_ = c.Begin(fixtureRequest(t))
	callbacks := []func(error){}
	p, err := NewCleanupPeer(base, func(done func(error)) { callbacks = append(callbacks, done) })
	if err != nil {
		t.Fatal(err)
	}
	c.peer = p
	_ = c.Close()
	before := len(base.seen)
	if c.Retry() == nil || len(base.seen) != before || c.peer == nil {
		t.Fatal("pending proof resumed or quota released")
	}
	callbacks[0](nil)
	if err := c.Close(); err != nil {
		t.Fatal(err)
	}
}

func TestAsyncCleanupImmediateCompletionAndInvalidInputs(t *testing.T) {
	_, base, _, _ := fixtureSetup(t)
	if _, err := NewCleanupPeer(nil, func(func(error)) {}); err == nil {
		t.Fatal("missing peer")
	}
	if _, err := NewCleanupPeer(base, nil); err == nil {
		t.Fatal("missing cleanup backend")
	}
	p, err := NewCleanupPeer(base, func(done func(error)) { done(nil) })
	if err != nil {
		t.Fatal(err)
	}
	if p.WaitCleanup(context.Background()) == nil || p.RetryCleanup() == nil {
		t.Fatal("unstarted cleanup completed")
	}
	if p.WaitCleanup(nil) == nil {
		t.Fatal("nil wait context")
	}
	if err := p.Close(); err != nil {
		t.Fatal(err)
	}
	if err := p.WaitCleanup(context.Background()); err != nil {
		t.Fatal(err)
	}
}

// A controlled context event makes the waiting branch deterministic without
// sleeps or a production deadline policy. Done signals entry into select.
type cleanupWaitContext struct {
	context.Context
	entered chan struct{}
	once    sync.Once
	outcome error
}

func (c *cleanupWaitContext) Done() <-chan struct{} {
	c.once.Do(func() { close(c.entered) })
	return c.Context.Done()
}
func (c *cleanupWaitContext) Err() error {
	if c.Context.Err() != nil {
		return c.outcome
	}
	return nil
}

func TestAsyncCleanupCancellationWhileWaiting(t *testing.T) {
	for _, outcome := range []error{context.Canceled, context.DeadlineExceeded} {
		t.Run(outcome.Error(), func(t *testing.T) {
			c, p, callbacks := cleanupFixture(t)
			_ = c.Close()
			base, cancel := context.WithCancel(context.Background())
			defer cancel()
			ctx := &cleanupWaitContext{Context: base, entered: make(chan struct{}), outcome: outcome}
			result := make(chan error, 1)
			go func() { result <- p.WaitCleanup(ctx) }()
			<-ctx.entered
			cancel()
			if err := <-result; !errors.Is(err, outcome) {
				t.Fatalf("wait result %v", err)
			}
			retained(t, c)
			if !errors.Is(c.Close(), ErrCleanupPending) || len(*callbacks) != 1 {
				t.Fatal("wait cancelled cleanup or restarted it")
			}
			(*callbacks)[0](nil)
			retained(t, c)
			if err := c.Close(); err != nil {
				t.Fatal(err)
			}
			if c.Owner() != nil || c.peer != nil {
				t.Fatal("late confirmed close leaked owner")
			}
		})
	}
}
