"""GCS media wrapper (plan A-2, C-6.2). Thin, typed, real-only: every call
hits the real bucket — there is no in-memory fallback anywhere (C-1.1).
"""

from __future__ import annotations

from datetime import timedelta, timezone

from google.cloud import storage  # namespace pkg — suppressed in mypy.ini

from backend.core.config import Settings


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
        self._bucket.blob(key).upload_from_string(
            data, content_type=content_type, timeout=60
        )

    def download_bytes(self, key: str) -> bytes:
        return self._bucket.blob(key).download_as_bytes(timeout=60)

    def delete(self, key: str) -> None:
        self._bucket.blob(key).delete(timeout=60)

    def exists(self, key: str) -> bool:
        return self._bucket.blob(key).exists(timeout=60)

    def signed_download_url(self, key: str, *, expires_minutes: int = 60) -> str:
        """V4 signed GET URL for the frontend/player (spec §3: signed URLs to FE).

        Cloud Run runtimes sign with their attached service account. Dev machines
        holding only user-account ADC (no private key) sign remotely via IAM
        signBlob by impersonating `gcs_signing_sa` — still real credentials,
        no key files anywhere (C-5.1).
        """
        blob = self._bucket.blob(key)
        credentials = self._client._credentials
        if _needs_remote_signer(credentials):
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
                expiration=datetime_now() + timedelta(minutes=expires_minutes),
                method="GET",
                credentials=signing_credentials,
            )
        return blob.generate_signed_url(
            version="v4",
            expiration=datetime_now() + timedelta(minutes=expires_minutes),
            method="GET",
            credentials=credentials,
        )


def _needs_remote_signer(credentials: object) -> bool:
    """User-account OAuth tokens have no private key and cannot sign locally."""
    from google.oauth2.credentials import Credentials as UserCredentials

    return isinstance(credentials, UserCredentials)


def datetime_now():
    from datetime import datetime

    return datetime.now(tz=timezone.utc)


def get_gcs(settings: Settings) -> GCSMedia:
    client = storage.Client(project=settings.gcp_project_id)
    return GCSMedia(client, settings.gcs_bucket, signing_sa=settings.gcs_signing_sa)
