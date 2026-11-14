import json, sqlite3
from contextlib import closing
import pytest
from lab.store import Store
from lab.feed import Inbox
from tests.test_feed import publish
from tests.test_grouped import progress

def test_owned_connections_closed_on_success_and_conflict(tmp_path,monkeypatch):
    refs=[]; original=Store.connect
    def tracked(self):
        db=original(self); refs.append(db); return db
    monkeypatch.setattr(Store,'connect',tracked)
    store=Store(tmp_path/'data'); inbox=Inbox(store,tmp_path/'inbox')
    publish(tmp_path,[progress()]); inbox.scan(); inbox.status()
    runs=store.runs(); store.artifacts(); store.artifact(runs[0]['sha256'])
    publish(tmp_path,[progress(p50_latency_ns=90000)]); inbox.scan()
    assert inbox.error
    for db in refs:
        with pytest.raises(sqlite3.ProgrammingError):db.execute('SELECT 1')

def test_held_reader_keeps_snapshot_and_raw_intact(tmp_path):
    store=Store(tmp_path/'data'); inbox=Inbox(store,tmp_path/'inbox')
    publish(tmp_path,[progress()]);inbox.scan()
    first=store.runs()[0]; raw=store.artifact(first['sha256'])
    with closing(store.connect()) as reader:
        reader.execute('BEGIN'); reader.execute('SELECT * FROM artifacts').fetchall()
        publish(tmp_path,[progress(),progress(2)]);inbox.scan()
        assert len(reader.execute('SELECT * FROM artifacts').fetchall())==1
        assert len(store.artifacts())==2
    assert store.artifact(first['sha256'])==raw
    assert inbox.status()['feeds'][0]['updates']==2
