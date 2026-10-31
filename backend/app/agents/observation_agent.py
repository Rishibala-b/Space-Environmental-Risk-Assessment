"""
ObservationAgent: Agent 1.

Fetches the CURRENT TLE for a NORAD ID live from Space-Track.org on every
request (via SpaceTrackService), then decodes it with the same tle_service used
for pasted TLEs -- a NORAD-ID lookup and a pasted-TLE lookup go through identical
feature-extraction code.

Inputs, in priority order:
  1. tle_line1 + tle_line2 (explicit fields)
  2. a TLE pasted inside `query`
  3. norad_id (explicit field -- no LLM call needed to understand it)
  4. free-text `query` (LLM or rule-based intent parsing)

Public entry point is `observe()`: plain arguments in, plain dict out, safe for a
future coordinator agent to call directly.
"""
from typing import Any, Dict, Optional

from app.services import tle_service
from app.services.llm_service import LLMService, ParsedIntent
from app.services.spacetrack_service import (
    SpaceTrackAuthError, SpaceTrackNotFoundError, SpaceTrackQueryError, SpaceTrackService,
    decay_warning,
)

_SPACETRACK_ERRORS = (SpaceTrackNotFoundError, SpaceTrackAuthError, SpaceTrackQueryError)


class ObservationAgent:
    def __init__(self, spacetrack_service: SpaceTrackService, llm_service: LLMService):
        self.spacetrack_service = spacetrack_service
        self.llm_service = llm_service

    # ---------------------------------------------------------------- public API --
    def observe(self, query: Optional[str] = None, tle_line1: Optional[str] = None,
                tle_line2: Optional[str] = None, compare_with_norad_id: Optional[str] = None,
                norad_id: Optional[Any] = None) -> Dict[str, Any]:

        # 1) Direct TLE input takes priority.
        if tle_line1 and tle_line2:
            return self._handle_tle(tle_line1, tle_line2)
        pasted = tle_service.looks_like_tle(query or "")
        if pasted:
            return self._handle_tle(*pasted)

        # 2) Explicit NORAD ID field: structured, so no intent parsing is needed.
        if norad_id is not None and str(norad_id).strip() != "":
            nid = str(norad_id).strip()
            if compare_with_norad_id:
                return self._handle_comparison(ParsedIntent(
                    intent="comparison", norad_ids=[nid, str(compare_with_norad_id).strip()]))
            return self._handle_object_lookup(ParsedIntent(intent="object_lookup", norad_ids=[nid]))

        if not query:
            return self._package("unknown", None, {"error": "No query, NORAD ID, or TLE was provided."})

        # 3) Free text.
        parsed = self.llm_service.understand_query(query)
        if compare_with_norad_id:
            cid = str(compare_with_norad_id).strip()
            parsed.intent = "comparison"
            if cid not in parsed.norad_ids:
                parsed.norad_ids.append(cid)

        if parsed.intent == "general_dataset":
            return self._handle_general_dataset()
        if parsed.intent == "comparison":
            return self._handle_comparison(parsed)
        if parsed.intent == "parameter_query":
            return self._handle_parameter_query(parsed)
        if parsed.intent == "object_lookup":
            return self._handle_object_lookup(parsed)

        return self._package("unknown", None, {
            "error": "I could not identify a NORAD ID, TLE, or recognizable question in that message."
        })

    # ------------------------------------------------------------- live fetch helper --
    def _fetch_and_decode(self, norad_id: str) -> Dict[str, Any]:
        """Fetches the current TLE from Space-Track and decodes it. Raises the
        SpaceTrack* exceptions on failure -- callers turn those into a clean error dict."""
        record = self.spacetrack_service.get_current_tle(norad_id)
        line1 = tle_service.clean_tle_line(record["TLE_LINE1"])
        line2 = tle_service.clean_tle_line(record["TLE_LINE2"])
        orbital_params = tle_service.extract_orbital_parameters(line1, line2)
        facts: Dict[str, Any] = {
            "NORAD_CAT_ID": str(int(norad_id)),
            "OBJECT_NAME": record.get("OBJECT_NAME"),
            "OBJECT_ID": record.get("OBJECT_ID"),
            "OBJECT_TYPE": record.get("OBJECT_TYPE"),
            "EPOCH": record.get("EPOCH"),
            "DECAY_DATE": record.get("DECAY_DATE"),
            "TLE_LINE1": line1,
            "TLE_LINE2": line2,
            **orbital_params,
        }
        warning = decay_warning(record)
        if warning:
            facts["warning"] = warning
        return {k: v for k, v in facts.items() if v is not None}

    # --------------------------------------------------------------- intent handlers --
    def _handle_object_lookup(self, parsed: ParsedIntent) -> Dict[str, Any]:
        if not parsed.norad_ids:
            return self._package("object_lookup", None, {"error": "No NORAD ID was recognized in the question."})
        norad_id = parsed.norad_ids[0]
        try:
            facts = self._fetch_and_decode(norad_id)
        except SpaceTrackNotFoundError as e:
            return self._package("object_lookup", norad_id, {"error": str(e)})
        except (SpaceTrackAuthError, SpaceTrackQueryError) as e:
            return self._package("object_lookup", norad_id, {"error": f"Could not retrieve NORAD {norad_id}: {e}"})
        return self._package("object_lookup", facts.get("NORAD_CAT_ID", norad_id), facts)

    def _handle_parameter_query(self, parsed: ParsedIntent) -> Dict[str, Any]:
        if not parsed.norad_ids:
            return self._package("parameter_query", None, {"error": "No NORAD ID was recognized in the question."})
        norad_id = parsed.norad_ids[0]
        try:
            facts = self._fetch_and_decode(norad_id)
        except SpaceTrackNotFoundError as e:
            return self._package("parameter_query", norad_id, {"error": str(e)})
        except (SpaceTrackAuthError, SpaceTrackQueryError) as e:
            return self._package("parameter_query", norad_id, {"error": f"Could not retrieve NORAD {norad_id}: {e}"})

        available = [k for k in facts.keys() if k not in ("TLE_LINE1", "TLE_LINE2", "warning") and not k.startswith("_")]
        if not parsed.parameter:
            return self._package("parameter_query", norad_id, {
                "error": "The question didn't specify which parameter to look up.",
                "available_parameters": available,
            })
        if parsed.parameter not in facts:
            return self._package("parameter_query", norad_id, {
                "error": f"'{parsed.parameter}' is not available for NORAD {norad_id}.",
                "available_parameters": available,
            })
        result = {
            "NORAD_CAT_ID": facts["NORAD_CAT_ID"],
            "OBJECT_NAME": facts.get("OBJECT_NAME"),
            parsed.parameter: facts[parsed.parameter],
            # TLE kept so the frontend can still plot the orbit.
            "TLE_LINE1": facts["TLE_LINE1"],
            "TLE_LINE2": facts["TLE_LINE2"],
        }
        if facts.get("warning"):
            result["warning"] = facts["warning"]
        return self._package("parameter_query", facts["NORAD_CAT_ID"], {k: v for k, v in result.items() if v is not None})

    def _handle_comparison(self, parsed: ParsedIntent) -> Dict[str, Any]:
        ids = list(dict.fromkeys(parsed.norad_ids))  # de-duplicate, keep order
        if len(ids) < 2:
            return self._package("comparison", None, {
                "error": f"A comparison needs two different NORAD IDs; only {len(ids)} were recognized."
            })
        id_a, id_b = ids[0], ids[1]
        records: Dict[str, Dict[str, Any]] = {}
        errors: Dict[str, str] = {}
        for nid in (id_a, id_b):
            try:
                records[nid] = self._fetch_and_decode(nid)
            except _SPACETRACK_ERRORS as e:
                errors[nid] = str(e)

        if errors:
            return self._package("comparison", None, {
                "error": "Could not retrieve one or more objects: "
                         + "; ".join(f"NORAD {nid}: {msg}" for nid, msg in errors.items())
            })
        rec_a, rec_b = records[id_a], records[id_b]
        skip = {"TLE_LINE1", "TLE_LINE2", "warning", "_extraction_method"}
        common_fields = sorted((set(rec_a.keys()) & set(rec_b.keys())) - skip)
        comparison = {f: {id_a: rec_a[f], id_b: rec_b[f]} for f in common_fields}
        facts: Dict[str, Any] = {"comparison": comparison}
        warnings = [w for w in (rec_a.get("warning"), rec_b.get("warning")) if w]
        if warnings:
            facts["warning"] = " ".join(warnings)
        return self._package("comparison", f"{id_a},{id_b}", facts)

    def _handle_general_dataset(self) -> Dict[str, Any]:
        return self._package("general_dataset", None, {
            "error": "This system looks up objects live from Space-Track.org rather than "
                     "a stored dataset -- there's no fixed catalogue to summarize. Ask about "
                     "a specific NORAD ID instead, e.g. 'Tell me about NORAD 25544', or use "
                     "Batch Analysis for many objects at once."
        })

    def _handle_tle(self, line1: str, line2: str) -> Dict[str, Any]:
        line1, line2 = tle_service.clean_tle_line(line1), tle_service.clean_tle_line(line2)
        is_valid, error = tle_service.validate_tle(line1, line2)
        if not is_valid:
            return self._package("tle_lookup", None, {"error": f"Invalid TLE: {error}"})

        norad_id = tle_service.extract_norad_id(line1)
        orbital_params = tle_service.extract_orbital_parameters(line1, line2)
        facts: Dict[str, Any] = {
            "NORAD_CAT_ID": norad_id, "TLE_LINE1": line1, "TLE_LINE2": line2, **orbital_params,
        }
        # Best-effort, non-fatal enrichment (name/type) from Space-Track.
        if norad_id:
            try:
                record = self.spacetrack_service.get_current_tle(norad_id)
                for key in ("OBJECT_NAME", "OBJECT_ID", "OBJECT_TYPE"):
                    if record.get(key):
                        facts[key] = record[key]
            except Exception:
                pass
        return self._package("tle_lookup", norad_id, {k: v for k, v in facts.items() if v is not None})

    # ------------------------------------------------------------------- helpers --
    def _package(self, intent: str, object_id: Optional[str], facts: Dict[str, Any]) -> Dict[str, Any]:
        response_text = self.llm_service.generate_response(intent, facts)
        return {
            "agent": "space_object_observation",
            "intent": intent,
            "object_id": object_id,
            "result": facts,
            "response": response_text,
            "source": "Live Space-Track.org query",
        }
