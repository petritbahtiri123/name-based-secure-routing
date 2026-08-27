// Package bootstrap loads demo-only already-enrolled client state from disk.
// It is not an NBSR protocol and is not production enrollment.
package bootstrap

import (
	"bytes"
	"crypto/ed25519"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"

	"nbsr.local/client/nbsr-go-client/internal/authority"
	"nbsr.local/client/nbsr-go-client/internal/identity"
)

const Classification = "DEMO FIXTURE — NOT PRODUCTION ENROLLMENT"
const ManifestName = "client-bootstrap.json"
const maxArtifactBytes = 64 << 10

type PublicArtifact struct {
	Schema            string                     `json:"schema"`
	Classification    string                     `json:"classification"`
	Endpoint          string                     `json:"endpoint"`
	ServerName        string                     `json:"server_name"`
	CAFile            string                     `json:"ca_file"`
	SecretFile        string                     `json:"secret_file"`
	NowUnix           uint64                     `json:"now_unix"`
	AcquireTemplate   authority.AcquireRequest   `json:"acquire_template"`
	Issuers           []authority.IssuerRecord   `json:"issuers"`
	Checkpoint        authority.CheckpointClaims `json:"checkpoint"`
	RouteIssuerKID    []byte                     `json:"route_issuer_kid"`
	RouteIssuerPublic [32]byte                   `json:"route_issuer_public"`
}

type SecretArtifact struct {
	Schema         string          `json:"schema"`
	Classification string          `json:"classification"`
	DeviceKeyRef   identity.KeyRef `json:"device_key_ref"`
	DevicePrivate  []byte          `json:"device_private"`
	TSProofPrivate []byte          `json:"ts_proof_private"`
}

type State struct {
	Classification    string
	Endpoint          string
	TLSConfig         *tls.Config
	DeviceSigner      identity.Signer
	Issuers           *authority.StaticIssuerResolver
	Checkpoint        authority.CheckpointClaims
	AcquireTemplate   authority.AcquireRequest
	TSProofPrivate    ed25519.PrivateKey
	NowUnix           uint64
	RouteIssuerKID    []byte
	RouteIssuerPublic [32]byte
}

func Write(root string, public PublicArtifact, secret SecretArtifact, caPEM []byte) error {
	if public.Schema != "nbsr-demo-client-bootstrap-v1" || public.Classification != Classification || secret.Schema != "nbsr-demo-client-secret-v1" || secret.Classification != Classification || public.CAFile != "acp-ca.pem" || public.SecretFile != "client-secret.json" || len(caPEM) == 0 {
		return errors.New("invalid demo bootstrap export")
	}
	if err := os.MkdirAll(root, 0o700); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(root, public.SecretFile), secret, 0o600); err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(root, public.CAFile), caPEM, 0o600); err != nil {
		return err
	}
	return writeJSON(filepath.Join(root, ManifestName), public, 0o600)
}

func Load(root string) (State, error) {
	absolute, err := filepath.Abs(root)
	if err != nil {
		return State{}, err
	}
	var public PublicArtifact
	if err = decodeStrict(filepath.Join(absolute, ManifestName), &public); err != nil {
		return State{}, err
	}
	if public.Schema != "nbsr-demo-client-bootstrap-v1" || public.Classification != Classification || public.Endpoint == "" || public.ServerName == "" || public.NowUnix == 0 || !safeLeaf(public.CAFile) || !safeLeaf(public.SecretFile) || len(public.Issuers) != 2 || len(public.RouteIssuerKID) == 0 || public.RouteIssuerPublic == ([32]byte{}) {
		return State{}, errors.New("invalid demo bootstrap manifest")
	}
	if public.Checkpoint.SourceOperator != public.AcquireTemplate.Key.SourceOperator || public.Checkpoint.Profile != public.AcquireTemplate.Key.Profile || public.Checkpoint.Generation != public.AcquireTemplate.Key.AuthorityGeneration || public.NowUnix >= public.Checkpoint.FreshUntil {
		return State{}, errors.New("invalid demo checkpoint binding")
	}
	trustedRouteIssuer := false
	for _, issuer := range public.Issuers {
		if bytes.Equal(issuer.KID, public.RouteIssuerKID) && issuer.PublicKey == public.RouteIssuerPublic {
			trustedRouteIssuer = true
		}
	}
	if !trustedRouteIssuer {
		return State{}, errors.New("route issuer substitution")
	}
	var secret SecretArtifact
	secretPath, err := referencedPath(absolute, public.SecretFile)
	if err != nil {
		return State{}, err
	}
	if err = decodeStrict(secretPath, &secret); err != nil {
		return State{}, err
	}
	if secret.Schema != "nbsr-demo-client-secret-v1" || secret.Classification != Classification || len(secret.DevicePrivate) != ed25519.PrivateKeySize || len(secret.TSProofPrivate) != ed25519.PrivateKeySize {
		return State{}, errors.New("invalid demo bootstrap secret")
	}
	deviceSigner, err := identity.NewMemorySigner(secret.DeviceKeyRef, ed25519.PrivateKey(secret.DevicePrivate))
	if err != nil || secret.DeviceKeyRef != public.AcquireTemplate.Device.SigningKey {
		return State{}, errors.New("demo bootstrap signer substitution")
	}
	issuers, err := authority.NewStaticIssuerResolver(public.Issuers)
	if err != nil {
		return State{}, err
	}
	caPath, err := referencedPath(absolute, public.CAFile)
	if err != nil {
		return State{}, err
	}
	caPEM, err := readBounded(caPath)
	if err != nil {
		return State{}, err
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(caPEM) {
		return State{}, errors.New("invalid demo ACP trust")
	}
	return State{Classification: Classification, Endpoint: public.Endpoint, TLSConfig: &tls.Config{RootCAs: roots, ServerName: public.ServerName, MinVersion: tls.VersionTLS13, MaxVersion: tls.VersionTLS13, NextProtos: []string{"h2"}}, DeviceSigner: deviceSigner, Issuers: issuers, Checkpoint: public.Checkpoint, AcquireTemplate: public.AcquireTemplate, TSProofPrivate: append(ed25519.PrivateKey(nil), secret.TSProofPrivate...), NowUnix: public.NowUnix, RouteIssuerKID: append([]byte(nil), public.RouteIssuerKID...), RouteIssuerPublic: public.RouteIssuerPublic}, nil
}

func writeJSON(path string, value any, mode os.FileMode) error {
	raw, err := json.Marshal(value)
	if err != nil {
		return err
	}
	raw = append(raw, '\n')
	if len(raw) > maxArtifactBytes {
		return errors.New("demo bootstrap artifact too large")
	}
	return os.WriteFile(path, raw, mode)
}

func decodeStrict(path string, value any) error {
	raw, err := readBounded(path)
	if err != nil {
		return err
	}
	if err = rejectDuplicateKeys(raw); err != nil {
		return err
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err = decoder.Decode(value); err != nil {
		return err
	}
	if err = decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return errors.New("bootstrap artifact must contain exactly one object")
	}
	return nil
}

func rejectDuplicateKeys(raw []byte) error {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	var walk func() error
	walk = func() error {
		token, err := decoder.Token()
		if err != nil {
			return err
		}
		delim, ok := token.(json.Delim)
		if !ok {
			return nil
		}
		switch delim {
		case '{':
			seen := map[string]struct{}{}
			for decoder.More() {
				keyToken, err := decoder.Token()
				if err != nil {
					return err
				}
				key, ok := keyToken.(string)
				if !ok {
					return errors.New("invalid object key")
				}
				if _, exists := seen[key]; exists {
					return errors.New("duplicate bootstrap field")
				}
				seen[key] = struct{}{}
				if err := walk(); err != nil {
					return err
				}
			}
			_, err = decoder.Token()
			return err
		case '[':
			for decoder.More() {
				if err := walk(); err != nil {
					return err
				}
			}
			_, err = decoder.Token()
			return err
		default:
			return errors.New("invalid JSON delimiter")
		}
	}
	return walk()
}

func readBounded(path string) ([]byte, error) {
	file, err := os.Open(filepath.Clean(path))
	if err != nil {
		return nil, err
	}
	defer file.Close()
	raw, err := io.ReadAll(io.LimitReader(file, maxArtifactBytes+1))
	if err != nil {
		return nil, err
	}
	if len(raw) > maxArtifactBytes {
		return nil, errors.New("demo bootstrap artifact too large")
	}
	return raw, nil
}
func safeLeaf(value string) bool {
	return value != "" && value == filepath.Base(value) && value != "." && value != ".."
}

func referencedPath(root, leaf string) (string, error) {
	if !safeLeaf(leaf) {
		return "", errors.New("invalid bootstrap reference")
	}
	path := filepath.Join(root, leaf)
	resolved, err := filepath.EvalSymlinks(path)
	if err != nil {
		return "", err
	}
	relative, err := filepath.Rel(root, resolved)
	if err != nil || filepath.IsAbs(relative) || relative == ".." || len(relative) >= 3 && relative[:3] == ".."+string(filepath.Separator) {
		return "", errors.New("bootstrap reference escapes root")
	}
	return resolved, nil
}
