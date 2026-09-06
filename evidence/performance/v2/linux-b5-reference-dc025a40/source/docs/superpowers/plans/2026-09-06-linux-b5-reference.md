# Linux B5 finite reference, stage1

One selected logical CPU from one physical core, one endpoint group, one runtime
worker only. New Python files; no Rust or Windows/B5 controller changes.

1. Literal RED for exact shape/command construction, source-result/error/cleanup
   validation and a checksum-bound Linux ceiling loader. Keep current build SHA,
   actual binaries, pool/topology/kernel/cgroup limits and observer state bound.
2. Implement bounded finite orchestration using existing Direct/NBSR commands,
   taskset before launch, disk stdout/stderr/resources, fixed existing readiness/
   exec/drain deadlines, same-identity zombie final CPU and source-final-before-ACK
   ordering. Request and validate NBSR11field reports for both peers.
3. Require3valid repeats or5ifCV>5%, retain failures, recompute existing strict
   closed-loop depth classifier. No arbitrary load/timeout relaxation.
4. Loader recomputes counts/rates/classification and derives exact rational70-80%
   only for matched clean current-source inputs. Older binaries remain diagnostic.
   Observer state is fixed and NOT_QUALIFIED without matched comparison; neither
   finite reference nor target derivation establishes sustained/server maximum.
5. Focused synthetic tests/Ruff, parent review, atomic stage. No build/Docker until
   separately coordinated. B5 runtime backend and multicore/groups are follow-ons.

Implementation status, 2026-09-06: steps 1–4 implemented. Focused verification:
74 tests PASS (new reference/loader plus existing strict classifier), Ruff PASS,
CLI help PASS. Literal RED logs and subsequent verification are retained under
`C:/NBSR-build/linux-b5-reference-20260906`. Source final and requested source
11-field cleanup report now validate before ACK. Step 5 parent review and atomic
staging are authorized after completed scoped rereview. Parent review identified missing declared-ladder and raw
execution-evidence gates: 16 literal RED failures were retained, then fixed.
The loader now requires exact declared path/depth/repeat coverage and sticky
paired 3-to-5 escalation, verifies command vectors against declared shape and
timing, and checks bounded resource identity/affinity/CPU/time continuity through
both terminal samples plus retained completion ACK. Scoped rereview found no
remaining Important issues; all implementation and review steps are complete.
Canonical source/log bindings are retained in
`evidence/performance/v2/linux-b5-reference-dc025a40`.
Linux live execution, external hardware, paced-soak
backend and observer-cost qualification remain NOT_RUN / NOT_QUALIFIED.
