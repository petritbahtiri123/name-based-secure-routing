from scripts import run_b3_session_lifecycle as b3


def test_rust_scale_uses_one_source_process_not_process_per_session():
    assert b3.source_plan("rust-rust", 512, 1) == [(1, 0, 512)]
    assert b3.source_plan("rust-rust", 1, 50) == [(50, 0, 1)]
    assert b3.source_plan("go-rust", 2, 1) == [(1, 0, 1), (1, 1, 1)]
