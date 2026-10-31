# Space Debris Intelligence System -- Frontend

React/Vite UI for the backend's Agent 1 (Observation), Agent 2 (Classification) and Batch Analysis.

## Pages

| Sidebar item | What it does |
|---|---|
| **Dashboard** | One NORAD ID -> Agent 1 (live lookup) -> Agent 2 (classification) -> 3D orbit. Agent 2 reuses Agent 1's TLE, so the whole flow is ONE Space-Track request. |
| **Agent 1 — Object Information** | Chat. Ask about a NORAD ID, a parameter, a comparison, or paste a TLE. One shared 3D globe below the chat; pick any answer with "Show this orbit on the globe". |
| **Agent 2 — Classification** | Chat. Classify by NORAD ID or pasted TLE. |
| **Batch Analysis** | Classify many objects at once: a NORAD ID list, a preset fragmentation event (Cosmos 2251, Iridium 33, Fengyun-1C, Cosmos 1408), or any launch designator. Summary tiles, sortable/filterable table, CSV download. |
| **Fleet View** | The latest batch on one 3D globe, colour-coded (satellites = blue circles, debris = orange diamonds, not classified = grey rings), with category toggles, orbit-path toggle and click-for-details. Plus a 2D altitude-vs-inclination chart that also works without WebGL. |

Batch Analysis and Fleet View share the same result -- switching between them never re-queries Space-Track.

## Install & run

```bash
npm install
copy .env.example .env      # macOS/Linux: cp .env.example .env
npm run dev
```
Opens at `http://localhost:5173`. Start the backend first (`uvicorn app.main:app --reload` in the backend folder).

The header shows a warning if the backend reports missing Space-Track credentials or an unloaded model.

## 3D globe notes

- CesiumJS and satellite.js are loaded from CDN at runtime (`src/services/cesium.js`), once per page.
- No Cesium Ion base layer is used (no Ion token needed); imagery is OpenStreetMap.
- If WebGL is unavailable (common on VMs / remote desktops), a fallback panel explains why and shows the key orbit facts; in Fleet View the 2D chart still works.
- Single-object view: one orbital period from the TLE epoch. Fleet view: every object propagated from *now*, so they share one clock. Decayed objects are not drawn.

## Project structure

```
src/
├── services/
│   ├── api.js               Axios calls: observe, classify, batch, batch events, health
│   ├── apiHelpers.js        Pure functions: routing, NORAD parsing, validation, colours, CSV
│   └── cesium.js            Shared Cesium/satellite.js loader, WebGL check, viewer factory, SGP4 helpers
├── context/
│   └── AgentSessionContext.jsx   Per-agent messages + shared batch state (in memory only)
├── components/
│   ├── Header, Sidebar, ChatInput, ChatMessage, StatusIndicator
│   ├── ObjectInfoCard, ClassificationCard
│   ├── SpaceVisualization.jsx    One-object 3D orbit
│   ├── FleetVisualization.jsx    Many-object 3D fleet view
│   ├── AltitudeInclinationChart.jsx  2D fleet map (SVG)
│   ├── BatchForm.jsx, BatchSummary.jsx, BatchResultsTable.jsx
├── pages/
│   ├── Dashboard.jsx, Agent1.jsx, Agent2.jsx
│   ├── BatchAnalysis.jsx
│   └── FleetView.jsx
├── App.jsx                  Layout shell, page routing, health polling
└── main.jsx
```

## Testing the pure logic (no browser needed)

```bash
node --input-type=module -e "import('./src/services/apiHelpers.js').then(h => { console.log(h.routeGlobalQuery('Is NORAD 119 debris?')); console.log(h.parseNoradList('25544, 20580 x')) })"
```

## Manual test checklist

1. `GET http://127.0.0.1:8000/agent/health` shows `spacetrack_configured: true` and `model_ready: true`.
2. Dashboard: analyze `25544` -> both steps succeed, 3D label turns to "Satellite" when the classification arrives.
3. Header search: "classify 25544" opens Agent 2 once; navigate away and back -- it is **not** sent again.
4. Batch Analysis -> Fragmentation event -> Cosmos 2251 -> Run. Check the summary shows 1 Space-Track request.
5. Open in Fleet View: toggle Debris off/on, toggle orbit paths, click an object for its details.
