"""Linux loopback packet accounting adapters; capture timing is diagnostic only."""

import os
import mmap
import argparse
import json
from pathlib import Path
import platform
import re
import secrets
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import tempfile
import time

from scripts import run_b1_wire_overhead as b1
from scripts.analyze_b1_v2_capture import probe_frames_from_pcapng
from scripts.run_b1_wire_overhead import _write_json
from scripts.performance.authority import write_loopback_authority
from scripts.performance.linux_b5_ceiling import NAMES, require
from scripts.performance.linux_b5_placement import seal_output
from scripts.performance.linux_b5_reference import git_state
from scripts.performance.linux_loopback import ROOT, digest, parse_proc_stat
from scripts.performance.wire_overhead import UdpFlowCounter, analyze_pairs
from scripts.run_b1_v2_capture import PacketObserver
from scripts.performance.process_cancellation import Cancellation, not_cancelled


def pid_start(pid, proc_root=Path('/proc')):
    text = (proc_root / str(pid) / 'stat').read_text()
    if int(text.split(' ', 1)[0]) != pid:
        raise ValueError('PID identity mismatch')
    return parse_proc_stat(text, 1, 1)['start_ticks']


def udp_owned_by_pid(peer, pid, start_ticks, *, proc_root=Path('/proc')):
    """Require a unique IPv4 endpoint inode in the authorized live PID's FDs."""
    if peer[0] != '127.0.0.1' or type(pid) is not int or pid <= 0:
        return None
    try:
        if pid_start(pid, proc_root) != start_ticks:
            return None
        base = proc_root / str(pid)
        lines = (base / 'net/udp').read_text().splitlines()
        if len(lines) > 4096:
            return None
        matches = []
        for line in lines[1:]:
            fields = line.split()
            host, port = fields[1].split(':')
            address = socket.inet_ntoa(int(host, 16).to_bytes(4, sys.byteorder))
            if address in ('0.0.0.0', peer[0]) and int(port, 16) == peer[1]:
                matches.append(int(fields[9]))
        if len(matches) != 1 or matches[0] <= 0:
            return None
        fds = list((base / 'fd').iterdir())
        if len(fds) > 4096:
            return None
        owned = any(os.readlink(fd) == f'socket:[{matches[0]}]' for fd in fds)
        if owned and pid_start(pid, proc_root) == start_ticks:
            return matches[0]
    except (OSError, ValueError, IndexError):
        pass
    return None


class LinuxUdpFlowCounter(UdpFlowCounter):
    def __init__(self, server):
        self.start_ticks = None
        self.ownership = None
        super().__init__(server, owner_lookup=self.lookup)

    def authorize_client_process(self, pid):
        self.start_ticks = pid_start(pid)
        super().authorize_client_process(pid)

    def lookup(self, peer, pid):
        inode = udp_owned_by_pid(peer, pid, self.start_ticks)
        if inode is not None:
            self.ownership = dict(pid=pid, start_ticks=self.start_ticks, socket_inode=inode,
                                  local_endpoint=list(peer), scope='first datagram PID/FD/inode binding')
            return pid
        return None

    def close(self):
        super().close()
        if any(thread.is_alive() for thread in self._threads):
            raise RuntimeError('packet counter thread failed to join')


class LinuxPacketObserver(PacketObserver):
    readiness_linktype = 1
    capinfos_name = 'capinfos'

    def __init__(self, *args, check_cancelled=not_cancelled, **kwargs):
        super().__init__(*args, **kwargs)
        self.check_cancelled = check_cancelled

    def wait_capture_ready(self, process, pcap, cell_dir):
        # ExternalCapture already owns the child and will stop/reap it on error.
        self.check_cancelled()
        super().wait_capture_ready(process, pcap, cell_dir)
        self.check_cancelled()

    def _account_capture(self, endpoint, directory):
        try:
            super()._account_capture(endpoint, directory)
        except BaseException as error:
            self.report.update(valid=False, status='invalid_packet_accounting',
                               packet_accounting_error=str(error))
            raise

    def process_options(self):
        return dict(start_new_session=True)

    def stop_signal(self):
        return signal.SIGINT

    def capture_command(self, server_port, pcap):
        return [*super().capture_command(server_port, pcap), '-p', '-s', '0', '-B', '64', '-a', 'filesize:2097152']

    def finish_capture(self, process, pcap, cell_dir):
        token = secrets.token_bytes(32).hex()
        while token == self.probe['token_hex']:
            token = secrets.token_bytes(32).hex()
        self.probe.update(terminal_token_hex=token, terminal_status='WAITING')
        deadline = time.monotonic() + 5
        try:
            while time.monotonic() < deadline:
                self.check_cancelled()
                if process.poll() is not None:
                    raise RuntimeError('dumpcap exited before terminal marker')
                self.probe_sender.sendto(bytes.fromhex(token), ('127.0.0.1', self.probe['destination_port']))
                self.probe['sent_packets'] += 1
                with pcap.open('rb') as stream:
                    size = os.fstat(stream.fileno()).st_size
                    if size > 2 * 1024**3:
                        raise ValueError('capture exceeds two GiB bound')
                    if size:
                        with mmap.mmap(stream.fileno(), size, access=mmap.ACCESS_READ) as data:
                            payloads = probe_frames_from_pcapng(data, self.probe, expected_linktype=1)
                        terminal = sorted(n for n, payload in payloads.items() if payload == token)
                        if terminal:
                            self.probe.update(terminal_status='PASS', terminal_observed_frame_numbers=terminal)
                            return
                time.sleep(min(.05, max(0, deadline - time.monotonic())))
            raise TimeoutError('capture terminal marker not observed within five seconds')
        except BaseException:
            self.probe['terminal_status'] = 'FAIL'
            raise
        finally:
            self.report['readiness'] = dict(self.probe)
            _write_json(Path(cell_dir) / 'capture-readiness.json', self.probe)

    def validate_capture_metadata(self, metadata):
        patterns = (r'^\s*Number of interfaces in file:\s*1\s*$',
                    r'^\s*Name = lo\s*$', r'^\s*Encapsulation = Ethernet(?: \(1 - ether\))?\s*$')
        if self.interface != 'lo' or any(len(re.findall(p, metadata, re.MULTILINE)) != 1 for p in patterns):
            raise ValueError('Linux packet accounting requires exactly lo / Ethernet capture metadata')


class LinuxPacketBackend:
    def __init__(self, directory, *, check_cancelled=not_cancelled):
        self.directory = directory
        self.flow_counter = None
        self.check_cancelled = check_cancelled

    def counter(self, server):
        self.check_cancelled()
        self.flow_counter = LinuxUdpFlowCounter(server)
        return self.flow_counter

    def measured_client(self, argv, *, cwd, server, timeout, client_started):
        client = None
        with (self.directory / 'client.stdout').open('w+') as output, \
                (self.directory / 'client.stderr').open('w+') as errors:
            try:
                client = subprocess.Popen(argv, cwd=cwd, stdout=output, stderr=errors, text=True)
                client_started(client.pid)
                deadline = time.monotonic() + timeout
                while True:
                    self.check_cancelled()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(argv, timeout)
                    try:
                        client.wait(timeout=min(.1, remaining))
                        break
                    except subprocess.TimeoutExpired:
                        pass
                self.check_cancelled()
                output.seek(0)
                stdout = output.read()
                if client.returncode:
                    errors.seek(0)
                    raise RuntimeError(f'packet workload failed: {errors.read()[-65536:]}')
                return stdout, []
            finally:
                if client is not None and client.poll() is None:
                    client.kill()
                    client.wait(timeout=5)

    @staticmethod
    def summarize_resources(samples, completed, measured_seconds):
        return dict(status='NOT_MEASURED', scope='packet accounting only; capture timing is not performance evidence')


def analyze_packet_pairs(rows, *, repeats):
    require(repeats in (1, 5), 'one smoke pair or five formal pairs required')
    grouped = {}
    for row in rows:
        shape = (row['payload_bytes'], row['streams'], row['operations_per_stream'])
        expected = shape[1] * shape[2]
        require(row.get('completed_operations') == expected
                and row.get('application_bytes') == expected * shape[0] * 2
                and not any(row.get(k, 0) for k in ('errors', 'timeouts', 'missing', 'duplicates', 'corrupt', 'wrong_request'))
                and row['packet_observer'].get('valid') is True, 'invalid packet workload')
        key = (row['repeat'], row['path'])
        group = grouped.setdefault(shape, {})
        require(key not in group, 'duplicate packet pair')
        group[key] = row
    require(bool(grouped), 'no packet pairs')
    cells = []
    for shape, group in sorted(grouped.items()):
        require(set(group) == {(r, p) for r in range(1, repeats + 1) for p in ('direct', 'nbsr')}, 'incomplete packet pairs')
        metrics = {}
        application = shape[0] * shape[1] * shape[2] * 2
        for field in ('packet_count', 'ip_bytes', 'udp_bytes', 'udp_payload_bytes', 'captured_frame_bytes'):
            values = {p: [group[r, p]['packet_observer']['packet_accounting'][field]
                          for r in range(1, repeats + 1)] for p in ('direct', 'nbsr')}
            require(all(type(v) is int and v > 0 for a in values.values() for v in a), 'invalid packet totals')
            deltas = [n - d for n, d in zip(values['nbsr'], values['direct'], strict=True)]
            metrics[field] = dict(direct_median=statistics.median(values['direct']),
                nbsr_median=statistics.median(values['nbsr']), paired_deltas=deltas,
                delta_median=statistics.median(deltas), delta_min=min(deltas), delta_max=max(deltas),
                delta_per_application_byte=statistics.median(deltas) / application if field != 'packet_count' else None,
                cv={p: statistics.stdev(v) / statistics.mean(v) if len(v) > 1 else None for p, v in values.items()})
        cells.append(dict(payload_bytes=shape[0], streams=shape[1], operations_per_stream=shape[2],
                          application_bytes=application, repeats=repeats, metrics=metrics))
    return dict(classification='SMOKE_ONLY' if repeats == 1 else 'MEASURED_LOOPBACK_PACKET_ACCOUNTING',
        cells=cells, performance_capacity='NOT_PROVEN', physical_ethernet_bytes='NOT_MEASURED',
        phase_scope='whole capture including setup, fixed operations, untimed validation and teardown',
        interpretation='paired NBSR minus equivalent Direct secure transport; generic framing is not NBSR overhead')


def execute(args, *, check_cancelled=not_cancelled):
    require(platform.system() == 'Linux', 'Linux required')
    require(not any(k.startswith('NBSR_') for k in os.environ), 'remove inherited NBSR experiment settings')
    require(1 <= args.operations <= 1000, 'fixed operations must be 1..1000 per stream')
    sha, dirty = git_state()
    require(not dirty, 'clean checkout required')
    output = args.output.resolve()
    require(not output.is_relative_to(ROOT), 'output must be outside checkout')
    build = json.loads(args.build_manifest.read_bytes())
    hashes = {name: digest(args.binaries / name) for name in NAMES.values()}
    require(build.get('source_sha') == sha and build.get('build_profile') == 'release'
            and build.get('build_commands') and build.get('toolchains')
            and build.get('binary_sha256') == hashes, 'exact current release manifest required')
    tools = {name: Path(shutil.which(name) or '') for name in ('dumpcap', 'tshark', 'capinfos')}
    require(all(p.is_file() for p in tools.values()), 'dumpcap, tshark and capinfos required')
    require(tools['capinfos'].parent == tools['tshark'].parent, 'capture tools must share directory')
    output.mkdir(parents=True, exist_ok=False)
    records = []
    try:
        raw = output / 'raw'
        raw.mkdir()
        retained = output / 'binaries'
        retained.mkdir()
        binaries = {}
        for role, name in NAMES.items():
            target = retained / name
            shutil.copy2(args.binaries / name, target)
            require(os.access(target, os.X_OK), 'executable binary required')
            binaries[role] = target
        _write_json(output / 'build-manifest.json', build)
        _write_json(output / 'environment.json', dict(repository_sha=sha, platform=platform.platform(),
            uid=os.getuid(), binary_sha256=hashes, capture_tools={name: dict(path=str(p), sha256=digest(p),
                version=subprocess.check_output([str(p), '--version'], text=True)) for name, p in tools.items()},
            controller_args={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
            scope='Linux lo, captured synthetic Ethernet IPv4/UDP; not physical NIC, WAN or server capacity',
            performance_timing='DIAGNOSTIC_ONLY', resource_metrics='NOT_MEASURED',
            capture_readiness='distinct exact initial and terminal markers; validated and excluded'))
        def unchanged():
            check_cancelled()
            require(git_state() == (sha, ''), 'source checkout changed')
            require(all(digest(retained / n) == h and digest(args.binaries / n) == h for n, h in hashes.items()), 'binary changed')
            require(json.loads(args.build_manifest.read_bytes()) == build, 'build manifest changed')
        with tempfile.TemporaryDirectory(prefix='nbsr-linux-b1-') as temp:
            authority = Path(temp) / 'authority'
            write_loopback_authority(authority)
            repeats = 1 if args.smoke else 5
            cells = [dict(payload_bytes=p, streams=1 if args.smoke else s, operations_per_stream=args.operations)
                     for p, s in ((1024, 64), (16384, 8))]
            for cell in cells:
                for repeat in range(1, repeats + 1):
                    for mode in (('direct', 'nbsr') if repeat % 2 else ('nbsr', 'direct')):
                        unchanged()
                        require(shutil.disk_usage(output).free >= 2 * 1024**3, 'insufficient free disk for next bounded capture')
                        print(f'payload={cell["payload_bytes"]} streams={cell["streams"]} repeat={repeat} path={mode}', flush=True)
                        directory = raw / f'{mode}-p{cell["payload_bytes"]}-s{cell["streams"]}-r{repeat}'
                        backend = LinuxPacketBackend(directory, check_cancelled=check_cancelled)
                        observer = LinuxPacketObserver(tools['dumpcap'], tools['tshark'], 'lo',
                                                       check_cancelled=check_cancelled)
                        try:
                            row = b1._run_repeat(path=mode, cell=cell, repeat=repeat, binaries=binaries,
                                authority=authority, warmup_seconds=0, raw_dir=raw, observer=observer, backend=backend)
                            require(backend.flow_counter.ownership is not None, 'missing client socket ownership')
                            row['linux_socket_ownership'] = backend.flow_counter.ownership
                            unchanged()
                        except Exception as error:
                            row = b1.failure_record(path=mode, cell=cell, repeat=repeat, warmup_seconds=0, error=error)
                            row['packet_observer'] = observer.report
                            records.append(row)
                            raise
                        row['packet_observer'] = observer.report
                        records.append(row)
                        _write_json(output / 'records.json', records)
                        require(not any(row.get(k, 0) for k in ('errors', 'timeouts', 'missing', 'duplicates', 'corrupt', 'wrong_request')),
                                'invalid workload; retain without replacement')
        _write_json(output / 'packet-summary.json', analyze_packet_pairs(records, repeats=repeats))
        _write_json(output / 'relay-summary.json', analyze_pairs(records))
    except Exception as error:
        _write_json(output / 'failure.json', dict(classification='INVALID_PARTIAL', error=str(error), replacement=False))
        raise
    finally:
        _write_json(output / 'records.json', records)
        seal_output(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binaries', 'build-manifest', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--operations', type=int, default=1000)
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    with Cancellation() as cancellation:
        execute(args, check_cancelled=cancellation.check)


if __name__ == '__main__':
    main()
