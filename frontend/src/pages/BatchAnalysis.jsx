import React from 'react'
import BatchForm from '../components/BatchForm'
import BatchSummary from '../components/BatchSummary'
import BatchResultsTable from '../components/BatchResultsTable'
import { useAgentSession } from '../context/AgentSessionContext'
import { batchRowsToCsv } from '../services/apiHelpers'

export default function BatchAnalysis({ onNavigate }) {
  const { batch, runBatch, clearBatch } = useAgentSession()
  const { result, loading, error } = batch
  const rows = result?.objects || []

  function downloadCsv() {
    const blob = new Blob([batchRowsToCsv(rows)], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    const tag = (result?.summary?.intldes || 'ids').replace(/[^\w-]/g, '')
    a.href = url
    a.download = `batch-analysis-${tag}-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div>
      <div className="page-title">BATCH ANALYSIS</div>
      <div className="page-subtitle">
        Classify many objects at once -- a list of NORAD IDs, or every catalogued piece of a fragmentation
        event -- live from Space-Track.org.
      </div>

      <div className="panel">
        <BatchForm onRun={runBatch} loading={loading} />
      </div>

      {loading && (
        <div className="panel">
          <div className="chat-loading">
            Querying Space-Track and classifying... large events can take up to a minute.
          </div>
        </div>
      )}

      {error && !loading && <div className="notice err" style={{ marginBottom: 20 }}>{error}</div>}

      {result?.summary && !loading && (
        <div className="panel">
          <div className="panel-head">
            <div className="info-label" style={{ margin: 0 }}>Results -- {result.summary.label}</div>
            <div className="panel-actions">
              <button className="btn small primary" onClick={() => onNavigate('fleet')} disabled={!rows.length}>
                Open in Fleet View
              </button>
              <button className="btn small" onClick={downloadCsv} disabled={!rows.length}>Download CSV</button>
              <button className="btn small ghost" onClick={clearBatch}>Clear</button>
            </div>
          </div>
          <BatchSummary summary={result.summary} response={result.response} />
          <div style={{ marginTop: 16 }}>
            <BatchResultsTable rows={rows} />
          </div>
        </div>
      )}
    </div>
  )
}
