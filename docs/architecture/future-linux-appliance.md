# Future NBSR Linux appliance and container delivery

Status: **recorded direction and deferred proposal, not an implemented product**.
Recorded: 2026-11-18, following the project owner's request to preserve the idea
and its design starting point for later work.

## Intent and decision boundary

Make NBSR easier to install, operate and reproduce without redesigning the
protocol or starting a new kernel project. Preserve this note alongside the
existing delivery roadmap so the idea is not lost while current protocol,
benchmark, CI and integration work continues.

The owner requested two future delivery routes: a small Linux-based appliance
for a VM or dedicated device, and a pullable container image (Docker Hub was
suggested) for Kubernetes pods. Alpine Linux was mentioned as a useful comparison
and candidate, **not a final distribution choice**.

The starting direction is a supported standard Linux kernel and ordinary NBSR
software. Kernel tuning is a later, measured optimization. This note does not
approve a kernel fork, a new kernel, a registry publication, a cluster deployment,
hardware purchases, paid services or any security-setting change. It does not
close any existing milestone. Detailed mechanisms below are proposals to review
when this work is scheduled, not frozen protocol decisions.

## Reuse before new design

The [project direction guide](project-direction.md) and
[Protocol Vision V3.6](NBSR_Protocol_Vision_V3.6.md) retain authority. In particular,
packaging must preserve session reuse with service isolation, independent
admission, exact identity bindings, origin privacy and fail-closed authority.

Reuse the [single-instance operator plan](../superpowers/plans/2026-10-10-single-instance-operator-package.md):
Stage 7 already covers Docker packaging, supervised startup and bounded shutdown;
Stage 8 covers repeatable acceptance and rollback; Stages 9-10 cover real
provisioning and a separately authorized pilot. This proposal is a future delivery
extension, not a replacement plan or another completion counter. Existing Docker
and Kubernetes material is a reuse candidate, not evidence of installed readiness.

Retain the existing role boundaries rather than creating an all-powerful appliance
daemon. Select a concrete supported role/profile before packaging; do not assume
client, Name/control-plane authority, source/destination Edge and origin connector
must share one image, process, privilege boundary or machine.

## Separate delivery routes

| Route | What it packages | Boundary to preserve |
| --- | --- | --- |
| Container image | NBSR binaries, minimal userspace and the dependencies required by the selected role | A container shares the node's Linux kernel. It does not ship or replace the host kernel. Kubernetes scheduling does not establish NBSR authority or readiness. |
| VM appliance | Minimal supported Linux guest, standard guest kernel, selected NBSR role and operational tooling | The guest kernel belongs to the appliance; hypervisor and host remain separate. Image boot success is not protocol acceptance. |
| Dedicated-device appliance | A supported hardware image/profile using the same NBSR interfaces | Boot, NIC/driver, storage, recovery and update support need hardware-specific evidence. VM acceptance does not establish hardware acceptance. |

Prefer shared versioned configuration, provisioning interfaces and release
provenance across these routes. Keep packaging-specific adapters small. Protocol
behavior and standardization must not depend on a particular distro or registry.

## Proposed minimum operational design

- Build from pinned reviewed inputs; retain source revision, build inputs,
  dependency inventory/SBOM, image digest and verification results.
- Choose the smallest base that meets compatibility, patching and diagnostic
  requirements, not the smallest download at any cost. Evaluate Alpine against
  another supported minimal base using actual binaries, libc/native dependencies,
  trust stores, DNS behavior, debugging and lifecycle tests. No winner is selected.
- Images contain no private keys, shared identities or real enrollment tokens.
  Provision identities and trust explicitly per instance. Reuse the approved
  custody, rotation/recovery and persistent authority/currentness boundaries.
- Use least privilege and separate writable state from packaged software.
  Propose non-root execution, bounded storage/logs and restricted filesystem and
  network access where the selected role permits them. Any required capability,
  device access, host networking or host mount needs an explicit reviewed reason;
  privileged pods must not become the default workaround.
- Distinguish process liveness, dependency availability and authenticated NBSR
  readiness. Restart must not resurrect revoked/expired authority or erase
  unresolved cleanup ownership.
- Define authenticated update verification and recovery before unattended updates.
  Rollback must preserve compatible state and anti-rollback/security floors; an old
  image must not restore revoked authority. Test interrupted updates and failed boot.
- Provide bounded, redacted diagnostics and a documented support/patch owner.
  Keep evidence provenance and retention intact. Benchmark results use the
  existing Performance Lab dashboard (currently port 8765), with distinct run
  identities and validity, not new dashboards per image or trial.

## Proposed work sequence and acceptance gates

1. **Reconcile prerequisites.** Re-read current stage evidence, the role inventory,
   threat model and existing packaging/manifests. Record remaining runtime gates.
   Do not package fixture-only authority as real registration.
2. **Choose one first profile.** Record supported role, base/architecture, state
   layout, trust provisioning, required privileges, update owner and support window.
   Keep Docker Hub versus another registry, public versus private distribution,
   and Kubernetes deployment format as explicit later choices.
3. **Package the standard baseline.** Begin with the existing Docker delivery
   boundary; then derive a minimal VM appliance if useful. Build no custom kernel.
   Reproducible packaging and configuration validation are separate from live
   authorization and from a performance claim.
4. **Verify installation and lifecycle.** Test clean start, configured enrollment,
   repeated start/request/stop, negative authorization, expiry/revocation, restart,
   bounded drain, resource pressure, diagnostic redaction and retained failures.
   Add the relevant tests and CI selection in the same change before its push.
5. **Verify each target.** For Kubernetes, cover pod restart/rescheduling, readiness,
   persistent-state ownership and upgrade/rollback without silently granting broad
   privileges. For VM/device profiles, cover boot, network loss, interrupted updates
   and recovery. Preserve all existing protocol modes and isolation contracts.
6. **Measure before tuning.** Compare ordinary supported Linux deployment with the
   packaged baseline under matched workload, source/build identity and resource
   bounds. Record startup/preparation time, image/disk footprint, CPU/memory,
   latency, throughput and cleanup evidence. Change one parameter at a time;
   retain failures and reject invalid comparisons.
7. **Review optimization and release separately.** Prefer userspace/configuration
   fixes first. Consider kernel configuration or patches only for a reproduced
   bottleneck with measured benefit, security review, regression coverage,
   rollback and a sustainable upstream/security-update plan. Publication and
   pilot deployment require their own authorization and acceptance.

## Questions intentionally left open

- Which role and platform should be the first supported delivery target?
- Which supported base, image format, architectures and hardware profiles meet
  compatibility and maintenance requirements?
- Which registry/account, signing/verifying mechanism and distribution policy
  should be used? Docker Hub is a requested candidate, not an existing release.
- Which configuration, secret/state provisioning and orchestration interfaces can
  be reused unchanged, and which need a scoped adapter?
- What update support lifetime, recovery procedure and resource envelope can be
  sustained by the team?
- Does any measured result justify kernel-specific optimization at all?

When resumed, use this note as the starting record, resolve these choices against
current source and evidence, and write the scoped implementation plan. Do not
restart design from a blank page, but do not mistake deferred proposals for
approved runtime behavior.
