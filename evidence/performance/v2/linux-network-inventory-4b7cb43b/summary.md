# Read-only network inventory qualification

Initial implementation 46961268; corrected partial-permission handling 4b7cb43b.
MEASURED: the clean-source Linux CLI ran as UID 65532 in Docker/WSL. The veth
interface reports 10000 Mbit/s through sysfs but has no device backing and is
never classified as verified physical hardware, a dedicated link or a ceiling.
All original reports remain unchanged. This is inventory mechanics only.

The first report correctly preserves unavailable ethtool/systemd tools. Installing
ethtool 6.1 and libmnl0 only in the disposable campaign container enabled actual
read-only driver, channel and offload queries. Veth ring/RSS queries remain
unsupported; virtualization tooling remains unavailable. No host NIC, OS security
policy, firewall, IRQ affinity, offload, MTU or transport setting was changed.

A real ethtool behavior exposed a collector defect: exit zero can accompany
`netlink error: Operation not permitted` and partial stdout. A literal failing
regression preceded the minimal fix. Corrected exact-source rerun preserves
partial stdout and classifies the command ADMIN_REQUIRED, even with exit zero.
This Docker-only subquery is OPTIONAL_LOW_VALUE for this campaign, not a request
to change container capabilities or another required Windows elevated capture.

The initial 13 RED tests failed because the module was absent; 13 then passed.
The scoped combined suite passed 67 before the added zero-exit regression; after
the fix, 16 inventory/server-plan tests passed, plus Ruff/diff checks. Setup had
an initial CRLF shell-script failure and a subsequent unsupported chmod of the
Windows bind mount. Both logs remain; the clean checkout already existed and
inventory ran successfully without changing mount permissions. These are setup
failures, not benchmark/performance measurements or discarded repeats.

Physical Linux/server hardware, switch path, dedicated NIC traffic, thermal and
observer qualification are NOT_PROVEN. Interface-wide snapshots include unrelated
traffic and are not NBSR wire accounting. Checksums and source binding establish
local evidence consistency, not remote hardware attestation.
