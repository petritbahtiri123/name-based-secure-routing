# Approved ISP adapter dependency inventory

The repository dependency check rejected the already-approved stdlib-only ISP
adapter because its historical closed manifest inventory lacked that exact
Go module. No dependency or source-module requirement was changed.

The validator now admits only deploy/isp-federation-poc/adapter/go.mod and
requires exactly the accepted module declaration plus go1.26.5. Unexpected
manifests/go.sum, missing manifests, changed module/version, require, replace,
toolchain and extra directives remain rejected. Original manifest dirty-state
and isolated dependency lock/hash checks remain intact.

Literal RED:10 failed/2 passed. GREEN:12 passed. Parent independently reran12
focused tests, Ruff and the actual dependency inspection: all PASS. One focused
parent review found no Important/Critical issue. Original failure and raw
RED/GREEN are retained; this is a validation-tool repair, not relaxation of
unknown dependency acceptance or a vulnerability-advisory audit.

Raw evidence: C:/NBSR-build/isp-adapter-inventory-redgreen.
Actual raw index SHA256:
c1656354a0033ded90a946bdce32dee193f4ef72cae2328b2177125d868add53.
Canonical text copies are normalized and independently checksummed.
