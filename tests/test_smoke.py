"""Repo-invariant smoke tests (plan F-3). These hold before any product code lands."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_license_present_at_repo_top() -> None:
    """C-2.3: OSI license must be detectable at the top of the public repo."""
    lic = ROOT / "LICENSE"
    assert lic.exists(), "LICENSE missing from repo root"
    assert "Apache License" in lic.read_text(encoding="utf-8")


def test_constitution_present() -> None:
    """Binding invariants doc must exist; specs/plans cite it."""
    assert (ROOT / "docs" / "constitution.md").exists()


def test_no_env_file_committed() -> None:
    """C-5.1: .env files must never be committed."""
    assert not (ROOT / ".env").exists()
    assert not (ROOT / "frontend" / ".env.local").exists()
