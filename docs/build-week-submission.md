# Build Week submission draft

**Title:** Name-Based Secure Routing (NBSR)

**Pitch:** Turn a service name into an authenticated, policy-authorized,
short-lived route—not merely an IP address.

**Problem:** DNS provides location without workload authorization, request
scope, or temporal access.

**Solution and operation:** A signed workload JWT authenticates to a FastAPI
control plane; OPA authorizes the logical name, method, and path; the control
plane returns an Ed25519 ticket; Envoy asks a verifier and forwards only to a
fixed protected backend.

**Architecture/security:** Docker Compose separates client, control, and
protected networks. Identity and ticket keys are distinct. Issuer, audience,
time, subject, service, method, path, signature, and required claims are
validated with fail-closed behavior.

**Impact/originality:** The prototype makes service discovery an explicit
temporary security decision, easy to demonstrate without a full service mesh.

**GPT-5.6 and Codex:** They accelerated implementation, tests, manifests,
cross-platform scripts, and skeptical security review. Humans retained the
trust-boundary, cryptographic, policy, and production-scope decisions.

**Limitations/roadmap:** No replay database, HA, managed rotation, full SPIFFE,
or production PKI. Next: workload-bound credentials, replay controls, signed
policy delivery, audit storage, rate limits, and multi-service registration.

**Setup/testing:** Run `./scripts/bootstrap.ps1`, `docker compose up -d --build`,
`./scripts/test.ps1`, and `./scripts/demo.ps1`; Bash equivalents are included.

**Codex feedback session:** `CODEX_FEEDBACK_SESSION_ID_HERE` — repository owner
must run `/feedback` and insert the real session ID.
