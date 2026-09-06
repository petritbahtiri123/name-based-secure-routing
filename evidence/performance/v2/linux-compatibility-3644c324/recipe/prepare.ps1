$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$recipe = $PSScriptRoot
$accepted = '3644c324a535586e89af72a8c9796e8d58fadf48'
$checkout = Join-Path $recipe 'bundle-checkout'
if ((Test-Path $checkout) -or (Test-Path (Join-Path $recipe 'source.bundle'))) { throw 'Use a fresh preparation directory; no overwrites.' }
git clone --no-checkout --no-hardlinks C:/Users/bajra/OneDrive/Documents/NBSR $checkout
git -C $checkout -c core.autocrlf=false checkout --detach $accepted
if ((git -C $checkout rev-parse HEAD) -ne $accepted) { throw 'Source SHA mismatch' }
git -C $checkout bundle create (Join-Path $recipe 'source.bundle') HEAD
docker image inspect rust@sha256:408fe88047cef61a2087653b0c5255fa51c0f2d6d94ddedd7a2562a9b91a46f6 > (Join-Path $recipe 'rust-base.json')
docker image inspect python@sha256:ff83a535339812dd72e69c93b3c48ddf7c85a324d6330af5797c82a255dbeef4 > (Join-Path $recipe 'python-base.json')
docker build --pull=false --file (Join-Path $recipe 'Dockerfile') --tag nbsr-linux-smoke-3644c324:prepared $recipe *> (Join-Path $recipe 'build.log')
docker image inspect nbsr-linux-smoke-3644c324:prepared > (Join-Path $recipe 'image-inspect.json')
