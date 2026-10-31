"""
Centralized configuration.

Every setting the app needs comes from environment variables (loaded from a local
.env file via python-dotenv). No credentials or file paths are hard-coded anywhere
else in the codebase -- if you need to change a path or add a key, this is the
only file you touch.

Architecture reminder: there is NO local dataset and NO cache. Agent 1, Agent 2
and the Batch agent all query Space-Track.org live, per request, via
SpaceTrackService. SPACETRACK_USERNAME/SPACETRACK_PASSWORD are REQUIRED.
"""
import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()  # reads a local .env file, if present, into the process environment


def _get_int(name: str, default: int) -> int:
    """Reads an integer env var; a malformed value falls back to the default
    (with a console note) instead of crashing the whole app at import time."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError:
        print(f"[config] {name}='{raw}' is not an integer -- using default {default}.")
        return default


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw.strip())
    except ValueError:
        print(f"[config] {name}='{raw}' is not a number -- using default {default}.")
        return default


@dataclass
class Settings:
    # --- Space-Track.org credentials (every agent needs these) -----------------
    # Required. Never hard-code these -- set them in your local .env only.
    spacetrack_username: str = os.getenv("SPACETRACK_USERNAME", "")
    spacetrack_password: str = os.getenv("SPACETRACK_PASSWORD", "")
    spacetrack_base_url: str = os.getenv("SPACETRACK_BASE_URL", "https://www.space-track.org")
    # Seconds to wait for ONE Space-Track HTTP response before giving up.
    spacetrack_timeout_seconds: int = _get_int("SPACETRACK_TIMEOUT_SECONDS", 20)

    # --- Space-Track usage policy (enforced client-side) ------------------------
    # Space-Track's published limits: fewer than 30 requests/minute and 300/hour.
    # The defaults stay just under those. Every call made by any agent goes
    # through one shared limiter, so batch runs can never push the account over.
    spacetrack_max_per_minute: int = _get_int("SPACETRACK_MAX_PER_MINUTE", 25)
    spacetrack_max_per_hour: int = _get_int("SPACETRACK_MAX_PER_HOUR", 280)
    # If a request would have to wait longer than this for a rate-limit slot, it
    # fails fast with a clear "rate limit" error instead of hanging the request.
    spacetrack_max_wait_seconds: float = _get_float("SPACETRACK_MAX_WAIT_SECONDS", 15.0)

    # --- Batch / fleet analysis --------------------------------------------------
    # Max objects one batch request may analyze (event queries are truncated to this).
    batch_max_objects: int = _get_int("BATCH_MAX_OBJECTS", 500)
    # NORAD IDs per Space-Track request. Space-Track accepts comma-separated IDs,
    # so 500 objects = 5 requests, not 500.
    batch_ids_per_request: int = _get_int("BATCH_IDS_PER_REQUEST", 100)
    # Parallel Space-Track requests during a batch (still bounded by the limiter).
    batch_max_workers: int = _get_int("BATCH_MAX_WORKERS", 3)

    # --- Classification model (Agent 2 + Batch) ----------------------------------
    # Points at the already-trained GradientBoostingClassifier .pkl. Never
    # trained or modified here -- only loaded with joblib.
    classification_model_path: str = os.getenv(
        "CLASSIFICATION_MODEL_PATH", "./data/gradient_boosting_model.pkl"
    )

    # --- LLM configuration -------------------------------------------------------
    # LLM_PROVIDER="anthropic" uses the Anthropic API.
    # LLM_PROVIDER="google" uses Gemini via the google-genai SDK.
    # LLM_PROVIDER="none" (or no API key set) uses the built-in rule-based fallback.
    llm_provider: str = os.getenv("LLM_PROVIDER", "none")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "claude-sonnet-4-5")

    # --- App ---
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = _get_int("API_PORT", 8000)

    # --- CORS (for the React/Vite frontend) ---
    frontend_origins: List[str] = field(default_factory=lambda: [
        o.strip() for o in os.getenv(
            "FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",") if o.strip()
    ])


settings = Settings()
