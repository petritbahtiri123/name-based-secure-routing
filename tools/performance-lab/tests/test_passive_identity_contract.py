"""Synthetic P0 identity contracts, not saved producer exports or measurements."""
import base64
import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from lab.app import create_app
from lab.bridge import PrefixBridge
from lab.feed import Inbox, export
from lab.store import Store
from tests.test_direct_origin import direct_origin
from tests.test_extractor import line, origin_line
from tests.test_grouped import final, progress, snapshot


def test_two_passive_profiles_share_store_without_inventing_path_identity(tmp_path):
    data, directory = tmp_path / 'data', tmp_path / 'inbox'
    inbox = Inbox(Store(data), directory)
    # No lifespan context: synchronous scan, no background watcher or listener.
    client = TestClient(create_app(data, directory))
    expected = {}
    try:
        for profile, origin, p50 in [('direct', direct_origin(), 90000),
                                     ('nbsr', origin_line(), 100000)]:
            experiment = f'synthetic-{profile}-not-a-measurement'
            bridge = PrefixBridge(tmp_path / profile, directory, experiment,
                                  experiment, origin_profile=profile)
            first = line(progress(p50_latency_ns=p50))
            bridge.accept(origin + first)
            inbox.scan()
            partial_sha = hashlib.sha256(first).hexdigest()
            feeds = {f['experiment']: f for f in client.get('/api/v1/feed').json()['feeds']}
            assert feeds[experiment]['sha256'] == partial_sha
            assert feeds[experiment]['state'] == 'waiting'
            grouped = first + line(progress(2)) + line(final())
            bridge.accept(origin + grouped)
            bridge.finish()
            inbox.scan()
            expected[experiment] = (hashlib.sha256(grouped).hexdigest(), grouped)
        feeds = {f['experiment']: f for f in client.get('/api/v1/feed').json()['feeds']}
        assert set(feeds) == set(expected)
        runs = client.get('/api/v1/runs').json()['runs']
        assert len(runs) == 4
        by_sha = {r['sha256']: r for r in runs}
        for experiment, (sha, raw) in expected.items():
            assert feeds[experiment]['sha256'] == sha
            assert feeds[experiment]['state'] == 'final'
            assert feeds[experiment]['updates'] == 2
            run = by_sha[sha]
            assert run['implementation'] == 'Unknown path'
            assert run['stream']['declared_implementation'] is None
            assert run['provenance']['implementation_source'] == 'Producer implementation not recorded'
            assert run['stream']['validity'] == 'valid'
            response = client.get(f'/api/v1/artifacts/{sha}')
            assert response.status_code == 200
            assert response.content == raw
    finally:
        client.close()


@pytest.mark.parametrize('mutation', ['hash', 'envelope-claim', 'metadata-rebind'])
def test_mismatched_delivery_claim_cannot_replace_existing_snapshot(tmp_path, mutation):
    data, directory = tmp_path / 'data', tmp_path / 'inbox'
    inbox = Inbox(Store(data), directory)
    source = tmp_path / 'synthetic-only.json'
    source.write_text(json.dumps(snapshot([progress()])), encoding='utf-8')
    export(source, directory, 'synthetic-owner')
    wire = next(directory.glob('*.packet')).read_bytes()
    inbox.accept(wire)
    before = inbox.status()['feeds']
    original = source.read_bytes()
    packet = json.loads(wire)
    packet['sequence'] += 1
    if mutation == 'hash':
        packet['sha256'] = '0' * 64
    elif mutation == 'envelope-claim':
        packet['implementation'] = 'direct-quic'
    else:
        obj = snapshot([progress(), progress(2)])
        obj['metadata']['implementation'] = 'direct-quic'
        raw = json.dumps(obj).encode()
        packet['artifact'] = base64.b64encode(raw).decode()
        packet['sha256'] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):
        inbox.accept(json.dumps(packet).encode())
    assert inbox.status()['feeds'] == before
    assert len(inbox.store.runs()) == 1
    assert inbox.store.artifact(before[0]['sha256']) == original
