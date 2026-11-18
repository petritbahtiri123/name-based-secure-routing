"""Future owner adapter; no launcher, watcher, live registration or deletion.

The caller supplies its reviewed bounded owner, run-bound receipt reader and
atomic reservation context. Those are trust boundaries, not inferred from files.
This module does not attach itself to any campaign, including frozen RUN1709.
"""

from pathlib import PurePosixPath
import time

from scripts.benchmark_evidence_zip import create_verified_zip, _inventory

LIMIT = 150 * 1024**2


def _terminal(value):
    return (
        type(value) is dict
        and type(value.get("exit_code")) is int
        and value.get("leader_reaped") is True
        and value.get("group_exit_observed") is True
        and value.get("owned_handles") is False
        and "drain_failure" in value
        and value["drain_failure"] is None
        and value.get("cleanup_errors") == []
    )


def _closure(value, run, expected_remote):
    if (
        type(value) is not dict
        or value.get("run") != run
        or not _terminal(value.get("parent"))
    ):
        raise ValueError("parent closure unconfirmed")
    capture = value.get("capture", {})
    if (
        capture.get("readers_quiescent") is not True
        or type(capture.get("reader_count")) is not int
        or capture["reader_count"] != 2
        or capture.get("reader_start_uncertain") is not False
    ):
        raise ValueError("capture writers unconfirmed")
    remote = value.get("remote", {})
    if remote.get("errors") != {} or set(remote.get("receipts", {})) != {
        "source",
        "destination",
    }:
        raise ValueError("remote cleanup unconfirmed")
    if type(expected_remote) is not dict or set(expected_remote) != {
        "source",
        "destination",
    }:
        raise ValueError("expected exact remote owners required")
    for role, identity in expected_remote.items():
        row = remote["receipts"][role]
        if (
            type(identity) is not tuple
            or len(identity) != 2
            or not all(type(x) is str and x for x in identity)
            or (row.get("unit"), row.get("cgroup")) != identity
            or row.get("role") != role
            or row.get("SERVICE_RESULT") != "success"
            or row.get("EXIT_CODE") != "exited"
            or row.get("EXIT_STATUS") != "0"
            or row.get("tls_cleanup") != "REMOVED"
            or row.get("mountpoint_cleanup") != "CONFIRMED"
            or any(
                row.get(k) is not True
                for k in ("cgroup_absent", "tls_holder_absent", "tls_path_absent")
            )
        ):
            raise ValueError("remote owner identity or cleanup mismatch")
    publisher = value.get("publisher")
    if type(publisher) is not dict:
        raise ValueError("publisher state missing")
    if publisher.get("dispatched") is False:
        if publisher.get("no_dispatch_confirmed") is not True:
            raise ValueError("publisher absence unproven")
    elif publisher.get("dispatched") is True:
        if (
            not _terminal(publisher.get("terminal"))
            or publisher.get("cleanup_confirmed") is not True
        ):
            raise ValueError("publisher cleanup unconfirmed")
    else:
        raise ValueError("publisher dispatch uncertain")


def _static_inventory(expected):
    _inventory(expected)
    for name in expected:
        p = PurePosixPath(name.lower())
        if p.suffix not in {".json", ".log", ".ndjson", ".txt", ".csv"} or any(
            any(
                word in part
                for word in (
                    "sqlite",
                    "dashboard",
                    "manifest",
                    "pending",
                    "lock",
                    "-wal",
                    "-shm",
                )
            )
            for part in p.parts
        ):
            raise ValueError(
                "only explicit static evidence; operational/source files excluded"
            )


def finalize_after_owner(
    owner,
    *,
    run,
    observe,
    reserve,
    root,
    archive,
    expected,
    maximum_archive_bytes,
    metadata_bytes,
    expected_remote,
):
    """Finish the supplied owner, then archive only after closure and admission.

    Invalid measurements are retained as invalid. Reservation must hold across
    archive creation/verification. The supplied owner must cover its descendants;
    an arbitrary PID/poll result is not a substitute for its terminal receipt.
    """
    if type(run) is not str or not run or len(run) > 128:
        raise ValueError("explicit run identity required")
    terminal = owner.finish()
    if not _terminal(terminal) or terminal.get("run") != run:
        raise ValueError("outer launcher not terminal")
    receipts = observe()
    _closure(receipts, run, expected_remote)
    _static_inventory(expected)
    if any(
        type(x) is not int or x <= 0 for x in (maximum_archive_bytes, metadata_bytes)
    ):
        raise ValueError("positive explicit capacities required")
    request = dict(
        archive_bytes=maximum_archive_bytes,
        restore_bytes=sum(row["bytes"] for row in expected.values()),
        metadata_bytes=metadata_bytes,
    )
    # No compression ratio assumption. Restore capacity is retained even though
    # this non-destructive adapter does not extract or prune any source files.
    with reserve(request) as admission:
        now = time.monotonic()
        if (
            type(admission) is not dict
            or admission.get("reservation_held") is not True
            or any(
                admission.get(k) != v or type(admission.get(k)) is not int
                for k, v in request.items()
            )
            or any(
                type(admission.get(k)) is not int or admission[k] < 0
                for k in ("existing_bytes", "external_reserved_bytes")
            )
            or type(admission.get("observed_monotonic")) not in (int, float)
            or not 0 <= now - admission["observed_monotonic"] <= 5
            or sum(request.values())
            + admission["existing_bytes"]
            + admission["external_reserved_bytes"]
            > LIMIT
        ):
            raise ValueError("fresh reserved peak exceeds admission or is unconfirmed")
        result = create_verified_zip(
            root, archive, expected, maximum_archive_bytes=maximum_archive_bytes
        )
    return dict(
        run=run,
        measurement_status=receipts["parent"].get("status"),
        archive=result,
        originals_retained=True,
        campaign_hook_installed=False,
    )
