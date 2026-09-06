from copy import deepcopy

import pytest

from scripts import run_b3_session_lifecycle as b3
from scripts.performance.post_close_cleanup import FIELDS


def fixture():
    final = dict.fromkeys(FIELDS, 0)
    source = [dict(final, phase='lifecycle_cleanup'), dict(final, phase='lifecycle_cycle_0_closed')]
    return final, source


def test_rust_cleanup_requires_all_eleven_exact_zero_fields():
    final, source = fixture()
    value = b3.ownership_cleanup('rust-rust', final, source, source_count=1, cycles=1)
    assert value['all_zero'] and value['source_cycle_all_zero']
    assert len(value['counters']) == 11 and len(value['source_counters'][0]) == 11
    assert value['counter_scope'] == 'rust-all-11-current-fields'


@pytest.mark.parametrize('field', ['pending_routes_current_entries', 'channel_registry_current_entries', 'stream_registry_current_entries'])
@pytest.mark.parametrize('value', [None, 1, False, '0'])
@pytest.mark.parametrize('role', ['destination', 'source_final', 'source_cycle'])
def test_omitted_fields_missing_nonzero_boolean_or_string_fail(field, value, role):
    final, source = fixture()
    target = final if role == 'destination' else source[0 if role == 'source_final' else 1]
    if value is None:
        target.pop(field)
    else:
        target[field] = value
    assert not b3.ownership_cleanup('rust-rust', final, source, source_count=1, cycles=1)['all_zero']


@pytest.mark.parametrize('which', ['final_missing', 'final_duplicate', 'cycle_missing', 'cycle_duplicate'])
def test_exact_report_counts(which):
    final, source = fixture()
    if which.endswith('missing'):
        source.pop(0 if which.startswith('final') else 1)
    else:
        source.append(deepcopy(source[0 if which.startswith('final') else 1]))
    assert not b3.ownership_cleanup('rust-rust', final, source, source_count=1, cycles=1)['all_zero']


def test_historical_go_scope_remains_explicit_eight():
    final = dict.fromkeys(b3.COUNTERS, 0)
    value = b3.ownership_cleanup('go-rust', final, [], source_count=1)
    assert value['all_zero'] and len(value['counters']) == 8
    assert value['counter_scope'] == 'historical-go-destination-8-fields'
