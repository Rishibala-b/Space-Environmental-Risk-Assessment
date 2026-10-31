"""
BatchAnalysisAgent: batch / fleet analysis.

Classifies many objects in one request, from either
  * a list of NORAD IDs, or
  * a launch / fragmentation event, identified by its international designator
    prefix (e.g. "1993-036" = Cosmos 2251 plus every catalogued piece from that
    launch, including collision fragments), or one of the presets in EVENTS.

Engineering, not a bigger loop:
  * Few requests: IDs are sent to Space-Track comma-separated in chunks
    (BATCH_IDS_PER_REQUEST, default 100), so 500 objects = 5 requests. An event
    query is a single request.
  * Concurrency: chunks are fetched in parallel (BATCH_MAX_WORKERS), and every
    request still goes through SpaceTrackService's shared rate limiter, so a
    batch can never push the account over Space-Track's limits.
  * One model call: every valid TLE is classified in a single predict_many().
  * Partial failures: every object gets its own `status`. A failed chunk, a
    missing ID, a malformed TLE or a missing model marks only the affected rows;
    everything else is still returned. No value is ever guessed.

Still live, still no local dataset or cache.
"""
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from app.agents.classification_agent import model_features
from app.services import tle_service
from app.services.classification_service import (
    MODEL_DISPLAY_NAME, ClassificationService,
)
from app.services.llm_service import LLMService
from app.services.spacetrack_service import (
    SpaceTrackAuthError, SpaceTrackQueryError, SpaceTrackService, decay_warning,
)
from app.utils.config import settings

# Row statuses
CLASSIFIED = "classified"
NOT_FOUND = "not_found"
INVALID_INPUT = "invalid_input"
INVALID_TLE = "invalid_tle"
FETCH_ERROR = "fetch_error"
MODEL_ERROR = "model_error"

# Well-known fragmentation events. `intldes` is the launch's international
# designator prefix; the query returns every catalogued object from that launch
# (parent, co-launched payloads, rocket bodies, fragments).
EVENTS: Dict[str, Dict[str, str]] = {
    "cosmos-2251": {
        "label": "Cosmos 2251 (2009 collision with Iridium 33)",
        "intldes": "1993-036",
        "description": "Russian satellite destroyed in the first accidental hypervelocity "
                       "collision between two intact satellites (10 Feb 2009).",
    },
    "iridium-33": {
        "label": "Iridium 33 launch (2009 collision with Cosmos 2251)",
        "intldes": "1997-051",
        "description": "Iridium 33 fragments plus the other Iridium satellites and "
                       "hardware from the same 1997 launch.",
    },
    "fengyun-1c": {
        "label": "Fengyun-1C (2007 anti-satellite test)",
        "intldes": "1999-025",
        "description": "Chinese weather satellite destroyed by an ASAT test "
                       "(11 Jan 2007) -- the largest debris-generating event on record.",
    },
    "cosmos-1408": {
        "label": "Cosmos 1408 (2021 anti-satellite test)",
        "intldes": "1982-092",
        "description": "Soviet satellite destroyed by a Russian ASAT test (15 Nov 2021). "
                       "Most fragments have since re-entered -- tick 'include decayed' to see them.",
    },
}

_TOKEN_SPLIT_RE = re.compile(r"[\s,;]+")


def parse_norad_list(value: Any) -> Tuple[List[str], List[str]]:
    """Accepts a list (ints/strings) or a string of IDs separated by commas,
    spaces, semicolons or newlines. Returns (valid_ids_in_order, invalid_tokens)."""
    if value is None:
        return [], []
    tokens: List[str] = []
    if isinstance(value, (list, tuple)):
        for item in value:
            tokens.extend(t for t in _TOKEN_SPLIT_RE.split(str(item)) if t)
    else:
        tokens = [t for t in _TOKEN_SPLIT_RE.split(str(value)) if t]

    valid: List[str] = []
    invalid: List[str] = []
    for tok in tokens:
        t = tok.strip()
        if t.isdigit() and int(t) > 0:
            norm = str(int(t))
            if norm not in valid:
                valid.append(norm)
        elif t:
            if t not in invalid:
                invalid.append(t)
    return valid, invalid


class BatchAnalysisAgent:
    def __init__(self, spacetrack_service: SpaceTrackService,
                 classification_service: ClassificationService, llm_service: LLMService,
                 max_objects: Optional[int] = None, ids_per_request: Optional[int] = None,
                 max_workers: Optional[int] = None):
        self.spacetrack_service = spacetrack_service
        self.classification_service = classification_service
        self.llm_service = llm_service
        self.max_objects = max_objects or settings.batch_max_objects
        self.ids_per_request = max(1, ids_per_request or settings.batch_ids_per_request)
        self.max_workers = max(1, max_workers or settings.batch_max_workers)

    @staticmethod
    def list_events() -> List[Dict[str, str]]:
        return [{"key": k, **v} for k, v in EVENTS.items()]

    # ---------------------------------------------------------------- public API --
    def analyze(self, norad_ids: Any = None, event: Optional[str] = None,
                intldes: Optional[str] = None, include_decayed: bool = False,
                limit: Optional[int] = None) -> Dict[str, Any]:
        started = time.monotonic()
        limit = max(1, min(int(limit or self.max_objects), self.max_objects))

        mode, label = None, None
        if event:
            key = str(event).strip().lower()
            if key not in EVENTS:
                return self._error(f"Unknown event '{event}'. Known events: {', '.join(EVENTS)}.")
            intldes, label, mode = EVENTS[key]["intldes"], EVENTS[key]["label"], "event"
        elif intldes:
            mode, label = "event", f"Launch {str(intldes).strip().upper()}"
        elif norad_ids:
            mode = "ids"
        else:
            return self._error("Provide a list of NORAD IDs, an event key, or an international designator.")

        if mode == "ids":
            rows, requests_made, truncated, requested = self._rows_from_ids(norad_ids, limit)
            label = f"{requested} requested NORAD ID(s)"
        else:
            try:
                rows, requests_made, truncated = self._rows_from_launch(intldes, include_decayed, limit)
            except (SpaceTrackAuthError, SpaceTrackQueryError) as e:
                return self._error(f"Could not retrieve objects for {label}: {e}")
            requested = len(rows)

        self._classify_rows(rows)

        summary = self._summarize(rows, requested, truncated, limit, requests_made,
                                  include_decayed, mode, label, intldes, started)
        return {
            "agent": "batch_analysis",
            "summary": summary,
            "objects": rows,
            "response": self.llm_service.generate_response("batch_summary", summary),
            "source": "Live Space-Track.org query",
        }

    # ------------------------------------------------------------------ fetching --
    def _rows_from_ids(self, norad_ids: Any, limit: int):
        valid, invalid = parse_norad_list(norad_ids)
        requested = len(valid) + len(invalid)
        truncated = len(valid) > limit
        valid = valid[:limit]

        rows: Dict[str, Dict[str, Any]] = {nid: {"norad_id": nid} for nid in valid}
        chunks = [valid[i:i + self.ids_per_request] for i in range(0, len(valid), self.ids_per_request)]

        def fetch(chunk: List[str]):
            try:
                return chunk, self.spacetrack_service.get_tles_for_ids(chunk), None
            except Exception as e:  # partial failure: only this chunk's rows are affected
                return chunk, {}, str(e)

        if chunks:
            with ThreadPoolExecutor(max_workers=min(self.max_workers, len(chunks))) as pool:
                for chunk, records, err in pool.map(fetch, chunks):
                    for nid in chunk:
                        if err:
                            rows[nid].update(status=FETCH_ERROR, error=f"Space-Track request failed: {err}")
                        elif nid in records:
                            rows[nid].update(self._record_fields(records[nid]))
                        else:
                            rows[nid].update(status=NOT_FOUND,
                                             error=f"NORAD ID {nid} does not exist on Space-Track.org (or has no current TLE).")

        ordered = [rows[nid] for nid in valid]
        ordered += [{"norad_id": tok, "status": INVALID_INPUT, "error": f"'{tok}' is not a valid NORAD ID."}
                    for tok in invalid]
        return ordered, len(chunks), truncated, requested

    def _rows_from_launch(self, intldes: str, include_decayed: bool, limit: int):
        # Ask for one extra record so we can tell the user if results were truncated.
        records = self.spacetrack_service.get_tles_for_launch(intldes, include_decayed, limit + 1)
        truncated = len(records) > limit
        rows = []
        for rec in records[:limit]:
            nid = str(int(rec["NORAD_CAT_ID"])) if rec.get("NORAD_CAT_ID") is not None else None
            if nid is None:
                continue
            rows.append({"norad_id": nid, **self._record_fields(rec)})
        return rows, 1, truncated

    @staticmethod
    def _record_fields(rec: Dict[str, Any]) -> Dict[str, Any]:
        fields = {
            "status": "fetched",
            "object_name": rec.get("OBJECT_NAME"),
            "object_id": rec.get("OBJECT_ID"),
            "object_type": rec.get("OBJECT_TYPE"),
            "epoch": rec.get("EPOCH"),
            "decay_date": rec.get("DECAY_DATE"),
            "TLE_LINE1": tle_service.clean_tle_line(rec.get("TLE_LINE1")) or None,
            "TLE_LINE2": tle_service.clean_tle_line(rec.get("TLE_LINE2")) or None,
        }
        warning = decay_warning(rec)
        if warning:
            fields["warning"] = warning
        return fields

    # -------------------------------------------------------------- classifying --
    def _classify_rows(self, rows: List[Dict[str, Any]]) -> None:
        pending: List[Tuple[Dict[str, Any], Dict[str, float]]] = []
        for row in rows:
            if row.get("status") != "fetched":
                continue
            l1, l2 = row.get("TLE_LINE1"), row.get("TLE_LINE2")
            if not (l1 and l2):
                row.update(status=INVALID_TLE, error="Space-Track record has no TLE lines.")
                continue
            ok, err = tle_service.validate_tle(l1, l2)
            if not ok:
                row.update(status=INVALID_TLE, error=f"Invalid TLE: {err}")
                continue
            try:
                params = tle_service.extract_orbital_parameters(l1, l2)
            except Exception as e:
                row.update(status=INVALID_TLE, error=f"Could not extract orbital features: {e}")
                continue
            row.update({
                "altitude_km": params["altitude_km"],
                "inclination_deg": params["inclination_deg"],
                "eccentricity": params["eccentricity"],
                "orbital_period_min": params["orbital_period_min"],
            })
            pending.append((row, model_features(params)))

        if not pending:
            return
        try:
            predictions = self.classification_service.predict_many([f for _, f in pending])
        except Exception as e:
            for row, _ in pending:
                row.update(status=MODEL_ERROR, error=str(e))
            return
        for (row, _), pred in zip(pending, predictions):
            row.update(pred)
            row["status"] = CLASSIFIED

    # ------------------------------------------------------------------ summary --
    @staticmethod
    def _summarize(rows, requested, truncated, limit, requests_made, include_decayed,
                   mode, label, intldes, started) -> Dict[str, Any]:
        classified = [r for r in rows if r.get("status") == CLASSIFIED]
        by_status: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        for r in rows:
            by_status[r.get("status", "unknown")] = by_status.get(r.get("status", "unknown"), 0) + 1
            if r.get("object_type"):
                by_type[r["object_type"]] = by_type.get(r["object_type"], 0) + 1
        return {
            "mode": mode,
            "label": label,
            "intldes": intldes,
            "include_decayed": include_decayed,
            "requested": requested,
            "returned": len(rows),
            "limit": limit,
            "truncated": truncated,
            "counts": {
                "satellite": sum(1 for r in classified if r.get("label") == 0),
                "debris": sum(1 for r in classified if r.get("label") == 1),
                "failed": len(rows) - len(classified),
            },
            "by_status": by_status,
            "by_catalog_type": by_type,
            "decayed": sum(1 for r in rows if r.get("decay_date")),
            "spacetrack_requests": requests_made,
            "model": MODEL_DISPLAY_NAME,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }

    def _error(self, message: str) -> Dict[str, Any]:
        return {
            "agent": "batch_analysis",
            "summary": None,
            "objects": [],
            "response": message,
            "error": message,
            "source": "Live Space-Track.org query",
        }
