import json
from pathlib import PurePosixPath

import pytest

from scripts.performance import linux_native_lifecycle as native
from scripts.performance import linux_native_lifecycle_pair as pair
from scripts.performance import linux_native_cycle_run as run
from scripts.performance.linux_b5_placement import seal_output
from tests.performance.test_linux_native_cycle_run import config
from tests.performance.test_linux_native_cycle_streams import many_stream_peers
from tests.performance.test_linux_native_cycle_pair import write, SHA


def command(role, channels, streams=1):
    return native.cycle_command(role=role,cycles=2,channels=channels,streams=streams,binaries=PurePosixPath('/bins'),
        authority=PurePosixPath('/private/tls'),lifecycle=PurePosixPath('/private/lifecycle'),
        output=PurePosixPath('/output'),bind='192.0.2.1:0' if role=='source' else '192.0.2.2:0',
        endpoint='192.0.2.2:4444' if role=='source' else None)


@pytest.mark.parametrize('channels',[16,32])
def test_channel_shape_reaches_commands(channels):
    value=config() | dict(channels=channels)
    run.validate_config(value)
    argv=run.endpoint_arguments(value,'source')
    assert argv[argv.index('--channels')+1]==str(channels)
    argv,_=command('source',channels)
    assert argv[argv.index('--services')+1]==str(channels)
    _,env=command('destination',channels)
    assert env['NBSR_PERF_LIFECYCLE_SERVICES']==str(channels)
    assert env['NBSR_PERF_STREAMS_PER_SERVICE']=='1'


@pytest.mark.parametrize('channels',[True,0,33,16.0,'16'])
def test_invalid_channel_count(channels):
    with pytest.raises(ValueError):
        command('source',channels)


def test_combined_axes_not_declared():
    with pytest.raises(ValueError):
        command('source',16,16)


def channel_peers(tmp_path):
    roots=many_stream_peers(tmp_path)
    for role,root in zip(('source','destination'),roots,strict=True):
        env=json.loads((root/'environment.json').read_bytes())
        env.update(channels=16,streams=1)
        original=env['fixture_sha256']['service']
        env['fixture_sha256']['service']={f'{i:02}/{n}':h for i in range(16) for n,h in original.items()}
        write(root,'environment.json',env)
        argv,overrides=command(role,16)
        write(root,'command.json',dict(argv=['/usr/bin/taskset','--cpu-list','0',*argv],environment_overrides=overrides))
        if role=='source':
            rows=[json.loads(line) for line in (root/'stdout').read_text().splitlines()]
            for row in rows:
                if row.get('phase')=='b3_materialized_streams_ready':
                    row['service_channels_current_live']=16
            (root/'stdout').write_text(''.join(json.dumps(row)+'\n' for row in rows))
        else:
            server=json.loads((root/'server-result.json').read_bytes())
            server.update(services_per_connection=16,streams_per_service=1)
            write(root,'server-result.json',server)
        seal_output(root)
    return roots


@pytest.mark.parametrize('role',['source','destination'])
def test_all_channel_samples_and_authorities_replay(tmp_path,role):
    roots=channel_peers(tmp_path)
    result=pair.check_peer(roots[0 if role=='source' else 1],role,SHA,2,cycles=2,channels=16)
    assert result['outcome']['successful']==2


@pytest.mark.parametrize('mutation',['missing-authority','wrong-active','wrong-metadata'])
def test_channel_shape_rejection(tmp_path,mutation):
    roots=channel_peers(tmp_path)
    role='destination' if mutation=='wrong-metadata' else 'source'
    root=roots[1 if role=='destination' else 0]
    if mutation=='missing-authority':
        env=json.loads((root/'environment.json').read_bytes())
        del env['fixture_sha256']['service']['15/name.txt']
        write(root,'environment.json',env)
    elif mutation=='wrong-active':
        rows=[json.loads(line) for line in (root/'stdout').read_text().splitlines()]
        rows[0]['service_channels_current_live']=1
        (root/'stdout').write_text(''.join(json.dumps(row)+'\n' for row in rows))
    else:
        server=json.loads((root/'server-result.json').read_bytes())
        server['services_per_connection']=1
        write(root,'server-result.json',server)
    seal_output(root)
    with pytest.raises(ValueError):
        pair.check_peer(root,role,SHA,2,cycles=2,channels=16)


def test_every_authority_is_bound(tmp_path):
    tls=tmp_path/'tls'
    root=tmp_path/'lifecycle'
    tls.mkdir()
    for name in ('ca.der','source.der','destination.der','source-key.der'):
        (tls/name).write_bytes(b'fixture')
    names=('name.txt','route-open-body.cbor','federation-context.cbor','source.cose',
           'destination.cose','request-id.bin','channel-id.bin','route-id.bin','grant-digest.bin')
    for i in range(16):
        folder=root/f'{i:02}'
        folder.mkdir(parents=True)
        for name in names:
            (folder/name).write_bytes(str(i).encode())
    before=native.immutable_fixture(tls,root,'source',16)
    assert len(before['service'])==16*len(names)
    (root/'15/name.txt').write_bytes(b'changed')
    after=native.immutable_fixture(tls,root,'source',16)
    assert before!=after
    assert {k for k in before['service'] if before['service'][k]!=after['service'][k]}=={'15/name.txt'}
