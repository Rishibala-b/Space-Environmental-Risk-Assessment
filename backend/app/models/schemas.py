"""
Request/response contracts for the API. FastAPI uses these to validate incoming
requests and to document the API (visit /docs once the server is running).

Error convention: agent-level problems (unknown NORAD ID, invalid TLE, Space-Track
unavailable, model missing) are returned with HTTP 200 and an explicit `error`
field, because they are the agent's answer to a well-formed request. Malformed
requests (wrong types) get FastAPI's normal 422.
"""
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


# ----------------------------------------------------------------- Agent 1 --
class ObserveRequest(BaseModel):
    query: Optional[str] = Field(
        default=None, description="Natural-language question, e.g. 'Tell me about NORAD 25544'."
    )
    norad_id: Optional[Union[int, str]] = Field(
        default=None, description="NORAD catalog ID. Looked up directly -- no language parsing needed."
    )
    tle_line1: Optional[str] = Field(default=None, description="Raw TLE line 1, if sending a TLE directly.")
    tle_line2: Optional[str] = Field(default=None, description="Raw TLE line 2, if sending a TLE directly.")
    compare_with_norad_id: Optional[Union[int, str]] = Field(
        default=None, description="Second NORAD ID for a two-object comparison."
    )


class ObserveResponse(BaseModel):
    agent: str = "space_object_observation"
    intent: str
    object_id: Optional[str] = None
    # Includes TLE_LINE1/TLE_LINE2 when available (for the 3D plot), and a
    # `warning` when Space-Track lists the object as decayed.
    result: Dict[str, Any]
    response: str
    source: str


# ----------------------------------------------------------------- Agent 2 --
class ClassifyRequest(BaseModel):
    line1: Optional[str] = Field(default=None, description="TLE line 1.")
    line2: Optional[str] = Field(default=None, description="TLE line 2.")
    norad_id: Optional[int] = Field(
        default=None, description="NORAD catalog ID -- fetches the current TLE live from Space-Track."
    )
    query: Optional[str] = Field(
        default=None, description="Optional natural-language request, e.g. 'Is NORAD 25544 satellite or debris?'"
    )
    enrich: bool = Field(
        default=True,
        description="For a pasted TLE, also look up the object's name/type on Space-Track. "
                    "Set false when the caller already has that record (saves a request).",
    )


class ClassifyResponse(BaseModel):
    agent: str = "space_object_classification"
    object_id: Optional[str] = None
    prediction: Optional[str] = None
    label: Optional[int] = None
    confidence: Optional[float] = None
    probabilities: Optional[Dict[str, float]] = None
    features: Optional[Dict[str, Any]] = None
    model: Optional[str] = None
    OBJECT_NAME: Optional[str] = None
    OBJECT_ID: Optional[str] = None
    OBJECT_TYPE: Optional[str] = None
    EPOCH: Optional[str] = None
    TLE_LINE1: Optional[str] = None
    TLE_LINE2: Optional[str] = None
    warning: Optional[str] = None
    response: str
    error: Optional[str] = None


# ------------------------------------------------------------------- Batch --
class BatchRequest(BaseModel):
    norad_ids: Optional[Union[List[Union[int, str]], str]] = Field(
        default=None,
        description="List of NORAD IDs, or one string of IDs separated by commas/spaces/newlines.",
    )
    event: Optional[str] = Field(
        default=None, description="Preset event key, e.g. 'cosmos-2251' (see GET /agent/batch/events)."
    )
    intldes: Optional[str] = Field(
        default=None, description="International designator prefix, e.g. '1993-036' (all objects from that launch)."
    )
    include_decayed: bool = Field(
        default=False, description="Event/launch queries: include objects that have already re-entered."
    )
    limit: Optional[int] = Field(default=None, ge=1, description="Max objects to analyze (capped by BATCH_MAX_OBJECTS).")


class BatchObject(BaseModel):
    norad_id: str
    status: str
    error: Optional[str] = None
    warning: Optional[str] = None
    object_name: Optional[str] = None
    object_id: Optional[str] = None
    object_type: Optional[str] = None
    epoch: Optional[str] = None
    decay_date: Optional[str] = None
    prediction: Optional[str] = None
    label: Optional[int] = None
    confidence: Optional[float] = None
    probabilities: Optional[Dict[str, float]] = None
    altitude_km: Optional[float] = None
    inclination_deg: Optional[float] = None
    eccentricity: Optional[float] = None
    orbital_period_min: Optional[float] = None
    TLE_LINE1: Optional[str] = None
    TLE_LINE2: Optional[str] = None


class BatchResponse(BaseModel):
    agent: str = "batch_analysis"
    summary: Optional[Dict[str, Any]] = None
    objects: List[BatchObject] = []
    response: str
    source: str
    error: Optional[str] = None


class BatchEvent(BaseModel):
    key: str
    label: str
    intldes: str
    description: str


# ------------------------------------------------------------------ Health --
class HealthResponse(BaseModel):
    status: str
    spacetrack_configured: bool
    llm_mode: str
    model_ready: bool
    model_error: Optional[str] = None
    spacetrack_usage: Optional[Dict[str, int]] = None
