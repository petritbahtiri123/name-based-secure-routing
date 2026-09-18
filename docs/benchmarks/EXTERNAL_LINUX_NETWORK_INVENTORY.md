# Read-only Linux network inventory

From the clean reviewed source checkout, before any timed cohort, run:

```bash
python3 -B -m scripts.performance.linux_network_inventory \
  --interface REAL_DATA_INTERFACE --output /absolute/new-network-inventory
```

Repeat into a separate new directory after the cohort if interface-wide counter
deltas are needed. Keep both sealed outputs with the workload evidence. Do not
run inventory subprocesses inside the timed interval. The command does not set
MTU, queues, offloads, RSS, IRQ affinity, speed or security policy. Each ethtool
or virtualization probe has a five-second deadline. Missing tools, unsupported
queries, invalid counters, permissions and timeouts remain explicit; missing
data is never reported as zero.

The output includes sysfs link fields, byte/packet/drop/error counters, queue
names, device-backed MSI/legacy IRQ affinity, driver/firmware information and
read-only ethtool ring/channel/offload/RSS reports. Install the distribution's
ethtool package through the normal host preparation procedure when unavailable.
An ADMIN_REQUIRED field names its exact read-only argv or inaccessible file;
defer only that observation to the host operator and retain the unprivileged
attempt. No automatic elevation or host configuration changes occur.

Device backing is an observation, not proof of a physical NIC: virtio and other
virtualized devices can have device entries. A successful virtualization query
reporting none is also not remote attestation. Every report therefore retains
external_hardware, hardware_ceiling and dedicated_data_path as NOT_PROVEN.
Operator hardware provenance, link topology, switch path, isolation and independent
host verification remain necessary. Docker veth/loopback reports cannot qualify
server hardware or physical-wire measurement.

Counters cover the entire interface and may include unrelated traffic. This
inventory does not attribute bytes to NBSR, establish a rate, detect a hardware
ceiling or supply packet-phase accounting. Preserve reset/wrap/link-change
evidence rather than treating a counter decrease as negative traffic. Do not
substitute these counters for matched Direct/NBSR capture accounting or sum
them across both ends of a link. Counter snapshots are not simultaneous and
monotonic timestamps from different hosts must not be subtracted.
