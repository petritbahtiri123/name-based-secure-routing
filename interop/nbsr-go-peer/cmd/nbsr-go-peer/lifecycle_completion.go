package main

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

func lifecycleCompletionPath(root string, ordinal int) string {
	return filepath.Join(root, fmt.Sprintf("destination-%d.complete", ordinal))
}

func requireFreshLifecycleCompletion(root string, ordinal int) error {
	_, err := os.Lstat(lifecycleCompletionPath(root, ordinal))
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		return err
	}
	return errors.New("stale lifecycle destination completion marker")
}

// This local benchmark barrier preserves the destination's real send-ACK wait.
// It is not a wire acknowledgment or a production transport operation.
func finishLifecycleConnection(ctx context.Context, root string, ordinal int, waitDestination bool, closePeer func() error) (resultErr error) {
	defer func() { resultErr = errors.Join(resultErr, closePeer()) }()
	if waitDestination {
		for {
			if err := ctx.Err(); err != nil {
				return err
			}
			data, err := os.ReadFile(lifecycleCompletionPath(root, ordinal))
			if err == nil {
				if string(data) != "complete\n" {
					return errors.New("invalid lifecycle destination completion marker")
				}
				break
			}
			if !os.IsNotExist(err) {
				return err
			}
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(10 * time.Millisecond):
			}
		}
	}
	return os.WriteFile(filepath.Join(root, fmt.Sprintf("connection-%d.ack", ordinal)), []byte("complete\n"), 0600)
}
