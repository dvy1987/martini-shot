"""Google sign-in gate for owner-class writes (C-5.2 spirit).

The `X-API-Key` header identifies the MACHINE (deployed FE, scripts). It
cannot identify a PERSON — anyone who copies the key out of the deployed
bundle holds it. Actions that change what the autonomous loop may do
(settings writes) require a second factor: a Google ID token verifying the
signer IS the owner.

Contract (used by the settings route; testable via dependency injection):
- `verify_owner_id_token(token, settings)` → claims dict on success.
- `GoogleTokenError` → 401 (missing config, malformed/expired/foreign-
  audience token, unverified email).
- `GoogleTokenNotOwner` → 403 (valid Google sign-in, but not the owner's
  account).

Fail-closed by construction: no GOOGLE_CLIENT_ID / GOOGLE_OWNER_EMAIL
configured means every token is refused.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.core.config import Settings

log = logging.getLogger("pc.api.google_auth")


class GoogleAuthError(Exception):
    """Base: token gate refused the request."""


class GoogleTokenError(GoogleAuthError):
    """401 — no/invalid/expired token, or the gate is unconfigured."""


class GoogleTokenNotOwner(GoogleAuthError):
    """403 — valid Google sign-in, but not the owner's account."""


def verify_owner_id_token(token: str, settings: Settings) -> dict[str, Any]:
    """Verify a Google ID token and require it to be the OWNER's account.

    Real cryptographic verification against Google's public keys with the
    configured OAuth client audience (google-auth library), then an
    allowlist check on the verified email. Anything short of that raises."""
    if not token:
        raise GoogleTokenError("missing Google ID token")
    client_id = settings.google_client_id
    owner_email = settings.google_owner_email
    if not client_id or not owner_email:
        # Unconfigured gate = locked gate. Never "allow through".
        log.warning("google owner gate unconfigured — refusing settings write")
        raise GoogleTokenError("owner sign-in gate is not configured")

    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    try:
        claims = google_id_token.verify_oauth2_token(
            token, google_requests.Request(), client_id
        )
    except Exception as exc:
        raise GoogleTokenError(
            f"invalid Google ID token: {type(exc).__name__}"
        ) from exc
    if not isinstance(claims, dict):
        raise GoogleTokenError("unexpected token claims")
    email = str(claims.get("email") or "")
    if not email or str(claims.get("email_verified") or "") not in (
        "true",
        "True",
        True,
    ):
        raise GoogleTokenError("token email is missing or unverified")
    if email.strip().lower() != owner_email.strip().lower():
        raise GoogleTokenNotOwner(email)
    return claims
