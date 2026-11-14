"""Local content-addressed evidence store; normalized views are rebuildable."""
import hashlib
import json
import re
import os
import tempfile
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from .adapters import ADAPTER_VERSION, MAX_BYTES
from .ingestion import normalize_artifact


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True,exist_ok=True)
        self.db = self.root / 'metadata.sqlite3'
        with closing(self.connect()) as db, db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS artifacts(sha256 TEXT PRIMARY KEY,size INTEGER NOT NULL,name TEXT NOT NULL,received TEXT NOT NULL,status TEXT NOT NULL,adapter TEXT NOT NULL,issue TEXT);
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,sha256 TEXT NOT NULL REFERENCES artifacts(sha256),body TEXT NOT NULL);
                PRAGMA user_version=1;
            ''')

    def connect(self):
        db = sqlite3.connect(self.db,timeout=10)
        db.execute('PRAGMA foreign_keys=ON')
        db.row_factory = sqlite3.Row
        return db

    def ingest(self, raw, name):
        if len(raw)>MAX_BYTES: raise ValueError('Artifact exceeds 4 MiB limit')
        sha = hashlib.sha256(raw).hexdigest()
        received = datetime.now(timezone.utc).isoformat()
        issue = None
        try:
            runs = normalize_artifact(raw)
            # Derived values must be serializable before any artifact transaction.
            # A normalization error is retained as quarantine, never an orphaned file.
            json.dumps(runs,allow_nan=False)
            if not runs: issue = 'Unsupported schema; original retained without normalized observations'
        except (ValueError, TypeError, KeyError, OverflowError) as e:
            runs = []; issue = str(e)
        status = 'imported' if runs else 'quarantined'
        target = self.root / 'sha256' / sha[:2] / sha
        target.parent.mkdir(parents=True,exist_ok=True)
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT received,adapter FROM artifacts WHERE sha256=?',(sha,)).fetchone()
            if previous: received = previous['received']
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.staging-',delete=False) as f:
                staged = Path(f.name)
                f.write(raw); f.flush(); os.fsync(f.fileno())
            try:
                try: os.link(staged,target)
                except FileExistsError:
                    if target.read_bytes() != raw: raise ValueError('Stored artifact integrity failure')
            finally:
                staged.unlink(missing_ok=True)
            db.execute('INSERT OR IGNORE INTO artifacts VALUES(?,?,?,?,?,?,?)',
                (sha,len(raw),Path(name).name[:160],received,status,ADAPTER_VERSION,issue))
            if previous and previous['adapter'] != ADAPTER_VERSION:
                db.execute('DELETE FROM runs WHERE sha256=?',(sha,))
                db.execute('UPDATE artifacts SET status=?,adapter=?,issue=? WHERE sha256=?',(status,ADAPTER_VERSION,issue,sha))
            for index, run in enumerate(runs):
                identity = f'{sha[:24]}-{index}'
                run.update(id=identity,sha256=sha,received=received)
                db.execute('INSERT OR IGNORE INTO runs VALUES(?,?,?)',(identity,sha,json.dumps(run,allow_nan=False)))
        return dict(sha256=sha,status=status,runs=len(runs),issue=issue)

    def runs(self):
        with closing(self.connect()) as db, db:
            return [json.loads(row['body']) for row in db.execute('SELECT body FROM runs ORDER BY rowid DESC')]

    def artifacts(self):
        with closing(self.connect()) as db, db:
            return [dict(row) for row in db.execute('SELECT * FROM artifacts ORDER BY received DESC')]

    def artifact(self, sha):
        if not re.fullmatch('[a-f0-9]{64}',sha): raise FileNotFoundError()
        with closing(self.connect()) as db, db:
            if not db.execute('SELECT 1 FROM artifacts WHERE sha256=?',(sha,)).fetchone(): raise FileNotFoundError()
        raw = (self.root/'sha256'/sha[:2]/sha).read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha: raise ValueError('Stored artifact integrity failure')
        return raw
