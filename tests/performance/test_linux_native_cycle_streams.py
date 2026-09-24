import json
from pathlib import PurePosixPath

import pytest

from scripts.performance import linux_native_lifecycle as native
from scripts.performance import linux_native_lifecycle_pair as pair
from scripts.performance import linux_native_cycle_run as run
from scripts.performance.linux_b5_placement import seal_output
from scripts.performance.post_close_cleanup import FIELDS
from tests.performance.test_linux_native_cycle_run import config
from tests.performance.test_linux_native_cycle_pair import cycle_peers, write, SHA


def command(role, streams):
    return native.cycle_command(role=role,cycles=2,streams=streams,binaries=PurePosixPath('/bins'),
        authority=PurePosixPath('/private/tls'),lifecycle=PurePosixPath('/private/lifecycle'),
        output=PurePosixPath('/output'),bind='192.0.2.1:0' if role=='source' else '192.0.2.2:0',
        endpoint='192.0.2.2:4444' if role=='source' else None)


@pytest.mark.parametrize('streams',[16,32,64])
def test_stream_count_reaches_both_peers_and_remote_arguments(streams):
    value=config() | dict(streams=streams)
    assert run.validate_config(value)==value
    argv=run.endpoint_arguments(value,'source')
    assert argv[argv.index('--streams')+1]==str(streams)
    source,_=command('source',streams)
    assert source[source.index('--streams-per-service')+1]==str(streams)
    assert source[source.index('--services')+1]=='1'
    _,env=command('destination',streams)
    assert env['NBSR_PERF_STREAMS_PER_SERVICE']==str(streams)
    assert env['NBSR_PERF_LIFECYCLE_SERVICES']=='1'


@pytest.mark.parametrize('streams',[True,0,65,16.0,'16'])
def test_invalid_stream_count_rejects(streams):
    with pytest.raises(ValueError):
        command('source',streams)


def many_stream_peers(tmp_path):
    roots=cycle_peers(tmp_path)
    for role,root in zip(('source','destination'),roots,strict=True):
        env=json.loads((root/'environment.json').read_bytes())
        env['streams']=16
        write(root,'environment.json',env)
        argv,overrides=command(role,16)
        write(root,'command.json',dict(argv=['/usr/bin/taskset','--cpu-list','0',*argv],environment_overrides=overrides))
        final=dict(phase='lifecycle_cleanup',**dict.fromkeys(FIELDS,0))
        rows=[]
        server=None
        if role=='source':
            for cycle in range(2):
                rows.append(dict(phase='b3_materialized_streams_ready',transport_sessions_current_live=1,
                    service_channels_current_live=1,application_streams_current_live=16,quic_streams_current_live=16))
                rows.extend(dict(sample_id=cycle*16+i,logical_client_id=cycle,success=True,bytes_transmitted=1024,bytes_received=1024) for i in range(16))
                rows.append(dict(phase=f'lifecycle_cycle_{cycle}_closed',**dict.fromkeys(FIELDS,0)))
        else:
            server=dict(status='PASS',connections=2,services_per_connection=1,streams_per_service=16,samples=[{} for _ in range(32)])
            write(root,'server-result.json',server)
        rows.append(final)
        (root/('stdout' if role=='source' else 'diagnostics.ndjson')).write_text(''.join(json.dumps(r)+'\n' for r in rows))
        seal_output(root)
    return roots


@pytest.mark.parametrize('role',['source','destination'])
def test_replay_verifies_every_materialized_stream(tmp_path,role):
    roots=many_stream_peers(tmp_path)
    result=pair.check_peer(roots[0 if role=='source' else 1],role,SHA,2,cycles=2,streams=16)
    assert result['outcome']['successful']==2


@pytest.mark.parametrize('mutation',['missing-sample','wrong-cycle','active-count','metadata'])
def test_wrong_stream_cardinality_never_passes(tmp_path,mutation):
    roots=many_stream_peers(tmp_path)
    root=roots[1 if mutation=='metadata' else 0]
    role='destination' if mutation=='metadata' else 'source'
    if mutation=='metadata':
        value=json.loads((root/'server-result.json').read_bytes())
        value['streams_per_service']=1
        write(root,'server-result.json',value)
    else:
        rows=[json.loads(line) for line in (root/'stdout').read_text().splitlines()]
        if mutation=='missing-sample':
            rows.pop(1)
        elif mutation=='wrong-cycle':
            rows[1]['logical_client_id']=1
        else:
            rows[0]['application_streams_current_live']=1
        (root/'stdout').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    seal_output(root)
    with pytest.raises(ValueError):
        pair.check_peer(root,role,SHA,2,cycles=2,streams=16)
