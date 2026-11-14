"""Synthetic extraction fixtures; never touch the production inbox/data store."""
import hashlib
import importlib
import json
import pytest
from lab.feed import Inbox, export, inspect
from lab.store import Store
from tests.test_grouped import progress, final


def extractor():
    try:
        module = importlib.import_module('lab.extractor')
    except ModuleNotFoundError as error:
        if error.name != 'lab.extractor':
            raise
        pytest.fail('Local stdout extractor is not implemented')
    return module.StdoutExtractor('synthetic-source-identity')


def line(obj):
    return json.dumps(obj, separators=(',', ':')).encode() + b'\n'


def append(parser, raw, offset=0, source_identity='synthetic-source-identity'):
    return parser.append(raw, offset=offset, source_identity=source_identity)


def test_exact_grouped_bytes_offsets_and_diagnostic_exclusion():
    parser = extractor()
    diagnostic = line({'event': 'diagnostic', 'schema': 'nbsr-rust-ownership-v1',
                       'private_detail': 'local-only synthetic diagnostic'})
    grouped = json.dumps(progress(), indent=None).encode() + b'\r\n'
    raw = diagnostic + grouped
    result = append(parser, raw)
    assert result['artifact'] == grouped
    assert result['raw'] == raw
    ledger = result['ledger']
    assert ledger['source_bytes'] == len(raw)
    assert ledger['source_sha256'] == hashlib.sha256(raw).hexdigest()
    assert ledger['artifact_sha256'] == hashlib.sha256(grouped).hexdigest()
    assert ledger['pending_bytes'] == 0
    assert ledger['state'] == 'partial'
    assert [(r['start'], r['end'], r['kind']) for r in ledger['records']] == [
        (0, len(diagnostic), 'diagnostic'), (len(diagnostic), len(raw), 'grouped')]
    assert ledger['records'][0]['sha256'] == hashlib.sha256(diagnostic).hexdigest()
    assert 'private_detail' not in json.dumps(ledger)
    ledger['records'].clear()
    assert len(parser.snapshot()['ledger']['records']) == 2


def test_split_lines_wait_without_inventing_progress():
    parser = extractor()
    first, second = line(progress()), line(progress(2))
    assert append(parser, first[:37])['artifact'] is None
    result = append(parser, first[37:] + second[:19], offset=37)
    assert result['artifact'] == first
    assert result['ledger']['pending_bytes'] == 19
    result = append(parser, second[19:], offset=len(first) + 19)
    assert result['artifact'] == first + second
    assert result['ledger']['pending_bytes'] == 0


def test_synthetic_extracted_shapes_use_existing_feed_contract(tmp_path):
    parser = extractor()
    inbox = Inbox(Store(tmp_path / 'data'), tmp_path / 'inbox')
    source = tmp_path / 'synthetic-reviewed.ndjson'
    offset = 0
    for row in [progress(), progress(2), final()]:
        raw = line(row)
        result = append(parser, raw, offset=offset)
        offset += len(raw)
        source.write_bytes(result['artifact'])
        assert export(source, tmp_path / 'inbox', 'synthetic-extractor-only')
        inbox.scan()
    result = parser.finish()
    assert result['ledger']['state'] == 'final'
    assert inbox.status()['feeds'][0]['state'] == 'final'
    assert inbox.status()['feeds'][0]['updates'] == 3
    assert inbox.store.artifact(inbox.status()['feeds'][0]['sha256']) == result['artifact']


@pytest.mark.parametrize('tail', [
    b'not-json\n', b'{"schema":1,"schema":2}\n', b'{"value":NaN}\n',
    b'{"value":1e999}\n', b'[]\n', b'\xff\n', b'\n',
    line({'schema': 'unreviewed-schema', 'event': 'diagnostic'}),
    line({'schema': 'nbsr-rust-ownership-v1', 'event': 'unexpected'}),
], ids=['text', 'duplicate-key', 'nan', 'infinity', 'array', 'utf8', 'blank',
        'unknown-diagnostic', 'wrong-diagnostic-event'])
def test_unknown_or_malformed_line_latches_unavailable(tail):
    parser = extractor()
    first = line(progress())
    with pytest.raises(ValueError):
        append(parser, first + tail)
    assert parser.retained_raw == first + tail
    with pytest.raises(ValueError, match='unavailable'):
        parser.snapshot()
    with pytest.raises(ValueError, match='unavailable'):
        append(parser, line(progress(2)), offset=len(first) + len(tail))


@pytest.mark.parametrize('offset,identity', [(0, 'synthetic-source-identity'),
                                           (9999, 'synthetic-source-identity'),
                                           (None, 'changed-source-identity'),
                                           (True, 'synthetic-source-identity')],
                         ids=['replayed', 'gap', 'changed-identity', 'bool-offset'])
def test_conflicting_offset_or_source_identity_stops_delivery(offset, identity):
    parser = extractor()
    first = line(progress())
    append(parser, first)
    with pytest.raises(ValueError):
        append(parser, line(progress(2)), offset=len(first) if offset is None else offset,
               source_identity=identity)
    with pytest.raises(ValueError, match='unavailable'):
        parser.snapshot()


@pytest.mark.parametrize('tail', [line(progress(3)),
                                 line({'event': 'diagnostic', 'schema': 'nbsr-rust-ownership-v1'}),
                                 b'{'], ids=['progress', 'diagnostic', 'partial-tail'])
def test_no_bytes_after_final_are_allowed(tail):
    parser = extractor()
    raw = line(progress()) + line(progress(2)) + line(final())
    append(parser, raw)
    with pytest.raises(ValueError):
        append(parser, tail, offset=len(raw))


@pytest.mark.parametrize('raw', [b'', line(progress()), line(progress()) + b'{'],
                         ids=['empty', 'missing-final', 'unfinished-tail'])
def test_explicit_finish_requires_complete_final(raw):
    parser = extractor()
    append(parser, raw)
    with pytest.raises(ValueError):
        parser.finish()


def test_semantic_failure_is_retained_as_invalid_not_dropped():
    parser = extractor()
    raw = line(progress(errors=1, evidence_valid=False))
    result = append(parser, raw)
    assert result['artifact'] == raw
    assert result['ledger']['measurement_validity'] == 'invalid'


def test_structurally_unsupported_grouped_record_is_rejected():
    parser = extractor()
    row = progress()
    row['unsupported_secret_field'] = 'synthetic-only'
    with pytest.raises(ValueError):
        append(parser, line(row))


@pytest.mark.parametrize('raw', [b' ' * 65537, b' ' * 65536 + b'\n',
                               b'x' * (4 * 1024 * 1024 + 1)],
                         ids=['unfinished-line', 'completed-line', 'source-byte-limit'])
def test_byte_and_line_limits_include_pending_tails(raw):
    parser = extractor()
    with pytest.raises(ValueError):
        append(parser, raw)


def test_source_record_budget_counts_excluded_diagnostics():
    parser = extractor()
    diagnostic = line({'event': 'diagnostic', 'schema': 'nbsr-rust-ownership-v1'})
    result = append(parser, diagnostic * 4096)
    assert result['artifact'] is None
    with pytest.raises(ValueError):
        append(parser, line(progress()), offset=len(diagnostic) * 4096)


def assert_unavailable(parser):
    for operation in (parser.snapshot, parser.finish,
                      lambda: append(parser, b'', offset=len(parser.retained_raw))):
        with pytest.raises(ValueError, match='unavailable'):
            operation()


@pytest.mark.parametrize('split', [False, True], ids=['coalesced', 'prior-valid-prefix'])
def test_review_numeric_overflow_latches_all_publication_paths(split):
    parser = extractor()
    first = line(progress())
    bad = line(progress(2, goodput_bytes_per_second=10**400))
    if split:
        assert append(parser, first)['ledger']['measurement_validity'] == 'valid'
    with pytest.raises(ValueError):
        append(parser, bad if split else first + bad,
               offset=len(first) if split else 0)
    assert parser.retained_raw == first + bad
    assert_unavailable(parser)
    with pytest.raises(ValueError, match='unavailable'):
        append(parser, line(progress(2)), offset=len(first) + len(bad))


@pytest.mark.parametrize('mode', ['coalesced', 'after-final', 'after-finish'])
@pytest.mark.parametrize('tail', [line(progress(3)),
                                 line({'event': 'diagnostic', 'schema': 'nbsr-rust-ownership-v1'}),
                                 b'{'], ids=['progress', 'diagnostic', 'partial-tail'])
def test_review_post_final_retention_is_independent_of_chunking(mode, tail):
    parser = extractor()
    complete = line(progress()) + line(progress(2)) + line(final())
    if mode != 'coalesced':
        append(parser, complete)
        if mode == 'after-finish':
            parser.finish()
    with pytest.raises(ValueError):
        append(parser, complete + tail if mode == 'coalesced' else tail,
               offset=0 if mode == 'coalesced' else len(complete))
    assert parser.retained_raw == complete + tail
    assert_unavailable(parser)


@pytest.mark.parametrize('split', [False, True], ids=['coalesced', 'prior-valid-prefix'])
def test_review_internal_carriage_return_cannot_reach_feed(split):
    parser = extractor()
    first = line(progress())
    bad = line(progress(2)).replace(b'{', b'{\r', 1)
    if split:
        append(parser, first)
    with pytest.raises(ValueError):
        append(parser, bad if split else first + bad,
               offset=len(first) if split else 0)
    assert parser.retained_raw == first + bad
    assert_unavailable(parser)


def test_every_split_boundary_preserves_utf8_crlf_and_feed_compatibility():
    diagnostic = json.dumps({'event': 'diagnostic', 'schema': 'nbsr-rust-ownership-v1',
                             'text': 'Kosovë € escaped carriage return: \r'},
                            ensure_ascii=False).encode('utf-8') + b'\r\n'
    first = line(progress()).replace(b'\n', b'\r\n')
    last = line(final()).replace(b'\n', b'\r\n')
    raw = diagnostic + first + line(progress(2)) + last
    reference = append(extractor(), raw)
    assert inspect(reference['artifact'])[0]['stream']['state'] == 'final'
    for boundary in range(len(raw) + 1):
        parser = extractor()
        append(parser, raw[:boundary])
        result = append(parser, raw[boundary:], offset=boundary)
        assert result == reference, f'Chunk boundary {boundary}'
        assert parser.finish() == reference


def sized_diagnostic(size):
    prefix = b'{"event":"diagnostic","schema":"nbsr-rust-ownership-v1","text":"'
    suffix = b'"}\n'
    return prefix + b'x' * (size - len(prefix) - len(suffix)) + suffix


@pytest.mark.parametrize('size', [65535, 65536, 65537])
def test_exact_line_budget_boundary(size):
    parser = extractor()
    raw = sized_diagnostic(size)
    if size > 65536:
        with pytest.raises(ValueError):
            append(parser, raw)
        assert_unavailable(parser)
    else:
        result = append(parser, raw)
        assert result['ledger']['source_bytes'] == size
        assert result['ledger']['consumed_bytes'] == size
    assert parser.retained_raw == raw


def test_exact_source_budget_does_not_drop_diagnostics():
    parser = extractor()
    raw = sized_diagnostic(65536) * 64
    result = append(parser, raw)
    assert result['ledger']['source_bytes'] == 4 * 1024 * 1024
    assert len(result['ledger']['records']) == 64
    assert result['artifact'] is None
    with pytest.raises(ValueError):
        append(parser, b'x', offset=len(raw))
    assert parser.retained_raw == raw
    assert_unavailable(parser)


def origin_line(**changes):
    row = dict(schema='nbsr-origin-monotonic-v1', origin_lo_ns=100,
               origin_hi_ns=110, sample_before_ns=120, sample_after_ns=130,
               client_origin_ns=5, client_sample_ns=25)
    row.update(changes)
    return line(row)


def test_origin_opt_in_retains_raw_and_excludes_chart_bytes():
    from lab.extractor import StdoutExtractor
    parser = StdoutExtractor('origin-fixture', origin_record=True)
    raw = origin_line() + line(progress()) + line(final())
    result = parser.append(raw, offset=0, source_identity='origin-fixture')
    assert result['raw'] == raw
    assert result['artifact'] == line(progress()) + line(final())
    assert result['ledger']['schema'] == 'nbsr-lab-local-extraction-v2'
    assert result['ledger']['records'][0]['kind'] == 'origin'
    assert parser.finish()['ledger']['state'] == 'final'


@pytest.mark.parametrize('raw', [origin_line(origin_hi_ns=140), origin_line(client_sample_ns=True), origin_line(extra='no'), origin_line()+origin_line(), line(progress())], ids=['bounds','bool','extra','duplicate','missing'])
def test_origin_contract_rejects_bad_or_missing(raw):
    from lab.extractor import StdoutExtractor
    parser = StdoutExtractor('origin-fixture', origin_record=True)
    with pytest.raises(ValueError):
        parser.append(raw, offset=0, source_identity='origin-fixture')
    with pytest.raises(ValueError):
        parser.snapshot()
