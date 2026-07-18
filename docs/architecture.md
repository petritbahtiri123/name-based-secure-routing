# Architecture

The Compose topology has three networks. Clients and the two public entry
points share `client-network`. The control plane reaches OPA through the
internal `control-network`. Envoy, verifier, and payments share the internal
`protected-network`; the clients do not.

Control-plane resolution never reveals a backend address. The OPA response
defines allowed methods, path prefix, policy version, and TTL. The signed ticket
transports this decision to the verifier. Envoy supplies the actual method,
path, and fixed logical service as external-authorization context.
