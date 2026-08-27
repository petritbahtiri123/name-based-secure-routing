// Package config defines the closed, demo-only configuration boundary. It
// contains references to generated secrets, never secret bytes, and has no
// client-side representation for an Origin Endpoint.
package config

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/netip"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"nbsr.local/client/nbsr-go-client/internal/resolution"
	"nbsr.local/interop/nbsr-go-peer/wirepeer"
)

const (
	Schema                    = "nbsr-demo-config-v1"
	DemoFixtureClassification = "DEMO FIXTURE — NOT PRODUCTION AUTHORITY"
	SharedSyntheticIP         = "127.0.0.2"
	ValidatedRustArtifactPath = `C:\NBSR-build\tranche5-closure-b124939\cargo-target\release\wp8_interop_server.exe`
	ValidatedRustSHA256       = "b20b52e4d4ac0c3d0f7b6ca6e04e7cd80c5099e6ed185da7b04071f3fc97a888"
	MaxConfigBytes            = 64 * 1024
)

type Config struct {
	Schema      string             `json:"schema"`
	Production  ProductionSemantic `json:"production_semantic"`
	Client      ClientConfig       `json:"client"`
	ACPFixture  ACPFixtureConfig   `json:"acp_fixture"`
	Destination DestinationConfig  `json:"destination"`
	Evidence    EvidenceConfig     `json:"evidence"`
	Secrets     SecretReferences   `json:"secrets"`
	Timeouts    Timeouts           `json:"timeouts"`
	Limits      Limits             `json:"limits"`
}

// ProductionSemantic contains existing NBSR contract values. None is a demo
// authority decision and none may be relaxed by local configuration.
type ProductionSemantic struct {
	ALPN                string `json:"alpn"`
	QUICVersion         string `json:"quic_version"`
	TLSVersion          string `json:"tls_version"`
	StreamCreditProfile string `json:"stream_credit_profile"`
}

// ClientConfig is deliberately origin-free. The Synthetic IP is local routing
// configuration only; the service fixture supplies correlation input, not
// authority. ApplicationTransport and ServicePort describe the demo
// application's reliable-stream profile carried through NBSR; NBSR's secure
// transport remains QUIC v1, TLS 1.3, and ALPN nbsr-quic-1.
type ClientConfig struct {
	ServiceFixture       string `json:"service_fixture"`
	SharedSyntheticIP    string `json:"shared_synthetic_ip"`
	ProxyEndpoint        string `json:"proxy_endpoint"`
	ACPEndpoint          string `json:"acp_endpoint"`
	DestinationReadiness string `json:"destination_readiness"`
	ApplicationTransport string `json:"application_transport"`
	ServicePort          uint16 `json:"service_port"`
}

type ACPFixtureConfig struct {
	Classification string `json:"classification"`
	PublicFixture  string `json:"public_fixture"`
}

type DestinationConfig struct {
	AuthorityFixture string      `json:"authority_fixture"`
	RustArtifact     ArtifactRef `json:"rust_artifact"`
}

type ArtifactRef struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
}

type EvidenceConfig struct {
	Directory string `json:"directory"`
}
type SecretReferences struct {
	Directory string `json:"directory"`
}
type Timeouts struct {
	HandshakeSeconds int `json:"handshake_seconds"`
	OperationSeconds int `json:"operation_seconds"`
}
type Limits struct {
	MaxProxyConnections int   `json:"max_proxy_connections"`
	MaxRequestBytes     int64 `json:"max_request_bytes"`
}

type ServiceFixture struct {
	Classification   string `json:"classification"`
	PresentationName string `json:"presentation_name"`
	ServiceIdentity  string `json:"service_identity"`
	Transport        string `json:"transport"`
	Port             uint16 `json:"port"`
}

func Load(path string) (Config, error) {
	var value Config
	if err := decodeOne(path, &value); err != nil {
		return Config{}, err
	}
	if err := value.Validate(); err != nil {
		return Config{}, err
	}
	return value, nil
}

// LoadForRun validates Task 5's per-run demo paths and freshly built Rust
// artifact. It is a demo orchestration boundary, not production enrollment.
func LoadForRun(path, runtimeRoot, buildRoot string) (Config, error) {
	var value Config
	if err := decodeOne(path, &value); err != nil {
		return Config{}, err
	}
	if err := value.validateSemantics(true); err != nil {
		return Config{}, err
	}
	runID, err := validateRuntimeRoot(runtimeRoot)
	if err != nil {
		return Config{}, err
	}
	if err := validateBuildRoot(buildRoot, runID); err != nil {
		return Config{}, err
	}
	for _, candidate := range []string{value.Client.DestinationReadiness, value.ACPFixture.PublicFixture, value.Destination.AuthorityFixture, value.Evidence.Directory, value.Secrets.Directory} {
		if err := containedPath(runtimeRoot, candidate); err != nil {
			return Config{}, errors.New("runtime artifact escapes the selected run")
		}
	}
	if err := containedPath(buildRoot, value.Destination.RustArtifact.Path); err != nil {
		return Config{}, errors.New("Rust artifact escapes the selected build")
	}
	file, err := os.Open(filepath.Clean(value.Destination.RustArtifact.Path))
	if err != nil {
		return Config{}, err
	}
	hasher := sha256.New()
	_, hashErr := io.Copy(hasher, file)
	closeErr := file.Close()
	if hashErr != nil || closeErr != nil || fmt.Sprintf("%x", hasher.Sum(nil)) != strings.ToLower(value.Destination.RustArtifact.SHA256) {
		return Config{}, errors.New("Rust artifact hash mismatch")
	}
	return value, nil
}

func ValidateTask5RuntimeRoot(root string) error {
	_, err := validateRuntimeRoot(root)
	return err
}

func ValidateTask5Roots(runtimeRoot, buildRoot string) error {
	runID, err := validateRuntimeRoot(runtimeRoot)
	if err != nil {
		return err
	}
	return validateBuildRoot(buildRoot, runID)
}

func ValidateTask5ContainedPath(root, candidate string) error {
	return containedPath(root, candidate)
}

func LoadServiceFixture(path string) (ServiceFixture, error) {
	var value ServiceFixture
	if err := decodeOne(path, &value); err != nil {
		return ServiceFixture{}, err
	}
	if value.Classification != DemoFixtureClassification || value.ServiceIdentity == "" || value.Transport != "tcp" || value.Port != 8080 {
		return ServiceFixture{}, errors.New("invalid demo service fixture")
	}
	name, err := resolution.CanonicalizePresentationName(value.PresentationName)
	if err != nil || name.String() != value.PresentationName {
		return ServiceFixture{}, errors.New("demo service name is not canonical")
	}
	return value, nil
}

func (value Config) Validate() error {
	if err := value.validateSemantics(false); err != nil {
		return err
	}
	if filepath.Clean(value.Destination.RustArtifact.Path) != filepath.Clean(ValidatedRustArtifactPath) || strings.ToLower(value.Destination.RustArtifact.SHA256) != ValidatedRustSHA256 {
		return errors.New("unvalidated Rust artifact")
	}
	return nil
}

func (value Config) validateSemantics(allowEphemeralProxy bool) error {
	if value.Schema != Schema || value.Production != (ProductionSemantic{
		ALPN: wirepeer.ALPN, QUICVersion: wirepeer.QUICVersion, TLSVersion: wirepeer.TLSVersion,
		StreamCreditProfile: wirepeer.StreamCreditProfile,
	}) {
		return errors.New("production-semantic configuration drift")
	}
	if value.Client.ApplicationTransport != "tcp" || value.Client.ServicePort != 8080 {
		return errors.New("invalid demo application profile")
	}
	if value.Client.SharedSyntheticIP != SharedSyntheticIP || netip.MustParseAddr(SharedSyntheticIP) != netip.MustParseAddr(value.Client.SharedSyntheticIP) {
		return errors.New("invalid shared Synthetic IP")
	}
	if !loopbackTCPWithZero(value.Client.ProxyEndpoint, allowEphemeralProxy) || !loopbackHTTPS(value.Client.ACPEndpoint) {
		return errors.New("demo client endpoints must be loopback TCP and HTTPS")
	}
	if !safeRelative(value.Client.ServiceFixture) || !safeRuntimePath(value.Client.DestinationReadiness) ||
		value.ACPFixture.Classification != DemoFixtureClassification || !safeRuntimePath(value.ACPFixture.PublicFixture) ||
		!safeRuntimePath(value.Destination.AuthorityFixture) || !safeRuntimePath(value.Evidence.Directory) || !safeRuntimePath(value.Secrets.Directory) {
		return errors.New("invalid demo fixture or runtime path")
	}
	if _, err := hex.DecodeString(value.Destination.RustArtifact.SHA256); err != nil || len(value.Destination.RustArtifact.SHA256) != 64 {
		return errors.New("invalid Rust artifact digest")
	}
	if value.Timeouts != (Timeouts{HandshakeSeconds: 5, OperationSeconds: 15}) || value.Limits != (Limits{MaxProxyConnections: 16, MaxRequestBytes: 4096}) {
		return errors.New("demo bounds or timeouts drift")
	}
	return nil
}

func validateRuntimeRoot(root string) (string, error) {
	if filepath.IsAbs(root) {
		return "", errors.New("runtime root must be repository-relative")
	}
	clean := filepath.ToSlash(filepath.Clean(root))
	const prefix = "test-results/nbsr-demo/runtime/"
	if !strings.HasPrefix(clean, prefix) {
		return "", errors.New("runtime root is outside the demo hierarchy")
	}
	runID := strings.TrimPrefix(clean, prefix)
	if strings.Contains(runID, "/") || !validRunID(runID) {
		return "", errors.New("invalid demo run ID")
	}
	return runID, nil
}

func validateBuildRoot(root, runID string) error {
	if !filepath.IsAbs(root) {
		return errors.New("build root must be absolute")
	}
	clean := filepath.Clean(root)
	parent := filepath.Clean(`C:\NBSR-build\nbsr-demo`)
	relative, err := filepath.Rel(parent, clean)
	if err != nil || relative != runID || !validRunID(runID) {
		return errors.New("build root is outside the approved hierarchy")
	}
	return nil
}

func containedPath(base, candidate string) error {
	baseAbsolute, err := filepath.Abs(filepath.Clean(base))
	if err != nil {
		return err
	}
	candidateAbsolute, err := filepath.Abs(filepath.Clean(candidate))
	if err != nil {
		return err
	}
	relative, err := filepath.Rel(baseAbsolute, candidateAbsolute)
	if err != nil || relative == "." || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return errors.New("path is not a run descendant")
	}
	baseResolved, baseErr := filepath.EvalSymlinks(baseAbsolute)
	parentResolved, parentErr := filepath.EvalSymlinks(filepath.Dir(candidateAbsolute))
	if baseErr != nil || parentErr != nil {
		return errors.New("path containment cannot be resolved")
	}
	resolvedRelative, relErr := filepath.Rel(baseResolved, parentResolved)
	if relErr != nil || resolvedRelative == ".." || strings.HasPrefix(resolvedRelative, ".."+string(filepath.Separator)) {
		return errors.New("path resolves outside the selected run")
	}
	return nil
}

func validRunID(value string) bool {
	if len(value) < 1 || len(value) > 64 || value[0] == '-' || value[len(value)-1] == '-' {
		return false
	}
	for _, character := range value {
		if (character < 'a' || character > 'z') && (character < '0' || character > '9') && character != '-' {
			return false
		}
	}
	return true
}

func decodeOne(path string, value any) error {
	file, err := os.Open(filepath.Clean(path))
	if err != nil {
		return err
	}
	defer file.Close()
	decoder := json.NewDecoder(io.LimitReader(file, MaxConfigBytes+1))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(value); err != nil {
		return err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return errors.New("configuration must contain one JSON object")
	}
	return nil
}

func loopbackTCP(endpoint string) bool {
	return loopbackTCPWithZero(endpoint, false)
}

func loopbackTCPWithZero(endpoint string, allowZero bool) bool {
	host, port, err := net.SplitHostPort(endpoint)
	address, parseErr := netip.ParseAddr(host)
	portNumber, portErr := strconv.ParseUint(port, 10, 16)
	return err == nil && parseErr == nil && portErr == nil && address.IsLoopback() && (allowZero || portNumber != 0)
}

func loopbackHTTPS(endpoint string) bool {
	parsed, err := url.Parse(endpoint)
	if err != nil || parsed.Scheme != "https" || parsed.User != nil || parsed.Path != "" || parsed.RawQuery != "" || parsed.Fragment != "" {
		return false
	}
	return loopbackTCP(parsed.Host)
}

func safeRelative(path string) bool {
	clean := filepath.Clean(path)
	return path != "" && !filepath.IsAbs(clean) && clean != "." && clean != ".." && !strings.HasPrefix(clean, ".."+string(filepath.Separator))
}

func safeRuntimePath(path string) bool {
	if !safeRelative(path) {
		return false
	}
	clean := filepath.ToSlash(filepath.Clean(path))
	return strings.HasPrefix(clean, "test-results/nbsr-demo/")
}
