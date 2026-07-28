# NBSR architecture documents

## Authoritative direction

[NBSR Protocol Vision V3.6](NBSR_Protocol_Vision_V3.6.md) is the current
authoritative architecture and implementation program for forward-looking
work.

The prior [Vision V3 Markdown](NBSR_Protocol_Vision_V3_and_Codex_Build_Directive.md)
and matching [PDF](NBSR_Protocol_Vision_V3_and_Codex_Build_Directive.pdf) are
retained as historical working sources. They are superseded where they permit
client-visible legacy origin answers or omit V3.6 session/channel and origin
lifecycle semantics.

Supporting current architecture:

- [Transport Session and Service Channel model](session-channel-model.md)
- [Origin publication and migration](origin-publication-migration.md)
- [Protocol state machines](protocol-state-machine.md)
- [V3.6 decision and compatibility record](../protocol/v3.6-decisions.md)
- [NBSR QUIC/TLS transport profile](nbsr-transport-profile.md)
- [Legacy DNS/Web PKI compatibility profile](legacy-compatibility-profile.md)
- [Synthetic address profile](synthetic-address-profile.md)
- [Standards reuse matrix](../protocol/standards-reuse-matrix.md)
- [Minimal NBSR-specific surface](../protocol/minimal-nbsr-protocol-surface.md)
- [Resource and timeout profile](../protocol/resource-timeout-profile.md)
- [OriginSet compatibility and authority D7 proposal](../protocol/originset-compatibility-authority-decision.md)

Earlier architectural material is preserved under
[`../history`](../history/README.md). Supporting research is preserved under
[`../research`](../research/README.md).
