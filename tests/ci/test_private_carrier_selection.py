from scripts.ci.check import command_groups


def test_private_carrier_fixture_runs_as_one_bounded_serial_target():
    commands = [c for c in command_groups("rust") if c.name == "rust-private-carrier"]
    assert len(commands) == 1
    cmd = commands[0]
    assert cmd.argv == (
        "cargo", "test", "--locked", "--offline", "--manifest-path",
        "crates/nbsr-transport/Cargo.toml", "--features", "benchmark-harness",
        "--jobs", "2", "--test", "private_carrier_refusal", "--", "--test-threads=1",
    )
    assert cmd.cwd == "."
