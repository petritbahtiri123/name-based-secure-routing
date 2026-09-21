import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()))
from scripts.performance.linux_native_lifecycle_coordinator import endpoint_arguments
from scripts.performance.linux_native_pair import verify_index

ROOT = Path('C:/NBSR-build/native-control-signals-3c3f784a-v2')
OUT = Path(__file__).resolve().parent
SHA = Path('C:/NBSR-build/linux-current-3c3f784a/source-sha.txt').read_text().strip()
records = json.loads((ROOT/'records.json').read_text())
assert len(records) == 6
results = []
for record in records:
    assert record['status'] == 'PASS_SIGNAL_CANCELLATION'
    label = record['label']
    role = label.split('-')[1]
    other = 'destination' if role == 'source' else 'source'
    cell = ROOT/label
    index = verify_index(cell)
    config = json.loads((ROOT/(label+'-config.json')).read_text())
    signal = json.loads((cell/'signal.json').read_text())
    result = json.loads((ROOT/(label+'-eof-result.json')).read_text())
    assert signal['signal']=='SIGTERM' and signal['mechanism']=='pidfd_send_signal'
    assert signal['argv']==endpoint_arguments(config,role) and signal['start_ticks']>0
    assert result['role']==role and result['exit_code'] != 0 and result['elapsed_ns'] < 15_000_000_000
    cleanup = json.loads((cell/'cleanup.json').read_text())
    assert all(not value['local_relay_forced'] for value in cleanup.values())
    for peer, expected in ((role,'cancelled by SIGTERM'),(other,'control EOF')):
        verify_index(cell/peer)
        verify_index(cell/peer/'peer')
        assert expected in json.loads((cell/peer/'peer/failure.json').read_text())['error']
        assert not (cell/peer/'result.json').exists()
        assert json.loads((cell/peer/'peer/environment.json').read_text())['repository_sha']==SHA
        assert json.loads((ROOT/(label+'-'+peer+'-remaining-processes.json')).read_text())==[]
    assert signal['pid'] != json.loads((cell/role/'peer/pid.json').read_text())['pid']
    results.append(dict(label=label, role=role, elapsed_ns=result['elapsed_ns'], index_sha256=index,
                        targeted='endpoint controller; owned Rust process cleanup is delegated'))
failed = Path('C:/NBSR-build/native-control-signals-3c3f784a')
assert 'PermissionError' in json.loads((failed/'command-failure.json').read_text())['output']
for role in ('source','destination'):
    recovered = failed/'signal-source-r1'/('recovered-'+role)
    verify_index(recovered)
    assert 'control EOF' in json.loads((recovered/'peer/failure.json').read_text())['error']
report = dict(status='PASS_SIX_CATCHABLE_ENDPOINT_SIGNAL_CONTROLS', source_sha=SHA, records=results,
    startup_failures_retained=['stdlib helper-name collision before launch', 'Docker address-pool exhaustion before launch',
                              'root-UID signal probe could not read non-root executable; no signal sent'],
    interpretation='Same-UID identity-checked pidfd delivery, no capability/security policy change; process cleanup, not graceful eleven-counter ownership proof',
    limits=['No real SSH/network-partition/host-loss/SIGKILL proof', 'Windows coordinator TerminateProcess is not this catchable Linux signal case'])
(OUT/'analysis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(status=report['status'], cases=6, max_elapsed_ns=max(v['elapsed_ns'] for v in results))))
