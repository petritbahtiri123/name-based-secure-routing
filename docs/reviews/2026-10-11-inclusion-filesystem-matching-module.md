<!-- Publication derivative; original SHA-256 36d19844d500aa7b5865e46da363913d790c628e37dd79ec0fa3953e4d566e71. Personal identifiers removed. Historical hashes, results and commands refer to original local inputs; placeholder commands were not executed. Originals retained locally. -->

# Approved filesystem trial: matching-module retry

The same exact disposable root and unchanged permission effects were authorized
for an ordinary safe retry. The only harness change explicitly imports Windows
PowerShell 5.1's matching Microsoft.PowerShell.Security module from `$PSHOME`.
Python had inherited a PowerShell-7-first module path; the earlier 5.1 child
selected incompatible Security.types.ps1xml and failed its authorization check.
No policy/registry/sandbox setting changed; denied execution-policy inspection
was not retried. The original failed attempt remains preserved separately.

## Measured outcome

One supervised group exited 0 in **5.43 seconds**, no resource abort; direct
child reaped. Three assertion groups passed (not three pytest test cases):

- Observed protected root ACL: owner is the approved current-user SID; exactly
  current user, SYSTEM and Administrators have explicit full control. Directory
  ACEs are inheritable to child files/directories; no inherited ACEs remain.
- Real unchanged private writes, bounded descriptor reads, fresh Repository
  instance reopen and idempotent retry succeeded. Each written destination's
  protected full-control allowlist was checked.
- An injected exception after a completed real watermark replacement produced
  StorageUnavailable. A fresh instance with the exact externally retained
  candidate digest repaired the primary; both stored copies matched afterward.

Preconditions ran again in the harness: exact identity, root absence, canonical
ancestors/no reparse points, parent owner, and no unexpected explicit ACEs on
the freshly created root. The supervisor enforced at least 8 GiB disk and 2 GiB
RAM at start and throughout its existing limits. Disk start was 11909812224
bytes; RAM at completion was 2774818816 bytes. All permission actions targeted
only the authorized root and its owned test files, using the unchanged helper.
Parent directories and existing data were not permission-change targets.

The exact root
`@LOCAL_USER_ROOT@\AppData\Local\Temp\nbsr-inclusion-restart-5168d29d-1251-4ad8-89c9-388a3a6a9574`
was removed after handle closure and root-identity/child checks. Absence was
verified both in the trial and by a separate read-only check. No visible
Python/Cargo/rustc/Go workers remained. Ruff check passed for the harness.

## Limits

This is opt-in test-harness evidence, not a production filesystem adapter.
The interruption is a deterministic exception after completed replacement, not
process termination, partial disk write, machine crash or power loss. No new
keys, credentials, network/socket activity, installation, elevation, extra
grants, hosted CI, commit or push occurred. No independently provisioned trusted
restart floor or real authority provenance is established. Prior 255-test memory
results were not rerun. Runtime/live remain disabled and Stage 3 remains partial.

The adjacent manifest retains exact source/hash, commands, before/after ACLs,
supervisor limits/results and cleanup. The old failed record is not rewritten.
