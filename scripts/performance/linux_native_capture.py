"""Owned bounded Linux capture; coordinates no benchmark or remote authority."""

import argparse
import contextlib
import json
import mmap
from pathlib import Path
import platform
import re
import secrets
import shutil
import signal
import socket
import subprocess
import time

from scripts.analyze_b1_v2_capture import probe_frames_from_pcapng
from scripts.performance.external_packet_capture import ExternalCapture
from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_b5_placement import seal_output
from scripts.performance.linux_b5_reference import git_state
from scripts.performance.linux_loopback import ROOT, digest, write_json
from scripts.performance.linux_native_packet_accounting import account_capture, endpoint
from scripts.performance.process_cancellation import Cancellation, not_cancelled
from scripts.run_b1_v2_capture import PacketObserver


class NativePacketObserver(PacketObserver):
    readiness_linktype = 1
    capture_name = 'native.pcapng'
    export_timeout = 30

    def __init__(self, dumpcap, tshark, *, interface, local_address, server, probe_port,
                 mtu=1500, check_cancelled=not_cancelled):
        super().__init__(dumpcap, tshark, interface)
        self.local_address = endpoint((local_address, 1))[0]
        self.server = endpoint(server)
        require(self.local_address != self.server[0], 'distinct native hosts required')
        require(re.fullmatch('[A-Za-z0-9_][A-Za-z0-9_.:-]{0,14}', interface)
                and interface not in ('lo', 'any'), 'one named native interface required')
        endpoint((server[0], probe_port))
        require(probe_port != server[1], 'probe port must differ from QUIC endpoint')
        require(type(mtu) is int and 68 <= mtu <= 65535, 'invalid MTU')
        self.probe_port, self.mtu, self.check_cancelled = probe_port, mtu, check_cancelled

    def process_options(self):
        return dict(start_new_session=True)

    def stop_signal(self):
        return signal.SIGINT

    def capture_filter(self, server_port):
        return (f'udp and host {self.local_address} and host {self.server[0]} and '
                f'(port {server_port} or (src host {self.local_address} and '
                f'src port {self.probe["source_port"]} and dst port {self.probe_port}))')

    def capture_command(self, server_port, pcap):
        return [*super().capture_command(server_port, pcap), '-p', '-s', '0', '-B', '64',
                '-a', 'duration:120', '-a', 'filesize:2097152']

    def _send_probe(self):
        self.check_cancelled()
        self.probe_sender.sendto(bytes.fromhex(self.probe['token_hex']), (self.server[0], self.probe_port))
        self.probe['sent_packets'] += 1

    def wait_capture_ready(self, process, pcap, cell_dir):
        self.process = process
        self.check_cancelled()
        super().wait_capture_ready(process, pcap, cell_dir)
        self.check_cancelled()

    def finish_capture(self, process, pcap, cell_dir):
        deadline = time.monotonic() + 5
        self.probe['terminal_status'] = 'WAITING'
        try:
            while time.monotonic() < deadline:
                self.check_cancelled()
                if process.poll() is not None:
                    raise RuntimeError('capture exited before terminal marker')
                self.probe_sender.sendto(bytes.fromhex(self.probe['terminal_token_hex']),
                                         (self.server[0], self.probe_port))
                self.probe['sent_packets'] += 1
                require(0 < pcap.stat().st_size <= 2 * 1024**3, 'capture exceeds bounded inventory')
                with pcap.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
                    observed = probe_frames_from_pcapng(data, self.probe, expected_linktype=1)
                terminal = [n for n, token in observed.items() if token == self.probe['terminal_token_hex']]
                if terminal:
                    self.probe.update(terminal_status='PASS', terminal_observed_frame_numbers=terminal)
                    return
                time.sleep(.05)
            raise TimeoutError('terminal marker not observed within five seconds')
        except BaseException:
            self.probe['terminal_status'] = 'FAIL'
            raise
        finally:
            write_json(cell_dir / 'probe.json', self.probe)

    def account_native(self, directory):
        try:
            require(self.report['valid'], 'capture did not close gracefully')
            flows = json.loads((directory / 'udp-flows.json').read_bytes())
            require(self.report['flow_count'] == 1 and len(flows) == 1, 'exactly one workload flow required')
            require(self.probe.get('status') == self.probe.get('terminal_status') == 'PASS',
                    'live marker coverage incomplete')
            client = (self.local_address, flows[0]['client_port'])
            pcap = directory / self.capture_name
            require(28 <= pcap.stat().st_size <= 2 * 1024**3, 'capture exceeds file bound')
            with pcap.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
                result = account_capture(data, interface=self.interface, client=client, server=self.server,
                    drop_log=(directory / 'dumpcap.stderr').read_text(), mtu=self.mtu, probe=self.probe)
            require(result['packet_count'] == self.report['packet_count'], 'flow export/capture inventory mismatch')
            self.report.update(packet_accounting=result, endpoint_process_ownership='NOT_PROVEN',
                               performance_timing='DIAGNOSTIC', setup_vs_established='NOT_PROVEN')
        except BaseException:
            self.report.update(valid=False, status='invalid_native_accounting')
            raise

    @contextlib.contextmanager
    def capture(self, endpoint_text, directory):
        require(endpoint_text == f'{self.server[0]}:{self.server[1]}', 'capture endpoint changed')
        self.report['valid'] = False
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                sender.bind((self.local_address, 0))
                sender.settimeout(.2)
                port = sender.getsockname()[1]
                require(port not in (self.server[1], self.probe_port), 'probe source port collision')
                self.probe_sender = sender
                self.probe = dict(source_address=self.local_address, destination_address=self.server[0],
                    source_port=port, destination_port=self.probe_port, token_hex=secrets.token_hex(32),
                    terminal_token_hex=secrets.token_hex(32), sent_packets=0)
                require(self.probe['token_hex'] != self.probe['terminal_token_hex'], 'probe token collision')
                # Use the existing owned-child lifecycle, not PacketObserver's loopback socket setup.
                with ExternalCapture.capture(self, endpoint_text, directory):
                    yield self
                self.account_native(directory)
        except BaseException as error:
            self.report.update(valid=False, status='INVALID_PARTIAL', error=str(error))
            raise
        finally:
            write_json(directory / 'capture-report.json', self.report)


def stop_requested(path, token):
    if not path.exists():
        return False
    with path.open('rb') as stream:
        data = stream.read(4097)
    require(len(data) <= 4096, 'stop marker exceeds bound')
    require(json.loads(data) == {'token': token}, 'stop token mismatch or unexpected fields')
    return True


def interface_metadata(interface, mtu, *, sys_root=Path('/sys')):
    require(re.fullmatch('[A-Za-z0-9_][A-Za-z0-9_.:-]{0,14}', interface)
            and interface not in ('lo', 'any'), 'one named native interface required')
    root = sys_root / 'class/net' / interface
    result = dict(interface=interface, mtu=int((root / 'mtu').read_text()),
                  link_type=int((root / 'type').read_text()), operstate=(root / 'operstate').read_text().strip())
    require(result['mtu'] == mtu and result['link_type'] == 1,
            'declared MTU or Ethernet type differs from actual interface')
    return result


def execute(args, *, check_cancelled=not_cancelled):
    require(platform.system() == 'Linux', 'Linux required')
    sha, dirty = git_state()
    require(not dirty, 'clean capture source required')
    output = args.output.resolve()
    require(not output.is_relative_to(ROOT), 'capture evidence must be outside checkout')
    require(shutil.disk_usage(output.parent).free >= 5 * 1024**3, 'five GiB capture reserve required')
    dumpcap, tshark = shutil.which('dumpcap'), shutil.which('tshark')
    require(dumpcap and tshark, 'dumpcap and tshark required; capture capability may require Administrator/root')
    host, port = args.server.rsplit(':', 1)
    observer = NativePacketObserver(dumpcap, tshark, interface=args.interface, local_address=args.local_address,
        server=(host, int(port)), probe_port=args.probe_port, mtu=args.mtu, check_cancelled=check_cancelled)
    nic = interface_metadata(args.interface, args.mtu)
    token = secrets.token_hex(32)
    output.mkdir(exist_ok=False)
    try:
        write_json(output / 'environment.json', dict(source_sha=sha, interface=args.interface,
            local_address=args.local_address, server=args.server, probe_destination_port=args.probe_port,
            declared_mtu=args.mtu, interface_observed=nic,
            scope='capture mechanics; physical hardware/ownership/offloads unqualified',
            tool_versions={name: subprocess.check_output([path, '--version'], text=True, timeout=5)
                           for name, path in (('dumpcap', dumpcap), ('tshark', tshark))}))
        deadline = time.monotonic() + 120
        with observer.capture(args.server, output):
            write_json(output / 'capture-ready.json', dict(token=token, source_sha=sha,
                status='START_MARKER_OBSERVED', note='Coordinator must now start workload; stop only after both peers complete'))
            while not stop_requested(output / 'capture-stop.json', token):
                check_cancelled()
                require(observer.process.poll() is None, 'capture exited while awaiting coordinator')
                if time.monotonic() >= deadline:
                    raise TimeoutError('capture coordinator deadline')
                time.sleep(.05)
        require(git_state() == (sha, ''), 'capture source changed')
        require(interface_metadata(args.interface, args.mtu) == nic, 'capture interface state changed')
        check_cancelled()
        write_json(output / 'result.json', dict(status='PASS_DIAGNOSTIC_NATIVE_CAPTURE',
            pcap_sha256=digest(output / observer.capture_name), report=observer.report,
            scope='Markers bracket captured flow; coordinator workload completion and process ownership need separate evidence'))
    except BaseException as error:
        write_json(output / 'failure.json', dict(status='INVALID_PARTIAL', error=str(error), error_type=type(error).__name__))
        raise
    finally:
        seal_output(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--interface', required=True)
    parser.add_argument('--local-address', required=True)
    parser.add_argument('--server', required=True, help='Exact destination IPv4:UDP port from readiness')
    parser.add_argument('--probe-port', type=int, required=True, help='Separate authorized remote UDP fixture port')
    parser.add_argument('--mtu', type=int, required=True)
    args = parser.parse_args()
    with Cancellation() as cancellation:
        execute(args, check_cancelled=cancellation.check)


if __name__ == '__main__':
    main()
