//go:build windows

// Command enrollment-storage-scm-gate is a test-only Windows service used to
// verify enrollment storage across real SCM restarts. It performs no network IO.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"golang.org/x/sys/windows"
	"golang.org/x/sys/windows/svc"

	"nbsr.local/client/nbsr-go-client/internal/authority"
	"nbsr.local/client/nbsr-go-client/internal/identity"
)

const serviceName = "NBSRClient"

type gateRequest struct {
	Action string `json:"action"`
	Marker string `json:"marker"`
}

type gateEvidence struct {
	Action         string `json:"action"`
	Success        bool   `json:"success"`
	Error          string `json:"error,omitempty"`
	PID            int    `json:"pid"`
	Account        string `json:"account"`
	SID            string `json:"sid"`
	UserProfile    string `json:"user_profile"`
	AppData        string `json:"app_data"`
	LocalAppData   string `json:"local_app_data"`
	EnrollmentRoot string `json:"enrollment_root"`
	IdentityMatch  bool   `json:"identity_match"`
	Ready          bool   `json:"ready"`
}

type serviceHandler struct {
	evidenceRoot string
}

func main() {
	if len(os.Args) != 3 || os.Args[1] != "--evidence" {
		fmt.Fprintln(os.Stderr, "usage: enrollment-storage-scm-gate --evidence <trusted-test-directory>")
		os.Exit(2)
	}
	if err := svc.Run(serviceName, &serviceHandler{evidenceRoot: os.Args[2]}); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func (handler *serviceHandler) Execute(_ []string, requests <-chan svc.ChangeRequest, status chan<- svc.Status) (bool, uint32) {
	status <- svc.Status{State: svc.StartPending}
	status <- svc.Status{State: svc.Running, Accepts: svc.AcceptStop | svc.AcceptShutdown}
	handler.runGate()
	for request := range requests {
		switch request.Cmd {
		case svc.Interrogate:
			status <- request.CurrentStatus
		case svc.Stop, svc.Shutdown:
			status <- svc.Status{State: svc.StopPending}
			return false, 0
		}
	}
	return false, 0
}

func (handler *serviceHandler) runGate() {
	requestPath := filepath.Join(handler.evidenceRoot, "request.json")
	raw, err := os.ReadFile(requestPath)
	if err != nil {
		return
	}
	var request gateRequest
	if err := json.Unmarshal(raw, &request); err != nil || !validMarker(request.Marker) {
		return
	}
	evidence := executeGate(strings.ToUpper(strings.TrimSpace(request.Action)))
	encoded, err := json.MarshalIndent(evidence, "", "  ")
	if err != nil {
		return
	}
	temp := filepath.Join(handler.evidenceRoot, request.Marker+".tmp")
	final := filepath.Join(handler.evidenceRoot, request.Marker)
	if err := os.WriteFile(temp, encoded, 0o600); err == nil {
		_ = os.Rename(temp, final)
	}
}

func validMarker(marker string) bool {
	return marker != "" && filepath.Base(marker) == marker && strings.HasSuffix(strings.ToLower(marker), ".json")
}

func executeGate(action string) gateEvidence {
	evidence := processEvidence(action)
	paths, err := authority.ResolveEnrollmentStatePaths()
	if err != nil {
		return failedEvidence(evidence, err)
	}
	evidence.EnrollmentRoot = paths.Root
	store, err := authority.NewFileEnrollmentStateStore()
	if err != nil {
		return failedEvidence(evidence, err)
	}
	expected := enrollmentFixture()
	ctx := context.Background()
	switch action {
	case "STORE":
		if err := store.Store(ctx, expected); err != nil {
			return failedEvidence(evidence, err)
		}
	case "LOAD":
	default:
		return failedEvidence(evidence, errors.New("unsupported gate action"))
	}
	loaded, err := authority.LoadEnrollmentState(ctx, store, uint64(time.Now().Unix()))
	if err != nil {
		return failedEvidence(evidence, err)
	}
	evidence.IdentityMatch = loaded.Identity == expected
	evidence.Ready = loaded.Ready
	if !evidence.IdentityMatch {
		return failedEvidence(evidence, errors.New("loaded identity mismatch"))
	}
	if evidence.Ready {
		return failedEvidence(evidence, errors.New("persisted enrollment state unexpectedly ready"))
	}
	evidence.Success = true
	return evidence
}

func processEvidence(action string) gateEvidence {
	evidence := gateEvidence{
		Action:       action,
		PID:          os.Getpid(),
		Account:      os.Getenv("USERDOMAIN") + `\` + os.Getenv("USERNAME"),
		UserProfile:  os.Getenv("USERPROFILE"),
		AppData:      os.Getenv("APPDATA"),
		LocalAppData: os.Getenv("LOCALAPPDATA"),
	}
	user, err := windows.GetCurrentProcessToken().GetTokenUser()
	if err == nil && user != nil && user.User.Sid != nil {
		evidence.SID = user.User.Sid.String()
	}
	return evidence
}

func failedEvidence(evidence gateEvidence, err error) gateEvidence {
	evidence.Error = err.Error()
	return evidence
}

func enrollmentFixture() identity.DeviceIdentity {
	return identity.DeviceIdentity{
		ID:                   filled32(0x33),
		SourceOperatorID:     "source.operator",
		CredentialGeneration: 1,
		CredentialNotBefore:  1_700_000_000,
		CredentialExpiresAt:  1_900_000_000,
		SigningKey: identity.KeyRef{
			ID:         filled32(0x44),
			Purpose:    identity.PurposeDeviceACPRequest,
			Generation: 1,
			Thumbprint: filled32(0x55),
		},
	}
}

func filled32(value byte) (result [32]byte) {
	for index := range result {
		result[index] = value
	}
	return result
}
