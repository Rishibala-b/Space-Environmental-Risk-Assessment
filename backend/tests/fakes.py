"""
Shared test doubles. Nothing here touches the network, a real model file, or a
real LLM -- every test in this folder runs offline and instantly.
"""
import json
import os
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.classification_service import FEATURE_ORDER  # noqa: E402
from app.services.llm_service import LLMService  # noqa: E402
from app.services.spacetrack_service import RateLimiter, SpaceTrackService  # noqa: E402

# Real, checksum-valid-shaped test TLEs.
ISS_L1 = "1 25544U 98067A   24001.50000000  .00016717  00000-0  10270-3 0  9997"
ISS_L2 = "2 25544  51.6400 208.9163 0004087  75.0964  35.7241 15.50505279227469"
BAD_CHECKSUM_L2 = "2 25544  51.6400 208.9163 0004087  75.0964  35.7241 15.50505279227460"
DEB_L1 = "1 47960U 21123A   24001.50000000  .00001234  00000-0  10270-3 0  9990"
DEB_L2 = "2 47960  82.5629  15.4321 0011523  88.1234 271.9871 14.90000000012343"

RECORDS: Dict[str, Dict[str, Any]] = {
    "25544": {"NORAD_CAT_ID": "25544", "OBJECT_NAME": "ISS (ZARYA)", "OBJECT_ID": "1998-067A",
              "OBJECT_TYPE": "PAYLOAD", "EPOCH": "2024-01-01T12:00:00",
              "TLE_LINE1": ISS_L1, "TLE_LINE2": ISS_L2, "DECAY_DATE": None},
    "47960": {"NORAD_CAT_ID": "47960", "OBJECT_NAME": "COSMOS 1408 DEB", "OBJECT_ID": "2021-123A",
              "OBJECT_TYPE": "DEBRIS", "EPOCH": "2024-01-01T12:00:00",
              "TLE_LINE1": DEB_L1, "TLE_LINE2": DEB_L2, "DECAY_DATE": None},
}


def no_llm() -> LLMService:
    """Always rule-based, whatever the developer's .env says."""
    return LLMService(provider="none", api_key="")


def free_limiter() -> RateLimiter:
    """A limiter that never blocks (tests make many calls in well under a minute)."""
    return RateLimiter(per_minute=10_000, per_hour=100_000, max_wait_seconds=0,
                       sleep=lambda s: None)


class FakeResponse:
    def __init__(self, status_code: int, json_data: Any = None, text: Optional[str] = None,
                 headers: Optional[Dict[str, str]] = None):
        self.status_code = status_code
        self._json = json_data
        self.text = text if text is not None else (json.dumps(json_data) if json_data is not None else "")
        self.headers = headers or {}

    def json(self):
        if self._json is None and self.text:
            return json.loads(self.text)
        return self._json


class FakeSpaceTrackSession:
    """Simulates Space-Track's gp class.

    * single ID:  .../NORAD_CAT_ID/25544/...
    * many IDs:   .../NORAD_CAT_ID/25544,47960/...
    * by launch:  .../OBJECT_ID/%5E1993-036/...  -> `launch_records`
    * `script`: optional list of FakeResponse returned (in order) before normal behaviour,
      e.g. [FakeResponse(401)] to simulate an expired session.
    * `fail_if_contains`: raise a network error for any URL containing that text.
    * `login_response`: what POST /ajaxauth/login returns.
    """

    def __init__(self, records: Optional[Dict[str, Dict[str, Any]]] = None,
                 launch_records: Optional[List[Dict[str, Any]]] = None,
                 script: Optional[List[FakeResponse]] = None,
                 fail_if_contains: Optional[str] = None,
                 login_response: Optional[FakeResponse] = None):
        self.records = RECORDS if records is None else records
        self.launch_records = launch_records or []
        self.script = list(script or [])
        self.fail_if_contains = fail_if_contains
        self.login_response = login_response or FakeResponse(200, text='""')
        self.get_calls: List[str] = []
        self.post_calls: List[str] = []

    def post(self, url, data=None, timeout=None):
        self.post_calls.append(url)
        return self.login_response

    def get(self, url, timeout=None):
        self.get_calls.append(url)
        if self.script:
            return self.script.pop(0)
        if self.fail_if_contains and self.fail_if_contains in url:
            raise ConnectionError("simulated network failure")
        if "/OBJECT_ID/" in url:
            limit = None
            if "/limit/" in url:
                limit = int(url.split("/limit/")[1].split("/")[0])
            data = self.launch_records if limit is None else self.launch_records[:limit]
            return FakeResponse(200, data)
        if "NORAD_CAT_ID/" in url:
            ids = url.split("NORAD_CAT_ID/")[1].split("/")[0].split(",")
            return FakeResponse(200, [self.records[i] for i in ids if i in self.records])
        return FakeResponse(200, [])


def make_spacetrack(session: Optional[FakeSpaceTrackSession] = None, **kwargs) -> SpaceTrackService:
    return SpaceTrackService(session=session or FakeSpaceTrackSession(),
                             username=kwargs.pop("username", "user"),
                             password=kwargs.pop("password", "pass"),
                             rate_limiter=kwargs.pop("rate_limiter", free_limiter()),
                             sleep=lambda s: None, **kwargs)


# ----------------------------------------------------------------- mock models --
def _n_rows_and_cols(X):
    if hasattr(X, "shape"):
        return X.shape[0], X.shape[1]
    return len(X), len(X[0])


class _MockModel:
    feature_names_in_ = FEATURE_ORDER
    classes_ = [0, 1]
    label = 0
    proba = [0.5, 0.5]

    def __init__(self):
        self.predict_calls = 0
        self.last_X = None

    def predict(self, X):
        self.predict_calls += 1
        self.last_X = X
        n, cols = _n_rows_and_cols(X)
        assert cols == len(FEATURE_ORDER), "wrong number of features passed to the model"
        return [self.label] * n

    def predict_proba(self, X):
        n, _ = _n_rows_and_cols(X)
        return [list(self.proba)] * n


class MockDebrisModel(_MockModel):
    label = 1
    proba = [0.0258, 0.9742]


class MockSatelliteModel(_MockModel):
    label = 0
    proba = [0.912, 0.088]


class MockWrongFeatureOrderModel(_MockModel):
    feature_names_in_ = list(reversed(FEATURE_ORDER))
