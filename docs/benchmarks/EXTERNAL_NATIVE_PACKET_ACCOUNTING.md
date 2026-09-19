# Native interface packet accounting subset

This read-only analyzer supports a stopped pcapng containing one exact IPv4/UDP
flow on one named, untagged Ethernet interface. It is a preparatory subset of
Task 8, not B1 completion or a physical-wire overhead result. It neither starts
a capture nor changes interface settings, routes, offloads or security policy.

From the reviewed checkout, after preserving the original capture and complete
dumpcap stderr, run:

```bash
python3 -B -m scripts.performance.linux_native_packet_accounting \
  --pcap /absolute/cell/native.pcapng \
  --drop-log /absolute/cell/dumpcap.stderr \
  --interface eth0 --mtu 1500 \
  --client 192.0.2.10:41000 --server 192.0.2.20:42000 \
  > /absolute/analysis/native-packet-accounting.json
```

Replace example addresses, exact observed ports, interface and MTU with the
retained experiment configuration. Put analysis outside sealed capture roots.
Analyze only stopped immutable files; preserve their original checksum indexes.
The output includes actual capture/log hashes. Hashes prove byte identity, not
authenticity, endpoint ownership or an immutable source of measurement.

The analyzer requires a complete block inventory, one section/interface, exact
interface name in both pcapng and dumpcap's loss report, complete bidirectional
tuple coverage and reconciled packet counts. Nonzero or unknown embedded drop
counters also reject, even if stderr reports zero. Truncated records, unrelated
flows, fragmentation, VLAN/tunnels, non-UDP traffic, oversized packets relative
to declared MTU and unsupported block types reject; nothing is silently removed.
Both section byte orders are supported. File/block bounds are 2 GiB/1 MiB.

Output separates captured frame bytes, IPv4 bytes, UDP bytes and UDP payload
bytes, with direction totals. Frame bytes can include captured padding/FCS;
preamble, inter-packet gap and actual physical-wire bytes are not inferred.
Packet IP/UDP checksums are not validated: transmit offload can leave incomplete
checksums in a host capture. MTU validation alone does not prove offloads were
disabled or establish packet segmentation on a physical NIC.

Every successful analysis is **DIAGNOSTIC_PACKET_ACCOUNTING_ONLY**. Start/end
coverage, setup versus established phases, process/socket ownership, workload
completion, equivalent Direct/NBSR work and observer qualification remain
NOT_PROVEN. Thus a successfully parsed excerpt can never qualify a complete B1
cell. Do not derive a protocol tax or a capacity result from this command alone.

Remaining integration: owned bounded capture lifecycle and marker coverage;
binding to validated native peer results and fixed useful work; physical NIC
and offload inventory; phase attribution; five equivalent pairs and paired
uncertainty; rejection of every failed/lost attempt without replacement.
The full external wire matrix and external hardware run remain unqualified.

Format reference: [IETF pcapng draft-05, interface/enhanced-packet/statistics
blocks](https://www.ietf.org/archive/id/draft-ietf-opsawg-pcapng-05.html).
This bounded subset deliberately rejects otherwise valid unsupported formats.
