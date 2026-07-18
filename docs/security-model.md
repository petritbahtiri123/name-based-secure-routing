# Security model

The control plane authenticates signed workload JWTs and delegates every route
decision to OPA. It alone holds the routing-ticket private key. The verifier
holds only its public key and binds authorization to the request Envoy actually
received. Envoy exposes a fixed payments route; clients cannot select upstreams.

The design fails closed when identity validation, OPA, verifier, or ticket
validation fails. Sensitive credentials are not intentionally logged. Local
demo keys are ignored by Git. Replay detection, rotation automation, rate
limiting, durable audit logs, and production PKI are outside prototype scope.
