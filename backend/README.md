# Space Debris Project -- Backend (Agent 1, Agent 2, Batch Analysis)

Every agent queries Space-Track.org **live** -- there is no local dataset and no cache.

- **Agent 1 (Observation)** -- looks up an object by NORAD ID (or decodes a pasted TLE) and explains its orbital data.
- **Agent 2 (Classification)** -- classifies an object as *active satellite* or *space debris* with the trained Gradient Boosting model.
- **Batch Analysis** -- classifies many objects at once: a list of NORAD IDs, or a whole launch / fragmentation event (e.g. Cosmos 2251 and all its fragments). Feeds the frontend's Fleet View.

## Setup

```bash
python -m venv venv
venv\Scripts\activate            # Windows   (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env           # macOS/Linux: cp .env.example .env
```

Edit `.env` (never `.env.example` -- that file is meant to be shared and must stay blank):
- `SPACETRACK_USERNAME` / `SPACETRACK_PASSWORD` -- **required**.
- `CLASSIFICATION_MODEL_PATH` -- defaults to `./data/gradient_boosting_model.pkl`.
- `LLM_PROVIDER=none` runs everything on the rule-based fallback, no key needed.

`scikit-learn` is pinned to **1.6.1** because that is the version the model was saved with.

## Run

```bash
uvicorn app.main:app --reload
```
Docs: `http://127.0.0.1:8000/docs`

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/agent/health` | Space-Track configured?, LLM mode, model loaded?, current Space-Track request usage |
| POST | `/agent/observe` | Agent 1 -- `{"norad_id": 25544}`, `{"query": "..."}`, or `{"tle_line1": "...", "tle_line2": "..."}` |
| POST | `/agent/classify` | Agent 2 -- `{"norad_id": 25544}`, `{"line1": "...", "line2": "...", "enrich": false}`, or `{"query": "..."}` |
| GET | `/agent/batch/events` | Preset fragmentation events |
| POST | `/agent/batch` | Batch -- `{"norad_ids": [25544, 47960]}`, `{"event": "cosmos-2251"}`, or `{"intldes": "1993-036", "include_decayed": false, "limit": 200}` |

Agent-level problems (unknown ID, invalid TLE, Space-Track down, model missing) come back as HTTP 200 with an `error` field; malformed requests get 422.

## Space-Track usage policy (enforced in code)

Space-Track allows fewer than 30 requests/minute and 300/hour, and asks that the same TLEs not be re-downloaded more than about once an hour. With no cache, this app protects the account by:

- **One shared rate limiter** (default 25/min, 280/hour) in front of every request from every agent. If no slot frees within `SPACETRACK_MAX_WAIT_SECONDS`, the request fails fast with a clear message.
- **Batching**: up to 100 NORAD IDs per request, so a 500-object batch is 5 requests; an event query is 1 request.
- **No duplicate calls**: the Dashboard passes Agent 1's TLE to Agent 2 (`enrich: false`).
- **Session handling**: expired sessions (~2 h idle) are re-authenticated automatically once; a failed login is detected from Space-Track's real `{"Login":"Failed"}` response.

If the demo will be used heavily, a short-lived in-memory cache (e.g. 1 hour per NORAD ID) is the next step -- that is a deliberate change to the no-local-data rule and should be agreed first.

## What the features are

11 features per TLE, in this exact order (checked against the model's `feature_names_in_`):

- **From the TLE** (read with the `sgp4` library's TLE parser -- no propagation): inclination, eccentricity, RAAN, argument of perigee, mean anomaly, mean motion.
- **Derived from mean motion with two-body relations**: semi-major axis, mean altitude, circular orbital velocity, orbital period, specific orbital energy.

## Project structure

```
app/
├── main.py                          FastAPI endpoints
├── agents/
│   ├── observation_agent.py         Agent 1
│   ├── classification_agent.py      Agent 2
│   └── batch_agent.py               Batch / fleet analysis
├── services/
│   ├── spacetrack_service.py        ALL Space-Track I/O + rate limiter + re-login
│   ├── tle_service.py               TLE cleaning, validation, NORAD-ID parsing, features (pure)
│   ├── classification_service.py    Loads the .pkl, single + batch prediction
│   └── llm_service.py               Query understanding + response phrasing only
├── models/schemas.py                Request/response contracts
└── utils/config.py                  Every env var, in one place
data/                                gradient_boosting_model.pkl (nothing else)
tests/
├── fakes.py                         Shared fake Space-Track session, mock models, no-LLM helper
├── test_agent.py                    Agent 1 (15 tests)
├── test_classification_agent.py     Agent 2 (17 tests)
├── test_spacetrack_service.py       Login, re-login, 429, rate limiter, multi-ID/launch queries, LLM parsing (16 tests)
└── test_batch_agent.py              Batch: chunking, partial failures, events, truncation (13 tests)
```

## Tests

```bash
python -m pytest tests/ -v
```
61 tests, fully offline: fake Space-Track session, mock models, and the LLM forced to rule-based mode -- so they never call Space-Track or Gemini/Claude, whatever your `.env` contains.
