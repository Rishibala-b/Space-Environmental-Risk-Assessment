import React from 'react'
import BatchForm from '../components/BatchForm'
import FleetVisualization from '../components/FleetVisualization'
import AltitudeInclinationChart from '../components/AltitudeInclinationChart'
import { useAgentSession } from '../context/AgentSessionContext'

// Fleet View: the most recent batch result on the 3D globe (colour-coded by
// classification) plus a 2D altitude-vs-inclination map. Uses the same batch
// result as the Batch Analysis page -- switching pages never re-queries
// Space-Track.

export default function FleetView({ onNavigate }) {
  const { batch, runBatch } = useAgentSession()
  const { result, loading, error } = batch
  const rows = result?.objects || []
  const summary = result?.summary

  return (
    <div>
      <div className="page-title">FLEET VIEW</div>
      <div className="page-subtitle">
        Many objects on one globe, colour-coded by the model's classification: satellites as circles,
        debris as diamonds.
      </div>

      {!summary && (
        <div className="panel">
          <div className="notice" style={{ marginBottom: 16 }}>
            No batch results yet. Run a batch here, or on the{' '}
            <span className="link" onClick={() => onNavigate('batch')}>Batch Analysis</span> page.
          </div>
          <BatchForm onRun={runBatch} loading={loading} />
        </div>
      )}

      {loading && (
        <div className="panel">
          <div className="chat-loading">Querying Space-Track and classifying...</div>
        </div>
      )}
      {error && !loading && <div className="notice err" style={{ marginBottom: 20 }}>{error}</div>}

      {summary && !loading && (
        <>
          <div className="panel">
            <div className="panel-head">
              <div>
                <div className="info-label" style={{ margin: 0 }}>{summary.label}</div>
                <div className="chat-meta">
                  {summary.counts.satellite} satellite · {summary.counts.debris} debris · {summary.counts.failed} not
                  classified
                </div>
              </div>
              <div className="panel-actions">
                <button className="btn small" onClick={() => onNavigate('batch')}>
                  Table &amp; new batch
                </button>
              </div>
            </div>
            <FleetVisualization objects={rows} />
          </div>

          <div className="panel">
            <div className="info-label" style={{ marginBottom: 4 }}>Altitude vs inclination</div>
            <div className="chat-meta" style={{ marginBottom: 12 }}>
              Where each object sits in orbit-space. Fragments from one event spread along a band around their
              parent's inclination.
            </div>
            <AltitudeInclinationChart objects={rows} />
          </div>
        </>
      )}
    </div>
  )
}
