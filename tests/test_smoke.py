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
    """C-5.1: .env files must never be COMMITTED. A local gitignored .env is
    expected on dev machines, so this checks the git index, not the filesystem."""
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    offenders = [
        f
        for f in tracked
        if (name := f.split("/")[-1]) == ".env"
        or (name.startswith(".env.") and not name.endswith((".example", ".sample")))
    ]
    assert not offenders, f"env files committed to git: {offenders}"
