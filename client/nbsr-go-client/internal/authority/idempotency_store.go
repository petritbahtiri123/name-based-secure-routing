package authority

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"sync"
)

const (
	maxIdempotencyDeadlineHorizon = uint64(30)
	maxIdempotencyCleanupGrace    = uint64(60)
	idempotencyStoreVersion       = uint64(1)
	idempotencyRecordOverhead     = uint64(64)
)

type IdempotencyStoreScope uint8

const (
	IdempotencyStoreSingleNode IdempotencyStoreScope = iota + 1
	IdempotencyStoreShared
)

type IdempotencyClaimStatus uint8

const (
	IdempotencyOwner IdempotencyClaimStatus = iota + 1
	IdempotencyReplay
	IdempotencyPending
	IdempotencyConflict
)

type IdempotencyKey struct {
	Namespace       string
	SourceOperator  string
	Profile         string
	ActorID         [32]byte
	ActorGeneration uint64
	Operation       string
	RequestID       RequestID
}

type IdempotencyRequest struct {
	Key              IdempotencyKey
	Digest           [32]byte
	DeadlineUnix     uint64
	NowUnix          uint64
	MaxTerminalBytes uint64
}

type IdempotencyClaim struct {
	Status   IdempotencyClaimStatus
	Terminal []byte
}

// TransactionalIdempotencyStore is the process-independent correctness
// boundary for request ownership and exact signed terminal replay. Begin must
// atomically choose one owner, replay, pending fence, or digest conflict.
type TransactionalIdempotencyStore interface {
	Scope() IdempotencyStoreScope
	Begin(context.Context, IdempotencyRequest) (IdempotencyClaim, error)
	Complete(context.Context, IdempotencyKey, [32]byte, []byte) error
	Close() error
}

type IdempotencyDeploymentMode string

const IdempotencyDeploymentSingleNode IdempotencyDeploymentMode = "single-node"

type FileIdempotencyStoreConfig struct {
	Path                string
	DeploymentMode      IdempotencyDeploymentMode
	ReplicaCount        int
	MaxEntries          int
	MaxBytes            uint64
	CleanupGraceSeconds uint64
}

type idempotencyRecordState uint64

const (
	idempotencyRecordPending  idempotencyRecordState = 1
	idempotencyRecordTerminal idempotencyRecordState = 2
)

type idempotencyRecord struct {
	keyBytes      []byte
	digest        [32]byte
	deadlineUnix  uint64
	state         idempotencyRecordState
	reservedBytes uint64
	terminal      []byte
}

// FileIdempotencyStore is an explicitly single-node backend. It holds an OS
// process lock for its lifetime and atomically replaces a bounded deterministic
// snapshot after every ownership or completion transaction.
type FileIdempotencyStore struct {
	mu                  sync.Mutex
	path                string
	maxEntries          int
	maxBytes            uint64
	cleanupGraceSeconds uint64
	records             map[string]idempotencyRecord
	lock                *idempotencyFileLock
	closed              bool
}

func NewFileIdempotencyStore(config FileIdempotencyStoreConfig) (*FileIdempotencyStore, error) {
	if config.DeploymentMode != IdempotencyDeploymentSingleNode || config.ReplicaCount != 1 ||
		config.MaxEntries <= 0 || config.MaxBytes == 0 || config.CleanupGraceSeconds > maxIdempotencyCleanupGrace {
		return nil, ErrInvalidLimits
	}
	path, err := validateIdempotencyStorePath(config.Path)
	if err != nil {
		return nil, err
	}
	lock, err := acquireIdempotencyFileLock(path + ".lock")
	if err != nil {
		return nil, err
	}
	store := &FileIdempotencyStore{
		path: path, maxEntries: config.MaxEntries, maxBytes: config.MaxBytes,
		cleanupGraceSeconds: config.CleanupGraceSeconds, records: make(map[string]idempotencyRecord), lock: lock,
	}
	records, err := store.load()
	if err != nil {
		_ = lock.Close()
		return nil, err
	}
	store.records = records
	return store, nil
}

func (store *FileIdempotencyStore) Scope() IdempotencyStoreScope {
	if store == nil {
		return 0
	}
	return IdempotencyStoreSingleNode
}

func (store *FileIdempotencyStore) Begin(ctx context.Context, request IdempotencyRequest) (IdempotencyClaim, error) {
	if store == nil {
		return IdempotencyClaim{}, ErrClosed
	}
	if ctx == nil {
		return IdempotencyClaim{}, ErrInvalidAuthority
	}
	if err := ctx.Err(); err != nil {
		return IdempotencyClaim{}, err
	}
	keyBytes, err := encodeIdempotencyKey(request.Key)
	if err != nil || request.Digest == ([32]byte{}) || request.NowUnix == 0 || request.DeadlineUnix <= request.NowUnix ||
		request.DeadlineUnix-request.NowUnix > maxIdempotencyDeadlineHorizon || request.MaxTerminalBytes == 0 {
		return IdempotencyClaim{}, ErrInvalidAuthority
	}

	store.mu.Lock()
	defer store.mu.Unlock()
	if store.closed {
		return IdempotencyClaim{}, ErrClosed
	}
	candidate, cleaned := store.withoutExpired(request.NowUnix)
	recordID := string(keyBytes)
	if record, ok := candidate[recordID]; ok {
		if cleaned {
			if err := store.persist(candidate); err != nil {
				return IdempotencyClaim{}, err
			}
			store.records = candidate
		}
		if record.digest != request.Digest {
			return IdempotencyClaim{Status: IdempotencyConflict}, nil
		}
		if record.state == idempotencyRecordTerminal {
			return IdempotencyClaim{Status: IdempotencyReplay, Terminal: append([]byte(nil), record.terminal...)}, nil
		}
		return IdempotencyClaim{Status: IdempotencyPending}, nil
	}

	candidate[recordID] = idempotencyRecord{
		keyBytes: append([]byte(nil), keyBytes...), digest: request.Digest, deadlineUnix: request.DeadlineUnix,
		state: idempotencyRecordPending, reservedBytes: request.MaxTerminalBytes,
	}
	if !store.withinBounds(candidate) {
		delete(candidate, recordID)
		if cleaned {
			if err := store.persist(candidate); err != nil {
				return IdempotencyClaim{}, err
			}
			store.records = candidate
		}
		return IdempotencyClaim{}, ErrCacheCapacity
	}
	if err := store.persist(candidate); err != nil {
		return IdempotencyClaim{}, err
	}
	store.records = candidate
	return IdempotencyClaim{Status: IdempotencyOwner}, nil
}

func (store *FileIdempotencyStore) Complete(ctx context.Context, key IdempotencyKey, digest [32]byte, terminal []byte) error {
	if store == nil {
		return ErrClosed
	}
	if ctx == nil || digest == ([32]byte{}) || len(terminal) == 0 {
		return ErrInvalidAuthority
	}
	if err := ctx.Err(); err != nil {
		return err
	}
	keyBytes, err := encodeIdempotencyKey(key)
	if err != nil {
		return err
	}

	store.mu.Lock()
	defer store.mu.Unlock()
	if store.closed {
		return ErrClosed
	}
	recordID := string(keyBytes)
	record, ok := store.records[recordID]
	if !ok || record.digest != digest {
		return ErrRequestConflict
	}
	if uint64(len(terminal)) > record.reservedBytes {
		return ErrInvalidAuthority
	}
	if record.state == idempotencyRecordTerminal {
		if bytes.Equal(record.terminal, terminal) {
			return nil
		}
		return ErrRequestConflict
	}
	candidate := cloneIdempotencyRecords(store.records)
	record.state = idempotencyRecordTerminal
	record.terminal = append([]byte(nil), terminal...)
	candidate[recordID] = record
	if !store.withinBounds(candidate) {
		return ErrCacheCapacity
	}
	if err := store.persist(candidate); err != nil {
		return err
	}
	store.records = candidate
	return nil
}

func (store *FileIdempotencyStore) Close() error {
	if store == nil {
		return nil
	}
	store.mu.Lock()
	if store.closed {
		store.mu.Unlock()
		return nil
	}
	store.closed = true
	lock := store.lock
	store.lock = nil
	store.mu.Unlock()
	if lock == nil {
		return nil
	}
	return lock.Close()
}

func (store *FileIdempotencyStore) withoutExpired(now uint64) (map[string]idempotencyRecord, bool) {
	candidate := cloneIdempotencyRecords(store.records)
	changed := false
	for key, record := range candidate {
		expires := record.deadlineUnix + store.cleanupGraceSeconds
		if expires < record.deadlineUnix || now >= expires {
			delete(candidate, key)
			changed = true
		}
	}
	return candidate, changed
}

func (store *FileIdempotencyStore) withinBounds(records map[string]idempotencyRecord) bool {
	if len(records) > store.maxEntries {
		return false
	}
	var used uint64
	for _, record := range records {
		cost := idempotencyRecordOverhead + uint64(len(record.keyBytes)) + 32 + record.reservedBytes
		if cost < record.reservedBytes || cost > store.maxBytes || used > store.maxBytes-cost {
			return false
		}
		used += cost
	}
	wire, err := encodeIdempotencySnapshot(records)
	return err == nil && uint64(len(wire)) <= store.maxBytes
}

func (store *FileIdempotencyStore) persist(records map[string]idempotencyRecord) error {
	wire, err := encodeIdempotencySnapshot(records)
	if err != nil || len(wire) == 0 || uint64(len(wire)) > store.maxBytes {
		return ErrCacheCapacity
	}
	return writeIdempotencySnapshot(store.path, wire)
}

func (store *FileIdempotencyStore) load() (map[string]idempotencyRecord, error) {
	info, err := os.Lstat(store.path)
	if errors.Is(err, os.ErrNotExist) {
		return make(map[string]idempotencyRecord), nil
	}
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrStoragePathRejected, err)
	}
	if !info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0 || info.Size() <= 0 || uint64(info.Size()) > store.maxBytes {
		return nil, ErrInvalidAuthority
	}
	wire, err := os.ReadFile(store.path)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrStoragePathRejected, err)
	}
	limits := defaultCBORLimits()
	limits.maxInputBytes = boundedUint64ToInt(store.maxBytes)
	limits.maxByteStringBytes = limits.maxInputBytes
	if store.maxEntries > limits.maxCollectionItems {
		limits.maxCollectionItems = store.maxEntries
	}
	value, err := decodeCBORExact(wire, limits)
	if err != nil {
		return nil, ErrInvalidAuthority
	}
	fields, ok := value.(map[uint64]any)
	if !ok || !keysZeroThrough(fields, 1) || fields[0] != idempotencyStoreVersion {
		return nil, ErrInvalidAuthority
	}
	items, ok := fields[1].([]any)
	if !ok || len(items) > store.maxEntries {
		return nil, ErrInvalidAuthority
	}
	records := make(map[string]idempotencyRecord, len(items))
	for _, item := range items {
		record, err := decodeIdempotencyRecord(item)
		if err != nil {
			return nil, err
		}
		key := string(record.keyBytes)
		if _, duplicate := records[key]; duplicate {
			return nil, ErrInvalidAuthority
		}
		records[key] = record
	}
	if !store.withinBounds(records) {
		return nil, ErrInvalidAuthority
	}
	return records, nil
}

func encodeIdempotencySnapshot(records map[string]idempotencyRecord) ([]byte, error) {
	ordered := make([]idempotencyRecord, 0, len(records))
	for _, record := range records {
		ordered = append(ordered, record)
	}
	sort.Slice(ordered, func(left, right int) bool { return bytes.Compare(ordered[left].keyBytes, ordered[right].keyBytes) < 0 })
	items := make([]any, 0, len(ordered))
	for _, record := range ordered {
		fields := map[uint64]any{
			0: record.keyBytes, 1: record.digest[:], 2: record.deadlineUnix,
			3: uint64(record.state), 4: record.reservedBytes,
		}
		if record.state == idempotencyRecordTerminal {
			fields[5] = record.terminal
		}
		items = append(items, fields)
	}
	return encodeCBOR(map[uint64]any{0: idempotencyStoreVersion, 1: items})
}

func decodeIdempotencyRecord(value any) (idempotencyRecord, error) {
	fields, ok := value.(map[uint64]any)
	if !ok || (!keysZeroThrough(fields, 4) && !keysZeroThrough(fields, 5)) {
		return idempotencyRecord{}, ErrInvalidAuthority
	}
	keyBytes, keyOK := fields[0].([]byte)
	digest, digestOK := fixed32(fields[1])
	deadline, deadlineOK := fields[2].(uint64)
	stateValue, stateOK := fields[3].(uint64)
	reserved, reservedOK := fields[4].(uint64)
	state := idempotencyRecordState(stateValue)
	if !keyOK || len(keyBytes) == 0 || !digestOK || digest == ([32]byte{}) || !deadlineOK || deadline == 0 ||
		!stateOK || (state != idempotencyRecordPending && state != idempotencyRecordTerminal) || !reservedOK || reserved == 0 {
		return idempotencyRecord{}, ErrInvalidAuthority
	}
	canonicalKey, err := canonicalIdempotencyKeyBytes(keyBytes)
	if err != nil || !bytes.Equal(canonicalKey, keyBytes) {
		return idempotencyRecord{}, ErrInvalidAuthority
	}
	record := idempotencyRecord{
		keyBytes: append([]byte(nil), keyBytes...), digest: digest, deadlineUnix: deadline, state: state, reservedBytes: reserved,
	}
	terminal, present := fields[5]
	if state == idempotencyRecordPending {
		if present {
			return idempotencyRecord{}, ErrInvalidAuthority
		}
		return record, nil
	}
	raw, ok := terminal.([]byte)
	if !present || !ok || len(raw) == 0 || uint64(len(raw)) > reserved {
		return idempotencyRecord{}, ErrInvalidAuthority
	}
	record.terminal = append([]byte(nil), raw...)
	return record, nil
}

func encodeIdempotencyKey(key IdempotencyKey) ([]byte, error) {
	if err := validateIdempotencyKey(key); err != nil {
		return nil, err
	}
	return encodeCBOR(map[uint64]any{
		0: key.Namespace, 1: key.SourceOperator, 2: key.Profile, 3: key.ActorID[:],
		4: key.ActorGeneration, 5: key.Operation, 6: key.RequestID[:],
	})
}

func canonicalIdempotencyKeyBytes(wire []byte) ([]byte, error) {
	value, err := decodeCBORExact(wire, defaultCBORLimits())
	if err != nil {
		return nil, ErrInvalidAuthority
	}
	fields, ok := value.(map[uint64]any)
	if !ok || !keysZeroThrough(fields, 6) {
		return nil, ErrInvalidAuthority
	}
	namespace, namespaceOK := fields[0].(string)
	source, sourceOK := fields[1].(string)
	profile, profileOK := fields[2].(string)
	actor, actorOK := fixed32(fields[3])
	generation, generationOK := fields[4].(uint64)
	operation, operationOK := fields[5].(string)
	requestID, requestIDOK := fixed16(fields[6])
	key := IdempotencyKey{
		Namespace: namespace, SourceOperator: source, Profile: profile, ActorID: actor,
		ActorGeneration: generation, Operation: operation, RequestID: requestID,
	}
	if !namespaceOK || !sourceOK || !profileOK || !actorOK || !generationOK || !operationOK || !requestIDOK {
		return nil, ErrInvalidAuthority
	}
	return encodeIdempotencyKey(key)
}

func validateIdempotencyKey(key IdempotencyKey) error {
	validOperation := validACPOperation(ACPOperation(key.Operation)) || key.Operation == "ENROLL"
	if (key.Namespace != "authority" && key.Namespace != "enrollment") || !validTextID(key.SourceOperator) ||
		!validTextID(key.Profile) || key.ActorID == ([32]byte{}) || key.ActorGeneration == 0 || !validOperation ||
		key.RequestID == (RequestID{}) {
		return ErrInvalidAuthority
	}
	if (key.Namespace == "authority") != validACPOperation(ACPOperation(key.Operation)) {
		return ErrInvalidAuthority
	}
	return nil
}

func cloneIdempotencyRecords(source map[string]idempotencyRecord) map[string]idempotencyRecord {
	clone := make(map[string]idempotencyRecord, len(source))
	for key, record := range source {
		record.keyBytes = append([]byte(nil), record.keyBytes...)
		record.terminal = append([]byte(nil), record.terminal...)
		clone[key] = record
	}
	return clone
}

func validateIdempotencyStorePath(path string) (string, error) {
	if path == "" || !filepath.IsAbs(path) {
		return "", ErrStoragePathRejected
	}
	clean := filepath.Clean(path)
	parent := filepath.Dir(clean)
	info, err := os.Stat(parent)
	if err != nil || !info.IsDir() {
		return "", ErrStoragePathRejected
	}
	resolvedParent, err := filepath.EvalSymlinks(parent)
	if err != nil || !sameFilesystemPath(parent, resolvedParent) {
		return "", ErrStoragePathRejected
	}
	if info, err := os.Lstat(clean); err == nil {
		if !info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0 {
			return "", ErrStoragePathRejected
		}
		resolved, resolveErr := filepath.EvalSymlinks(clean)
		if resolveErr != nil || !sameFilesystemPath(clean, resolved) {
			return "", ErrStoragePathRejected
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return "", ErrStoragePathRejected
	}
	return clean, nil
}

func sameFilesystemPath(left, right string) bool {
	left, right = filepath.Clean(left), filepath.Clean(right)
	if runtime.GOOS == "windows" {
		return strings.EqualFold(left, right)
	}
	return left == right
}

func writeIdempotencySnapshot(path string, wire []byte) error {
	parent := filepath.Dir(path)
	temp, err := os.CreateTemp(parent, filepath.Base(path)+".tmp-")
	if err != nil {
		return fmt.Errorf("%w: %v", ErrStoragePathRejected, err)
	}
	tempPath := temp.Name()
	defer os.Remove(tempPath)
	if err := temp.Chmod(0o600); err != nil {
		_ = temp.Close()
		return fmt.Errorf("%w: %v", ErrStoragePathRejected, err)
	}
	if _, err := temp.Write(wire); err != nil {
		_ = temp.Close()
		return fmt.Errorf("%w: %v", ErrStoragePathRejected, err)
	}
	if err := temp.Sync(); err != nil {
		_ = temp.Close()
		return fmt.Errorf("%w: %v", ErrStoragePathRejected, err)
	}
	if err := temp.Close(); err != nil {
		return fmt.Errorf("%w: %v", ErrStoragePathRejected, err)
	}
	if err := replaceIdempotencySnapshot(tempPath, path); err != nil {
		return fmt.Errorf("%w: %v", ErrStoragePathRejected, err)
	}
	return nil
}

func boundedUint64ToInt(value uint64) int {
	maximum := uint64(^uint(0) >> 1)
	if value > maximum {
		return int(maximum)
	}
	return int(value)
}

var _ TransactionalIdempotencyStore = (*FileIdempotencyStore)(nil)
