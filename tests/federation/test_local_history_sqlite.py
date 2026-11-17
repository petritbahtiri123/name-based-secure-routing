"""Synthetic signed fixtures + real SQLite file; no production trust claims."""
import shutil
import pytest
from scripts import inclusion_persistence as store
from scripts.revocation_inclusion_v2 import make_fixture
from scripts.local_history_sqlite import LocalHistoryStorage


def repo(storage):
    return store.Repository(storage, context_binding=b"C" * 32)


def initialize(path):
    storage = LocalHistoryStorage.create(path)
    raw, context, initial = make_fixture()
    result, first = repo(storage).initialize(raw, context, initial)
    assert result["decision"] == "ACCEPT"
    return storage, raw, first


def test_restart_preserves_signed_history(tmp_path):
    path = tmp_path / "history.db"
    storage, raw, first = initialize(path)
    raw2, context2, _ = make_fixture(previous_package=raw, event_id=b"2" * 32)
    result, second = repo(storage).apply(raw2, context2, first.digest)
    assert result["decision"] == "ACCEPT"
    storage.close()
    with LocalHistoryStorage.open(path) as reopened:
        loaded = repo(reopened).load(second.digest)
        assert loaded == second
        assert first.state.retained_revocations <= loaded.state.retained_revocations
        with pytest.raises(store.SnapshotRejected):
            repo(reopened).load(first.digest)


def test_whole_database_rollback_needs_external_expectation(tmp_path):
    path, backup = tmp_path / "history.db", tmp_path / "old.db"
    storage, raw, first = initialize(path)
    storage.close()
    shutil.copyfile(path, backup)
    with LocalHistoryStorage.open(path) as storage:
        raw2, context2, _ = make_fixture(previous_package=raw, event_id=b"2" * 32)
        _, second = repo(storage).apply(raw2, context2, first.digest)
    shutil.copyfile(backup, path)
    with LocalHistoryStorage.open(path) as storage:
        with pytest.raises(store.SnapshotRejected):
            repo(storage).load(second.digest)
        # Explicit limitation: rolling back the external expectation too is undetectable.
        assert repo(storage).load(first.digest) == first


def test_missing_database_is_not_bootstrap(tmp_path):
    path = tmp_path / "missing.db"
    with pytest.raises(store.StorageUnavailable):
        LocalHistoryStorage.open(path)
    assert not path.exists()


def test_empty_storage_and_missing_expectation_refuse(tmp_path):
    with LocalHistoryStorage.create(tmp_path / "empty.db") as storage:
        for expectation in (None, b"X" * 32):
            with pytest.raises(store.SnapshotRejected):
                repo(storage).load(expectation)


def test_invalid_package_does_not_create_history(tmp_path):
    with LocalHistoryStorage.create(tmp_path / "history.db") as storage:
        _, context, initial = make_fixture()
        result, snapshot = repo(storage).initialize(b"invalid", context, initial)
        assert result["decision"] != "ACCEPT"
        assert snapshot is None
        with storage.exclusive():
            assert storage.read(store.PRIMARY) is None
            assert storage.read(store.WATERMARK) is None


def test_exception_rolls_back_both_values(tmp_path):
    with LocalHistoryStorage.create(tmp_path / "history.db") as storage:
        with pytest.raises(RuntimeError):
            with storage.exclusive():
                storage.replace(store.WATERMARK, b"candidate")
                raise RuntimeError("interrupted before primary")
        with storage.exclusive():
            assert storage.read(store.WATERMARK) is None


def test_second_writer_refuses_and_can_retry_after_release(tmp_path):
    path = tmp_path / "history.db"
    with LocalHistoryStorage.create(path) as first, LocalHistoryStorage.open(path) as second:
        with first.exclusive():
            with pytest.raises(store.StorageUnavailable):
                with second.exclusive():
                    pytest.fail("competing writer admitted")
        with second.exclusive():
            assert second.read(store.PRIMARY) is None


def test_create_never_overwrites_existing_database(tmp_path):
    path = tmp_path / "history.db"
    storage, _, first = initialize(path)
    storage.close()
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        LocalHistoryStorage.create(path)
    assert path.read_bytes() == before
    with LocalHistoryStorage.open(path) as storage:
        assert repo(storage).load(first.digest) == first

@pytest.mark.parametrize("change", ["profile", "obligations", "anchor", "expiry", "witness_policy"])
def test_canonical_verifier_refusal_preserves_persisted_state(tmp_path, change):
    path = tmp_path / "history.db"
    storage, raw, first = initialize(path)
    raw2, context, _ = make_fixture(previous_package=raw, event_id=b"2" * 32)
    if change == "profile":
        context = dict(context, profile="unsupported-profile")
    elif change == "obligations":
        context = dict(context, obligations={})
    elif change == "anchor":
        context = dict(context, accepted_anchor=b"X" * 32)
    elif change == "expiry":
        context = dict(context, validation=dict(context["validation"], now=253402300800))
    else:
        # Proposed history 3/4 must not be silently imported into this verifier.
        context = dict(context, required_witnesses=4)
    result, unchanged = repo(storage).apply(raw2, context, first.digest)
    assert result["decision"] not in ("ACCEPT", "IDEMPOTENT")
    assert result["runtime_authority"] is False
    assert unchanged == first
    storage.close()
    with LocalHistoryStorage.open(path) as reopened:
        assert repo(reopened).load(first.digest) == first


def test_independent_context_substitution_refuses_restart(tmp_path):
    path = tmp_path / "history.db"
    storage, _, first = initialize(path)
    storage.close()
    with LocalHistoryStorage.open(path) as storage:
        wrong = store.Repository(storage, context_binding=b"D" * 32)
        with pytest.raises(store.SnapshotRejected):
            wrong.load(first.digest)
        assert repo(storage).load(first.digest) == first


def test_typed_effect_and_idempotent_event_survive_restart(tmp_path):
    path = tmp_path / "history.db"
    storage, raw, first = initialize(path)
    storage.close()
    _, context, _ = make_fixture()
    with LocalHistoryStorage.open(path) as storage:
        result, repeated = repo(storage).apply(raw, context, first.digest)
        assert result["decision"] == "IDEMPOTENT"
        assert result["typed_enforcement"] == store.parse_record(first.state.record)[36]
        assert result["runtime_authority"] is False
        assert repeated == first
        assert repeated.state.requests == first.state.requests

class FaultConnection:
    """Inject only SQLite boundary errors; all storage operations use the real DB."""

    def __init__(self, connection, *, commit=None, rollback=False, primary=False):
        self.connection = connection
        self.commit = commit
        self.rollback = rollback
        self.primary = primary
        self.forbid_sql = False
        self.attempts = []

    @property
    def in_transaction(self):
        return self.connection.in_transaction

    def execute(self, sql, parameters=()):
        import sqlite3

        self.attempts.append(sql)
        if self.forbid_sql:
            raise AssertionError("latched operation reached SQL")
        if sql == "COMMIT" and self.commit == "before":
            raise sqlite3.OperationalError("injected before commit")
        if sql == "ROLLBACK" and self.rollback:
            raise sqlite3.OperationalError("injected rollback failure")
        if self.primary and sql.startswith("INSERT") and parameters[0] == store.PRIMARY:
            raise sqlite3.OperationalError("injected primary write failure")
        result = self.connection.execute(sql, parameters)
        if sql == "COMMIT" and self.commit == "after":
            raise sqlite3.OperationalError("injected lost commit acknowledgement")
        return result

    def close(self):
        self.connection.close()


@pytest.mark.parametrize("phase", ["before", "after"])
def test_commit_error_latches_repository_and_backend(tmp_path, phase):
    path = tmp_path / "history.db"
    storage, raw, first = initialize(path)
    repository = repo(storage)
    # Independent successful operation on a separate real database, before fault.
    oracle_storage, oracle_raw, oracle_first = initialize(tmp_path / "oracle.db")
    oracle_raw2, oracle_context, _ = make_fixture(previous_package=oracle_raw, event_id=b"2" * 32)
    _, expected = repo(oracle_storage).apply(oracle_raw2, oracle_context, oracle_first.digest)
    oracle_storage.close()
    storage._db = FaultConnection(storage._db, commit=phase)
    raw2, context2, _ = make_fixture(previous_package=raw, event_id=b"2" * 32)
    with pytest.raises(store.StorageUnavailable):
        repository.apply(raw2, context2, first.digest)
    assert "COMMIT" in storage._db.attempts
    assert_latches_without_sql(repository, storage)
    # A new Repository cannot bypass the adapter instance's uncertainty latch.
    for candidate in (repository, repo(storage)):
        with pytest.raises(store.StorageUnavailable):
            candidate.load(first.digest)
    storage.close()
    with LocalHistoryStorage.open(path) as reopened:
        with reopened.exclusive():
            primary = reopened.read(store.PRIMARY)
            assert primary == reopened.read(store.WATERMARK)
        durable = store.decode(primary)
        if phase == "before":
            assert durable == first
        else:
            assert durable == expected
            assert primary == store.encode(expected)
            with pytest.raises(store.SnapshotRejected):
                repo(reopened).load(first.digest)
        # Observed digest is a test oracle, NOT an independently trusted recovery source.
        assert repo(reopened).load(durable.digest) == durable


def test_rollback_error_retains_lock_until_explicit_close(tmp_path):
    path = tmp_path / "history.db"
    storage, raw, first = initialize(path)
    repository = repo(storage)
    storage._db = FaultConnection(storage._db, rollback=True, primary=True)
    raw2, context2, _ = make_fixture(previous_package=raw, event_id=b"2" * 32)
    with pytest.raises(store.StorageUnavailable):
        repository.apply(raw2, context2, first.digest)
    assert "ROLLBACK" in storage._db.attempts
    assert storage._db.in_transaction
    assert_latches_without_sql(repository, storage)
    for candidate in (repository, repo(storage)):
        with pytest.raises(store.StorageUnavailable):
            candidate.load(first.digest)
    with LocalHistoryStorage.open(path) as other:
        with pytest.raises(store.StorageUnavailable):
            repo(other).load(first.digest)
    storage.close()  # Real sqlite close rolls back this still-open transaction.
    with LocalHistoryStorage.open(path) as reopened:
        assert repo(reopened).load(first.digest) == first


@pytest.mark.parametrize("name", [store.PRIMARY, store.WATERMARK])
def test_corrupt_snapshot_refuses_without_fallback_or_mutation(tmp_path, name):
    path = tmp_path / "history.db"
    storage, _, first = initialize(path)
    with storage.exclusive():
        storage.replace(name, b"{truncated")
        before = {key: storage.read(key) for key in (store.PRIMARY, store.WATERMARK)}
    storage.close()
    with LocalHistoryStorage.open(path) as reopened:
        with pytest.raises(store.SnapshotRejected):
            repo(reopened).load(first.digest)
        with reopened.exclusive():
            assert {key: reopened.read(key) for key in before} == before


@pytest.mark.parametrize("primary_state", ["missing", "predecessor"])
def test_repair_requires_matching_external_expectation(tmp_path, primary_state):
    path = tmp_path / "history.db"
    storage, raw, first = initialize(path)
    raw2, context2, _ = make_fixture(previous_package=raw, event_id=b"2" * 32)
    _, second = repo(storage).apply(raw2, context2, first.digest)
    with storage.exclusive():
        if primary_state == "missing":
            storage._db.execute("DELETE FROM values_store WHERE name=?", (store.PRIMARY,))
        else:
            storage.replace(store.PRIMARY, store.encode(first))
        before = storage.read(store.PRIMARY)
    storage.close()
    with LocalHistoryStorage.open(path) as reopened:
        with pytest.raises(store.SnapshotRejected):
            repo(reopened).load(first.digest)
        with reopened.exclusive():
            assert reopened.read(store.PRIMARY) == before
        assert repo(reopened).load(second.digest) == second
    with LocalHistoryStorage.open(path) as reopened:
        with reopened.exclusive():
            assert reopened.read(store.PRIMARY) == reopened.read(store.WATERMARK) == store.encode(second)


def test_missing_watermark_never_repairs_from_primary(tmp_path):
    path = tmp_path / "history.db"
    storage, _, first = initialize(path)
    with storage.exclusive():
        storage._db.execute("DELETE FROM values_store WHERE name=?", (store.WATERMARK,))
    storage.close()
    with LocalHistoryStorage.open(path) as reopened:
        with pytest.raises(store.SnapshotRejected):
            repo(reopened).load(first.digest)
        with reopened.exclusive():
            assert reopened.read(store.WATERMARK) is None
            assert reopened.read(store.PRIMARY) == store.encode(first)


def assert_latches_without_sql(repository, storage):
    storage._db.commit = None
    storage._db.rollback = False
    storage._db.primary = False
    storage._db.forbid_sql = True
    attempts = len(storage._db.attempts)
    with pytest.raises(store.StorageUnavailable, match="unavailable or nested ownership"):
        with storage.exclusive():
            pytest.fail("adapter uncertainty latch bypassed")
    with pytest.raises(store.StorageUnavailable, match="uncertain commit; fresh instance required"):
        repository.load(b"X" * 32)
    assert len(storage._db.attempts) == attempts
