"""Bounded glibc malloc_info accounting; neither RSS nor live-object proof."""

import re
import xml.etree.ElementTree as ET


def observer_spec(spec, *, platform, enabled):
    if not enabled:
        return spec
    if (platform != 'linux' or spec.get('kind') != 'cycles' or spec.get('sessions') != 1
            or type(spec.get('cycles')) is not int or not 1 <= spec['cycles'] <= 100):
        raise ValueError('allocator observer requires Linux same-process cycles within 1..100')
    return spec | {'allocator_snapshots': True}


def parse_snapshot(raw):
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= 1024 * 1024 or b'<!' in raw:
        raise ValueError('invalid allocator XML size/declaration')
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise ValueError('malformed allocator XML') from error
    if root.tag != 'malloc' or root.attrib != {'version': '1'}:
        raise ValueError('unsupported allocator XML version')

    def amount(node, tag, kind):
        found = [v for v in node if v.tag == tag and v.get('type') == kind]
        if len(found) != 1:
            raise ValueError('missing/duplicate allocator field')
        value = found[0].get('size', '')
        if not re.fullmatch(r'0|[1-9][0-9]{0,19}', value) or int(value) >= 2**64:
            raise ValueError('invalid allocator byte count')
        return int(value)

    heaps = root.findall('heap')
    if not 1 <= len(heaps) <= 1024 or [h.get('nr') for h in heaps] != list(map(str, range(len(heaps)))):
        raise ValueError('invalid allocator heap inventory')
    totals = {}
    for key, tag, kind in [('arena_system_bytes', 'system', 'current'),
                           ('fast_free_bytes', 'total', 'fast'), ('rest_free_bytes', 'total', 'rest')]:
        totals[key] = amount(root, tag, kind)
        if totals[key] != sum(amount(heap, tag, kind) for heap in heaps):
            raise ValueError('allocator heap/global mismatch')
    free = totals['fast_free_bytes'] + totals['rest_free_bytes']
    if free > totals['arena_system_bytes']:
        raise ValueError('free allocator bytes exceed system bytes')
    return dict(schema='nbsr-glibc-allocator-snapshot-v1', heap_count=len(heaps), **totals,
                reported_free_bytes=free, mmap_bytes=amount(root, 'total', 'mmap'),
                arena_remainder_bytes=totals['arena_system_bytes'] - free,
                remainder_basis='DERIVED system minus reported free; includes metadata/caches, not exact live Rust objects',
                live_rust_allocations='NOT_PROVEN', resident_bytes='NOT_MEASURED')
