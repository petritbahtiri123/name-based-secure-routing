import pytest

from scripts.performance.b3_allocator_snapshot import parse_snapshot


def test_observer_accepts_only_explicit_linux_same_process_cycles():
    from scripts.performance.b3_allocator_snapshot import observer_spec
    cell = dict(kind='cycles', sessions=1, cycles=10)
    assert observer_spec(cell, platform='linux', enabled=True)['allocator_snapshots'] is True
    assert observer_spec(cell, platform='windows', enabled=False) == cell
    for platform, value in [('windows', cell), ('linux', cell | {'kind': 'sessions'}),
                            ('linux', cell | {'sessions': 2}), ('linux', cell | {'cycles': 101})]:
        with pytest.raises(ValueError):
            observer_spec(value, platform=platform, enabled=True)


def xml():
    heap = ('<total type="fast" count="2" size="64"/>'
            '<total type="rest" count="1" size="1024"/>'
            '<system type="current" size="4096"/>')
    return ('<malloc version="1"><heap nr="0">' + heap + '</heap>' + heap
            + '<total type="mmap" count="1" size="8192"/></malloc>').encode()


def test_reports_allocator_space_without_claiming_live_objects_or_rss():
    value = parse_snapshot(xml())
    assert value['arena_system_bytes'] == 4096
    assert value['reported_free_bytes'] == 1088
    assert value['arena_remainder_bytes'] == 3008
    assert value['mmap_bytes'] == 8192
    assert value['live_rust_allocations'] == 'NOT_PROVEN'
    assert value['resident_bytes'] == 'NOT_MEASURED'


@pytest.mark.parametrize('fault', ['version', 'duplicate', 'negative', 'mismatch', 'entity', 'oversize'])
def test_untrustworthy_allocator_xml_rejects(fault):
    raw = xml()
    if fault == 'version':
        raw = raw.replace(b'version="1"', b'version="2"')
    elif fault == 'duplicate':
        raw = raw.replace(b'</malloc>', b'<total type="mmap" count="1" size="8192"/></malloc>')
    elif fault == 'negative':
        raw = raw.replace(b'size="64"', b'size="-64"')
    elif fault == 'mismatch':
        raw = raw.replace(b'size="4096"', b'size="4097"', 1)
    elif fault == 'entity':
        raw = b'<!DOCTYPE malloc [<!ENTITY x "secret">]>' + raw
    else:
        raw = b'x' * (1024 * 1024 + 1)
    with pytest.raises(ValueError):
        parse_snapshot(raw)
