"""RED tests: _auth_headers accepts every Grafana Cloud credential shape the
owner can paste (portal template base64(id:token), standard OTLP env header,
raw cloud-access-policy token) — no manual base64 math on the owner's side.
"""

import base64

from backend.core.otel import _auth_headers

ID, TOKEN = "1810754", "glc_dummy-secret"


def test_portal_template_becomes_basic_header() -> None:
    headers = _auth_headers(f"base64({ID}:{TOKEN})")
    expected = base64.b64encode(f"{ID}:{TOKEN}".encode()).decode()
    assert headers == {"Authorization": f"Basic {expected}"}


def test_standard_otlp_env_header_is_accepted() -> None:
    expected = base64.b64encode(f"{ID}:{TOKEN}".encode()).decode()
    for raw in (f"Authorization=Basic {expected}", f"Basic {expected}"):
        assert _auth_headers(raw) == {"Authorization": f"Basic {expected}"}


def test_url_encoded_space_is_normalized() -> None:
    expected = base64.b64encode(f"{ID}:{TOKEN}".encode()).decode()
    assert _auth_headers(f"Authorization=Basic%20{expected}") == {
        "Authorization": f"Basic {expected}"
    }


def test_raw_token_still_uses_bearer() -> None:
    assert _auth_headers(TOKEN) == {"Authorization": f"Bearer {TOKEN}"}


def test_empty_token_disables_auth() -> None:
    assert _auth_headers("") is None
