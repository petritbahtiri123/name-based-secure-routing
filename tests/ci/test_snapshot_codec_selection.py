from scripts.ci.check import command_groups


def test_snapshot_selection_is_exact_codec_only_subset():
    prefix = "tests/test_wp6_continuity_snapshot.py"
    names = (
        'test_snapshot_encoding_is_canonical_stable_and_round_trips',
        'test_decoder_rejects_unknown_missing_corrupt_unsorted_or_duplicate_state',
        'test_decoder_rejects_noncanonical_partial_and_oversized_input',
        'test_replica_config_requires_sorted_unique_bounded_majority',
    )
    expected = {f"{prefix}::{name}" for name in names}
    core = next(c for c in command_groups("python-core") if c.name == "python-core")
    selected = [arg for arg in core.argv if arg.startswith(prefix)]
    assert len(selected) == len(expected)
    assert set(selected) == expected
