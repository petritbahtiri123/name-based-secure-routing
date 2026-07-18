package nbsr.route_test

import data.nbsr.route.decision
import rego.v1

test_allowed if {
  result := decision with input as {"identity": "spiffe://nbsr.local/workload/client-allowed", "service": "payments.internal", "method": "GET", "path": "/api/payment-status"}
  result.allow
}

test_denied_identity if {
  result := decision with input as {"identity": "spiffe://nbsr.local/workload/client-denied", "service": "payments.internal", "method": "GET", "path": "/api/payment-status"}
  not result.allow
}

test_unknown_service if {
  result := decision with input as {"identity": "spiffe://nbsr.local/workload/client-allowed", "service": "admin.internal", "method": "GET", "path": "/api/payment-status"}
  not result.allow
}

test_bad_method if {
  result := decision with input as {"identity": "spiffe://nbsr.local/workload/client-allowed", "service": "payments.internal", "method": "POST", "path": "/api/payment-status"}
  not result.allow
}

test_bad_path if {
  result := decision with input as {"identity": "spiffe://nbsr.local/workload/client-allowed", "service": "payments.internal", "method": "GET", "path": "/admin"}
  not result.allow
}
