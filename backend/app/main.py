"""
FastAPI adapter over the agents. Deliberately thin: every request unpacks into a
call to an agent's public method; all real logic lives in app/agents and
app/services, so a future coordinator agent can reuse any agent without HTTP.

Agents:
  * Agent 1 -- ObservationAgent            POST /agent/observe
  * Agent 2 -- SpaceObjectClassificationAgent POST /agent/classify
  * Batch  -- BatchAnalysisAgent           POST /agent/batch, GET /agent/batch/events

All of them query Space-Track.org live (no local dataset, no cache) through ONE
shared SpaceTrackService, whose rate limiter keeps the whole app under
Space-Track's usage limits.

Run with:  uvicorn app.main:app --reload
Docs at:   http://127.0.0.1:8000/docs
"""
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.batch_agent import BatchAnalysisAgent
from app.agents.classification_agent import SpaceObjectClassificationAgent
from app.agents.observation_agent import ObservationAgent
from app.models.schemas import (
    BatchEvent, BatchRequest, BatchResponse, ClassifyRequest, ClassifyResponse,
    HealthResponse, ObserveRequest, ObserveResponse,
)
from app.services.classification_service import ClassificationService
from app.services.llm_service import LLMService
from app.services.spacetrack_service import SpaceTrackService
from app.utils.config import settings

app = FastAPI(
    title="Space Debris Project -- Agents 1 & 2 + Batch Analysis",
    description="Agent 1 looks up a space object live from Space-Track.org and "
                "explains its orbital data. Agent 2 classifies a TLE (pasted, or "
                "fetched live by NORAD ID) as active satellite or space debris "
                "using the trained Gradient Boosting model. Batch analysis "
                "classifies many objects (a list, or a whole fragmentation event) "
                "at once. No LLM invents data -- every number comes from "
                "Space-Track or the model.",
    version="2.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Singletons, built once at startup and reused across requests.
spacetrack_service = SpaceTrackService()
llm_service = LLMService()
classification_service = ClassificationService()

observation_agent = ObservationAgent(spacetrack_service, llm_service)
classification_agent = SpaceObjectClassificationAgent(classification_service, llm_service, spacetrack_service)
batch_agent = BatchAnalysisAgent(spacetrack_service, classification_service, llm_service)


@app.get("/agent/health", response_model=HealthResponse)
def health():
    model = classification_service.model_info()
    return HealthResponse(
        status="ok",
        spacetrack_configured=spacetrack_service.is_configured(),
        llm_mode=llm_service.mode(),
        model_ready=bool(model.get("ready")),
        model_error=model.get("error"),
        spacetrack_usage=spacetrack_service.rate_usage(),
    )


@app.post("/agent/observe", response_model=ObserveResponse)
def observe(request: ObserveRequest):
    result = observation_agent.observe(
        query=request.query,
        tle_line1=request.tle_line1,
        tle_line2=request.tle_line2,
        compare_with_norad_id=request.compare_with_norad_id,
        norad_id=request.norad_id,
    )
    return ObserveResponse(**result)


@app.post("/agent/classify", response_model=ClassifyResponse)
def classify(request: ClassifyRequest):
    result = classification_agent.classify(
        line1=request.line1, line2=request.line2, norad_id=request.norad_id,
        query=request.query, enrich=request.enrich,
    )
    return ClassifyResponse(**result)


@app.get("/agent/batch/events", response_model=List[BatchEvent])
def batch_events():
    return BatchAnalysisAgent.list_events()


@app.post("/agent/batch", response_model=BatchResponse)
def batch(request: BatchRequest):
    result = batch_agent.analyze(
        norad_ids=request.norad_ids,
        event=request.event,
        intldes=request.intldes,
        include_decayed=request.include_decayed,
        limit=request.limit,
    )
    return BatchResponse(**result)
