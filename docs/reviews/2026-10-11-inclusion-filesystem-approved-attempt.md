<!-- Publication derivative; original SHA-256 6bebc5b0a62c61ac79de64cb91acce15ebd7826872caaa78b7c98fd4e895d49a. Personal identifiers removed. Historical hashes, results and commands refer to original local inputs; placeholder commands were not executed. Originals retained locally. -->

# Approved filesystem trial: preflight blocked

User authorized the exact disposable root
`@LOCAL_USER_ROOT@\AppData\Local\Temp\nbsr-inclusion-restart-5168d29d-1251-4ad8-89c9-388a3a6a9574`
and unchanged helper ACL operations plus owned cleanup only. No other path,
elevation, extra grants, installation or production activation was authorized.

Read-only preparation confirmed absence, canonical parent, owner @LOCAL_TEST_ACCOUNT@
and SID @LOCAL_ACCOUNT_SID@. Disk and RAM start
checks passed: 11917484032 and 2849337344 bytes respectively. The supervisor
rechecked its resource guards before starting the one approved group.

The trial stopped before directory creation: its child `powershell` process
reported that `Microsoft.PowerShell.Security` could not be loaded for `Get-Acl`.
This prevented verification of the parent ACL. It is a preflight environment
blocker, not evidence that the private-write helper or ACL mutation failed.
No automatic retry, alternate grants, elevation or weaker ACL inspection followed.

Measured result: exit 1; 1.41 seconds supervised; no resource abort; direct
child reaped. Zero filesystem assertions passed. Root creation, permission
changes, real writes/read/reopen and interrupted-replacement/repair cases were
NOT RUN. A separate read-only check confirmed the exact root remained absent;
there was nothing to clean up. No visible Python/Cargo/rustc/Go workers remained.

The retained opt-in harness is `scripts/inclusion_filesystem_trial.py`; it is
not a filesystem storage implementation or CI-selected test. Independent
pre-execution review identified a cleanup ownership gap. Before the run, it was
corrected to retain the created directory identity and reject unknown/nonregular/
reparse children before literal-path cleanup. Those paths remain unexecuted.
The current retained evidence does not validate real ACLs, file durability,
restart trust, filesystem cleanup or power-loss behavior.

Next step is to diagnose the child PowerShell module-loading restriction through
read-only inspection or user assistance before proposing another bounded trial.
No security setting change or module installation is implied. Preserve this
failed attempt and obtain any needed action-time scope approval for a retry.
