import React from 'react'

// Headline numbers for a batch run. Every value comes from the backend summary.
export default function BatchSummary({ summary, response }) {
  if (!summary) return null
  const c = summary.counts || {}
  const tiles = [
    { label: 'Objects analyzed', value: summary.returned, sub: summary.label },
    { label: 'Active satellites', value: c.satellite, cls: 'satellite' },
    { label: 'Space debris', value: c.debris, cls: 'debris' },
    { label: 'Not classified', value: c.failed, sub: 'not found, invalid, or failed' },
    {
      label: 'Space-Track requests',
      value: summary.spacetrack_requests,
      sub: `${(summary.elapsed_ms / 1000).toFixed(1)} s total`,
    },
  ]
  return (
    <div>
      <div className="stat-cards">
        {tiles.map((t) => (
          <div className={`stat-card ${t.cls ? `accent-${t.cls}` : ''}`} key={t.label}>
            <div className="info-label">{t.label}</div>
            <div className="stat-value">{t.value ?? 'N/A'}</div>
            {t.sub && <div className="stat-sub">{t.sub}</div>}
          </div>
        ))}
      </div>
      {summary.truncated && (
        <div className="notice warn" style={{ marginBottom: 12 }}>
          More objects matched than the limit of {summary.limit}; only the first {summary.limit} were analyzed.
          Raise "Max objects" (up to the backend's BATCH_MAX_OBJECTS) to include more.
        </div>
      )}
      {summary.decayed > 0 && (
        <div className="notice warn" style={{ marginBottom: 12 }}>
          {summary.decayed} object(s) have already re-entered; they are classified from their last TLE and
          are not drawn in Fleet View.
        </div>
      )}
      {response && <div className="batch-response">{response}</div>}
    </div>
  )
}
