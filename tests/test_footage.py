"""Ownership/infringement refusals must force original-clip generation."""

from __future__ import annotations

from backend.core.footage import is_ownership_refusal


def test_recitation_is_ownership_refusal() -> None:
    assert is_ownership_refusal("Recitation: content blocked") is True
    assert (
        is_ownership_refusal(
            "The request was rejected in the interests of third-party content providers"
        )
        is True
    )
    assert is_ownership_refusal("copyright infringement filter") is True


def test_ordinary_errors_are_not_ownership_refusals() -> None:
    assert is_ownership_refusal("404 No such object") is False
    assert is_ownership_refusal("unknown station 'dub'") is False
    assert is_ownership_refusal("429 RESOURCE_EXHAUSTED") is False


def test_ownership_refusal_wraps_recitation() -> None:
    from backend.core.footage import OwnershipRefusal, is_ownership_refusal

    err = OwnershipRefusal("Recitation: content blocked")
    assert is_ownership_refusal(err) is True
