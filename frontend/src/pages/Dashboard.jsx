import React, { useState } from 'react'
import { observeAgent1, classifyAgent2 } from '../services/api'
import ObjectInfoCard from '../components/ObjectInfoCard'
import ClassificationCard from '../components/ClassificationCard'
import SpaceVisualization from '../components/SpaceVisualization'
import {
  noradIdFromTleLine1, objectTypeLabel, validateNoradIdInput,
} from '../services/apiHelpers'

const STEP_DEFS = [
  { key: 'info', title: 'Object information retrieved', agent: 'Agent 1' },
  { key: 'classify', title: 'Classification completed', agent: 'Agent 2' },
]

export default function Dashboard({ onNavigate }) {
  const [noradId, setNoradId] = useState('')
  const [tleLine1, setTleLine1] = useState('')
  const [tleLine2, setTleLine2] = useState('')
  const [steps, setSteps] = useState({})
  const [running, setRunning] = useState(false)

  async function analyzeObject() {
    const check = validateNoradIdInput(noradId)
    if (!check.valid) {
      setSteps({ info: { status: 'error', detail: check.error } })
      return
    }
    const id = String(parseInt(noradId.trim(), 10))
    const override = tleLine1.trim() && tleLine2.trim()
    if ((tleLine1.trim() || tleLine2.trim()) && !override) {
      setSteps({ info: { status: 'error', detail: 'To override the TLE, fill in BOTH TLE lines (or leave both empty).' } })
      return
    }
    if (override) {
      const tleId = noradIdFromTleLine1(tleLine1)
      if (tleId && tleId !== id) {
        setSteps({ info: { status: 'error', detail: `The override TLE is for NORAD ${tleId}, not ${id}. Use matching values.` } })
        return
      }
    }

    setRunning(true)
    setSteps({ info: { status: 'pending' }, classify: { status: 'pending' } })

    // Step 1 -- Agent 1: live Space-Track lookup by NORAD ID (1 request).
    let info = null
    try {
      const res = await observeAgent1({ norad_id: id })
      info = res.result
      setSteps((s) => ({ ...s, info: { status: info?.error ? 'error' : 'done', data: info, detail: info?.error } }))
    } catch (err) {
      setSteps((s) => ({ ...s, info: { status: 'error', detail: err.message } }))
    }

    // Step 2 -- Agent 2: classify the TLE Agent 1 already fetched (or the
    // override), with enrich:false -- so no second Space-Track request.
    const line1 = override ? tleLine1.trim() : info?.TLE_LINE1
    const line2 = override ? tleLine2.trim() : info?.TLE_LINE2
    if (!line1 || !line2) {
      setSteps((s) => ({
        ...s,
        classify: { status: 'error', detail: 'Skipped: Agent 1 did not return a TLE to classify.' },
      }))
      setRunning(false)
      return
    }
    setSteps((s) => ({ ...s, plot: { line1, line2 } }))
    try {
      const cls = await classifyAgent2({ line1, line2, enrich: false })
      // Catalogue facts come from Agent 1's Space-Track record.
      const merged = cls.error
        ? cls
        : {
            ...cls,
            OBJECT_NAME: cls.OBJECT_NAME || info?.OBJECT_NAME,
            warning: cls.warning || (!override ? info?.warning : undefined),
          }
      setSteps((s) => ({ ...s, classify: { status: cls.error ? 'error' : 'done', data: merged, detail: cls.error } }))
    } catch (err) {
      setSteps((s) => ({ ...s, classify: { status: 'error', detail: err.message } }))
    }
    setRunning(false)
  }

  const infoData = steps.info?.data
  const clsData = steps.classify?.data
  // Plot exactly the TLE that was classified (Agent 1's, or the override).
  const plotLine1 = steps.plot?.line1 || infoData?.TLE_LINE1
  const plotLine2 = steps.plot?.line2 || infoData?.TLE_LINE2

  return (
    <div>
      <div className="page-title">DASHBOARD</div>
      <div className="page-subtitle">Overview and cross-agent object analysis.</div>

      <div className="panel">
        <div className="info-label" style={{ marginBottom: 10 }}>Analyze Object</div>
        <div className="form-grid">
          <div className="form-field">
            <label>NORAD ID</label>
            <input
              value={noradId}
              onChange={(e) => setNoradId(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !running && analyzeObject()}
              placeholder="e.g. 25544"
            />
          </div>
          <div className="form-field">
            <label>TLE Line 1 (optional override)</label>
            <input value={tleLine1} onChange={(e) => setTleLine1(e.target.value)} placeholder="1 25544U 98067A ..." />
          </div>
          <div className="form-field">
            <label>TLE Line 2 (optional override)</label>
            <input value={tleLine2} onChange={(e) => setTleLine2(e.target.value)} placeholder="2 25544 51.6400 ..." />
          </div>
        </div>
        <button className="btn primary" onClick={analyzeObject} disabled={running}>
          {running ? 'Analyzing...' : 'Analyze Object'}
        </button>

        {Object.keys(steps).length > 0 && (
          <div className="workflow-steps" style={{ marginTop: 20 }}>
            {STEP_DEFS.filter((def) => steps[def.key]).map((def) => {
              const s = steps[def.key]
              const icon = s.status === 'done' ? '✓' : s.status === 'error' ? '!' : '…'
              return (
                <div className="workflow-step" key={def.key}>
                  <div className={`workflow-step-icon ${s.status}`}>{icon}</div>
                  <div className="workflow-step-body">
                    <div className="workflow-step-title">{def.agent}: {def.title}</div>
                    {s.detail && <div className="workflow-step-detail">{s.detail}</div>}
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {infoData && (
          <div style={{ marginTop: 16 }}>
            <ObjectInfoCard result={infoData} />
          </div>
        )}
        {clsData && (
          <div style={{ marginTop: 16 }}>
            <ClassificationCard result={clsData} />
          </div>
        )}
        {plotLine1 && plotLine2 && (
          <div style={{ marginTop: 16 }}>
            <SpaceVisualization
              tleLine1={plotLine1}
              tleLine2={plotLine2}
              noradId={noradIdFromTleLine1(plotLine1)}
              label={objectTypeLabel(clsData?.prediction || infoData?.OBJECT_TYPE)}
            />
          </div>
        )}
      </div>

      <div className="panel">
        <div className="info-label" style={{ marginBottom: 10 }}>Quick Access</div>
        <div className="quick-examples">
          <span className="quick-chip" onClick={() => onNavigate('agent1')}>Go to Agent 1</span>
          <span className="quick-chip" onClick={() => onNavigate('agent2')}>Go to Agent 2</span>
          <span className="quick-chip" onClick={() => onNavigate('batch')}>Go to Batch Analysis</span>
          <span className="quick-chip" onClick={() => onNavigate('fleet')}>Go to Fleet View</span>
        </div>
      </div>
    </div>
  )
}
