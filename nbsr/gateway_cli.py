from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from nbsr.gateway_journal import JournalError, OwnershipJournal, build_rollback_plan
from nbsr.gateway_plan import GatewayPlan, PlanError, build_gateway_plan
from nbsr.gateway_profile import GatewayProfile, PlatformSnapshot, ProfileError
from nbsr.gateway_verify import verify_gateway


_MAX_INPUT_BYTES = 64 * 1024
_ERROR_CODE = "NBSR_GATEWAY_INPUT_REJECTED"


def _load_json(path: str) -> Any:
    target = Path(path)
    if target.stat().st_size > _MAX_INPUT_BYTES:
        raise ValueError("input exceeds maximum size")
    return json.loads(target.read_text(encoding="utf-8"))


def _emit(value: object) -> None:
    sys.stdout.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nbsr-gateway-plan")
    subcommands = parser.add_subparsers(dest="command", required=True)

    plan = subcommands.add_parser("plan")
    plan.add_argument("--profile", required=True)
    plan.add_argument("--snapshot", required=True)

    verify = subcommands.add_parser("verify")
    verify.add_argument("--profile", required=True)
    verify.add_argument("--plan", required=True)
    verify.add_argument("--journal", required=True)
    verify.add_argument("--snapshot", required=True)

    rollback = subcommands.add_parser("rollback-plan")
    rollback.add_argument("--plan", required=True)
    rollback.add_argument("--journal", required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    try:
        if args.command == "plan":
            profile = GatewayProfile.from_dict(_load_json(args.profile))
            snapshot = PlatformSnapshot.from_dict(_load_json(args.snapshot))
            _emit(build_gateway_plan(profile, snapshot).to_dict())
            return 0
        if args.command == "verify":
            profile = GatewayProfile.from_dict(_load_json(args.profile))
            plan = GatewayPlan.from_dict(_load_json(args.plan))
            journal = OwnershipJournal.from_dict(_load_json(args.journal))
            snapshot = PlatformSnapshot.from_dict(_load_json(args.snapshot))
            report = verify_gateway(profile, plan, journal, snapshot)
            _emit(report.to_dict())
            return 0 if report.passed else 1
        plan = GatewayPlan.from_dict(_load_json(args.plan))
        journal = OwnershipJournal.from_dict(_load_json(args.journal))
        _emit(build_rollback_plan(plan, journal).to_dict())
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, ProfileError, PlanError, JournalError):
        sys.stderr.write(f"{_ERROR_CODE}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
