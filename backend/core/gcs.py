"""GCS media wrapper (plan A-2, C-6.2). Thin, typed, real-only: every call
hits the real bucket — there is no in-memory fallback anywhere (C-1.1).
"""

from __future__ import annotations

from datetime import timedelta, timezone
from typing import Any

from google.cloud import storage  # namespace pkg — suppressed in mypy.ini

from backend.core.config import Settings


def object_key(ref: str, *, bucket: str | None = None) -> str:
    """Turn a gs:// URI or a raw object name into a bucket-relative key.

    E-3 jobs store `gs://martini-shot-media/e3/ep-01.mp4`. Passing that
    string to `blob()` makes GCS look up object
    `gs://martini-shot-media/e3/ep-01.mp4` and 404.
    """
    text = (ref or "").strip()
    if not text:
        raise ValueError("empty GCS object ref")
    if text.startswith("gs://"):
        rest = text[5:]
        if "/" not in rest:
            raise ValueError(f"gs:// URI missing object key: {ref!r}")
        uri_bucket, key = rest.split("/", 1)
        if not key:
            raise ValueError(f"gs:// URI missing object key: {ref!r}")
        if bucket and uri_bucket != bucket:
            raise ValueError(
                f"gs:// URI bucket {uri_bucket!r} does not match {bucket!r}"
            )
        return key
    return text.lstrip("/")


class GCSMedia:
    def __init__(
        self,
        client: storage.Client,
        bucket_name: str,
        *,
        signing_sa: str = "",
    ) -> None:
        self._client = client
        self._bucket = client.bucket(bucket_name)
        self._signing_sa = signing_sa

    def upload_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> None:
        self._bucket.blob(object_key(key, bucket=self._bucket.name)).upload_from_string(
            data, content_type=content_type, timeout=60
        )

    def download_bytes(self, key: str) -> bytes:
        return self._bucket.blob(
            object_key(key, bucket=self._bucket.name)
        ).download_as_bytes(timeout=60)

    def delete(self, key: str) -> None:
        self._bucket.blob(object_key(key, bucket=self._bucket.name)).delete(timeout=60)

    def exists(self, key: str) -> bool:
        return self._bucket.blob(object_key(key, bucket=self._bucket.name)).exists(
            timeout=60
        )

    def signed_download_url(self, key: str, *, expires_minutes: int = 60) -> str:
        """V4 signed GET URL for the frontend/player (spec §3: signed URLs to FE).

        Cloud Run runtimes sign with their attached service account. Dev machines
        holding only user-account ADC (no private key) sign remotely via IAM
        signBlob by impersonating `gcs_signing_sa` — still real credentials,
        no key files anywhere (C-5.1).
        """
        blob = self._bucket.blob(object_key(key, bucket=self._bucket.name))
        credentials = self._client._credentials
        expiration = datetime_now() + timedelta(minutes=expires_minutes)
        if not _needs_remote_signer(credentials):
            return blob.generate_signed_url(
                version="v4",
                expiration=expiration,
                method="GET",
                credentials=credentials,
            )
        from google.oauth2.credentials import Credentials as UserCredentials

        if isinstance(credentials, UserCredentials):
            if not self._signing_sa:
                raise RuntimeError(
                    "GCS_SIGNING_SA must be set to sign URLs with user-account ADC"
                )
            from google.auth import impersonated_credentials

            signing_credentials = impersonated_credentials.Credentials(
                source_credentials=credentials,
                target_principal=self._signing_sa,
                target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
                lifetime=300,
            )
            return blob.generate_signed_url(
                version="v4",
                expiration=expiration,
                method="GET",
                credentials=signing_credentials,
            )
        return _sign_with_access_token(
            blob, credentials, signing_sa=self._signing_sa, expiration=expiration
        )


def _needs_remote_signer(credentials: object) -> bool:
    """User ADC and Cloud Run metadata credentials have no private key."""
    signer = getattr(credentials, "signer", None)
    signer_email = getattr(credentials, "signer_email", None)
    return signer is None or not signer_email


def _sign_with_access_token(
    blob: Any,
    credentials: object,
    *,
    signing_sa: str,
    expiration: object,
) -> str:
    """IAM signBlob using the runtime service account (Cloud Run / GCE)."""
    from google.auth.transport.requests import Request

    token = getattr(credentials, "token", None)
    sa_email = signing_sa or str(
        getattr(credentials, "service_account_email", "") or ""
    )
    if (
        not token
        or not getattr(credentials, "valid", False)
        or sa_email in {"", "default"}
    ):
        refresh = getattr(credentials, "refresh", None)
        if callable(refresh):
            refresh(Request())
        token = getattr(credentials, "token", None)
        if sa_email in {"", "default"}:
            sa_email = signing_sa or str(
                getattr(credentials, "service_account_email", "") or ""
            )
    if not sa_email or sa_email == "default" or not token:
        raise RuntimeError("cannot determine service account email for URL signing")
    return blob.generate_signed_url(
        version="v4",
        expiration=expiration,
        method="GET",
        service_account_email=sa_email,
        access_token=token,
    )


def datetime_now():
    from datetime import datetime

    return datetime.now(tz=timezone.utc)


def get_gcs(settings: Settings) -> GCSMedia:
    client = storage.Client(project=settings.gcp_project_id)
    return GCSMedia(client, settings.gcs_bucket, signing_sa=settings.gcs_signing_sa)
