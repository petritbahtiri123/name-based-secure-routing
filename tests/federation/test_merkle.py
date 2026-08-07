from __future__ import annotations

import pytest

from nbsr.federation.transparency import (
    EMPTY_TREE_ROOT,
    leaf_hash,
    merkle_root,
    node_hash,
    verify_consistency,
    verify_inclusion,
)


H_A = bytes.fromhex("022a6979e6dab7aa5ae4c3e5e45f7e977112a7e63593820dbec1ec738a24f93c")
H_B = bytes.fromhex("57eb35615d47f34ec714cacdf5fd74608a5e8e102724e80b24b287c0c27b6a31")
H_C = bytes.fromhex("597fcb31282d34654c200d3418fca5705c648ebf326ec73d8ddef11841f876d8")
H_AB = bytes.fromhex("b137985ff484fb600db93107c77b0365c80d78f5b429ded0fd97361d077999eb")
H_ABC = bytes.fromhex("36642e73c2540ab121e3a6bf9545b0a24982cd830eb13d3cd19de3ce6c021ec1")
H_ABCD = bytes.fromhex("33376a3bd63e9993708a84ddfe6c28ae58b83505dd1fed711bd924ec5a6239f0")
H_ABCDE = bytes.fromhex("fe14a5426fbd70c0fa73f52342afed0da0bd23c4838662ccf6b88a3070ead97b")


def test_hand_recorded_merkle_roots() -> None:
    assert EMPTY_TREE_ROOT.hex() == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert leaf_hash(b"a") == H_A
    assert node_hash(H_A, H_B) == H_AB
    assert merkle_root([]) == EMPTY_TREE_ROOT
    assert merkle_root([b"a"]) == H_A
    assert merkle_root([b"a", b"b"]) == H_AB
    assert merkle_root([b"a", b"b", b"c"]) == H_ABC
    assert merkle_root([b"a", b"b", b"c", b"d"]) == H_ABCD
    assert merkle_root([b"a", b"b", b"c", b"d", b"e"]) == H_ABCDE
    assert merkle_root([b"a", b"b", b"c"]) == H_ABC


def test_inclusion_paths_are_ordered_and_bound_to_index_and_size() -> None:
    assert verify_inclusion(H_A, 0, 3, [H_B, H_C], H_ABC)
    assert verify_inclusion(H_C, 2, 3, [H_AB], H_ABC)
    assert not verify_inclusion(H_A, 0, 3, [H_C, H_B], H_ABC)
    assert not verify_inclusion(H_A, 1, 3, [H_B, H_C], H_ABC)
    assert not verify_inclusion(H_A, 0, 2, [H_B, H_C], H_ABC)


def test_inclusion_rejects_malformed_or_excessive_paths() -> None:
    with pytest.raises(ValueError, match="proof"):
        verify_inclusion(H_A, 0, 1, [b"x"], H_A)
    with pytest.raises(ValueError, match="proof"):
        verify_inclusion(H_A, 0, 1, [H_A] * 65, H_A)


def test_consistency_paths_prove_append_only_growth() -> None:
    assert verify_consistency(0, 3, EMPTY_TREE_ROOT, H_ABC, [])
    assert verify_consistency(1, 3, H_A, H_ABC, [H_B, H_C])
    assert verify_consistency(2, 3, H_AB, H_ABC, [H_C])
    assert verify_consistency(3, 3, H_ABC, H_ABC, [])
    assert not verify_consistency(3, 3, H_ABC, H_ABCD, [])
    assert not verify_consistency(2, 3, H_AB, H_ABC, [H_A])


def test_consistency_rejects_shrink_and_malformed_paths() -> None:
    assert not verify_consistency(3, 2, H_ABC, H_AB, [])
    with pytest.raises(ValueError, match="proof"):
        verify_consistency(1, 2, H_A, H_AB, [b"bad"])
    with pytest.raises(ValueError, match="proof"):
        verify_consistency(1, 2, H_A, H_AB, [H_B] * 65)


def test_merkle_construction_is_bounded() -> None:
    with pytest.raises(ValueError, match="leaf count"):
        merkle_root([b"a"] * 65_537)


def test_hand_recorded_non_power_of_two_consistency_vector() -> None:
    root6 = bytes.fromhex("e069fc12e231ccfd4516bf1617945fb3ccd5cc8910d92d6265289f088f777fdd")
    path = [
        bytes.fromhex(value)
        for value in (
            "2824a7ccda2caa720c85c9fba1e8b5b735eecfdb03878e4f8dfe6c3625030bc4",
            "f5a06d3c52937089c51b7c6c1cc1948ccdc5581328b2ebb578e8cca66a7b5221",
            "33376a3bd63e9993708a84ddfe6c28ae58b83505dd1fed711bd924ec5a6239f0",
        )
    ]
    assert verify_consistency(5, 6, H_ABCDE, root6, path)
