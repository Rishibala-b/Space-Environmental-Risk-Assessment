"""
Tests for Agent 2 (SpaceObjectClassificationAgent). Mock model + fake Space-Track
session + rule-based LLM -- no network, no .pkl, no API keys.

Run:  python -m pytest tests/ -v     (or: python tests/test_classification_agent.py)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fakes import (  # noqa: E402
    BAD_CHECKSUM_L2, DEB_L1, DEB_L2, ISS_L1, ISS_L2, RECORDS, FakeSpaceTrackSession,
    MockDebrisModel, MockSatelliteModel, MockWrongFeatureOrderModel, make_spacetrack, no_llm,
)
from app.agents.classification_agent import SpaceObjectClassificationAgent  # noqa: E402
from app.services.classification_service import ClassificationService # noqa: E402


def make_agent(model=None, model_path=None, session=None):
    classification_service = ClassificationService(model=model, model_path=model_path)
    return SpaceObjectClassificationAgent(classification_service, no_llm(), make_spacetrack(session))


def test_1_valid_tle_classification():
    result = make_agent(model=MockDebrisModel()).classify(line1=ISS_L1, line2=ISS_L2)
    assert result["agent"] == "space_object_classification"
    assert "error" not in result
    assert result["prediction"] == "SPACE DEBRIS"


def test_2_invalid_tle():
    result = make_agent(model=MockDebrisModel()).classify(line1=ISS_L1, line2=BAD_CHECKSUM_L2)
    assert "checksum" in result["error"].lower()


def test_3_missing_model():
    result = make_agent(model_path="/nonexistent/gradient_boosting_model.pkl").classify(line1=ISS_L1, line2=ISS_L2)
    assert "not found" in result["error"].lower()


def test_4_probability_output():
    result = make_agent(model=MockDebrisModel()).classify(line1=ISS_L1, line2=ISS_L2)
    assert result["probabilities"]["satellite"] == 2.58
    assert result["probabilities"]["debris"] == 97.42


def test_5_confidence_calculation():
    result = make_agent(model=MockDebrisModel()).classify(line1=ISS_L1, line2=ISS_L2)
    assert result["confidence"] == result["probabilities"]["debris"]


def test_6_correct_feature_ordering():
    assert ClassificationService(model=MockDebrisModel()).is_ready()
    bad = ClassificationService(model=MockWrongFeatureOrderModel())
    assert not bad.is_ready()
    assert "mismatch" in bad.load_error().lower()


def test_7_satellite_classification_response():
    result = make_agent(model=MockSatelliteModel()).classify(line1=ISS_L1, line2=ISS_L2)
    assert result["prediction"] == "ACTIVE SATELLITE"
    assert result["label"] == 0
    assert result["confidence"] == 91.2


def test_8_debris_classification_response():
    result = make_agent(model=MockDebrisModel()).classify(line1=ISS_L1, line2=ISS_L2)
    assert result["prediction"] == "SPACE DEBRIS"
    assert result["OBJECT_NAME"] == "ISS (ZARYA)"  # enriched live by NORAD ID from the TLE


def test_9_api_endpoint_wiring():
    main_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "main.py")
    source = open(main_path, encoding="utf-8").read()
    assert '"/agent/classify"' in source
    assert '"/agent/observe"' in source
    assert '"/agent/batch"' in source
    assert "/agent/trajectory" not in source


def test_10_agent_1_still_works():
    from app.agents.observation_agent import ObservationAgent
    result = ObservationAgent(make_spacetrack(), no_llm()).observe(query="Tell me about NORAD 25544")
    assert result["intent"] == "object_lookup"
    assert result["result"]["OBJECT_NAME"] == "ISS (ZARYA)"


def test_11_classify_by_norad_id_live_fetch():
    session = FakeSpaceTrackSession()
    result = make_agent(model=MockDebrisModel(), session=session).classify(norad_id=25544)
    assert result["prediction"] == "SPACE DEBRIS"
    assert result["OBJECT_NAME"] == "ISS (ZARYA)"
    assert len(session.get_calls) == 1, "should fetch Space-Track exactly once, not twice"


def test_12_classify_norad_id_not_found():
    result = make_agent(model=MockDebrisModel()).classify(norad_id=99999999)
    assert "does not exist" in result["error"]


# ------------------------------------------------------------ new behaviour --
def test_13_enrich_false_makes_no_spacetrack_call():
    session = FakeSpaceTrackSession()
    result = make_agent(model=MockSatelliteModel(), session=session).classify(
        line1=ISS_L1, line2=ISS_L2, enrich=False)
    assert "error" not in result
    assert session.get_calls == []


def test_15_model_receives_named_feature_columns():
    model = MockSatelliteModel()
    make_agent(model=model).classify(line1=ISS_L1, line2=ISS_L2, enrich=False)
    try:
        import pandas  # noqa: F401
    except ImportError:
        return
    assert list(model.last_X.columns)[0] == "inclination_deg"


def test_16_decayed_object_warning_on_classification():
    records = {"25544": {**RECORDS["25544"], "DECAY_DATE": "2024-05-01"}}
    result = make_agent(model=MockSatelliteModel(), session=FakeSpaceTrackSession(records=records)).classify(norad_id=25544)
    assert "decayed" in result["warning"]


def test_17_year_is_not_used_as_norad_id():
    session = FakeSpaceTrackSession()
    result = make_agent(model=MockSatelliteModel(), session=session).classify(
        query="Launched in 1998 -- is NORAD 25544 debris?")
    assert result["object_id"] == "25544"


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
