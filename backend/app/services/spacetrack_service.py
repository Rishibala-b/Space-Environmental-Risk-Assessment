"""
SpaceTrackService: ALL live Space-Track.org access for every agent. No other file
makes network calls to Space-Track.

There is no local dataset and no cache -- every call hits Space-Track's `gp`
class live. Because of that, this file is also where Space-Track's usage policy
is enforced:

  * Rate limiting: one process-wide limiter (default 25/minute, 280/hour, just
    under Space-Track's published 30/minute and 300/hour). Every request from
    every agent -- single lookups and batch chunks alike -- takes a slot first.
    If a slot isn't free within SPACETRACK_MAX_WAIT_SECONDS, the call fails fast
    with a clear error instead of hanging.
  * Batching: many NORAD IDs go into ONE request (comma-separated), so a
    500-object batch is 5 requests, not 500.
  * Sessions: Space-Track sessions expire after ~2 hours of inactivity. A 401
    triggers exactly one automatic re-login + retry.
  * Login failures are detected from Space-Track's real failure body,
    {"Login": "Failed"}, not from guessed text.

Design for testability: accepts an injectable `session` (anything with
`.get(url, timeout=...)` and, if re-login is exercised, `.post(url, data=, timeout=)`),
an injectable `rate_limiter`, and an injectable `sleep` so tests never wait.
"""
import json
import re
import threading
import time
from collections import deque
from typing import Any, Callable, Dict, Iterable, List, Optional
from urllib.parse import quote

from app.utils.config import settings


class SpaceTrackAuthError(Exception):
    """Login failed (bad credentials, account problem) or credentials missing."""


class SpaceTrackNotFoundError(Exception):
    """A NORAD ID genuinely does not exist on Space-Track (or has no current TLE)."""


class SpaceTrackQueryError(Exception):
    """Any other Space-Track failure: rate limit, malformed response, timeout, HTTP error."""


# Fields requested from the gp class. OBJECT_ID is the international (COSPAR)
# designator, e.g. "1993-036A" -- used to group fragments by parent event.
GP_FIELDS = [
    "NORAD_CAT_ID", "OBJECT_NAME", "OBJECT_ID", "OBJECT_TYPE", "EPOCH",
    "TLE_LINE1", "TLE_LINE2", "DECAY_DATE",
]

_INTLDES_PREFIX_RE = re.compile(r"^\d{4}-\d{3}[A-Z]{0,3}$")


# --------------------------------------------------------------------------- #
#  Rate limiter                                                                #
# --------------------------------------------------------------------------- #
class RateLimiter:
    """Thread-safe sliding-window limiter over two windows (per minute, per hour).

    `clock` and `sleep` are injectable so tests can run instantly."""

    def __init__(self, per_minute: int, per_hour: int, max_wait_seconds: float,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.per_minute = max(1, per_minute)
        self.per_hour = max(1, per_hour)
        self.max_wait_seconds = max_wait_seconds
        self._clock = clock
        self._sleep = sleep
        self._minute: deque = deque()
        self._hour: deque = deque()
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        while self._minute and now - self._minute[0] >= 60:
            self._minute.popleft()
        while self._hour and now - self._hour[0] >= 3600:
            self._hour.popleft()

    def acquire(self) -> None:
        waited = 0.0
        while True:
            with self._lock:
                now = self._clock()
                self._prune(now)
                if len(self._minute) < self.per_minute and len(self._hour) < self.per_hour:
                    self._minute.append(now)
                    self._hour.append(now)
                    return
                wait_min = (60 - (now - self._minute[0])) if len(self._minute) >= self.per_minute else 0
                wait_hr = (3600 - (now - self._hour[0])) if len(self._hour) >= self.per_hour else 0
                wait = max(wait_min, wait_hr, 0.05)
            if waited + wait > self.max_wait_seconds:
                raise SpaceTrackQueryError(
                    "Space-Track request budget reached (this app stays under "
                    f"{self.per_minute}/minute and {self.per_hour}/hour to respect "
                    f"Space-Track's usage policy). Try again in about {int(wait) + 1} seconds."
                )
            self._sleep(wait)
            waited += wait

    def usage(self) -> Dict[str, int]:
        with self._lock:
            self._prune(self._clock())
            return {
                "last_minute": len(self._minute), "per_minute_limit": self.per_minute,
                "last_hour": len(self._hour), "per_hour_limit": self.per_hour,
            }


# One limiter shared by every SpaceTrackService in the process (unless a test
# injects its own), so the app as a whole stays under the limits.
_shared_limiter = RateLimiter(
    per_minute=settings.spacetrack_max_per_minute,
    per_hour=settings.spacetrack_max_per_hour,
    max_wait_seconds=settings.spacetrack_max_wait_seconds,
)


# --------------------------------------------------------------------------- #
#  Service                                                                     #
# --------------------------------------------------------------------------- #
class SpaceTrackService:
    def __init__(self, session=None, base_url: Optional[str] = None,
                 username: Optional[str] = None, password: Optional[str] = None,
                 rate_limiter: Optional[RateLimiter] = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.base_url = (base_url or settings.spacetrack_base_url).rstrip("/")
        self.username = username if username is not None else settings.spacetrack_username
        self.password = password if password is not None else settings.spacetrack_password
        self._session = session            # injected for tests; real requests.Session() otherwise
        self._logged_in = session is not None  # an injected session is assumed pre-authenticated
        self._limiter = rate_limiter or _shared_limiter
        self._sleep = sleep
        self._auth_lock = threading.Lock()

    # ------------------------------------------------------------------ auth --
    def is_configured(self) -> bool:
        return bool(self.username and self.password)

    def rate_usage(self) -> Dict[str, int]:
        return self._limiter.usage()

    def _login(self) -> None:
        """Logs in on the current session object (creating a real one if none).
        Must be called with _auth_lock held."""
        if not self.is_configured():
            raise SpaceTrackAuthError(
                "Space-Track credentials are not configured. Set SPACETRACK_USERNAME "
                "and SPACETRACK_PASSWORD in your .env file."
            )
        if self._session is None:
            import requests
            self._session = requests.Session()

        self._limiter.acquire()  # the login POST counts against the limits too
        try:
            resp = self._session.post(
                f"{self.base_url}/ajaxauth/login",
                data={"identity": self.username, "password": self.password},
                timeout=settings.spacetrack_timeout_seconds,
            )
        except Exception as e:
            raise SpaceTrackAuthError(f"Could not reach Space-Track.org: {e}")

        if resp.status_code != 200 or _is_login_failure(resp):
            self._logged_in = False
            raise SpaceTrackAuthError(
                "Space-Track login failed. Check SPACETRACK_USERNAME/SPACETRACK_PASSWORD "
                "and confirm your account is active."
            )
        self._logged_in = True

    def _ensure_logged_in(self) -> None:
        if self._logged_in and self._session is not None:
            return
        with self._auth_lock:
            if not (self._logged_in and self._session is not None):
                self._login()

    def _relogin(self) -> None:
        with self._auth_lock:
            self._logged_in = False
            self._login()

    # ----------------------------------------------------------- raw request --
    def _get_json(self, url: str) -> Any:
        """One logical GET: rate-limited, re-logs in once on 401, retries a
        429/network error a bounded number of times. Returns parsed JSON."""
        self._ensure_logged_in()
        relogged = False
        attempt = 0
        while True:
            attempt += 1
            self._limiter.acquire()
            try:
                resp = self._session.get(url, timeout=settings.spacetrack_timeout_seconds)
            except Exception as e:
                if attempt >= 2:
                    raise SpaceTrackQueryError(f"Network error contacting Space-Track: {e}")
                self._sleep(2)
                continue

            if resp.status_code == 401 and not relogged:
                # Session expired (Space-Track sessions last ~2h idle). Log in again once.
                relogged = True
                try:
                    self._relogin()
                except SpaceTrackAuthError:
                    raise
                continue
            if resp.status_code == 401:
                raise SpaceTrackAuthError("Space-Track rejected the session even after re-login.")
            if resp.status_code == 429:
                if attempt >= 3:
                    raise SpaceTrackQueryError("Space-Track rate limit reached. Try again shortly.")
                retry_after = _retry_after_seconds(resp, default=5 * attempt)
                self._sleep(min(retry_after, 10))
                continue
            if resp.status_code != 200:
                raise SpaceTrackQueryError(f"Space-Track query failed (HTTP {resp.status_code}).")

            try:
                data = resp.json()
            except ValueError:
                raise SpaceTrackQueryError("Space-Track returned an unexpected (non-JSON) response.")

            if isinstance(data, dict) and "error" in data:
                raise SpaceTrackQueryError(f"Space-Track error: {data['error']}")
            if isinstance(data, list) and data and isinstance(data[0], dict) and "error" in data[0]:
                raise SpaceTrackQueryError(f"Space-Track error: {data[0]['error']}")
            return data

    def _gp_url(self, filters: str) -> str:
        return (
            f"{self.base_url}/basicspacedata/query/class/gp/"
            f"{filters}predicates/{','.join(GP_FIELDS)}/format/json"
        )

    # ------------------------------------------------------------------ query --
    def get_current_tle(self, norad_id: Any) -> Dict[str, Any]:
        """Current TLE + catalogue metadata for ONE NORAD ID. Decayed objects are
        still returned (with DECAY_DATE set) so callers can warn about them.
        Raises SpaceTrackNotFoundError / SpaceTrackAuthError / SpaceTrackQueryError."""
        norad_id_int = _to_norad_int(norad_id)
        data = self._get_json(self._gp_url(f"NORAD_CAT_ID/{norad_id_int}/"))
        if not data:
            raise SpaceTrackNotFoundError(
                f"NORAD ID {norad_id_int} does not exist on Space-Track.org (or has no current TLE)."
            )
        record = data[0]
        missing = [f for f in ("TLE_LINE1", "TLE_LINE2") if not record.get(f)]
        if missing:
            raise SpaceTrackQueryError(
                f"Space-Track's record for NORAD ID {norad_id_int} is missing {missing}."
            )
        return record

    def get_tles_for_ids(self, norad_ids: Iterable[Any]) -> Dict[str, Dict[str, Any]]:
        """ONE request for many NORAD IDs (caller is responsible for chunking to a
        sensible size -- see settings.batch_ids_per_request). Returns
        {norad_id_str: record}; IDs Space-Track doesn't know are simply absent."""
        ids = sorted({_to_norad_int(n) for n in norad_ids})
        if not ids:
            return {}
        data = self._get_json(self._gp_url(f"NORAD_CAT_ID/{','.join(str(i) for i in ids)}/"))
        out: Dict[str, Dict[str, Any]] = {}
        for rec in data or []:
            if isinstance(rec, dict) and rec.get("NORAD_CAT_ID") is not None:
                out[str(int(rec["NORAD_CAT_ID"]))] = rec
        return out

    def get_tles_for_launch(self, intldes_prefix: str, include_decayed: bool = False,
                            limit: int = 500) -> List[Dict[str, Any]]:
        """Every object whose international designator starts with `intldes_prefix`
        (e.g. "1993-036" = Cosmos 2251 and all its catalogued fragments), in ONE
        request. By default only objects still in orbit (DECAY_DATE is null)."""
        prefix = (intldes_prefix or "").strip().upper()
        if not _INTLDES_PREFIX_RE.match(prefix):
            raise SpaceTrackQueryError(
                f"'{intldes_prefix}' is not a valid international designator prefix "
                "(expected e.g. '1993-036')."
            )
        limit = max(1, int(limit))
        filters = f"OBJECT_ID/{quote('^' + prefix, safe='')}/"
        if not include_decayed:
            filters += "DECAY_DATE/null-val/"
        filters += f"orderby/{quote('NORAD_CAT_ID asc')}/limit/{limit}/"
        data = self._get_json(self._gp_url(filters))
        return [r for r in (data or []) if isinstance(r, dict)]


# --------------------------------------------------------------------------- #
#  helpers                                                                     #
# --------------------------------------------------------------------------- #
def _to_norad_int(norad_id: Any) -> int:
    try:
        value = int(str(norad_id).strip())
    except (TypeError, ValueError):
        raise SpaceTrackQueryError(f"'{norad_id}' is not a valid integer NORAD ID.")
    if value <= 0:
        raise SpaceTrackQueryError(f"'{norad_id}' is not a valid NORAD ID (must be positive).")
    return value


def _is_login_failure(resp) -> bool:
    """Space-Track answers a failed login with HTTP 200 and the body
    {"Login": "Failed"}. A successful login body is an empty JSON string ("")."""
    text = getattr(resp, "text", "") or ""
    try:
        body = json.loads(text) if text.strip() else ""
    except ValueError:
        body = None
    if isinstance(body, dict) and str(body.get("Login", "")).lower() == "failed":
        return True
    lowered = text.lower()
    return "login failed" in lowered or '"failed"' in lowered


def _retry_after_seconds(resp, default: float) -> float:
    headers = getattr(resp, "headers", None) or {}
    try:
        return float(headers.get("Retry-After", default))
    except (TypeError, ValueError):
        return default


def decay_warning(record: Optional[Dict[str, Any]]) -> Optional[str]:
    """Returns a user-facing warning if Space-Track lists the object as decayed
    (re-entered). Its TLE is then the last one before re-entry, not a live orbit."""
    if record and record.get("DECAY_DATE"):
        return (
            f"Space-Track lists this object as decayed (re-entered) on {record['DECAY_DATE']}. "
            "The TLE used is its last one before re-entry, not a current orbit."
        )
    return None
