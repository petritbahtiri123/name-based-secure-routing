param(
    [string]$OutputDirectory = "evidence/wp8-task10"
)

$ErrorActionPreference = "Stop"
$repository = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$output = [System.IO.Path]::GetFullPath((Join-Path $repository $OutputDirectory))
if (-not $output.StartsWith($repository + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "capture output must remain inside the repository"
}

$wiresharkDirectory = "C:\Program Files\Wireshark"
$dumpcap = Join-Path $wiresharkDirectory "dumpcap.exe"
$tshark = Join-Path $wiresharkDirectory "tshark.exe"
if (-not (Test-Path -LiteralPath $dumpcap) -or -not (Test-Path -LiteralPath $tshark)) {
    throw "Wireshark dumpcap and tshark are required"
}

$captureInterface = "\Device\NPF_Loopback"
$capturePort = 45975
$captureFilter = "udp port 45975 and host 127.0.0.1"
$pcap = Join-Path $output "live-federation.pcapng"
$manifest = Join-Path $output "capture-manifest.json"
$attempt = Join-Path $output "capture-attempt.json"
$captureStdout = Join-Path $output "dumpcap.stdout.txt"
$captureStderr = Join-Path $output "dumpcap.stderr.txt"
$cargoTarget = Join-Path $env:LOCALAPPDATA "Temp\nbsr-task10-cargo"
$testName = "federated_two_operator_route_transfers_only_after_f75_admission"
$testCommand = "cargo test --manifest-path crates/nbsr-transport/Cargo.toml --test application_stream $testName"
$captureDurationSeconds = 2

New-Item -ItemType Directory -Force -Path $output | Out-Null
foreach ($path in @($pcap, $manifest, $captureStdout, $captureStderr)) {
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
}

$interfaces = & $dumpcap -D 2>&1
if ($LASTEXITCODE -ne 0 -or -not ($interfaces -match [regex]::Escape($captureInterface))) {
    throw "Npcap loopback adapter $captureInterface is unavailable"
}
$toolVersion = (& $dumpcap --version 2>&1 | Select-Object -First 1).Trim()
$env:CARGO_TARGET_DIR = $cargoTarget
& cargo test --manifest-path (Join-Path $repository "crates/nbsr-transport/Cargo.toml") --test application_stream --no-run
if ($LASTEXITCODE -ne 0) { throw "live federation test prebuild failed with exit code $LASTEXITCODE" }
$startedAt = [DateTime]::UtcNow.ToString("o")
$capture = $null
$testPassed = $false
$captureArguments = "-i `"$captureInterface`" -f `"$captureFilter`" -a duration:$captureDurationSeconds -w `"$pcap`""
try {
    $capture = Start-Process -FilePath $dumpcap -ArgumentList $captureArguments -WindowStyle Hidden -RedirectStandardOutput $captureStdout -RedirectStandardError $captureStderr -PassThru

    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    while (-not (Test-Path -LiteralPath $pcap) -and [DateTime]::UtcNow -lt $deadline) {
        if ($capture.HasExited) {
            throw "dumpcap exited before capture began: $(Get-Content -Raw $captureStderr -ErrorAction SilentlyContinue)"
        }
        Start-Sleep -Milliseconds 100
    }
    if (-not (Test-Path -LiteralPath $pcap)) { throw "dumpcap did not initialize the capture file" }

    $env:NBSR_WP8_CAPTURE_PORT = "$capturePort"
    & cargo test --manifest-path (Join-Path $repository "crates/nbsr-transport/Cargo.toml") --test application_stream $testName
    if ($LASTEXITCODE -ne 0) { throw "live federation test failed with exit code $LASTEXITCODE" }
    $testPassed = $true
    if (-not $capture.WaitForExit(10000)) { throw "dumpcap did not stop after its bounded capture window" }
}
finally {
    Remove-Item Env:NBSR_WP8_CAPTURE_PORT -ErrorAction SilentlyContinue
    if ($null -ne $capture -and -not $capture.HasExited) {
        Stop-Process -Id $capture.Id
        $capture.WaitForExit()
    }
}

if (-not $testPassed -or -not (Test-Path -LiteralPath $pcap)) { throw "live capture did not complete" }
$item = Get-Item -LiteralPath $pcap
if ($item.Length -lt 256) { throw "packet capture is unexpectedly empty" }

$inventory = @(& $tshark -n -r $pcap -T fields -E "separator=," -e frame.interface_id -e ip.src -e ip.dst -e ip.proto -e udp.srcport -e udp.dstport)
if ($LASTEXITCODE -ne 0) { throw "tshark packet inventory failed with exit code $LASTEXITCODE" }
$inventory = @($inventory | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
if ($inventory.Count -eq 0) { throw "packet capture contains no decoded packets" }
foreach ($line in $inventory) {
    $fields = $line.Split(",")
    if ($fields.Count -ne 6) { throw "packet inventory has an unexpected field count: $line" }
    $interfaceId, $sourceAddress, $destinationAddress, $protocol, $sourcePort, $destinationPort = $fields
    if ($interfaceId -ne "0" -or $sourceAddress -ne "127.0.0.1" -or $destinationAddress -ne "127.0.0.1" -or $protocol -ne "17") {
        throw "capture contains a packet outside the approved loopback UDP interface/endpoints: $line"
    }
    if ($sourcePort -ne "$capturePort" -and $destinationPort -ne "$capturePort") {
        throw "capture contains a packet outside the approved UDP port: $line"
    }
}

$stderr = Get-Content -Raw $captureStderr -ErrorAction SilentlyContinue
$dropped = $null
if ($stderr -match "(?im)Packets received/dropped on interface .*?:\s*\d+/(\d+)") {
    $dropped = [int]$Matches[1]
}
if ($null -eq $dropped) { throw "dumpcap did not report capture drop statistics" }
if ($dropped -ne 0) { throw "dumpcap reported $dropped dropped packets" }

$record = [ordered]@{
    capture = "live-federation.pcapng"
    capture_tool_version = $toolVersion
    interface_identifier = $captureInterface
    filter = $captureFilter
    flow = "127.0.0.1 UDP/$capturePort QUIC/TLS nbsr/1 shared-rust-transport"
    packet_count = $inventory.Count
    dropped_count = $dropped
    length = $item.Length
    sha256 = (Get-FileHash -LiteralPath $pcap -Algorithm SHA256).Hash.ToLowerInvariant()
    privacy = "public-safe deterministic test identities; no decryption secrets; complete packet inventory allowlisted"
    test_correlation = [ordered]@{
        command = $testCommand
        test = $testName
        result = "passed"
        capture_started_utc = $startedAt
        capture_stopped_utc = [DateTime]::UtcNow.ToString("o")
    }
}
[System.IO.File]::WriteAllText($manifest, (($record | ConvertTo-Json -Depth 3) + [Environment]::NewLine), [System.Text.UTF8Encoding]::new($false))
foreach ($path in @($captureStdout, $captureStderr)) {
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
}
if (Test-Path -LiteralPath $attempt) { Remove-Item -LiteralPath $attempt -Force }
Write-Output "WP8 live packet capture: $pcap ($($item.Length) bytes, $($inventory.Count) packets)"
