package nbsr.route

import rego.v1

default decision := {
  "allow": false,
  "reason": "default deny",
  "policy_version": "2026-07-18.1",
  "allowed_methods": [],
  "allowed_path_prefix": "",
  "ticket_ttl": 60,
}

decision := {
  "allow": true,
  "reason": "explicit workload route grant",
  "policy_version": "2026-07-18.1",
  "allowed_methods": ["GET"],
  "allowed_path_prefix": "/api/payment-status",
  "ticket_ttl": 60,
} if {
  input.identity == "spiffe://nbsr.local/workload/client-allowed"
  input.service == "payments.internal"
  input.method == "GET"
  startswith(input.path, "/api/payment-status")
}
