"""Offline preparation for an explicitly approved, metadata-only cache probe."""
import hashlib
import re
import tomllib

from scripts.performance.windows_docker_provisioning import windows_argv_units


def registry_packages(wire):
    packages = tomllib.loads(wire.decode('utf-8'))['package']
    result = []
    for package in packages:
        if 'source' not in package:
            continue
        if (package['source'] != 'registry+https://github.com/rust-lang/crates.io-index'
                or not re.fullmatch(r'[A-Za-z0-9_.+-]+', package['name'])
                or not re.fullmatch(r'[A-Za-z0-9_.+-]+', package['version'])
                or not re.fullmatch(r'[0-9a-f]{64}', package['checksum'])):
            raise ValueError('unsupported lock package')
        result.append((package['name'], package['version'], package['checksum']))
    if not result or len(result) > 512 or len(set(result)) != len(result):
        raise ValueError('invalid package inventory')
    return result


# The input hash binds this restricted AWK reader to the host-validated lock bytes.
# No package names are interpolated into shell code; glob expansion stays quoted.
PROGRAM = r'''set -eu
export RUSTUP_AUTO_INSTALL=0 CARGO_NET_OFFLINE=true
for tool in awk sha256sum timeout; do
 if ! command -v "$tool" >/dev/null 2>&1; then printf 'MISSING_TOOL %s\n' "$tool"; exit 2; fi
done
actual=$(sha256sum "$1"); actual=${actual%% *}
[ "$actual" = "$2" ] || { printf 'LOCK_MISMATCH\n'; exit 3; }
printf 'LOCK %s\n' "$actual"
for tool in rustc cargo; do
 if command -v "$tool" >/dev/null 2>&1; then
  printf 'VERSION %s\n' "$tool"
  timeout 2 "$tool" --version || printf 'VERSION_FAILED %s\n' "$tool"
 else printf 'MISSING_TOOL %s\n' "$tool"; fi
done
if command -v rustc >/dev/null 2>&1; then timeout 2 rustc -vV || true; fi
for home in /usr/local/cargo /root/.cargo; do
 for part in registry/index registry/cache registry/src; do
  if [ -d "$home/$part" ]; then printf 'DIRECTORY %s present\n' "$home/$part"; else printf 'DIRECTORY %s absent\n' "$home/$part"; fi
 done
done
awk '
{sub(/\r$/, "")}
function emit() { if (s != "") print n, v, c }
/^\[\[package\]\]$/ {emit(); n=""; v=""; c=""; s=""}
/^name = / {n=$3; gsub(/"/, "", n)}
/^version = / {v=$3; gsub(/"/, "", v)}
/^source = / {s=$3}
/^checksum = / {c=$3; gsub(/"/, "", c)}
END {emit()}' "$1" | (
 count=0
 while read -r name version checksum; do
  count=$((count+1)); [ "$count" -le 512 ] || exit 4
  printf 'PACKAGE %s %s %s\n' "$name" "$version" "$checksum"
  for home in /usr/local/cargo /root/.cargo; do
   for archive in "$home"/registry/cache/*/"$name-$version.crate"; do
    if [ -f "$archive" ]; then printf 'ARCHIVE '; sha256sum "$archive"; fi
   done
   for source in "$home"/registry/src/*/"$name-$version"; do
    if [ -d "$source" ]; then printf 'SOURCE %s\n' "$source"; fi
   done
  done
 done
 printf 'COUNT %s\n' "$count"
 [ "$count" = "$3" ] || exit 5
)
printf 'COMPLETE\n'
'''


def probe_arguments(wire, lock_path='/inspection/Cargo.lock'):
    packages = registry_packages(wire)
    args = ['15', '/bin/sh', '-c', PROGRAM, 'cache-metadata', lock_path,
            hashlib.sha256(wire).hexdigest(), str(len(packages))]
    windows_argv_units(args)
    return args
