import io, json, base64
import pytest

def test_reader_prefixes_real_file(tmp_path):
    from lab.remote_reader import read_prefix
    path=tmp_path/'stdout'; path.write_bytes(b'one\n')
    state={}
    first=read_prefix(str(path),state,1024)
    path.write_bytes(b'one\ntwo\n')
    second=read_prefix(str(path),state,1024)
    assert first == b'one\n'
    assert second == b'one\ntwo\n'

@pytest.mark.parametrize('kind',['truncate','rewrite','replace','limit'])
def test_reader_rejects_source_change(tmp_path,kind):
    from lab.remote_reader import read_prefix
    path=tmp_path/'stdout'; path.write_bytes(b'one\n')
    state={}; read_prefix(str(path),state,8)
    if kind=='truncate': path.write_bytes(b'o')
    if kind=='rewrite': path.write_bytes(b'two\n')
    if kind=='replace':
        path.rename(tmp_path/'old'); path.write_bytes(b'one\n')
    if kind=='limit': path.write_bytes(b'one\nmore\n')
    with pytest.raises(ValueError): read_prefix(str(path),state,8)

def test_reader_rejects_nonregular(tmp_path):
    from lab.remote_reader import read_prefix
    with pytest.raises((ValueError,OSError)): read_prefix(str(tmp_path),{},1024)

def test_frame_binding_and_sequence(tmp_path):
    from lab.bridge import FramedBridge
    b=FramedBridge(tmp_path/'capture',tmp_path/'inbox','run1','/exact/stdout')
    b.accept_frame(json.dumps(dict(schema='nbsr-lab-reader-start-v1',run='run1',source='/exact/stdout',state='waiting-for-source',cadence_seconds=5,lifetime_seconds=60,wire_budget=262144)).encode())
    row=dict(schema='nbsr-lab-prefix-v1',run='run1',source='/exact/stdout',sequence=1,file_identity=[1,2],prefix=base64.b64encode(b'').decode())
    b.accept_frame(json.dumps(row).encode())
    row['sequence']=3
    with pytest.raises(ValueError): b.accept_frame(json.dumps(row).encode())
    row['sequence']=2
    with pytest.raises(ValueError): b.accept_frame(json.dumps(row).encode())

def test_reader_lifetime_and_wire_budget(tmp_path):
    import subprocess, sys
    path=tmp_path/'stdout'; path.write_bytes(b'abc')
    result=subprocess.run([sys.executable,'-m','lab.remote_reader','--source',str(path),'--run','run1','--seconds','1','--wire-bytes','1024'],capture_output=True,timeout=5)
    assert result.returncode == 0
    rows=[json.loads(x) for x in result.stdout.splitlines()]
    assert rows[0]['schema']=='nbsr-lab-reader-start-v1'
    assert rows[1]['schema']=='nbsr-lab-prefix-v1'
    assert rows[-1]['reason']=='bounded-lifetime-expired'
    result=subprocess.run([sys.executable,'-m','lab.remote_reader','--source',str(path),'--run','run1','--seconds','1','--wire-bytes','1'],capture_output=True,timeout=5)
    assert result.returncode != 0
    assert result.stdout == b''

def test_frame_log_partial_and_bound(tmp_path):
    from lab.bridge import FrameLogPump
    rows=[]
    class Consumer:
        def accept_frame(self, raw): rows.append(raw)
    p=tmp_path/'log';p.write_bytes(b'abc')
    pump=FrameLogPump(Consumer(), 20)
    pump.poll(p); assert rows==[]
    p.write_bytes(b'abc\ndef\n');pump.poll(p)
    assert rows==[b'abc',b'def']
    p.write_bytes(b'bad\ndef\n')
    with pytest.raises(ValueError):pump.poll(p)

def test_reader_stops_on_source_final_not_campaign_validity(tmp_path):
    import subprocess,sys,time
    path=tmp_path/'stdout';path.write_bytes(b'{"schema":"nbsr-b5-grouped-final-v1"}\n')
    started=time.monotonic()
    result=subprocess.run([sys.executable,'-m','lab.remote_reader','--source',str(path),'--run','run1','--seconds','10','--wire-bytes','4096'],capture_output=True,timeout=3)
    assert result.returncode==0
    assert json.loads(result.stdout.splitlines()[-1])['reason']=='source-final-observed'
    assert time.monotonic()-started<3

def test_reader_start_before_missing_source(tmp_path):
    import subprocess,sys
    from lab.bridge import FramedBridge
    path=tmp_path/'missing'
    result=subprocess.run([sys.executable,'-m','lab.remote_reader','--source',str(path),'--run','run1','--seconds','1','--wire-bytes','4096'],capture_output=True,timeout=4)
    rows=result.stdout.splitlines()
    assert json.loads(rows[0])['schema']=='nbsr-lab-reader-start-v1'
    b=FramedBridge(tmp_path/'capture',tmp_path/'inbox','run1',str(path))
    b.accept_frame(rows[0]); assert b.started
    b.accept_frame(rows[-1]); assert b.ended
