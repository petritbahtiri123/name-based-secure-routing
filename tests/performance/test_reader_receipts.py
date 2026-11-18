import hashlib,json,pathlib,sys
import pytest
BASE=pathlib.Path(__file__).resolve().parents[2];sys.path.insert(0,str(BASE))
from scripts.performance import reader_output_limits as limits


def test_closed_and_settled_receipts_are_distinct_bounded_and_hash_linked(tmp_path):
    p=BASE/'scripts/performance/reader_receipts.py';assert p.is_file(),'versioned persistent receipts missing'
    from scripts.performance.reader_receipts import ReceiptPair
    claim=limits.live_completion_claim(limits.ClaimBook())
    identity=dict(run='r',source='/fixture',owner='a'*64,request_sha256='b'*64)
    pair=ReceiptPair(tmp_path,claim,identity,checkpoint=lambda:None)
    closed=pair.publish_closed('c'*64)
    assert closed['state']=='CLOSED_UNSETTLED' and closed['campaign_valid'] is False
    first=tmp_path/'reader-closed-v2.json';sha=hashlib.sha256(first.read_bytes()).hexdigest()
    settled=pair.publish_settled(valid=True,settlement_sha256='d'*64)
    assert settled['closed_receipt_sha256']==sha and settled['campaign_valid'] is False
    assert pair.verify_pair()['state']=='SETTLED_REQUIRES_OTHER_GATES'
    assert claim.reserved_bytes==2*sum(p.stat().st_size for p in tmp_path.iterdir())
    old=first.read_bytes();first.write_bytes(old+b' ')
    with pytest.raises(ValueError):pair.verify_pair()
    first.write_bytes(old)
    with pytest.raises(ValueError):pair.verify_pair()


def test_receipt_failure_cannot_restore_or_publish_settled(tmp_path):
    from scripts.performance.reader_receipts import ReceiptPair
    pair=ReceiptPair(tmp_path,limits.live_completion_claim(limits.ClaimBook()),
        dict(run='r',source='/fixture',owner='a'*64,request_sha256='b'*64),checkpoint=lambda:None)
    with pytest.raises(ValueError):pair.publish_settled(valid=True,settlement_sha256='d'*64)
    with pytest.raises(ValueError):pair.publish_closed('c'*64)


def test_receipt_pair_reserves_only_existing_16k_for_two_alias_pairs_and_result(tmp_path):
    from scripts.performance.reader_receipts import ReceiptPair
    pair=ReceiptPair(tmp_path,limits.live_completion_claim(limits.ClaimBook()),
        dict(run='r',source='x'*2500,owner='a'*64,request_sha256='b'*64),checkpoint=lambda:None)
    with pytest.raises(ValueError,match='cap'):pair.publish_closed('c'*64)


@pytest.mark.parametrize('size',[8192,8193])
def test_acquisition_result_8k_partition_uses_same_claim_without_truncation(tmp_path,size):
    from scripts.performance.reader_receipts import ReceiptPair
    claim=limits.live_completion_claim(limits.ClaimBook())
    pair=ReceiptPair(tmp_path,claim,dict(run='r',source='/fixture',owner='a'*64,request_sha256='b'*64),checkpoint=lambda:None)
    pair.publish_closed('c'*64);pair.publish_settled(valid=True,settlement_sha256='d'*64)
    value=dict(status='LOCAL_READER_JOINED',joined=True,errors=[],identity=pair.identity,padding='')
    value['padding']='x'*(size-len(json.dumps(value,sort_keys=True,separators=(',',':')).encode()))
    assert hasattr(pair,'publish_result'),'shared result partition missing'
    if size==8193:
        with pytest.raises(ValueError,match='8KiB'):pair.publish_result(value)
        assert not (tmp_path/'acquisition-result.json').exists()
    else:
        before=claim.reserved_bytes;pair.publish_result(value)
        assert claim.reserved_bytes==before+8192 and claim.reserved_bytes<=16384
        assert json.loads((tmp_path/'acquisition-result.json').read_bytes())==value
        with pytest.raises(ValueError):pair.publish_result(value)

@pytest.mark.parametrize("change", [{"joined":False},{"errors":["failure"]},{"identity":{}}])
def test_contradictory_result_latches(tmp_path,change):
    from scripts.performance.reader_receipts import ReceiptPair
    pair=ReceiptPair(tmp_path,limits.live_completion_claim(limits.ClaimBook()),dict(run='r',source='/fixture',owner='a'*64,request_sha256='b'*64),checkpoint=lambda:None)
    pair.publish_closed('c'*64);pair.publish_settled(valid=True,settlement_sha256='d'*64)
    value=dict(status='LOCAL_READER_JOINED',joined=True,errors=[],identity=pair.identity);value.update(change)
    with pytest.raises(ValueError):pair.publish_result(value)
    with pytest.raises(ValueError):pair.verify_pair()

def test_result_mutation_then_restore_latches(tmp_path):
    from scripts.performance.reader_receipts import ReceiptPair
    pair=ReceiptPair(tmp_path,limits.live_completion_claim(limits.ClaimBook()),dict(run='r',source='/fixture',owner='a'*64,request_sha256='b'*64),checkpoint=lambda:None)
    pair.publish_closed('c'*64);pair.publish_settled(valid=True,settlement_sha256='d'*64)
    pair.publish_result(dict(status='LOCAL_READER_JOINED',joined=True,errors=[],identity=pair.identity))
    pair.verify_complete()
    path=tmp_path/'acquisition-result.json';original=path.read_bytes();path.write_bytes(original+b' ')
    with pytest.raises(ValueError):pair.verify_pair()
    path.write_bytes(original)
    with pytest.raises(ValueError):pair.verify_complete()

@pytest.mark.parametrize('boundary', ['closed-fsync', 'closed-link', 'result-fsync'])
def test_publication_io_failure_retains_charge_and_cannot_retry(tmp_path, monkeypatch, boundary):
    from scripts.performance import reader_receipts as receipts

    claim = limits.live_completion_claim(limits.ClaimBook())
    pair = receipts.ReceiptPair(
        tmp_path, claim,
        dict(run='r', source='/fixture', owner='a' * 64, request_sha256='b' * 64),
        checkpoint=lambda: None,
    )
    value = dict(status='LOCAL_READER_JOINED', joined=True, errors=[], identity=pair.identity)
    if boundary == 'result-fsync':
        pair.publish_closed('c' * 64)
        pair.publish_settled(valid=True, settlement_sha256='d' * 64)
    before = claim.reserved_bytes
    operation = 'link' if boundary == 'closed-link' else 'fsync'

    def fail(*args):
        raise OSError('injected publication I/O failure')

    with monkeypatch.context() as patch:
        patch.setattr(receipts.os, operation, fail)
        with pytest.raises(OSError, match='injected publication'):
            if boundary == 'result-fsync':
                pair.publish_result(value)
            else:
                pair.publish_closed('c' * 64)

    retained = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    name = 'acquisition-result.json' if boundary == 'result-fsync' else 'reader-closed-v2.json.pending'
    assert retained[name]
    assert json.loads(retained[name]) == (value if boundary == 'result-fsync' else dict(
        schema='nbsr-reader-lifecycle-receipt-v2', state='CLOSED_UNSETTLED',
        **pair.identity, capture_sha256='c' * 64, campaign_valid=False,
    ))
    multiplier = 1 if boundary == 'result-fsync' else 2
    assert claim.reserved_bytes == before + multiplier * len(retained[name])
    assert pair.failed and claim.failed
    charged = claim.reserved_bytes
    if boundary != 'result-fsync':
        assert 'reader-closed-v2.json' not in retained
    # Restoring the OS operation must not resurrect the failed publication.
    for attempt in (
        lambda: pair.publish_closed('c' * 64),
        lambda: pair.publish_settled(valid=True, settlement_sha256='d' * 64),
        lambda: pair.publish_result(value),
        pair.verify_complete,
    ):
        with pytest.raises(ValueError, match='latched'):
            attempt()
    assert claim.reserved_bytes == charged
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == retained
