"""G1 RED: ingest station checksum (arrival+checksum only, AC-S1.2 subset)."""

from backend.stations.ingest.checksum import sha256_hex

G1_DIGEST = "e651652d7cc45083d37620a36aa0610ccf1ad840a968a53c79352b4d5a35915a"  # pragma: allowlist secret - test fixture digest, not a credential
EMPTY_DIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"  # pragma: allowlist secret - published empty-input digest, not a credential


def test_sha256_hex_is_stable_for_known_bytes() -> None:
    digest = sha256_hex(b"martini-shot-g1")
    assert digest == G1_DIGEST
    assert digest == sha256_hex(b"martini-shot-g1")
    assert digest != sha256_hex(b"martini-shot-g1-other")


def test_empty_payload_has_known_sha256() -> None:
    # SHA-256 of empty bytes is a published constant.
    assert sha256_hex(b"") == EMPTY_DIGEST
