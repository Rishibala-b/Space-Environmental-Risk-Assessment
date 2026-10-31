"""
Tests for the Space-Track fixes: correct login-failure detection, automatic
re-login on an expired session, 429 back-off, the shared rate limiter,
multi-ID and launch queries -- plus the LLM parameter-mapping and text-parsing
fixes. No network.

Run:  python -m pytest tests/ -v     (or: python tests/test_spacetrack_service.py)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fakes import FakeResponse, FakeSpaceTrackSession, ISS_L1, ISS_L2, make_spacetrack  # noqa: E402
from app.services import tle_service  # noqa: E402
from app.services.llm_service import LLMService, _strip_code_fences, map_parameter  # noqa: E402
from app.services.spacetrack_service import (  # noqa: E402
    RateLimiter, SpaceTrackAuthError, SpaceTrackQueryError, SpaceTrackService,
)


def _fresh_service(session, **kw):
    """A service that has NOT logged in yet (so the login path is exercised)."""
    svc = make_spacetrack(session, **kw)
    svc._logged_in = False
    return svc


# ------------------------------------------------------------------- login --
def test_1_login_failed_body_is_detected():
    session = FakeSpaceTrackSession(login_response=FakeResponse(200, text='{"Login":"Failed"}'))
    svc = _fresh_service(session)
    try:
        svc.get_current_tle(25544)
        assert False, "should have raised"
    except SpaceTrackAuthError as e:
        assert "login failed" in str(e).lower()
    assert session.get_calls == []  # never queried with a bad session


def test_2_successful_login_then_query():
    session = FakeSpaceTrackSession()
    svc = _fresh_service(session)
    record = svc.get_current_tle(25544)
    assert record["OBJECT_NAME"] == "ISS (ZARYA)"
    assert len(session.post_calls) == 1


def test_3_expired_session_relogs_in_once():
    session = FakeSpaceTrackSession(script=[FakeResponse(401)])
    svc = make_spacetrack(session)          # "already logged in" -- then the session expires
    record = svc.get_current_tle(25544)
    assert record["NORAD_CAT_ID"] == "25544"
    assert len(session.post_calls) == 1     # exactly one re-login
    assert len(session.get_calls) == 2      # the 401, then the retry


def test_4_persistent_401_raises_auth_error():
    session = FakeSpaceTrackSession(script=[FakeResponse(401), FakeResponse(401)])
    try:
        make_spacetrack(session).get_current_tle(25544)
        assert False, "should have raised"
    except SpaceTrackAuthError:
        pass


def test_5_429_backs_off_then_succeeds():
    session = FakeSpaceTrackSession(script=[FakeResponse(429, headers={"Retry-After": "1"})])
    assert make_spacetrack(session).get_current_tle(25544)["NORAD_CAT_ID"] == "25544"


def test_6_missing_credentials():
    try:
        SpaceTrackService(session=None, username="", password="").get_current_tle(25544)
        assert False
    except SpaceTrackAuthError as e:
        assert "credentials are not configured" in str(e)


# ------------------------------------------------------------ rate limiter --
def test_7_rate_limiter_fails_fast_when_budget_exhausted():
    now = [0.0]
    limiter = RateLimiter(per_minute=2, per_hour=100, max_wait_seconds=5,
                          clock=lambda: now[0], sleep=lambda s: now.__setitem__(0, now[0] + s))
    limiter.acquire()
    limiter.acquire()
    try:
        limiter.acquire()   # would need to wait ~60 s > 5 s allowed
        assert False, "should have raised"
    except SpaceTrackQueryError as e:
        assert "budget" in str(e)


def test_8_rate_limiter_waits_when_slot_frees_soon():
    now = [0.0]
    limiter = RateLimiter(per_minute=1, per_hour=100, max_wait_seconds=120,
                          clock=lambda: now[0], sleep=lambda s: now.__setitem__(0, now[0] + s))
    limiter.acquire()
    limiter.acquire()      # sleeps ~60 s of fake time, then succeeds
    assert now[0] >= 60


# --------------------------------------------------------- multi / launch --
def test_9_many_ids_in_one_request():
    session = FakeSpaceTrackSession()
    out = make_spacetrack(session).get_tles_for_ids(["25544", "47960", "11111"])
    assert set(out) == {"25544", "47960"}
    assert len(session.get_calls) == 1
    assert "NORAD_CAT_ID/11111,25544,47960/" in session.get_calls[0]


def test_10_launch_query_url():
    session = FakeSpaceTrackSession(launch_records=[])
    make_spacetrack(session).get_tles_for_launch("1993-036", include_decayed=False, limit=50)
    url = session.get_calls[0]
    assert "OBJECT_ID/%5E1993-036/" in url
    assert "DECAY_DATE/null-val/" in url
    assert "/limit/50/" in url


def test_11_launch_query_rejects_bad_designator():
    try:
        make_spacetrack().get_tles_for_launch("1993; drop", limit=5)
        assert False
    except SpaceTrackQueryError:
        pass


# --------------------------------------------------------- LLM + parsing --
def test_12_llm_parameter_word_is_mapped_to_field():
    assert map_parameter("altitude") == "altitude_km"
    assert map_parameter("Orbital Period") == "orbital_period_min"
    assert map_parameter("inclination_deg") == "inclination_deg"
    assert map_parameter("banana") is None


def test_13_code_fenced_json_is_parsed():
    assert json.loads(_strip_code_fences('```json\n{"intent": "object_lookup"}\n```'))["intent"] == "object_lookup"


class _FakeLLMClient:
    """Mimics google-genai: client.models.generate_content(...).text"""
    def __init__(self, text):
        self.models = self
        self._text = text

    def generate_content(self, model, contents):
        return type("R", (), {"text": self._text})()


def test_14_llm_cannot_invent_norad_ids_and_parameter_is_mapped():
    fake = _FakeLLMClient('```json\n{"intent":"parameter_query","norad_ids":["25544","99999"],"parameter":"altitude"}\n```')
    llm = LLMService(provider="google", api_key="x", client=fake)
    parsed = llm.understand_query("What's the altitude of NORAD 25544?")
    assert parsed.norad_ids == ["25544"]           # 99999 was not in the user's text
    assert parsed.parameter == "altitude_km"
    assert parsed.intent == "parameter_query"


def test_15_find_norad_ids_rules():
    assert tle_service.find_norad_ids("NORAD 5") == ["5"]
    assert tle_service.find_norad_ids("launched 1998, id 25544") == ["25544"]
    assert tle_service.find_norad_ids("inclination 51.64 of 25544") == ["25544"]
    assert tle_service.find_norad_ids("25544, 43013 48274") == ["25544", "43013", "48274"]


def test_16_alpha5_and_crlf():
    assert tle_service.extract_norad_id("1 A0001U" + ISS_L1[8:]) == "100001"
    ok, err = tle_service.validate_tle(ISS_L1 + "\r", ISS_L2 + " \r")
    assert ok, err


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed} passed, {failed} failed (out of {len(tests)})")
