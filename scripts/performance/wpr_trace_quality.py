"""Fail closed on missing, ambiguous or lossy xperf trace headers."""
import argparse
from pathlib import Path
import re


def validate_header(text):
    for field in ('Buffers', 'Events'):
        values = re.findall(rf'^\s*Total # Lost {field}\s*:\s*(\d+)\s*$', text, re.MULTILINE)
        if values != ['0']:
            raise ValueError(f'trace loss unavailable, ambiguous or nonzero: {field}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('header', type=Path)
    args = parser.parse_args()
    validate_header(args.header.read_text(encoding='utf-8-sig'))
    print('TRACE_LOSS_CHECK_PASS: observer impact remains unqualified')
