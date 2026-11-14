import json, base64
import pytest
from lab.extractor import StdoutExtractor
from lab.bridge import FramedBridge
from tests.test_extractor import line, origin_line
from tests.test_grouped import progress, final


def direct_origin(**changes):
    row=json.loads(origin_line())
    del row['client_origin_ns']; del row['client_sample_ns']
    row.update(changes)
    return line(row)


def test_direct_explicit_profile_preserves_artifact_and_raw():
    p=StdoutExtractor('fixture',origin_record=True,origin_profile='direct')
    grouped=line(progress())+line(final())
    raw=direct_origin()+grouped
    got=p.append(raw,offset=0,source_identity='fixture')
    assert got['raw']==raw and got['artifact']==grouped
    assert p.finish()['ledger']['state']=='final'


@pytest.mark.parametrize('profile,origin',[('nbsr',direct_origin()),('direct',origin_line())])
def test_profile_never_autodetects_other_shape(profile,origin):
    p=StdoutExtractor('fixture',origin_record=True,origin_profile=profile)
    with pytest.raises(ValueError): p.append(origin+line(progress()),offset=0,source_identity='fixture')
    with pytest.raises(ValueError): p.snapshot()


@pytest.mark.parametrize('changes',[{'extra':0},{'sample_before_ns':True},{'origin_hi_ns':140},{'origin_lo_ns':-1},{'sample_after_ns':2**64}])
def test_direct_rejects_unreviewed_fields_types_bounds(changes):
    p=StdoutExtractor('fixture',origin_record=True,origin_profile='direct')
    with pytest.raises(ValueError): p.append(direct_origin(**changes),offset=0,source_identity='fixture')
    with pytest.raises(ValueError): p.snapshot()


@pytest.mark.parametrize('bad',[None,True,'Direct','auto',''])
def test_unknown_profile_rejected(bad):
    with pytest.raises(ValueError): StdoutExtractor('fixture',origin_record=True,origin_profile=bad)


def test_framed_direct_profile_and_identity_binding(tmp_path):
    b=FramedBridge(tmp_path/'capture',tmp_path/'inbox','run','/fixed/stdout',origin_profile='direct')
    b.accept_frame(line(dict(schema='nbsr-lab-reader-start-v1',run='run',source='/fixed/stdout',state='waiting-for-source',cadence_seconds=5,lifetime_seconds=60,wire_budget=262144)))
    raw=direct_origin()+line(progress())+line(final())
    row=dict(schema='nbsr-lab-prefix-v1',run='run',source='/fixed/stdout',sequence=1,file_identity=[1,2],prefix=base64.b64encode(raw).decode())
    b.accept_frame(line(row))
    assert b.bridge.capture.snapshot_path().read_bytes()==line(progress())+line(final())
    row['sequence']=2; row['source']='/wrong/stdout'
    with pytest.raises(ValueError): b.accept_frame(line(row))
    assert b.failed


def test_direct_origin_chunk_boundaries_and_duplicate_rejection():
    raw=direct_origin()+line(progress())
    for split in range(len(direct_origin())+1):
        p=StdoutExtractor('fixture',origin_record=True,origin_profile='direct')
        p.append(raw[:split],offset=0,source_identity='fixture')
        got=p.append(raw[split:],offset=split,source_identity='fixture')
        assert got['artifact']==line(progress())
        with pytest.raises(ValueError): p.append(direct_origin(),offset=len(raw),source_identity='fixture')
