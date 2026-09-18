import hashlib,json,shutil
from pathlib import Path
repo=Path('C:/Users/bajra/OneDrive/Documents/NBSR')
raw=Path('C:/NBSR-build/b1-linux-formal-6b3d37e8')
out=repo/'evidence/performance/v2/b1-linux-packets-6b3d37e8'
def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def seal(root):
 idx=root/'checksums.sha256'
 assert not idx.exists(),f'already sealed: {root}'
 idx.write_bytes(''.join(f'{digest(p)}  {p.relative_to(root).as_posix()}\n' for p in sorted(root.rglob('*')) if p.is_file() and p!=idx).encode())
def verify(root):
 for line in (root/'checksums.sha256').read_text().splitlines():
  h,n=line.split('  ',1);p=(root/n).resolve();assert p.is_relative_to(root.resolve()) and digest(p)==h,n
rows=json.loads((raw/'cohort/records.json').read_text())
assert len(rows)==20 and not (raw/'cohort/failure.json').exists()
for row in rows:
 assert row['errors']==row['timeouts']==0
 assert row['completed_operations']==row['expected_operations']
 report=row['packet_observer']; assert report['valid'] and report['capture_drops']['dropped']==0
 assert report['readiness']['status']==report['readiness']['terminal_status']=='PASS'
 assert row['linux_socket_ownership']['socket_inode']>0
 assert '-B' in report['capture_command'] and report['capture_command'][report['capture_command'].index('-B')+1]=='64'
 assert report['packet_accounting']['physical_ethernet_bytes'] is None
verify(raw/'cohort')
seal(raw)
refs=json.loads(Path('C:/NBSR-build/b1-predecessor-sealed-20260918.json').read_text())
for root in (raw,Path('C:/NBSR-build/linux-current-eb4b0608'),Path('C:/NBSR-build/linux-current-6b3d37e8')):
 verify(root);refs.append(dict(root=str(root),index_sha256=digest(root/'checksums.sha256')))
out.mkdir(parents=True,exist_ok=False)
(out/'.gitattributes').write_bytes(b'* -text whitespace=cr-at-eol,-blank-at-eof\n*.log -whitespace\n*.patch -whitespace\n')
(out/'raw-evidence.json').write_text(json.dumps(refs,indent=2)+'\n')
for ref in refs:
 root=Path(ref['root']);shutil.copyfile(root/'checksums.sha256',out/(root.name+'-raw-index.sha256'))
for name in ('records.json','environment.json','packet-summary.json','relay-summary.json','build-manifest.json'):
 shutil.copyfile(raw/'cohort'/name,out/name)
for name in ('run.py','command.json','runtime.log','final-tests.log','final-ruff.log'):
 shutil.copyfile(raw/name,out/name)
port=Path('C:/NBSR-build/linux-b1-port-16f800f3')
for name in ('python-red.log','terminal-red.log','metadata-red.log','pairs-red.log','buffer-red.log','python-final.log','buffer-green.log','implementation.patch','buffer-fix.patch','review.json','capture-packages.txt','capture-image.json'):
 shutil.copyfile(port/name,out/name)
shutil.copyfile(Path(__file__),out/'freeze.py')
packet=json.loads((out/'packet-summary.json').read_text());relay=json.loads((out/'relay-summary.json').read_text())
lines=['# Linux Direct/NBSR packet accounting at 6b3d37e8','','Classification: MEASURED Docker/WSL Linux loopback packet accounting. Not a capacity or physical-wire result.','',
'Five counterbalanced pairs per workload, 20 captures total: 1 KiB / 64 streams and 16 KiB / 8 streams, 1000 operations per stream, no warmup. All useful operations complete; zero workload errors/timeouts, zero rejected relay datagrams and zero reported capture losses. Every capture has exact initial/terminal marker validation and PID/start-time/socket-inode client ownership.','',
'| Payload / streams | Useful application bytes per run | Direct median IP bytes | NBSR median IP bytes | Median paired delta | Paired delta range | Delta / useful app bytes |','| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
for c in packet['cells']:
 m=c['metrics']['ip_bytes']
 lines.append(f"| {c['payload_bytes']} / {c['streams']} | {c['application_bytes']} | {m['direct_median']} | {m['nbsr_median']} | {m['delta_median']} | {m['delta_min']} .. {m['delta_max']} | {100*m['delta_per_application_byte']:.6f}% |")
lines+=['','MEASURED IP/UDP lengths cover the whole capture: setup, useful fixed operations, matched untimed validation and teardown. Useful application bytes exclude untimed exchanges. These observed paired deltas include secure-transport packetization/scheduling variability; they are not a constant NBSR wire-format tax. No selected favorable pair substitutes for the cohort.','',
'| Payload / streams | Direct IP-byte CV | NBSR IP-byte CV | Direct packet-count CV | NBSR packet-count CV |','| --- | ---: | ---: | ---: | ---: |']
for c in packet['cells']:
 m=c['metrics']; lines.append(f"| {c['payload_bytes']} / {c['streams']} | {100*m['ip_bytes']['cv']['direct']:.4f}% | {100*m['ip_bytes']['cv']['nbsr']:.4f}% | {100*m['packet_count']['cv']['direct']:.4f}% | {100*m['packet_count']['cv']['nbsr']:.4f}% |")
lines+=['','All UDP, payload, packet-count and synthetic captured-frame totals/deltas/CVs are retained in packet-summary.json. Physical Ethernet including FCS/preamble/IFG is NOT_MEASURED. Established-only packet phase accounting, retransmission attribution and performance observer qualification are NOT_PROVEN. Capture timing is DIAGNOSTIC_ONLY; CPU/memory resources were not sampled for a capacity claim.','',
'## Separate relay phases','','The relay counts UDP payload at its existing acknowledged setup/established barriers. This is not the same scope as the full pcap. Derived IPv4 estimates in relay-summary.json remain DERIVED, while pcap IP lengths above are MEASURED.','',
'| Payload / streams | Median setup UDP payload delta | Established median paired UDP payload delta | Established delta range |','| --- | ---: | ---: | ---: |']
for c in relay['cells']:
 d=c['pair_incremental_bytes'];lines.append(f"| {c['payload_bytes']} / {c['streams']} | {c['median_setup_incremental_bytes']} | {c['median_incremental_bytes']} | {min(d)} .. {max(d)} |")
lines+=['','## Preserved failures and measured harness correction','','The initial controlled UDP fixture failed metadata matching on Capinfos\' exact Ethernet suffix, then showed why immediate shutdown missed final packets even with reported zero drops. A distinct captured terminal marker closes that measurement gap. The corrected two-packet fixture passed. Literal RED/GREEN tests cover these cases; Windows NULL/Loopback remains the default.','',
'At eb4b0608, the mechanics smoke completed four captures. The first formal cohort retained one complete Direct run (105168 captured, zero drops) and an invalid NBSR capture (122221 captured, 845 pcap drops). No complete matched pair was accepted. This unfavorable predecessor is retained separately and is not merged into the new cohort.','',
'The minimal observer correction requests a bounded 64 MiB kernel capture buffer instead of Dumpcap\'s documented 2 MiB default. Both paths use the same request, unchanged workload and timeouts. Fresh release builds at eb4b0608 and 6b3d37e8 produce identical binary hashes. The new cohort has zero observed drops; this does not guarantee lossless capture at other loads. No production NBSR optimization or security/wire change was made.','',
'## Environment and verification','','Debian 12 capture tools, Wireshark 4.0.17, Docker Desktop/WSL. Capture ran as root only inside the disposable container with its default capabilities; no Windows elevation, host security-policy change or added container privilege was used. Dumpcap prints cap_set_proc warnings, retained verbatim; acceptance depends on actual packet/drop/marker evidence. This is not native Linux/server, physical NIC, independent-operator federation or host/root security evidence.','',
'Focused Python regression tests and Ruff logs are retained. The full raw recursive indexes bind pcapng, exports, commands, release binaries, build manifests, tool/image metadata, failed attempts and source patches. Raw locations and exact index hashes are in raw-evidence.json. All canonical/raw checksums and canonical privacy must pass before commit.','',
'Reproduction: docs/benchmarks/B1_LINUX_PACKET_ACCOUNTING.md. Existing administrator/native-server/soak/authority blockers remain separate. No new stable/degraded/saturated throughput or admission boundary is established by this stage.']
(out/'summary.md').write_text('\n'.join(lines)+'\n')
seal(out)
print('CANONICAL_INDEX',digest(out/'checksums.sha256'))
print('\n'.join(lines[:12]))
