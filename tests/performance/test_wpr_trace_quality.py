import pytest

from scripts.performance.wpr_trace_quality import validate_header


def test_zero_loss_header():
    validate_header('Total # Lost Buffers : 0\nTotal # Lost Events : 0\n')


@pytest.mark.parametrize('header', [
    '', 'Total # Lost Events : 0\n',
    'Total # Lost Buffers : 1\nTotal # Lost Events : 0\n',
    'Total # Lost Buffers : 0\nTotal # Lost Events : 46258\n',
    'Total # Lost Buffers : 0\nTotal # Lost Events : 0\nTotal # Lost Events : 1\n',
])
def test_missing_lossy_or_ambiguous_header_rejects(header):
    with pytest.raises(ValueError):
        validate_header(header)
