"""Uvicorn entrypoint: `python -m uvicorn backend.api.main:app --reload`.

Builds the app from process env (.env included) with telemetry enabled.
"""

from backend.api.app import create_app
from backend.core.config import get_settings

app = create_app(get_settings())
