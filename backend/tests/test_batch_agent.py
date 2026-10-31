"""
Tests for batch / fleet analysis: chunking, concurrency, partial failures,
event queries, truncation, and one-model-call classification. No network.

Run:  python -m pytest tests/ -v     (or: python tests/test_batch_agent.py)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fakes import (  # noqa: E402
    DEB_L1, DEB_L2, ISS_L1, ISS_L2, RECORDS, FakeSpaceTrackSession, MockDebrisModel,
    MockSatelliteModel, make_spacetrack, no_llm,
)
from app.agents.batch_agent import BatchAnalysisAgent, parse_norad_list  # noqa: E402
from app.services.classification_service import ClassificationService  # noqa: E402


def _rec(norad, name="OBJ", otype="DEBRIS", l1=DEB_L1, l2=DEB_L2, decay=None):
    return {"NORAD_CAT_ID": str(norad), "OBJECT_NAME": name, "OBJECT_ID": "1993-036X",
            "OBJECT_TYPE": otype, "EPOCH": "2024-01-01T12:00:00",
            "TLE_LINE1": l1, "TLE_LINE2": l2, "DECAY_DATE": decay}


def make_agent(session=None, model=None, model_path=None, ids_per_request=100, max_objects=500):
    return BatchAnalysisAgent(
        make_spacetrack(session),
        ClassificationService(model=model or MockDebrisModel(), model_path=model_path) if model_path is None
        else ClassificationService(model_path=model_path),
        no_llm(), max_objects=max_objects, ids_per_request=ids_per_request, max_workers=3,
    )


def _by_id(result):
    return {o["norad_id"]: o for o in result["objects"]}


def test_1_parse_norad_list():
    assert parse_norad_list("25544, 47960\n25544;abc 0") == (["25544", "47960"], ["abc", "0"])
    assert parse_norad_list([25544, "47960"]) == (["25544", "47960"], [])


def test_2_ids_batch_mixed_outcomes():
    session = FakeSpaceTrackSession()
    result = make_agent(session).analyze(norad_ids=["25544", "47960", "11111", "xyz"])
    rows = _by_id(result)
    assert rows["25544"]["status"] == "classified"
    assert rows["47960"]["status"] == "classified"
    assert rows["11111"]["status"] == "not_found"
    assert rows["xyz"]["status"] == "invalid_input"
    s = result["summary"]
    assert s["counts"] == {"satellite": 0, "debris": 2, "failed": 2}
    assert s["spacetrack_requests"] == 1               # both real IDs in ONE request
    assert rows["25544"]["TLE_LINE1"] == ISS_L1        # TLEs returned for fleet plotting


def test_3_chunking_makes_expected_number_of_requests():
    records = {str(n): _rec(n) for n in range(100, 105)}
    session = FakeSpaceTrackSession(records=records)
    result = make_agent(session, ids_per_request=2).analyze(norad_ids=list(records))
    assert result["summary"]["spacetrack_requests"] == 3      # 5 IDs / 2 per request
    assert len(session.get_calls) == 3
    assert result["summary"]["counts"]["debris"] == 5


def test_4_one_failed_chunk_does_not_sink_the_batch():
    records = {str(n): _rec(n) for n in range(100, 106)}
    session = FakeSpaceTrackSession(records=records, fail_if_contains="104")
    result = make_agent(session, ids_per_request=2).analyze(norad_ids=list(records))
    rows = _by_id(result)
    assert rows["104"]["status"] == "fetch_error" and rows["105"]["status"] == "fetch_error"
    assert all(rows[str(n)]["status"] == "classified" for n in range(100, 104))


def test_5_single_model_call_for_whole_batch():
    model = MockSatelliteModel()
    records = {str(n): _rec(n) for n in range(100, 140)}
    make_agent(FakeSpaceTrackSession(records=records), model=model).analyze(norad_ids=list(records))
    assert model.predict_calls == 1


def test_6_missing_model_keeps_catalog_data():
    result = make_agent(model_path="/nonexistent/model.pkl").analyze(norad_ids=["25544"])
    row = result["objects"][0]
    assert row["status"] == "model_error"
    assert row["object_name"] == "ISS (ZARYA)" and row["TLE_LINE1"]   # still plottable


def test_7_invalid_tle_in_record():
    bad = _rec(200, l2=DEB_L2[:-1] + "0")
    result = make_agent(FakeSpaceTrackSession(records={"200": bad})).analyze(norad_ids=["200"])
    assert result["objects"][0]["status"] == "invalid_tle"


def test_8_event_preset_query():
    launch = [_rec(22675, "COSMOS 2251", "PAYLOAD", ISS_L1, ISS_L2)] + [_rec(n) for n in (34427, 34428)]
    session = FakeSpaceTrackSession(launch_records=launch)
    result = make_agent(session).analyze(event="cosmos-2251")
    s = result["summary"]
    assert s["mode"] == "event" and s["intldes"] == "1993-036"
    assert s["returned"] == 3 and s["spacetrack_requests"] == 1
    assert s["by_catalog_type"] == {"PAYLOAD": 1, "DEBRIS": 2}
    assert "%5E1993-036" in session.get_calls[0]


def test_9_event_truncation_flag():
    launch = [_rec(n) for n in range(1000, 1010)]
    result = make_agent(FakeSpaceTrackSession(launch_records=launch)).analyze(intldes="1993-036", limit=4)
    assert result["summary"]["returned"] == 4
    assert result["summary"]["truncated"] is True


def test_10_ids_over_limit_are_truncated():
    records = {str(n): _rec(n) for n in range(100, 110)}
    result = make_agent(FakeSpaceTrackSession(records=records), max_objects=3).analyze(norad_ids=list(records))
    assert result["summary"]["returned"] == 3 and result["summary"]["truncated"] is True


def test_11_unknown_event_and_empty_request():
    assert "Unknown event" in make_agent().analyze(event="nope")["error"]
    assert "error" in make_agent().analyze()


def test_12_decayed_objects_flagged():
    records = {"25544": {**RECORDS["25544"], "DECAY_DATE": "2024-05-01"}}
    result = make_agent(FakeSpaceTrackSession(records=records)).analyze(norad_ids="25544")
    assert result["summary"]["decayed"] == 1
    assert "decayed" in result["objects"][0]["warning"]


def test_13_auth_failure_reported_per_row():
    session = FakeSpaceTrackSession()
    agent = make_agent(session)
    agent.spacetrack_service._logged_in = False
    agent.spacetrack_service.username = ""
    result = agent.analyze(norad_ids=["25544", "47960"])
    assert all(o["status"] == "fetch_error" for o in result["objects"])
    assert "credentials" in result["objects"][0]["error"]


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
