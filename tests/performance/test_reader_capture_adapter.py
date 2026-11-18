import ast,base64,hashlib,json,pathlib,sys,threading
import pytest
BASE=pathlib.Path(__file__).resolve().parents[2]
sys.path[:0]=[str(BASE),str(BASE/'tools/performance-lab')]
from scripts.performance.reader_acquisition import Acquisition
from lab.bridge import FramedBridge,FrameLogPump

def fixture():
    ns={'json':json}
    for name,wanted in [('test_grouped.py',{'progress','final'}),('test_extractor.py',{'origin_line','line'})]:
        tree=ast.parse((BASE/'tools/performance-lab/tests'/name).read_text())
        exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in wanted],type_ignores=[]),name,'exec'),ns)
    return ns

@pytest.mark.parametrize('bad',[None,'missing-final','partial-frame','wrong-identity','disk-log','disk-raw','disk-manifest','disk-grouped','replace-log'])
def test_actual_parser_and_acquisition_final_capture(tmp_path,bad):
    path=BASE/'scripts/performance/reader_capture.py'
    assert path.is_file(), 'final capture adapter missing'
    from scripts.performance.reader_capture import FinalCapture
    f=fixture();raw=f['origin_line']()+f['line'](f['progress']())+f['line'](f['progress'](2))
    if bad!='missing-final':raw+=f['line'](f['final']())
    rows=[dict(schema='nbsr-lab-reader-start-v1',run='r',source='/fixture',state='waiting-for-source',cadence_seconds=5,lifetime_seconds=80,wire_budget=131072),
          dict(schema='nbsr-lab-prefix-v1',run='r',source='/fixture',sequence=1,file_identity=[1,2],prefix=base64.b64encode(raw).decode()),
          dict(schema='nbsr-lab-reader-ended-v1',run='r',reason='source-final-observed',observations=1)]
    wire=b''.join(f['line'](r) for r in rows)+(b'{' if bad=='partial-frame' else b'')
    log=tmp_path/'stdout.log';log.write_bytes(wire)
    consumer=FramedBridge(tmp_path/'capture',tmp_path/'inbox','r','/fixture');pump=FrameLogPump(consumer,131072)
    gate=threading.Event();holder={}
    def reader():
        assert gate.wait(2)
        return holder['capture'](dict(run='wrong' if bad=='wrong-identity' else 'r',source='/fixture',owner='a'*64))
    def poll(*,final):
        pump.poll(log)
        if final:consumer.bridge.finish()
        return {'ready':consumer.started}
    acq=Acquisition(reader,poll,interval=.01,whole=2,ready_budget=1)
    capture=FinalCapture(acq,consumer,pump,run='r',source='/fixture',wire_cap=131072,log_path=log)
    holder['capture']=capture;acq.start(wait_ready=False);gate.set();result=acq.finish()
    if bad in ('missing-final','partial-frame','wrong-identity'):
        assert result['status']=='INVALID_ACQUISITION'
    else:
        assert result['status']=='LOCAL_READER_JOINED',json.dumps(result['errors'])
        assert result['reader_value']==dict(run='r',source='/fixture',owner='a'*64,quiescent=True,final_valid=True,sha256=hashlib.sha256(raw).hexdigest())
        capture.verify()
        if bad and bad.startswith('disk-'):
            name={'disk-log':None,'disk-raw':'raw.bin','disk-manifest':'manifest.json','disk-grouped':'grouped.ndjson'}[bad]
            target=log if name is None else consumer.bridge.capture._directory/f'snapshot-{consumer.bridge.capture._sequence:04d}'/name
            original=target.read_bytes();target.write_bytes(original+b'x')
            with pytest.raises(ValueError):capture.verify()
            target.write_bytes(original)
            with pytest.raises(ValueError):capture.verify()  # restoration never clears failure
        elif bad=='replace-log':
            replacement=log.with_suffix('.replacement');replacement.write_bytes(log.read_bytes());replacement.replace(log)
            with pytest.raises(ValueError):capture.verify()
        else:
            consumer.bridge._prefix+=b'x'
            with pytest.raises(ValueError):capture.verify()
