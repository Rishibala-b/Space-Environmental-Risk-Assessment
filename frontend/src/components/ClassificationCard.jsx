import React from 'react'
import { formatNumber } from '../services/apiHelpers'

export default function ClassificationCard({ result }) {
  if (!result) return null

  if (result.error) {
    return <div className="notice err">{result.error}</div>
  }

  const isDebris = result.label === 1
  const isSatellite = result.label === 0
  const variant = isDebris ? 'debris' : isSatellite ? 'satellite' : ''

  return (
    <div>
      {result.warning && <div className="notice warn" style={{ marginBottom: 12 }}>{result.warning}</div>}

      {result.prediction && (
        <div className={`classification-result ${variant}`}>
          <div className="classification-label">Classification</div>
          <div className="classification-value">{result.prediction}</div>
          {result.confidence !== null && result.confidence !== undefined && (
            <div className="classification-confidence">Confidence: {formatNumber(result.confidence, 2)}%</div>
          )}
        </div>
      )}

      {result.probabilities && (
        <div style={{ marginTop: 16 }}>
          <div className="prob-bar-row">
            <div className="prob-bar-label">Satellite</div>
            <div className="prob-bar-track">
              <div className="prob-bar-fill satellite" style={{ width: `${result.probabilities.satellite ?? 0}%` }} />
            </div>
            <div className="prob-bar-pct">{formatNumber(result.probabilities.satellite, 1)}%</div>
          </div>
          <div className="prob-bar-row">
            <div className="prob-bar-label">Debris</div>
            <div className="prob-bar-track">
              <div className="prob-bar-fill debris" style={{ width: `${result.probabilities.debris ?? 0}%` }} />
            </div>
            <div className="prob-bar-pct">{formatNumber(result.probabilities.debris, 1)}%</div>
          </div>
        </div>
      )}

      {result.features && (
        <div style={{ marginTop: 20 }}>
          <div className="info-label" style={{ marginBottom: 8 }}>Extracted Orbital Features</div>
          <div className="info-grid">
            {Object.entries(result.features)
              .filter(([, v]) => v !== null && v !== undefined)
              .map(([key, value]) => (
                <div className="info-field" key={key}>
                  <div className="info-label">{key.replace(/_/g, ' ')}</div>
                  <div className="info-value">{typeof value === 'number' ? formatNumber(value, 4) : String(value)}</div>
                </div>
              ))}
          </div>
        </div>
      )}

      {result.model && (
        <div className="chat-meta" style={{ marginTop: 12 }}>
          Model: {result.model}
          {result.OBJECT_NAME ? ` • ${result.OBJECT_NAME}` : ''}
        </div>
      )}
    </div>
  )
}
