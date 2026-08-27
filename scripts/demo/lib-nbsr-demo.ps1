Set-StrictMode -Version Latest

$script:NbsrStateSchema = 'nbsr-demo-state-v1'
$script:NbsrMaxStateBytes = 65536

function Get-NbsrRepositoryRoot {
    [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
}

function Assert-NbsrContainedPath {
    param([Parameter(Mandatory)][string]$Base, [Parameter(Mandatory)][string]$Candidate, [switch]$AllowMissingLeaf)
    $baseFull = [System.IO.Path]::GetFullPath($Base).TrimEnd([System.IO.Path]::DirectorySeparatorChar)
    $candidateFull = [System.IO.Path]::GetFullPath($Candidate)
    $relative = [System.IO.Path]::GetRelativePath($baseFull, $candidateFull)
    if ($relative -eq '.' -or [System.IO.Path]::IsPathRooted($relative) -or $relative -eq '..' -or $relative.StartsWith("..$([System.IO.Path]::DirectorySeparatorChar)", [StringComparison]::Ordinal)) {
        throw 'path escapes its owned root'
    }
    $cursor = if (Test-Path -LiteralPath $candidateFull) { $candidateFull } else { Split-Path -Parent $candidateFull }
    while ($cursor -and (Test-Path -LiteralPath $cursor)) {
        $item = Get-Item -LiteralPath $cursor -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'reparse points are not allowed in owned paths' }
        if ([StringComparer]::OrdinalIgnoreCase.Equals($cursor.TrimEnd('\'), $baseFull.TrimEnd('\'))) { break }
        $next = Split-Path -Parent $cursor
        if ($next -eq $cursor) { break }
        $cursor = $next
    }
    if (-not $AllowMissingLeaf -and -not (Test-Path -LiteralPath $candidateFull)) { throw 'required path does not exist' }
    $candidateFull
}

function Assert-NbsrArtifact {
    param([Parameter(Mandatory)][string]$BuildRoot, [Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$Sha256)
    $full = Assert-NbsrContainedPath -Base $BuildRoot -Candidate $Path
    if ($Sha256 -notmatch '^[0-9a-fA-F]{64}$') { throw 'invalid executable hash' }
    $actual = (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $Sha256.ToLowerInvariant()) { throw 'executable hash mismatch' }
    $full
}

function Assert-NbsrRunRoots {
    param([Parameter(Mandatory)][string]$RepositoryRoot, [Parameter(Mandatory)][string]$RunId, [Parameter(Mandatory)][string]$RuntimeRoot, [Parameter(Mandatory)][string]$BuildRoot)
    if ($RunId -notmatch '^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$') { throw 'invalid run identity' }
    $runtimeBase = [IO.Path]::GetFullPath((Join-Path $RepositoryRoot 'client\nbsr-go-client\demo\test-results\nbsr-demo\runtime'))
    $expectedRuntime = [IO.Path]::GetFullPath((Join-Path $runtimeBase $RunId))
    $expectedBuild = [IO.Path]::GetFullPath((Join-Path 'C:\NBSR-build\nbsr-demo' $RunId))
    if (-not [StringComparer]::OrdinalIgnoreCase.Equals($expectedRuntime, [IO.Path]::GetFullPath($RuntimeRoot)) -or -not [StringComparer]::OrdinalIgnoreCase.Equals($expectedBuild, [IO.Path]::GetFullPath($BuildRoot))) {
        throw 'state roots do not match the approved run hierarchy'
    }
    Assert-NbsrContainedPath -Base $runtimeBase -Candidate $expectedRuntime | Out-Null
    Assert-NbsrContainedPath -Base 'C:\NBSR-build\nbsr-demo' -Candidate $expectedBuild | Out-Null
}

function Write-NbsrJsonAtomic {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)]$Value)
    $directory = Split-Path -Parent ([System.IO.Path]::GetFullPath($Path))
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $json = $Value | ConvertTo-Json -Depth 12 -Compress
    if ([Text.Encoding]::UTF8.GetByteCount($json) -gt $script:NbsrMaxStateBytes) { throw 'state manifest exceeds bound' }
    $temporary = Join-Path $directory ('.state-' + [guid]::NewGuid().ToString('N') + '.tmp')
    [IO.File]::WriteAllText($temporary, $json + "`n", [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Read-NbsrState {
    param([Parameter(Mandatory)][string]$Path)
    $full = [System.IO.Path]::GetFullPath($Path)
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { throw 'demo state does not exist' }
    $bytes = [IO.File]::ReadAllBytes($full)
    if ($bytes.Length -eq 0 -or $bytes.Length -gt $script:NbsrMaxStateBytes) { throw 'invalid state size' }
    $text = [Text.Encoding]::UTF8.GetString($bytes)
    try { $document = [Text.Json.JsonDocument]::Parse($text) } catch { throw 'malformed demo state' }
    try { Assert-NbsrJsonHasUniqueFields -Element $document.RootElement } finally { $document.Dispose() }
    try { $state = $text | ConvertFrom-Json -Depth 12 } catch { throw 'malformed demo state' }
    $required = @('schema','run_id','lifecycle','source_sha','runtime_root','build_root','service','synthetic_ip','started_at_utc','endpoints','readiness','artifacts','components')
    $actual = @($state.PSObject.Properties.Name)
    if (@($actual | Where-Object { $_ -notin $required }).Count -ne 0 -or @($required | Where-Object { $_ -notin $actual }).Count -ne 0) { throw 'unexpected state fields' }
    if ($state.schema -ne $script:NbsrStateSchema -or $state.run_id -notmatch '^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$' -or $state.lifecycle -notin @('RUNNING','STOPPED','FAILED')) { throw 'invalid state identity' }
    foreach ($artifact in @($state.artifacts)) {
        $fields = @($artifact.PSObject.Properties.Name)
        if (@($fields | Where-Object { $_ -notin @('name','executable','sha256') }).Count -ne 0 -or @('name','executable','sha256' | Where-Object { $_ -notin $fields }).Count -ne 0) { throw 'invalid state artifact shape' }
        if ($artifact.name -notin @('authority','client','backend','destination') -or [string]$artifact.sha256 -notmatch '^[0-9a-fA-F]{64}$') { throw 'invalid state artifact' }
    }
    foreach ($component in @($state.components)) {
        $fields = @($component.PSObject.Properties.Name)
        if (@($fields | Where-Object { $_ -notin @('name','pid','start_time_utc','executable','sha256') }).Count -ne 0 -or @('name','pid','start_time_utc','executable','sha256' | Where-Object { $_ -notin $fields }).Count -ne 0) { throw 'invalid state component shape' }
        if ([int]$component.pid -le 0 -or [string]$component.sha256 -notmatch '^[0-9a-fA-F]{64}$') { throw 'invalid state component' }
    }
    if ($state.lifecycle -in @('RUNNING','STOPPED')) {
        foreach ($property in @('acp','destination','proxy')) { if ($property -notin @($state.endpoints.PSObject.Properties.Name)) { throw 'incomplete state endpoints' } }
        foreach ($property in @('authority','destination','client','destination_start_gate','completion_ack')) { if ($property -notin @($state.readiness.PSObject.Properties.Name)) { throw 'incomplete state readiness' } }
        if (@($state.artifacts).Count -ne 4 -or @($state.components).Count -ne 3) { throw 'incomplete running state' }
    }
    $state
}

function Assert-NbsrJsonHasUniqueFields {
    param([Parameter(Mandatory)][Text.Json.JsonElement]$Element)
    if ($Element.ValueKind -eq [Text.Json.JsonValueKind]::Object) {
        $names = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
        foreach ($property in $Element.EnumerateObject()) {
            if (-not $names.Add($property.Name)) { throw 'duplicate state field' }
            Assert-NbsrJsonHasUniqueFields -Element $property.Value
        }
    } elseif ($Element.ValueKind -eq [Text.Json.JsonValueKind]::Array) {
        foreach ($item in $Element.EnumerateArray()) { Assert-NbsrJsonHasUniqueFields -Element $item }
    }
}

function Get-NbsrProcessIdentity {
    param([Parameter(Mandatory)][Diagnostics.Process]$Process, [Parameter(Mandatory)][string]$Executable, [Parameter(Mandatory)][string]$Sha256)
    $Process.Refresh()
    [ordered]@{ name = [IO.Path]::GetFileNameWithoutExtension($Executable); pid = $Process.Id; start_time_utc = $Process.StartTime.ToUniversalTime().ToString('o'); executable = [IO.Path]::GetFullPath($Executable); sha256 = $Sha256.ToLowerInvariant() }
}

function Assert-NbsrProcessIdentity {
    param([Parameter(Mandatory)]$Component, [string]$BuildRoot)
    try { $process = Get-Process -Id ([int]$Component.pid) -ErrorAction Stop } catch { throw "owned process is not running: $($Component.name)" }
    $expectedStart = if ($Component.start_time_utc -is [DateTime]) {
        ([DateTime]$Component.start_time_utc).ToUniversalTime()
    } else {
        [DateTime]::Parse([string]$Component.start_time_utc, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
    }
    if ([Math]::Abs(($process.StartTime.ToUniversalTime() - $expectedStart).TotalMilliseconds) -gt 10) { throw "process start-time mismatch: $($Component.name)" }
    $expectedPath = [IO.Path]::GetFullPath([string]$Component.executable)
    if (-not [StringComparer]::OrdinalIgnoreCase.Equals([IO.Path]::GetFullPath($process.Path), $expectedPath)) { throw "process executable mismatch: $($Component.name)" }
    $artifactRoot = if ($BuildRoot) { $BuildRoot } else { Split-Path -Parent $expectedPath }
    Assert-NbsrArtifact -BuildRoot $artifactRoot -Path $expectedPath -Sha256 ([string]$Component.sha256) | Out-Null
    $process
}

function Stop-NbsrOwnedProcess {
    param([Parameter(Mandatory)]$Component, [string]$BuildRoot, [int]$GraceSeconds = 3)
    $process = Assert-NbsrProcessIdentity -Component $Component -BuildRoot $BuildRoot
    if ($process.HasExited) { return }
    $null = $process.CloseMainWindow()
    if (-not $process.WaitForExit($GraceSeconds * 1000)) {
        Stop-Process -Id $process.Id -Force -ErrorAction Stop
        $process.WaitForExit(5000) | Out-Null
    }
    if (-not $process.HasExited) { throw "owned process did not stop: $($Component.name)" }
}

function Stop-NbsrOwnedProcesses {
    param([Parameter(Mandatory)]$Components, [string]$BuildRoot)
    $failures = [Collections.Generic.List[string]]::new()
    for ($index = $Components.Count - 1; $index -ge 0; $index--) {
        if (Get-Process -Id ([int]$Components[$index].pid) -ErrorAction SilentlyContinue) {
            try { Stop-NbsrOwnedProcess -Component $Components[$index] -BuildRoot $BuildRoot }
            catch { $failures.Add([string]$Components[$index].name) }
        }
    }
    if ($failures.Count -ne 0) { throw "owned process rollback incomplete: $($failures -join ', ')" }
}

function Wait-NbsrReadiness {
    param([Parameter(Mandatory)][Diagnostics.Process]$Process, [Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][scriptblock]$Validate, [int]$TimeoutSeconds = 15)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $Process.Refresh()
        if ($Process.HasExited) { throw "component exited before readiness: $($Process.ExitCode)" }
        if (Test-Path -LiteralPath $Path -PathType Leaf) {
            try { return & $Validate $Path } catch { }
        }
        Start-Sleep -Milliseconds 100
    }
    throw 'component readiness timeout'
}

function Start-NbsrLoggedProcess {
    param([string]$Executable, [string[]]$Arguments, [string]$WorkingDirectory, [string]$LogDirectory, [string]$Name)
    New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
    Start-Process -FilePath $Executable -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -RedirectStandardOutput (Join-Path $LogDirectory "$Name.stdout.log") -RedirectStandardError (Join-Path $LogDirectory "$Name.stderr.log") -NoNewWindow -PassThru
}

function Test-NbsrLoopbackEndpoint {
    param([string]$Endpoint, [switch]$Https)
    $value = if ($Https) { ([Uri]$Endpoint).Authority } else { $Endpoint }
    $hostName, $portText = $value -split ':', 2
    $address = $null
    $port = 0
    return [Net.IPAddress]::TryParse($hostName, [ref]$address) -and [Net.IPAddress]::IsLoopback($address) -and [int]::TryParse($portText, [ref]$port) -and $port -gt 0
}

function Invoke-NbsrConnectRequest {
    param(
        [Parameter(Mandatory)][string]$ProxyEndpoint,
        [Parameter(Mandatory)][string]$Service,
        [int]$Port = 8080,
        [int]$TimeoutSeconds = 15
    )
    if (-not (Test-NbsrLoopbackEndpoint -Endpoint $ProxyEndpoint) -or $Service -notmatch '^[a-z0-9.-]{1,253}$' -or $Port -le 0 -or $Port -gt 65535 -or $TimeoutSeconds -le 0) {
        throw 'invalid CONNECT request parameters'
    }
    $proxyHost, $proxyPort = $ProxyEndpoint -split ':', 2
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $null = $client.ConnectAsync($proxyHost, [int]$proxyPort).WaitAsync([TimeSpan]::FromSeconds($TimeoutSeconds)).GetAwaiter().GetResult()
        $stream = $client.GetStream()
        $stream.ReadTimeout = $TimeoutSeconds * 1000
        $stream.WriteTimeout = $TimeoutSeconds * 1000
        $encoding = [Text.Encoding]::ASCII
        $connect = $encoding.GetBytes("CONNECT ${Service}:$Port HTTP/1.1`r`nHost: ${Service}:$Port`r`n`r`n")
        $null = $stream.Write($connect, 0, $connect.Length)
        $headers = [Collections.Generic.List[byte]]::new()
        while ($headers.Count -lt 4096) {
            $value = $stream.ReadByte()
            if ($value -lt 0) { throw 'proxy closed before CONNECT response' }
            $headers.Add([byte]$value)
            $count = $headers.Count
            if ($count -ge 4 -and $headers[$count-4] -eq 13 -and $headers[$count-3] -eq 10 -and $headers[$count-2] -eq 13 -and $headers[$count-1] -eq 10) { break }
        }
        $headerText = $encoding.GetString($headers.ToArray())
        if (-not $headerText.StartsWith('HTTP/1.1 200 ', [StringComparison]::Ordinal) -or -not $headerText.EndsWith("`r`n`r`n", [StringComparison]::Ordinal)) { throw 'proxy rejected CONNECT' }
        $request = $encoding.GetBytes("GET / HTTP/1.1`r`nHost: ${Service}:$Port`r`nUser-Agent: nbsr-task5`r`nConnection: close`r`n`r`n")
        $null = $stream.Write($request, 0, $request.Length)
        $null = $stream.Flush()
        $null = $client.Client.Shutdown([Net.Sockets.SocketShutdown]::Send)
        $response = [Collections.Generic.List[byte]]::new()
        $buffer = [byte[]]::new(1024)
        while (($read = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            if ($response.Count + $read -gt 16 * 1024) { throw 'application response exceeds bound' }
            for ($index = 0; $index -lt $read; $index++) { $response.Add($buffer[$index]) }
        }
        $text = $encoding.GetString($response.ToArray())
        $separator = $text.IndexOf("`r`n`r`n", [StringComparison]::Ordinal)
        if ($separator -lt 0 -or -not $text.StartsWith('HTTP/1.1 200 ', [StringComparison]::Ordinal)) { throw 'invalid application response' }
        $text.Substring($separator + 4).TrimEnd("`r", "`n")
    } finally {
        $null = $client.Dispose()
    }
}

function New-NbsrTransportAuthority {
    param([Parameter(Mandatory)][string]$Directory)
    New-Item -ItemType Directory -Path $Directory | Out-Null
    $now = [DateTimeOffset]::UtcNow
    $curve = [Security.Cryptography.ECCurve]::CreateFromFriendlyName('nistP256')
    $caKey = [Security.Cryptography.ECDsa]::Create($curve)
    $caRequest = [Security.Cryptography.X509Certificates.CertificateRequest]::new('CN=NBSR Demo CA', $caKey, [Security.Cryptography.HashAlgorithmName]::SHA256)
    $caRequest.CertificateExtensions.Add([Security.Cryptography.X509Certificates.X509BasicConstraintsExtension]::new($true, $false, 0, $true))
    $ca = $caRequest.CreateSelfSigned($now.AddMinutes(-1), $now.AddHours(2))
    [IO.File]::WriteAllBytes((Join-Path $Directory 'ca.der'), $ca.Export([Security.Cryptography.X509Certificates.X509ContentType]::Cert))
    foreach ($entry in @(@('source','source.edge'), @('destination','destination.edge'))) {
        $key = [Security.Cryptography.ECDsa]::Create($curve)
        $request = [Security.Cryptography.X509Certificates.CertificateRequest]::new("CN=$($entry[1])", $key, [Security.Cryptography.HashAlgorithmName]::SHA256)
        $san = [Security.Cryptography.X509Certificates.SubjectAlternativeNameBuilder]::new(); $san.AddDnsName($entry[1]); $request.CertificateExtensions.Add($san.Build())
        $eku = [Security.Cryptography.OidCollection]::new(); $null = $eku.Add([Security.Cryptography.Oid]::new('1.3.6.1.5.5.7.3.1')); $null = $eku.Add([Security.Cryptography.Oid]::new('1.3.6.1.5.5.7.3.2')); $request.CertificateExtensions.Add([Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]::new($eku, $false))
        $serial = [byte[]]::new(16); [Security.Cryptography.RandomNumberGenerator]::Fill($serial)
        $certificate = $request.Create($ca, $now.AddMinutes(-1), $now.AddHours(1), $serial)
        [IO.File]::WriteAllBytes((Join-Path $Directory "$($entry[0]).der"), $certificate.Export([Security.Cryptography.X509Certificates.X509ContentType]::Cert))
        [IO.File]::WriteAllBytes((Join-Path $Directory "$($entry[0])-key.der"), $key.ExportPkcs8PrivateKey())
        $certificate.Dispose(); $key.Dispose()
    }
    $ca.Dispose(); $caKey.Dispose()
}
