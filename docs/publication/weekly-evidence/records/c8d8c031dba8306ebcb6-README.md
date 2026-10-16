# Approved read-only metadata retry

Command-specific approval succeeded. One bounded invocation finished in 1.984 seconds, command ownership false. Four exact stopped-container metadata queries succeeded. The image query failed because the image Config has no WorkingDir key; it was not a permission rejection. No further Docker retry was made. No object was created, started, built, pulled or removed.

All four candidates remain exited, have no label keys, and bind to sha256:dd08db4a391b16a9d303a251d2693808baf470f2fc4870d8e3c54b7523deed71. All five mounts per container are bind mounts: /build, /control and /old read-only; /fixture and /out writable. Creation timestamps and exact IDs are retained in result.json. This confirms recipe consistency but does not prove writable layers disposable. Missing retained evidence roots and unknown layer contents keep all candidates on HOLD.

The green-cache image ID remains established by the prior successful image inventory, with historical Linux/amd64 and Rust 1.97.1 clues in the retained controller-cancellation report. This retry did not successfully verify current platform or cache contents. No current-lockfile offline coverage or build-readiness claim follows.

If handing off the remaining image metadata query, use this safe read-only command (no environment values):

```powershell
docker image inspect --format '{{json .Id}} {{json .Os}} {{json .Architecture}} {{json .RepoTags}}' sha256:7d59795425e21fc5ff09eabea1aad314806e8f20d3a505c5e47cc2df0e20e53d
```
