import pytest
from lab.capture import CaptureSession
from tests.test_extractor import origin_line, line
from tests.test_grouped import progress, final

def test_capture_origin_opt_in(tmp_path):
    c = CaptureSession(tmp_path/'capture', 'fixture', origin_record=True)
    raw = origin_line()+line(progress())+line(final())
    c.append(raw, offset=0, source_identity='fixture')
    directory = c.finish()
    assert (directory/'raw.bin').read_bytes() == raw
    assert c.snapshot_path().read_bytes() == line(progress())+line(final())

def test_prefix_bridge_deduplicates_and_preserves_raw(tmp_path):
    from lab.bridge import PrefixBridge
    b = PrefixBridge(tmp_path/'capture', tmp_path/'inbox', 'fixture', 'experiment')
    first = origin_line()+line(progress())
    b.accept(first)
    b.accept(first)
    assert len(list((tmp_path/'inbox').glob('*.packet'))) == 1
    b.accept(first+line(final()))
    b.finish()
    assert len(list((tmp_path/'inbox').glob('*.packet'))) == 2
    assert b.capture.snapshot_path().parent.joinpath('raw.bin').read_bytes() == first+line(final())

@pytest.mark.parametrize('change', ['truncate','rewrite','bad'])
def test_prefix_bridge_failure_latches(tmp_path, change):
    from lab.bridge import PrefixBridge
    b = PrefixBridge(tmp_path/'capture', tmp_path/'inbox', 'fixture', 'experiment')
    first = origin_line()+line(progress())
    b.accept(first)
    bad = {'truncate':first[:-1], 'rewrite':b'X'+first[1:], 'bad':first+b'wrong\n'}[change]
    with pytest.raises(ValueError): b.accept(bad)
    with pytest.raises(ValueError): b.accept(first+line(final()))
    assert len(list((tmp_path/'inbox').glob('*.packet'))) == 1

def test_prefix_partial_does_not_publish(tmp_path):
    from lab.bridge import PrefixBridge
    b = PrefixBridge(tmp_path/'capture', tmp_path/'inbox', 'fixture', 'experiment')
    raw = origin_line()+line(progress())
    b.accept(raw[:-1])
    assert not (tmp_path/'inbox').exists()
    b.accept(raw)
    assert len(list((tmp_path/'inbox').glob('*.packet'))) == 1

def test_prefix_failure_to_publish_latches(tmp_path, monkeypatch):
    import lab.bridge as bridge
    b = bridge.PrefixBridge(tmp_path/'capture', tmp_path/'inbox', 'fixture', 'experiment')
    def fail(*args): raise OSError('disk')
    monkeypatch.setattr(bridge, 'export', fail)
    with pytest.raises(OSError): b.accept(origin_line()+line(progress()))
    with pytest.raises(ValueError): b.accept(origin_line()+line(progress()))
    assert b.capture.snapshot_path().exists()

def test_capture_explicit_budget(tmp_path):
    from lab.capture import CaptureSession
    c=CaptureSession(tmp_path/'small','fixture',origin_record=True,max_session_bytes=1)
    with pytest.raises(ValueError): c.append(origin_line()+line(progress()),offset=0,source_identity='fixture')
