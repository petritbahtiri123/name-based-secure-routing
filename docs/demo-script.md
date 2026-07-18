# Three-minute demo script

1. **0:00–0:15:** DNS locates services; NBSR proves who may route there now.
2. **0:15–0:40:** Show the architecture and three trust boundaries.
3. **0:40–1:10:** Run the authorized client through Envoy.
4. **1:10–1:30:** Show OPA deny `client-denied`.
5. **1:30–1:50:** Show tampered and expired ticket rejection.
6. **1:50–2:10:** Show actual client-to-backend network failure.
7. **2:10–2:30:** Show kind manifests and NetworkPolicies.
8. **2:30–2:50:** Explain Ed25519 key separation and request scoping.
9. **2:50–3:00:** Close: a name becomes a temporary authorized route.

Recording checklist: fresh bootstrap; healthy Compose stack; readable terminal;
no tokens visible; scenario table fully visible; kind view preloaded; mention
prototype limitations; replace `CODEX_FEEDBACK_SESSION_ID_HERE` only after
running `/feedback`.
