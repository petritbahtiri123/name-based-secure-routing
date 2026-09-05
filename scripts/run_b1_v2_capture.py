"""Paired packet-accounting controls; timing is diagnostic while capture is on."""
from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.analyze_b1_v2_capture import account_packets, capture_drop_counts, probe_frames_from_pcapng
from scripts.performance.authority import write_loopback_authority
from scripts.performance.external_packet_capture import ExternalCapture
from scripts import run_b1_wire_overhead as b1
from scripts.run_b4b_task4k import checksums

FIELDS = ["frame.number", "frame.len", "frame.cap_len", "ip.len", "ip.hdr_len", "ip.src", "ip.dst",
          "udp.srcport", "udp.dstport", "udp.length", "ip.flags.mf", "ip.frag_offset"]


class PacketObserver(ExternalCapture):
    def capture_filter(self, server_port):
        return (f"udp port {server_port} or (udp and src host 127.0.0.1 and dst host 127.0.0.1 "
                f"and src port {self.probe['source_port']} and dst port {self.probe['destination_port']})")

    def _send_probe(self):
        self.probe_sender.sendto(bytes.fromhex(self.probe["token_hex"]),
                                 ("127.0.0.1", self.probe["destination_port"]))
        self.probe["sent_packets"] += 1

    def _read_probe_payloads(self, pcap, *, timeout, strict=False):
        selected = ("ip.src==127.0.0.1 && ip.dst==127.0.0.1 && "
                    f"udp.srcport=={self.probe['source_port']} && udp.dstport=={self.probe['destination_port']}")
        result = subprocess.run([str(self.tshark), "-r", str(pcap), "-Y", selected,
                                 "-T", "fields", "-E", "separator=/t", "-E", "occurrence=f",
                                 "-e", "frame.number", "-e", "udp.payload"],
                                capture_output=True, text=True, timeout=timeout, check=strict)
        # A writer may currently be extending a block. Retry an incomplete read.
        if result.returncode:
            return {}
        payloads = {}
        for row in csv.reader(result.stdout.splitlines(), delimiter="\t"):
            if len(row) != 2 or not row[0].isdigit():
                raise ValueError("invalid readiness probe export")
            number = int(row[0])
            payload = bytes.fromhex(row[1].replace(":", ""))
            if number in payloads or payload.hex() != self.probe["token_hex"]:
                raise ValueError("readiness probe token mismatch or duplicate frame")
            payloads[number] = payload.hex()
        return payloads

    def _read_live_probe_payloads(self, pcap):
        try:
            with pcap.open("rb") as stream:
                data = stream.read(1024 * 1024 + 1)
        except FileNotFoundError:
            return {}
        if len(data) > 1024 * 1024:
            raise ValueError("readiness capture exceeds bounded preflight inventory")
        return probe_frames_from_pcapng(data, self.probe)

    def wait_capture_ready(self, process, pcap, cell_dir):
        deadline = time.monotonic() + 5
        self.probe.update(status="WAITING", started_unix_ns=time.time_ns())
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("capture readiness marker not observed within five seconds")
                if process.poll() is not None:
                    raise RuntimeError("dumpcap exited before readiness marker")
                self._send_probe()
                payloads = self._read_live_probe_payloads(pcap)
                if payloads:
                    self.probe.update(status="PASS", observed_frame_numbers=sorted(payloads),
                                      ready_unix_ns=time.time_ns())
                    return
                time.sleep(min(0.05, max(0, deadline - time.monotonic())))
        except Exception:
            self.probe["status"] = "FAIL"
            raise
        finally:
            self.report["readiness"] = dict(self.probe)
            b1._write_json(Path(cell_dir) / "capture-readiness.json", self.probe)

    @contextlib.contextmanager
    def capture(self, endpoint, directory):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver, \
                socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            receiver.bind(("127.0.0.1", 0))
            sender.bind(("127.0.0.1", 0))
            sender.settimeout(0.2)
            self.probe_sender = sender
            self.probe = {"source_port": sender.getsockname()[1], "destination_port": receiver.getsockname()[1],
                          "token_hex": secrets.token_bytes(32).hex(), "sent_packets": 0,
                          "scope": "separate owned loopback tuple; never sent to the QUIC endpoint"}
            if int(endpoint.rsplit(":", 1)[1]) in (self.probe["source_port"], self.probe["destination_port"]):
                raise ValueError("probe ports must differ from workload endpoint")
            with super().capture(endpoint, directory):
                yield self
        self._account_capture(endpoint, directory)

    def _account_capture(self, endpoint, directory):
        if not self.report["valid"]:
            raise ValueError("capture did not close cleanly")
        drop = capture_drop_counts((directory / "dumpcap.stderr").read_text())
        pcap = directory / "loopback.pcapng"
        metadata = subprocess.run([str(self.tshark.parent / "capinfos.exe"), "-M", "-I", "-c", "-d", str(pcap)],
                                  capture_output=True, text=True, check=True).stdout
        (directory / "capinfos.txt").write_text(metadata, newline="\n")
        if "Number of interfaces in file: 1" not in metadata or r"Name = \Device\NPF_Loopback" not in metadata or "Encapsulation = NULL/Loopback" not in metadata:
            raise ValueError("capture interface or encapsulation differs from declared loopback")
        command = [str(self.tshark), "-r", str(pcap), "-T", "fields", "-E", "separator=/t", "-E", "occurrence=f"]
        for field in FIELDS:
            command.extend(["-e", field])
        exported = subprocess.run(command, capture_output=True, text=True, check=True)
        (directory / "packet-layers.tsv").write_text(exported.stdout, newline="\n")
        rows = list(csv.reader(exported.stdout.splitlines(), delimiter="\t"))
        if any(len(row) != len(FIELDS) for row in rows):
            raise ValueError("incomplete packet layer export")
        accounting = account_packets([dict(zip(FIELDS, row, strict=True)) for row in rows],
                                     server_port=int(endpoint.rsplit(":", 1)[1]), captured_packets=drop["captured"],
                                     readiness_probe=self.probe,
                                     probe_payloads=self._read_probe_payloads(pcap, timeout=30, strict=True))
        if self.report["packet_count"] != accounting["packet_count"]:
            raise ValueError("workload flow export and full capture inventory differ")
        self.report["packet_accounting"] = accounting
        self.report["capture_drops"] = drop
        b1._write_json(directory / "packet-accounting.json", self.report)


def execute(args):
    args.output.mkdir(parents=True, exist_ok=False)
    raw = args.output / "raw"
    raw.mkdir()
    retained = args.output / "binaries"
    retained.mkdir()
    binaries = {}
    for role, filename in (("direct", "perf_direct_peer.exe"), ("nbsr", "perf_rust_source.exe"), ("server", "wp8_interop_server.exe")):
        shutil.copy2(args.target / "release" / filename, retained / filename)
        binaries[role] = retained / filename
    metadata = {"schema": "nbsr-b1-v2-capture-control-v1",
                "repository_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                "binary_sha256": {role: hashlib.sha256(path.read_bytes()).hexdigest() for role, path in binaries.items()},
                "scope": "IPv4 Windows loopback; capture observes only server-facing leg of equivalent single-flow relay",
                "phase_scope": "Whole capture: setup, fixed measured operations, matched untimed frame-validation exchanges and teardown. No warmup. Established-only packet split NOT_PROVEN.",
                "capture_readiness": "Exact private UDP probe observed in open pcapng before workload; separately validated probes excluded from workload byte totals.",
                "performance_timing": "DIAGNOSTIC; no timing capacity claim from capture runs",
                "operation_denominator": "Aggregate request/response bytes for fixed useful operations; excludes untimed frame-validation exchanges",
                "physical_ethernet_bytes": "NOT_MEASURED"}
    b1._write_json(args.output / "environment.json", metadata)
    (args.output / "source.patch").write_bytes(subprocess.check_output(["git", "diff", "--binary"]))
    for path in ("scripts/run_b1_v2_capture.py", "scripts/analyze_b1_v2_capture.py", "scripts/run_b1_wire_overhead.py", "scripts/performance/external_packet_capture.py"):
        destination = args.output / "source" / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    records = []
    try:
        with tempfile.TemporaryDirectory(prefix="nbsr-b1-v2-") as temporary:
            authority = Path(temporary) / "authority"
            write_loopback_authority(authority)
            cells = [{"payload_bytes": 1024, "streams": 1 if args.smoke else 64, "operations_per_stream": args.operations},
                     {"payload_bytes": 16384, "streams": 1 if args.smoke else 8, "operations_per_stream": args.operations}]
            for cell in cells:
                for repeat in range(1, args.repeats + 1):
                    for mode in (("direct", "nbsr") if repeat % 2 else ("nbsr", "direct")):
                        print(f"payload={cell['payload_bytes']} streams={cell['streams']} repeat={repeat} path={mode}", flush=True)
                        observer = PacketObserver(args.wireshark / "dumpcap.exe", args.wireshark / "tshark.exe")
                        try:
                            record = b1._run_repeat(path=mode, cell=cell, repeat=repeat, binaries=binaries,
                                                    authority=authority, warmup_seconds=0, raw_dir=raw, observer=observer)
                            if any(record.get(key, 0) for key in ("errors", "timeouts", "missing", "duplicates", "corrupt", "wrong_request")):
                                raise ValueError("failed workload cannot support packet delta")
                            record["packet_observer"] = observer.report
                            record["packet_phase_scope"] = metadata["phase_scope"]
                        except Exception as error:
                            record = b1.failure_record(path=mode, cell=cell, repeat=repeat, warmup_seconds=0, error=error)
                            record["packet_observer"] = observer.report
                            records.append(record)
                            b1._write_json(args.output / "records.json", records)
                            raise
                        records.append(record)
                        b1._write_json(args.output / "records.json", records)
    finally:
        checksums(args.output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", type=Path, default=Path(r"C:\NBSR-build\b4b-task4k"))
    parser.add_argument("--wireshark", type=Path, default=Path(r"C:\Program Files\Wireshark"))
    parser.add_argument("--operations", type=int, default=1000)
    parser.add_argument("--repeats", type=int, choices=(1, 3, 5), default=5)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.operations <= 10000:
        parser.error("fixed operation count must be 1..10000 per stream")
    execute(args)
