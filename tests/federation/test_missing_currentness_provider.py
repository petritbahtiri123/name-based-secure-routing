"""Fixture refusal only; no authenticated producer or runtime readiness."""

import pytest


def test_missing_independent_provider_cannot_publish_currentness():
    # Canonical fixture seam, imported read-only. The candidate is deliberately
    # just shape-valid local data; it must not supply its own independent trust.
    from .freshness_support.currentness_seam import CurrentnessBarrier, RestoreIdentity, Unavailable

    barrier = CurrentnessBarrier(None)
    with pytest.raises(Unavailable):
        barrier.restore(RestoreIdentity(b"c" * 32, b"d" * 32, b"s" * 32, 1))
    with pytest.raises(Unavailable):
        barrier.capture()
    with pytest.raises(Unavailable):
        barrier.set_eligible(True)
