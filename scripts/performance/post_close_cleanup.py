"""Fail-closed validation of explicitly requested post-run ownership evidence."""

FIELDS = (
    "transport_sessions_current_live", "service_channels_current_live",
    "application_streams_current_live", "nbsr_tasks_current_live",
    "quic_connections_current_live", "quic_streams_current_live",
    "pending_routes_current_entries", "channel_registry_current_entries",
    "stream_registry_current_entries", "replay_state_current_entries",
    "audit_queue_current_entries",
)


def validate_report(value, role, pid):
    if not isinstance(value, dict):
        return False
    ownership = value.get("ownership")
    states = {"runtime_alive", "all_group_runtimes_joined"} if role == "source" else {"runtime_alive"}
    return (
        value.get("schema") == "nbsr-p2a-post-close-v1"
        and type(value.get("pid")) is int and value["pid"] == pid
        and value.get("role") == role
        and value.get("diagnostics_enabled_before_run") is True
        and isinstance(value.get("runtime_state"), str) and value["runtime_state"] in states
        and isinstance(ownership, dict)
        and all(type(ownership.get(field)) is int and ownership[field] == 0 for field in FIELDS)
    )
