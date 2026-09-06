$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$recipe = $PSScriptRoot
$name = 'nbsr-linux-smoke-3644c324'
$volume = $name + '-evidence'
$destination = Join-Path $recipe 'captured'
if (Test-Path $destination) { throw 'Existing captured evidence; choose a fresh recipe/run identity.' }
$image = (Get-Content -Raw (Join-Path $recipe 'image-inspect.json') | ConvertFrom-Json)[0].Id
if ($image -notmatch '^sha256:[0-9a-f]{64}$') { throw 'Invalid image identity' }
if (docker ps -a -q --filter "name=^/$name`$") { throw 'Container already exists' }
if (docker volume ls -q --filter "name=^$volume`$") { throw 'Volume already exists' }
docker volume create --label "nbsr.smoke.run=$name" $volume > (Join-Path $recipe 'volume-create.txt')
$id = docker create --name $name --label "nbsr.smoke.run=$name" --network none --user 65532:65532 --read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit 128 --memory 1g --cpus 1 --tmpfs /tmp:rw,noexec,nosuid,nodev,size=16777216,uid=65532,gid=65532 --mount "type=volume,source=$volume,target=/evidence" $image
docker inspect $id > (Join-Path $recipe 'container-before.json')
$PSNativeCommandUseErrorActionPreference = $false
docker start --attach $id *> (Join-Path $recipe 'run.log')
$startExit = $LASTEXITCODE
$PSNativeCommandUseErrorActionPreference = $true
docker inspect $id > (Join-Path $recipe 'container-after.json')
docker volume inspect $volume > (Join-Path $recipe 'volume-inspect.json')
docker cp "${id}:/evidence" $destination
Get-ChildItem $destination -Recurse -File | Where-Object Name -ne wrapper-checksums.sha256 | ForEach-Object {
    '{0}  {1}' -f (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLower(), [IO.Path]::GetRelativePath($destination, $_.FullName).Replace('\','/')
} | Set-Content (Join-Path $destination 'wrapper-checksums.sha256')
Write-Output "Runner attachment exit=$startExit; inspect container-after.json State.ExitCode and captured/run/analysis.json. Stopped container and volume retained for explicit owned cleanup."
