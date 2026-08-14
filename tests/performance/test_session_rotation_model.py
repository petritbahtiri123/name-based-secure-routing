from scripts.performance.session_rotation_model import Authority, RotationModel, canonical_results


def authority(session: str, channel: str, generation: int) -> Authority:
    return Authority(
        session_id=session,
        connection_binding=f"binding-{session}",
        channel_id=channel,
        route_id=f"route-{generation}",
        grant_digest=f"grant-{generation}",
        grant_nonce=f"nonce-{generation}",
        request_id=f"request-{generation}",
        monotonic_sequence=generation,
        resume_handle=f"resume-{generation}",
    )


def established_pair() -> tuple[RotationModel, Authority, Authority]:
    model = RotationModel(threshold=2)
    old = authority("TS-A", "SC-A", 1)
    fresh = authority("TS-B", "SC-B", 2)
    assert model.establish(old) == "ACCEPT"
    assert model.admit_channel(old) == "ACCEPT"
    assert model.establish(fresh) == "ACCEPT"
    assert model.admit_channel(fresh) == "ACCEPT"
    return model, old, fresh


def test_committed_stream_replay_stays_rejected_on_old_session() -> None:
    model, old, _ = established_pair()
    assert model.open_stream(old, 4) == "ACCEPT"
    assert model.open_stream(old, 4) == "REJECT_STREAM_REPLAY"


def test_numeric_stream_id_is_fresh_in_independently_authorized_session() -> None:
    model, old, fresh = established_pair()
    assert model.open_stream(old, 4) == "ACCEPT"
    assert model.open_stream(fresh, 4) == "ACCEPT"


def test_old_channel_or_routegrant_cannot_authorize_new_session() -> None:
    model, old, fresh = established_pair()
    stale_channel = Authority(**{**old.__dict__, "session_id": fresh.session_id, "connection_binding": fresh.connection_binding})
    assert model.open_stream(stale_channel, 8) == "REJECT_STALE_AUTHORITY"


def test_request_and_monotonic_replay_are_session_local_and_fail_closed() -> None:
    model, old, fresh = established_pair()
    rollback = Authority(**{**fresh.__dict__, "request_id": "request-rollback", "monotonic_sequence": 1})
    assert model.admit_channel(old) == "REJECT_REQUEST_REPLAY"
    assert model.admit_channel(rollback) == "REJECT_SEQUENCE_ROLLBACK"


def test_resume_material_is_single_use_and_does_not_transfer_authority() -> None:
    model, old, fresh = established_pair()
    assert model.issue_resume(old) == "ACCEPT"
    assert model.consume_resume(old.resume_handle, fresh) == "ACCEPT"
    assert model.consume_resume(old.resume_handle, fresh) == "REJECT_RESUME_REPLAY"


def test_failed_new_session_admission_keeps_old_session_active() -> None:
    model = RotationModel(threshold=2)
    old = authority("TS-A", "SC-A", 1)
    bad = Authority(**{**authority("TS-B", "SC-B", 2).__dict__, "grant_digest": old.grant_digest})
    assert model.establish(old) == "ACCEPT"
    assert model.admit_channel(old) == "ACCEPT"
    assert model.establish(bad) == "ACCEPT"
    assert model.admit_channel(bad) == "REJECT_STALE_AUTHORITY"
    assert model.open_stream(old, 4) == "ACCEPT"


def test_exact_threshold_routes_only_after_fresh_admission() -> None:
    model, old, fresh = established_pair()
    assert model.open_stream(old, 4) == "ACCEPT"
    assert model.open_stream(old, 8) == "ACCEPT"
    assert model.rotation_due(old.session_id)
    assert model.select_for_new_stream(old.session_id, fresh.session_id) == "TS-B"


def test_inflight_old_stream_drains_without_moving_and_releases_history() -> None:
    model, old, fresh = established_pair()
    assert model.open_stream(old, 4) == "ACCEPT"
    assert model.begin_drain(old.session_id) == "ACCEPT"
    assert model.stream_owner(4, old.session_id) == "TS-A"
    assert model.open_stream(fresh, 4) == "ACCEPT"
    assert model.finish_stream(old.session_id, 4) == "ACCEPT"
    assert model.retire(old.session_id) == "ACCEPT"
    assert model.replay_entries(old.session_id) == 0


def test_revocation_during_transition_blocks_new_streams() -> None:
    model, old, fresh = established_pair()
    assert model.revoke(fresh.channel_id) == "ACCEPT"
    assert model.open_stream(fresh, 4) == "REJECT_REVOKED"
    assert model.open_stream(old, 4) == "ACCEPT"


def test_no_application_session_selector_means_transparent_rotation_gate_fails() -> None:
    model, _, _ = established_pair()
    gates = model.production_gates(application_selector_present=False, fresh_authority_provider_present=False)
    assert gates == {
        "no_replay_weakening": True,
        "no_authority_resurrection": True,
        "no_protocol_ambiguity": False,
        "fresh_session_establishment": True,
        "bounded_deterministic_rotation": False,
        "fail_closed_failures": True,
    }


def test_canonical_results_report_design_blocked_gate() -> None:
    assert canonical_results()["decision"] == "DESIGN_BLOCKED"
    assert canonical_results()["all_implementation_gates_pass"] is False
    assert canonical_results()["adversarial_cases"] == {
        "old_stream_replay": "REJECT_STREAM_REPLAY",
        "fresh_numeric_stream_reuse": "ACCEPT",
        "old_channel_or_grant_resurrection": "REJECT_STALE_AUTHORITY",
        "resume_replay": "REJECT_RESUME_REPLAY",
        "revocation_during_transition": "REJECT_REVOKED",
    }
