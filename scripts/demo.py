from __future__ import annotations

import subprocess
import sys
import time

import httpx

CONTROL = "https://localhost:8000"
GATEWAY = "https://localhost:8080"
ENTERPRISE_CA = "secrets/demo-ca.pem"


def resolve(identity: str, service="payments.internal", method="GET", path="/api/payment-status", ttl=None):
    token = open(f"tokens/client-{identity}.jwt", encoding="utf-8").read().strip()  # noqa: SIM115
    headers = {"Authorization": f"Bearer {token}"}
    return httpx.post(
        f"{CONTROL}/v1/routes/resolve",
        headers=headers,
        json={"service": service, "method": method, "path": path},
        timeout=5,
        verify=ENTERPRISE_CA,
    )


def gateway(ticket=None, method="GET", path="/api/payment-status"):
    headers = {"Authorization": f"NBSR {ticket}"} if ticket else {}
    return httpx.request(method, f"{GATEWAY}{path}", headers=headers, timeout=5, verify=ENTERPRISE_CA)


def tamper_ticket(ticket: str) -> str:
    header, payload, signature = ticket.split(".")
    changed_signature = ("A" if signature[0] != "A" else "B") + signature[1:]
    return ".".join((header, payload, changed_signature))


def main() -> int:
    rows: list[tuple[str, str, str, bool]] = []

    good = resolve("allowed")
    good_ticket = good.json().get("routing_ticket", "") if good.status_code == 200 else ""
    ok = good.status_code == 200 and gateway(good_ticket).status_code == 200
    rows.append(("Authorized request", "ALLOW", "ALLOW" if ok else "DENY", ok))

    denied = resolve("denied")
    rows.append(("Unauthorized identity", "DENY", "DENY" if denied.status_code == 403 else "ALLOW", denied.status_code == 403))
    unknown = resolve("allowed", service="admin.internal")
    rows.append(("Unknown service", "DENY", "DENY" if unknown.status_code == 403 else "ALLOW", unknown.status_code == 403))
    missing = gateway()
    rows.append(("Missing ticket", "DENY", "DENY" if missing.status_code in (401, 403) else "ALLOW", missing.status_code in (401, 403)))
    tampered = tamper_ticket(good_ticket)
    bad = gateway(tampered)
    rows.append(("Tampered ticket", "DENY", "DENY" if bad.status_code in (401, 403) else "ALLOW", bad.status_code in (401, 403)))

    escalated = gateway(good_ticket, method="POST", path="/api/payments")
    rows.append(("Method/path escalation", "DENY", "DENY" if escalated.status_code in (401, 403) else "ALLOW", escalated.status_code in (401, 403)))
    direct = subprocess.run(["docker", "compose", "run", "--rm", "--no-deps", "--entrypoint", "python", "client-allowed", "-c", "import urllib.request; urllib.request.urlopen('http://payments-service:7000/health', timeout=2)"], capture_output=True)
    rows.append(("Direct backend access", "DENY", "DENY" if direct.returncode != 0 else "ALLOW", direct.returncode != 0))
    time.sleep(2.2)
    expired_response = gateway(good_ticket)
    expired = expired_response.status_code in (401, 403)
    rows.append(("Expired ticket", "DENY", "DENY" if expired else "ALLOW", expired))

    print(f"{'Scenario':30} {'Expected':8} {'Actual':8} Result")
    for name, expected, actual, passed in rows:
        print(f"{name:30} {expected:8} {actual:8} {'PASS' if passed else 'FAIL'}")
    return 0 if all(row[3] for row in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
