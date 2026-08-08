param([string]$OutputDirectory = "evidence/wp8-task10b")

$ErrorActionPreference = "Stop"
$repository = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$output = [System.IO.Path]::GetFullPath((Join-Path $repository $OutputDirectory))
if (-not $output.StartsWith($repository + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) { throw "capture output must remain inside the repository" }
$dumpcap = "C:\Program Files\Wireshark\dumpcap.exe"
$tshark = "C:\Program Files\Wireshark\tshark.exe"
if (-not (Test-Path -LiteralPath $dumpcap) -or -not (Test-Path -LiteralPath $tshark)) { throw "Wireshark dumpcap and tshark are required" }

$captureInterface = "\Device\NPF_Loopback"
$capturePort = 45976
$captureFilter = "udp port 45976 and host 127.0.0.1"
$pcap = Join-Path $output "independent-go-rust.pcapng"
$manifest = Join-Path $output "capture-manifest.json"
$stdout = Join-Path $output "dumpcap.stdout.txt"
$stderr = Join-Path $output "dumpcap.stderr.txt"
$cargoTarget = Join-Path $env:LOCALAPPDATA "Temp\nbsr-task10b-cargo"
$goPeer = Join-Path $env:LOCALAPPDATA "Temp\nbsr-task10b-go-peer.exe"
$testCommand = "python -m pytest tests/federation/test_independent_wire_peer.py -k cross_process -q"
New-Item -ItemType Directory -Force -Path $output | Out-Null
foreach ($path in @($pcap, $manifest, $stdout, $stderr)) { if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force } }

$interfaces = & $dumpcap -D 2>&1
if ($LASTEXITCODE -ne 0 -or -not ($interfaces -match [regex]::Escape($captureInterface))) { throw "Npcap loopback adapter is unavailable" }
$toolVersion = (& $dumpcap --version 2>&1 | Select-Object -First 1).Trim()
$env:CARGO_TARGET_DIR = $cargoTarget
& cargo build --manifest-path (Join-Path $repository "crates/nbsr-transport/Cargo.toml") --bin wp8_interop_server
if ($LASTEXITCODE -ne 0) { throw "interop server prebuild failed" }
Push-Location (Join-Path $repository "interop/nbsr-go-peer")
try { & go build -trimpath -o $goPeer ./cmd/nbsr-go-peer } finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw "independent Go peer prebuild failed" }
$capture = $null
try {
    $capture = Start-Process -FilePath $dumpcap -ArgumentList "-i `"$captureInterface`" -f `"$captureFilter`" -a duration:8 -w `"$pcap`"" -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $deadline = [DateTime]::UtcNow.AddSeconds(5)
    while (-not (Test-Path -LiteralPath $pcap) -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 50 }
    if (-not (Test-Path -LiteralPath $pcap)) { throw "dumpcap did not initialize" }
    $startedAt = [DateTime]::UtcNow.ToString("o")
    $env:NBSR_TASK10B_CAPTURE_PORT = "$capturePort"
    $env:NBSR_TASK10B_CARGO_TARGET = $cargoTarget
    $env:NBSR_TASK10B_GO_PEER = $goPeer
    & python -m pytest (Join-Path $repository "tests/federation/test_independent_wire_peer.py") -k cross_process -q
    if ($LASTEXITCODE -ne 0) { throw "independent interop test failed" }
    if (-not $capture.WaitForExit(15000)) { throw "dumpcap did not stop" }
} finally {
    Remove-Item Env:NBSR_TASK10B_CAPTURE_PORT -ErrorAction SilentlyContinue
    Remove-Item Env:NBSR_TASK10B_CARGO_TARGET -ErrorAction SilentlyContinue
    Remove-Item Env:NBSR_TASK10B_GO_PEER -ErrorAction SilentlyContinue
    if ($null -ne $capture -and -not $capture.HasExited) { Stop-Process -Id $capture.Id; $capture.WaitForExit() }
}
$item = Get-Item -LiteralPath $pcap
if ($item.Length -lt 256) { throw "packet capture is unexpectedly empty" }
$inventory = @(& $tshark -n -r $pcap -T fields -E "separator=," -e frame.interface_id -e ip.src -e ip.dst -e ip.proto -e udp.srcport -e udp.dstport)
if ($LASTEXITCODE -ne 0) { throw "tshark inventory failed" }
$inventory = @($inventory | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
if ($inventory.Count -eq 0) { throw "capture contains no packets" }
foreach ($line in $inventory) {
    $fields = $line.Split(",")
    if ($fields.Count -ne 6 -or $fields[0] -ne "0" -or $fields[1] -ne "127.0.0.1" -or $fields[2] -ne "127.0.0.1" -or $fields[3] -ne "17" -or ($fields[4] -ne "$capturePort" -and $fields[5] -ne "$capturePort")) { throw "packet outside allowlist: $line" }
}
$captureLog = Get-Content -Raw $stderr
if ($captureLog -notmatch "(?im)Packets received/dropped on interface .*?:\s*\d+/(\d+)") { throw "missing drop statistics" }
$dropped = [int]$Matches[1]
if ($dropped -ne 0) { throw "capture dropped $dropped packets" }
$record = [ordered]@{
    capture = "independent-go-rust.pcapng"; capture_tool_version = $toolVersion; interface_identifier = $captureInterface; filter = $captureFilter
    flow = "127.0.0.1 UDP/$capturePort QUIC/TLS nbsr-quic-1 Go-source to Rust-destination"
    packet_count = $inventory.Count; dropped_count = $dropped; length = $item.Length
    sha256 = (Get-FileHash -LiteralPath $pcap -Algorithm SHA256).Hash.ToLowerInvariant()
    privacy = "public-safe ephemeral test identities; ciphertext only; no key logging; complete packet inventory allowlisted"
    test_correlation = [ordered]@{ command = $testCommand; result = "passed"; capture_started_utc = $startedAt; capture_stopped_utc = [DateTime]::UtcNow.ToString("o") }
}
[System.IO.File]::WriteAllText($manifest, (($record | ConvertTo-Json -Depth 3) + [Environment]::NewLine), [System.Text.UTF8Encoding]::new($false))
foreach ($path in @($stdout, $stderr)) { Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue }
Write-Output "WP8 Task 10B capture: $pcap ($($item.Length) bytes, $($inventory.Count) packets)"
