# Storage review: no deletion performed

C: free **12.85GiB / 13.79GB (5.41%)** of254.90GB. Low overall, but above8GiB trial-start guard; cumulative growth remains under2GiB. All inspected project/temp/Docker paths shareC:.

| Verified consumer | Size | Disposition |
|---|---:|---|
| Docker data VHDX |49.76GiB /53.43GB|Shared; preserve pinned image, Linux build caches, volumes/unrelated data. Actual safely reclaimable amount unknown.|
| Temp nbsr-ci-clean-f6400959 |3.12GiB|Contains2.02GiB evidence and1.10GiB Gitdata; preserve.|
| Repository evidence |1.32GiB|Mostly performance evidence, much alreadygzip; preserve.|
| Windows Cargo target |1.20GiB|Preserve provisioned build capability.|
| Old development materialization |0.56GiB|Source/unique work; preserve.|

Docker disk-usage query timed out; helper cleanup succeeded. No retry, prune, deletion, reset or compaction. Historical image metadata is not a current reclaimability inventory. An available build recipe does not prove offline rebuild capability. Internal Docker space and host VHDX shrink are different; no reclaimable total can be promised.

Created **inactive-diagnostic-evidence.zip**,10knowninactive bundles/152files,572685uncompressed bytes to141705ZIPbytes. Full CRC and every entry SHA256/size read-back passed; manifest included and retained separately. No original removed. Only these exact archived originals are a later deletion candidate, reclaiming less than1MiB logical, not meaningful GBs. No safe immediate multiGiB deletion is established. Source/git/worktrees, unique logs, images, caches and volumes remain intact.

See cleanup-candidates.json for exact paths, loss/restore conditions and size limitations. Scan was metadata-only for known paths, excluding reparse/unmaterialized entries; no whole-drive scan or OneDrive hydration. No content from unrelated personal files was inspected.
