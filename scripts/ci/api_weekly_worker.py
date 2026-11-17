"""One reviewed request per invocation; dry by default. No automatic retries."""

import argparse
from decimal import Decimal
import hashlib
import http.client
import json
import os
from pathlib import Path

MODEL = "gpt-5.4-mini-2026-03-17"
INPUT = Decimal("0.75")
OUTPUT = Decimal("4.5")
LIMIT = Decimal("10.00")
SYNTHESIS_RESERVE = Decimal("0.50")


class HTTPFailure(Exception):
    def __init__(self, status):
        self.status = status


def response_metadata(response):
    status = response.get("status")
    if status not in {"completed", "incomplete", "failed", "cancelled", "queued", "in_progress"}:
        status = "unrecognized"
    usage = response.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    safe_usage = {k: v for k in ("input_tokens", "output_tokens") if type(v := usage.get(k)) is int and 0 <= v <= 1000000}
    details = response.get("incomplete_details")
    reason = details.get("reason") if isinstance(details, dict) else None
    return {
        "status": status,
        "usage": safe_usage,
        "incomplete_reason": reason if reason in {"max_output_tokens", "content_filter"} else None,
    }


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True).encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    if path.is_symlink() or path.is_junction():
        raise ValueError("linked input")
    return path.read_bytes()


def create(path, value):
    # Never replace a reservation or receipt. Interrupted writes fail closed.
    with path.open("xb") as f:
        f.write(encoded(value))
        f.flush()
        os.fsync(f.fileno())


def send(request, counting=False):
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key or "\n" in key or "\r" in key:
        raise ValueError("credential unavailable")
    connection = http.client.HTTPSConnection("api.openai.com", timeout=60)
    try:
        route = "/v1/responses/input_tokens" if counting else "/v1/responses"
        if counting:
            request = {k: request[k] for k in ("model", "instructions", "input", "tools")}
        connection.request("POST", route, encoded(request), {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        response = connection.getresponse()
        if response.status != 200:
            raise HTTPFailure(response.status)
        body = response.read(131073)
        if len(body) > 131072:
            raise ValueError("oversized response")
        return json.loads(body)
    finally:
        connection.close()


def request_for(root, item):
    name = item["request_sha256"]
    if len(name) != 64 or any(c not in "0123456789abcdef" for c in name):
        raise ValueError("invalid request identity")
    raw = read(root / "requests" / (name + ".json"))
    if len(raw) > 100000 or digest(raw) != name:
        raise ValueError("request changed")
    request = json.loads(raw)
    if (
        set(request) != {"model", "instructions", "input", "tools", "store", "max_output_tokens"}
        or request["model"] != MODEL
        or request["tools"] != []
        or request["store"] is not False
        or request["max_output_tokens"] != 2000
        or not isinstance(request["input"], str)
        or not isinstance(request["instructions"], str)
    ):
        raise ValueError("request contract")
    reserve = (Decimal(len(encoded(request)) + 1024) * INPUT + 2000 * OUTPUT) / 1000000
    return request, reserve


def count_one(root, plan, identity, counter):
    folder = root / "counts"
    folder.mkdir(exist_ok=True)
    create(folder / "lock", {"plan_sha256": identity})
    try:
        for item in plan["requests"]:
            name = item["request_sha256"]
            receipt = folder / (name + ".json")
            if receipt.exists():
                count_receipt(root, identity, item)
                continue
            started = folder / (name + ".started.json")
            if started.exists():
                raise ValueError("uncertain count request; manual reconciliation required")
            request, _ = request_for(root, item)
            create(started, {"plan_sha256": identity, "request_sha256": name})
            response = counter(request)
            n = response.get("input_tokens")
            if response.get("object") != "response.input_tokens" or type(n) is not int or not 0 <= n <= 100000:
                raise ValueError("invalid token count")
            create(receipt, {"plan_sha256": identity, "request_sha256": name, "input_tokens": n, "model": MODEL, "api_inference_calls": 0})
            return {"mode": "count", "input_tokens": n, "api_inference_calls": 0}
        return {"mode": "count-complete", "api_inference_calls": 0}
    finally:
        (folder / "lock").unlink()


def count_receipt(root, identity, item):
    data = json.loads(read(root / "counts" / (item["request_sha256"] + ".json")))
    n = data.get("input_tokens")
    if (
        data.get("plan_sha256") != identity
        or data.get("request_sha256") != item["request_sha256"]
        or data.get("model") != MODEL
        or type(n) is not int
        or not 0 <= n <= 100000
    ):
        raise ValueError("count identity mismatch")
    return n


def run(root, live=False, sender=send, counter=None):
    raw = read(root / "plan.json")
    identity = digest(raw)
    if live and os.environ.get("NBSR_BATCH_PLAN_SHA256") != identity:
        raise ValueError("approved plan identity required")
    plan = json.loads(raw)
    if (
        plan.get("preparation_complete") is not True
        or plan.get("scope") != "code-docs-configuration"
        or plan.get("repository") != "petritbahtiri123/name-based-secure-routing"
        or plan.get("ref") != "refs/heads/codex/nbsr-v3-wp0-wp1"
        or plan.get("weekly_limit_usd") != "10.00"
    ):
        raise ValueError("approved complete weekly snapshot required")
    snapshot_raw = read(root / "snapshot.json")
    snapshot = json.loads(snapshot_raw)
    if (
        digest(snapshot_raw) != plan.get("snapshot_sha256")
        or snapshot.get("preparation_complete") is not True
        or any(snapshot.get(k) != plan.get(k) for k in ("repository", "ref", "scope", "commit", "source_set_sha256"))
    ):
        raise ValueError("weekly snapshot identity mismatch")
    items = plan["requests"]
    if not items or len({i["request_sha256"] for i in items}) != len(items):
        raise ValueError("empty or duplicate plan")
    if not live:
        total = sum((request_for(root, item)[1] for item in items), Decimal(0))
        return {"mode": "dry-run", "api_calls": 0, "requests": len(items), "plan_sha256": identity, "full_plan_reserved_usd": str(total)}
    if (
        os.environ.get("NBSR_ANALYSIS_MODEL") != MODEL
        or Decimal(os.environ.get("NBSR_INPUT_RATE", "0")) != INPUT
        or Decimal(os.environ.get("NBSR_OUTPUT_RATE", "0")) != OUTPUT
        or Decimal(os.environ.get("NBSR_MAX_USD", "0")) != LIMIT
    ):
        raise ValueError("approved model/rates/cumulative budget required")
    mode = os.environ.get("NBSR_BATCH_MODE", "")
    if mode == "count":
        return count_one(root, plan, identity, counter or (lambda request: send(request, True)))
    if mode not in {"analyze", "analyze-bytes"}:
        raise ValueError("explicit count or analyze mode required")
    if mode == "analyze-bytes":
        counts = [len(encoded(request_for(root, item)[0])) + 1024 for item in items]
        reserves = [(Decimal(n) * INPUT + 2000 * OUTPUT) / 1000000 for n in counts]
    else:
        # Count includes message framing; retain a further 128-token margin per request.
        counts = [count_receipt(root, identity, item) + 128 for item in items]
        reserves = [(Decimal(n) * INPUT + 2000 * OUTPUT) / 1000000 for n in counts]
    if sum(reserves) > LIMIT - SYNTHESIS_RESERVE:
        raise ValueError("entire frozen plan exceeds approved budget; no partial start")
    ledger = root / "ledger"
    ledger.mkdir(exist_ok=True)
    lock = ledger / "lock"
    create(lock, {"plan_sha256": identity})
    attempted = None
    try:
        spent = Decimal(0)
        held = []
        pending = None
        for index, item in enumerate(items):
            reservation = ledger / f"{index:05d}.reserved.json"
            receipt = ledger / f"{index:05d}.complete.json"
            if reservation.exists():
                reserved = json.loads(read(reservation))
                if reserved["plan_sha256"] != identity or reserved["request_sha256"] != item["request_sha256"]:
                    raise ValueError("ledger identity mismatch")
                if not receipt.exists():
                    hold = ledger / f"{index:05d}.held.json"
                    if not hold.exists():
                        raise ValueError("uncertain request; manual reconciliation required")
                    decision = json.loads(read(hold))
                    if (
                        decision.get("reservation_sha256") != digest(read(reservation))
                        or decision.get("decision") != "retain_full_reservation_skip_without_retry"
                    ):
                        raise ValueError("invalid manual hold")
                    debit = Decimal(reserved["reserved_usd"])
                    if not debit.is_finite() or debit != reserves[index]:
                        raise ValueError("hold amount mismatch")
                    spent += debit
                    held.append(index)
                    continue
                completed = json.loads(read(receipt))
                if (
                    completed["plan_sha256"] != identity
                    or completed["request_sha256"] != item["request_sha256"]
                    or completed["reservation_sha256"] != digest(read(reservation))
                ):
                    raise ValueError("receipt identity mismatch")
                cost = Decimal(completed["cost_usd"])
                if not cost.is_finite() or cost < 0 or cost > Decimal(reserved["reserved_usd"]):
                    raise ValueError("invalid receipt cost")
                spent += cost
            elif receipt.exists():
                raise ValueError("orphan receipt")
            elif pending is None:
                pending = (index, item)
        if pending is None:
            return {
                "mode": "partial-held" if held else "complete",
                "cost_usd": str(spent),
                "held_chunks": held,
                "coverage": "planned chunks excluding held chunks",
            }
        index, item = pending
        request, _ = request_for(root, item)
        reserve = reserves[index]
        if spent + reserve > LIMIT - SYNTHESIS_RESERVE:
            raise ValueError("cumulative budget insufficient; partial coverage")
        reservation = ledger / f"{index:05d}.reserved.json"
        create(
            reservation,
            {
                "plan_sha256": identity,
                "request_sha256": item["request_sha256"],
                "reserved_usd": str(reserve),
                "spent_before_usd": str(spent),
            },
        )
        attempted = index
        response = sender(request)
        if not isinstance(response, dict):
            raise ValueError("response is not object")
        create(
            ledger / f"{index:05d}.response-metadata.json",
            {"plan_sha256": identity, "request_sha256": item["request_sha256"], **response_metadata(response)},
        )
        usage = response.get("usage", {})
        ni, no = usage.get("input_tokens"), usage.get("output_tokens")
        if (
            response.get("status") != "completed"
            or type(ni) is not int
            or type(no) is not int
            or not 0 <= ni <= counts[index]
            or not 0 <= no <= 2000
        ):
            raise ValueError("unverified usage or incomplete result; reservation retained")
        texts = [
            c["text"]
            for x in response.get("output", [])
            if x.get("type") == "message"
            for c in x.get("content", [])
            if c.get("type") == "output_text"
        ]
        if not texts or any(not isinstance(t, str) for t in texts):
            raise ValueError("no advisory result; reservation retained")
        actual = (ni * INPUT + no * OUTPUT) / 1000000
        receipt = {
            "plan_sha256": identity,
            "request_sha256": item["request_sha256"],
            "reservation_sha256": digest(read(reservation)),
            "cost_usd": str(actual),
            "usage": {"input_tokens": ni, "output_tokens": no},
            "unverified_model_analysis": "\n".join(texts),
            "coverage": item["ranges"],
            "limitation": "Advisory only; not verified defects or whole-repository coverage.",
        }
        create(ledger / f"{index:05d}.complete.json", receipt)
        return {"mode": "live", "chunk": index, "cost_usd": str(actual), "cumulative_usd": str(spent + actual)}
    except Exception as error:
        if attempted is not None:
            category = (
                "http_rejected"
                if isinstance(error, HTTPFailure)
                else "timeout"
                if isinstance(error, TimeoutError)
                else "transport_or_io"
                if isinstance(error, (OSError, http.client.HTTPException))
                else "response_or_receipt_validation"
            )
            safe = {
                "category": category,
                "reservation_retained": True,
                "plan_sha256": identity,
                "request_sha256": items[attempted]["request_sha256"],
            }
            if isinstance(error, HTTPFailure) and type(error.status) is int and 100 <= error.status <= 599:
                safe["http_status"] = error.status
            try:
                create(ledger / f"{attempted:05d}.failure.json", safe)
            except OSError:
                pass  # Reservation remains blocking even if diagnostic storage fails.
        raise
    finally:
        lock.unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=["ci"], default="ci")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(run(Path(__file__).resolve().parents[2], args.live)))
    except Exception:
        print("Analysis failed closed. No retry. Inspect local ledger; no secret diagnostics.")
        raise SystemExit(1) from None
