import json
from pathlib import Path
import sys

REPO = Path('C:/Users/bajra/OneDrive/Documents/NBSR')
sys.path.insert(0, str(REPO))
from scripts.run_b3_session_lifecycle import ownership_cleanup

root = Path('C:/NBSR-build/linux-b3-live-1cca67ad-r2/captured')
results = []
for records in sorted(root.glob('*/records.json')):
    for row in json.loads(records.read_text()):
        raw = records.parent / 'raw/rust-rust' / row['name']
        source = [json.loads(line) for line in (raw / 'source-0.stdout').read_text().splitlines()]
        final = [json.loads(line) for line in (raw / 'destination-diagnostics.ndjson').read_text().splitlines()][-1]
        cleanup = ownership_cleanup('rust-rust', final, source, source_count=1,
                                    cycles=row['cycles'] if row['kind'] == 'cycles' else None)
        assert cleanup['all_zero'] and len(cleanup['counters']) == 11
        results.append(dict(cell=row['name'], cleanup=cleanup,
                            scope='postprocessing replay only; original raw/cell records unchanged'))
assert len(results) == 12
Path(__file__).with_name('replay.json').write_text(json.dumps(results, indent=2))
print('PASS:12 retained raw cells,24final and9cycle reports through new11-field gate; no workload rerun')
