# Verified agent handoff

Use this compact record in the task message or a newly authorized checkpoint.
Do not overwrite historical checkpoints, evidence manifests or source pins.
Verify facts at handoff time; retain unknowns rather than inferring ownership,
authority or runtime state from a branch name or an old successful check.

```text
Observed at (UTC):
Verified checkout root:
Branch / HEAD:
Dirty scope and provenance: tracked + untracked relevant paths; source/patch hashes
Owning task / contact and confirmed file ownership:
Current checkpoint (absolute path), recorded status and timestamp:
Supersedes / historical records retained:
Authorized scope / prohibited actions / execution budget:
Completed observations (with evidence pointers):
Next smallest action / acceptance check:
Blockers, uncertain outcomes and cleanup ownership:
```

Use non-mutating Git checks such as `git --no-optional-locks rev-parse --show-toplevel`,
`git --no-optional-locks branch --show-current`, `git --no-optional-locks rev-parse HEAD`
and scoped `git --no-optional-locks status --short`. If untracked files are excluded,
say so. A clean tracked status is not a complete source or binary identity.
Use the normal approval mechanism for restricted reads; do not bypass denials.

For a concurrent handoff, agree which task may edit each affected file and capture
its current fingerprint. Recheck immediately before writing; reconcile changes
rather than overwriting them. Read only relevant status/manifests and selected
entries. Do not inspect restricted session files or scan unrelated private files.

Use placeholders such as `<verified-checkout-root>` and `<checkpoint-path>` in
portable examples. Supply actual paths privately in the authorized task handoff
when needed. A checkpoint's parent directory is not necessarily the checkout;
its historical status does not establish the latest experiment state. Reverify
branch, HEAD, dirty source identity, checkpoint freshness and owner before reuse.

Keep diagnosis, implementation, local checks, live measurements and hypotheses
separate. Record command/environment/fixture identity, source and binary provenance,
limits, failures and validation gaps when applicable. Link existing evidence;
never manufacture a fresh success claim from an older checkpoint.
