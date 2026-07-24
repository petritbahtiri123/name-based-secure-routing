import argparse
import json
import os
import sys

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--identity", choices=["allowed", "denied"], default="allowed")
    parser.add_argument("--service", default="payments.internal")
    parser.add_argument("--method", default="GET")
    parser.add_argument("--path", default="/api/payment-status")
    args = parser.parse_args()
    token_path = f"/run/tokens/client-{args.identity}.jwt"
    token = open(token_path, encoding="utf-8").read().strip()  # noqa: SIM115
    control = os.getenv("NBSR_CONTROL_URL", "https://control-plane:8000")
    enterprise_ca = os.getenv("NBSR_ENTERPRISE_CA_PATH", "/run/secrets/demo-ca.pem")
    with httpx.Client(timeout=5, verify=enterprise_ca) as client:
        resolved = client.post(f"{control}/v1/routes/resolve", headers={"Authorization": f"Bearer {token}"}, json={"service": args.service, "method": args.method, "path": args.path})
        if resolved.status_code != 200:
            print(json.dumps({"stage": "resolve", "status": resolved.status_code}))
            return 1
        payload = resolved.json()
        gateway = os.getenv("NBSR_GATEWAY_URL", "https://gateway:8080")
        response = client.request(args.method, f"{gateway}{args.path}", headers={"Authorization": f"NBSR {payload['routing_ticket']}"})
        print(json.dumps({"stage": "gateway", "status": response.status_code, "body": response.json()}))
        return 0 if response.is_success else 1


if __name__ == "__main__":
    sys.exit(main())
