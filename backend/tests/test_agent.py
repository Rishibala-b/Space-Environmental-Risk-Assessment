"""
Tests for Agent 1 (ObservationAgent). Fake Space-Track session, rule-based LLM --
no network, no API keys, whatever your .env contains.

Run:  python -m pytest tests/ -v     (or: python tests/test_agent.py)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fakes import (  # noqa: E402
    BAD_CHECKSUM_L2, ISS_L1, ISS_L2, RECORDS, FakeSpaceTrackSession, make_spacetrack, no_llm,
)
from app.agents.observation_agent import ObservationAgent  # noqa: E402
from app.services.spacetrack_service import SpaceTrackService  # noqa: E402


def make_agent(session=None):
    return ObservationAgent(make_spacetrack(session), no_llm())


def test_1_object_lookup_live_fetch():
    result = make_agent().observe(query="Tell me about NORAD 25544")
    assert result["intent"] == "object_lookup"
    assert result["result"]["OBJECT_NAME"] == "ISS (ZARYA)"
    assert "TLE_LINE1" in result["result"] and "TLE_LINE2" in result["result"]
    assert "error" not in result["result"]


def test_2_tle_pasted_directly():
    result = make_agent().observe(query=f"Analyze this TLE:\n{ISS_L1}\n{ISS_L2}")
    assert result["intent"] == "tle_lookup"
    assert result["object_id"] == "25544"
    assert result["result"]["OBJECT_NAME"] == "ISS (ZARYA)"


def test_3_orbital_parameter_query():
    result = make_agent().observe(query="What is the inclination of NORAD 25544?")
    assert result["intent"] == "parameter_query"
    assert result["result"]["inclination_deg"] == 51.64
    assert "TLE_LINE1" in result["result"]  # still plottable


def test_4_comparison_query():
    result = make_agent().observe(query="Compare NORAD 25544 and 47960")
    assert result["intent"] == "comparison"
    cmp_ = result["result"]["comparison"]
    assert cmp_["OBJECT_TYPE"]["25544"] == "PAYLOAD"
    assert cmp_["OBJECT_TYPE"]["47960"] == "DEBRIS"


def test_5_unknown_norad_id_not_found_on_spacetrack():
    result = make_agent().observe(query="Tell me about NORAD 99999999")
    assert result["intent"] == "object_lookup"
    assert "does not exist" in result["result"]["error"]


def test_6_missing_parameter_not_computable():
    result = make_agent().observe(query="What is the true anomaly of NORAD 25544?")
    assert result["intent"] == "parameter_query"
    assert "error" in result["result"]


def test_7_invalid_tle():
    result = make_agent().observe(tle_line1=ISS_L1, tle_line2=BAD_CHECKSUM_L2)
    assert result["intent"] == "tle_lookup"
    assert "checksum" in result["result"]["error"].lower()


def test_8_general_dataset_question_gets_clean_redirect():
    result = make_agent().observe(query="What information does the dataset contain?")
    assert result["intent"] == "general_dataset"
    assert "specific NORAD ID" in result["result"]["error"]


def test_9_no_credentials_configured():
    spacetrack = SpaceTrackService(session=None, username="", password="")
    result = ObservationAgent(spacetrack, no_llm()).observe(query="Tell me about NORAD 25544")
    assert "credentials are not configured" in result["result"]["error"]


def test_10_no_query_no_tle():
    result = make_agent().observe()
    assert "error" in result["result"]


# ------------------------------------------------------------ new behaviour --
def test_11_explicit_norad_id_field():
    session = FakeSpaceTrackSession()
    result = make_agent(session).observe(norad_id=25544)
    assert result["intent"] == "object_lookup"
    assert result["result"]["OBJECT_NAME"] == "ISS (ZARYA)"
    assert len(session.get_calls) == 1


def test_12_decayed_object_gets_warning():
    records = {"25544": {**RECORDS["25544"], "DECAY_DATE": "2024-05-01"}}
    result = make_agent(FakeSpaceTrackSession(records=records)).observe(norad_id="25544")
    assert "warning" in result["result"]
    assert "decayed" in result["result"]["warning"]
    assert "Warning:" in result["response"]


def test_13_year_in_question_is_not_mistaken_for_norad_id():
    result = make_agent().observe(query="The ISS launched in 1998 -- tell me about NORAD 25544")
    assert result["object_id"] == "25544"


def test_14_windows_line_endings_in_pasted_tle():
    result = make_agent().observe(tle_line1=ISS_L1 + "\r\n", tle_line2=ISS_L2 + "  \r\n")
    assert "error" not in result["result"], result["result"]


def test_15_comparison_needs_two_distinct_ids():
    result = make_agent().observe(query="Compare NORAD 25544 vs 25544")
    assert "error" in result["result"]


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
