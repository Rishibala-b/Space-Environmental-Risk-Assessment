"""
SpaceObjectClassificationAgent: Agent 2.

Classifies an object as ACTIVE SATELLITE or SPACE DEBRIS with the trained
Gradient Boosting model. Accepts a pasted TLE, or a NORAD ID (explicit field or
found in free text), in which case the current TLE is fetched live from
Space-Track.org.

Pipeline:
  TLE (pasted OR fetched live by NORAD ID)
       ->  tle_service (validate + extract; shared with Agent 1 and Batch)
       ->  ClassificationService (the ONLY source of the label/probabilities)
       ->  LLMService.generate_response() (phrases the computed result only)

`enrich=False` skips the optional name/type lookup for a pasted TLE -- the
Dashboard uses this because Agent 1 has already fetched that record, which
avoids a duplicate Space-Track request.
"""
from typing import Any, Dict, Optional

from app.services import tle_service
from app.services.classification_service import (
    FEATURE_ORDER, MODEL_DISPLAY_NAME, ClassificationService,
)
from app.services.llm_service import LLMService
from app.services.spacetrack_service import (
    SpaceTrackAuthError, SpaceTrackNotFoundError, SpaceTrackQueryError, SpaceTrackService,
    decay_warning,
)


def readable_features(raw_params: Dict[str, Any]) -> Dict[str, Any]:
    """The 'features' block in responses, with display-friendly names."""
    return {
        "inclination": raw_params.get("inclination_deg"),
        "eccentricity": raw_params.get("eccentricity"),
        "raan": raw_params.get("raan_deg"),
        "argument_of_perigee": raw_params.get("arg_perigee_deg"),
        "mean_anomaly": raw_params.get("mean_anomaly_deg"),
        "mean_motion": raw_params.get("mean_motion_rev_per_day"),
        "orbital_period": raw_params.get("orbital_period_min"),
        "specific_orbital_energy": raw_params.get("specific_orbital_energy_km2_s2"),
        "semi_major_axis_km": raw_params.get("semi_major_axis_km"),
        "altitude_km": raw_params.get("altitude_km"),
        "velocity_km_s": raw_params.get("orbital_velocity_km_s"),
    }


def model_features(raw_params: Dict[str, Any]) -> Dict[str, float]:
    return {key: raw_params[key] for key in FEATURE_ORDER if key in raw_params}


class SpaceObjectClassificationAgent:
    def __init__(self, classification_service: ClassificationService, llm_service: LLMService,
                 spacetrack_service: Optional[SpaceTrackService] = None):
        self.classification_service = classification_service
        self.llm_service = llm_service
        self.spacetrack_service = spacetrack_service

    def classify(self, line1: Optional[str] = None, line2: Optional[str] = None,
                 norad_id: Optional[Any] = None, query: Optional[str] = None,
                 enrich: bool = True) -> Dict[str, Any]:
        # 1) A TLE may arrive via dedicated fields, or pasted inside free-text `query`.
        if not (line1 and line2):
            pasted = tle_service.looks_like_tle(query or "")
            if pasted:
                line1, line2 = pasted

        # 2) Otherwise fetch the current TLE live by NORAD ID.
        fetched_record = None  # reused below -- no second Space-Track call
        if not (line1 and line2):
            candidate_id = norad_id
            if candidate_id is None and query:
                ids = tle_service.find_norad_ids(query)
                candidate_id = ids[0] if ids else None
            if candidate_id is not None:
                if self.spacetrack_service is None:
                    return self._package({"error": "NORAD-ID lookup is not available (Space-Track "
                                                   "service not configured)."}, object_id=str(candidate_id))
                try:
                    fetched_record = self.spacetrack_service.get_current_tle(candidate_id)
                    line1, line2 = fetched_record["TLE_LINE1"], fetched_record["TLE_LINE2"]
                except SpaceTrackNotFoundError as e:
                    return self._package({"error": str(e)}, object_id=str(candidate_id))
                except (SpaceTrackAuthError, SpaceTrackQueryError) as e:
                    return self._package({"error": f"Could not retrieve NORAD {candidate_id}: {e}"},
                                         object_id=str(candidate_id))

        if not (line1 and line2):
            return self._package({
                "error": "Classification requires a TLE or a NORAD ID. Provide 'line1'/'line2', "
                         "a 'norad_id', or paste a TLE / mention a NORAD ID in 'query'."
            })

        # 3) Validate + decode (identical for pasted or fetched TLEs).
        line1, line2 = tle_service.clean_tle_line(line1), tle_service.clean_tle_line(line2)
        is_valid, error = tle_service.validate_tle(line1, line2)
        if not is_valid:
            return self._package({"error": f"Invalid TLE: {error}"})

        try:
            raw_params = tle_service.extract_orbital_parameters(line1, line2)
        except Exception as e:
            return self._package({"error": f"Could not extract orbital features from this TLE: {e}"})

        features = model_features(raw_params)
        missing = [k for k in FEATURE_ORDER if k not in features]
        if missing:
            return self._package({"error": f"Could not compute required feature(s): {missing}"})

        try:
            prediction = self.classification_service.predict(features)
        except Exception as e:
            return self._package({"error": str(e)})

        object_norad_id = tle_service.extract_norad_id(line1)
        facts: Dict[str, Any] = {
            **prediction,
            "features": readable_features(raw_params),
            "model": MODEL_DISPLAY_NAME,
            "TLE_LINE1": line1,
            "TLE_LINE2": line2,
        }

        # 4) Catalogue enrichment: reuse the record fetched above, or (pasted TLE
        #    with enrich=True) make one best-effort, non-fatal lookup.
        record = fetched_record
        if record is None and enrich and object_norad_id and self.spacetrack_service is not None:
            try:
                record = self.spacetrack_service.get_current_tle(object_norad_id)
            except Exception:
                record = None
        if record is not None:
            for key in ("OBJECT_NAME", "OBJECT_ID", "OBJECT_TYPE", "EPOCH"):
                if record.get(key):
                    facts[key] = record[key]
            # A decay warning only applies when we classified Space-Track's own TLE.
            if fetched_record is not None:
                warning = decay_warning(fetched_record)
                if warning:
                    facts["warning"] = warning

        return self._package(facts, object_id=object_norad_id)

    # ------------------------------------------------------------------- helpers --
    def _package(self, facts: Dict[str, Any], object_id: Optional[str] = None) -> Dict[str, Any]:
        response_text = self.llm_service.generate_response("classification", facts)
        result = {
            "agent": "space_object_classification",
            "object_id": object_id,
            "response": response_text,
        }
        result.update(facts)
        return result
