"""Local prototype only: caller-owned private temp directory, no hostile paths.

SQLite serializes cooperating connections. This is not a deployed private-path
adapter, independent rollback anchor, process-wide lease or authority producer.
"""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from scripts.inclusion_persistence import PRIMARY, WATERMARK, StorageUnavailable


class LocalHistoryStorage:
    def __init__(self, connection):
        self._db = connection
        self._owned = False
        self._failed = False

    @classmethod
    def create(cls, path):
        path = Path(path).absolute()
        # Explicit fixture bootstrap; O_EXCL prevents replacing an existing store.
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        instance = cls.open(path, _bootstrap=True)
        try:
            with instance.exclusive():
                instance._db.execute("CREATE TABLE values_store (name TEXT PRIMARY KEY, value BLOB NOT NULL)")
        except BaseException:
            instance.close()
            # Retain the failed file for inspection; never silently bootstrap again.
            raise
        return instance

    @classmethod
    def open(cls, path, *, _bootstrap=False):
        connection = None
        try:
            connection = sqlite3.connect(Path(path).absolute().as_uri() + "?mode=rw", uri=True,
                                         timeout=0, isolation_level=None)
            connection.execute("PRAGMA synchronous=FULL")
            # Default rollback journal; no uncheckpointed WAL sidecar in backup tests.
            if connection.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
                raise StorageUnavailable("unsupported journal mode")
            if not _bootstrap:
                connection.execute("SELECT name, value FROM values_store LIMIT 0")
            return cls(connection)
        except BaseException as exc:
            if connection is not None:
                connection.close()
            if isinstance(exc, sqlite3.Error):
                raise StorageUnavailable("cannot open existing history") from exc
            raise

    @contextmanager
    def exclusive(self):
        if self._failed or self._owned:
            raise StorageUnavailable("unavailable or nested ownership")
        try:
            self._db.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as exc:
            raise StorageUnavailable("history ownership unavailable") from exc
        self._owned = True
        try:
            yield
            try:
                self._db.execute("COMMIT")
            except BaseException:
                self._failed = True
                raise
        except BaseException:
            try:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
            except BaseException:
                self._failed = True
                raise
            raise
        finally:
            self._owned = False

    def _check(self, name):
        if not self._owned or self._failed or name not in (PRIMARY, WATERMARK):
            raise StorageUnavailable("invalid access to history")

    def read(self, name):
        self._check(name)
        row = self._db.execute("SELECT value FROM values_store WHERE name=?", (name,)).fetchone()
        return None if row is None else bytes(row[0])

    def replace(self, name, data):
        self._check(name)
        if type(data) is not bytes:
            raise TypeError("history value must be bytes")
        self._db.execute("INSERT INTO values_store(name,value) VALUES(?,?) "
                         "ON CONFLICT(name) DO UPDATE SET value=excluded.value", (name, data))

    def close(self):
        if self._owned:
            raise StorageUnavailable("cannot close an owned transaction")
        self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
