# Linux FD exit-transition diagnosis

2026-09-07. DIAGNOSTIC, not a qualified reference or server result.

Harness ad86ab245fa76de09f53b32f149e44e634246d7d; unchanged release binaries
from edc0f96d0be2ae089e559092cab8fce2de50aac8, verified against their original
build hashes. One selected guest CPU, one group, 32 streams, 1 KiB, depth 1,
3 seconds warmup and 30 seconds measured. Failure-only observation adds proc
stat and WNOWAIT child-exit correlation only after PermissionError; it never
retries or converts a failed attempt into a valid one.

Six UID 0 and ten UID 65532 counterbalanced attempts completed without the FD
failure. All requested NBSR eleven-counter cleanup reports validate. These are
nonreproductions, not proof that the original failure is fixed. The root series
has only three repeats and Direct dispersion exceeds 5%; it is not a capacity
cohort. All ten unprivileged attempts are retained separately.

A separate 500-child same-UID Linux exit experiment recorded FD denial in all
500 trials. In 290, the immediate stat recheck still reported R rather than Z;
all denied rechecks had PF_EXITING set. Of these 290, WNOWAIT observed completed
exit in only 8. In 48 more, the following stat had become Z; in 234 it remained R.
Every child was subsequently joined successfully. Thus another immediate
nonblocking waitid alone does not cover the transition.

This proves an OS exit-transition case that the harness's zombie-only exception
rule rejects. It does NOT prove the original /proc/230/fd failure had that cause:
the original runner discarded the necessary exception notes. Those notes are now
retained. The original five-valid/one-invalid cohort remains invalid and intact.

Kernel source explains the observed ordering: exit_mm and exit_files precede
exit_notify in [do_exit](https://github.com/torvalds/linux/blob/master/kernel/exit.c),
and [PF_EXITING](https://github.com/torvalds/linux/blob/master/include/linux/sched.h)
is bit 0x4. The local raw stat observations, not a kernel-source inference alone,
establish this experiment's states. The synthetic probe varies 0/32/256/2048 open
descriptors to observe exit; it is not an NBSR workload or performance test.

Preparation limitations: the first base image lacked cryptography. Two subsequent
commands inherited the prepared image's smoke entrypoint; their generated evidence
was copied into rejected-entrypoint-a/b and the owned containers stopped. The
intended runs then used explicit --entrypoint python3 and --network none, image
dd08db4a391b. The unprivileged script drops supplementary groups/GID/UID to 65532
after fixture preparation and before authority generation and peer launch.
No Windows elevation or security-policy change was used.

The root run's binding contained the preceding harness SHA literal; the separate
binding-correction.json records ad86ab24. All retained harness byte hashes were
verified; Git blob equality additionally required CRLF normalization for Windows
checkout files. The unprivileged binding has the correct SHA directly. Console
progress used a nonexistent goodput key and printed null; actual metric records
contain aggregate_application_gbps and are used by analysis.

Raw roots and 255 file hashes are in raw-evidence.json and the three indexes.
The scripts are retained in those roots. Recompute summaries with:

```powershell
python C:/NBSR-build/linux-fd-exit-transition-ad86ab24/analyze.py C:/Users/bajra/OneDrive/Documents/NBSR
```

Next smallest justified change: explicitly represent an identity-checked exiting
process as an unavailable FD observation, only for an opted-in lifecycle owner;
never call it a measured zero or final CPU/cleanup. A later same-identity zombie
sample and successful join must still be required. Ordinary live permission
denials must continue to fail. RED/GREEN and a real same-UID lifecycle test are
required before accepting that change.
