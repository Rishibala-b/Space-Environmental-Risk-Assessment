import React from 'react'
import { formatNumber } from '../services/apiHelpers'

const ORBITAL_KEYS = new Set([
  'inclination_deg', 'eccentricity', 'raan_deg', 'arg_perigee_deg', 'mean_anomaly_deg',
  'true_anomaly_deg', 'mean_motion_rev_per_day', 'semi_major_axis_km', 'altitude_km',
  'orbital_velocity_km_s', 'orbital_period_min', 'specific_orbital_energy_km2_s2',
])
const OBJECT_KEYS = new Set([
  'NORAD_CAT_ID', 'OBJECT_NAME', 'OBJECT_ID', 'OBJECT_TYPE', 'EPOCH', 'DECAY_DATE', 'label', 'Label',
])
const TLE_KEYS = ['TLE_LINE1', 'TLE_LINE2']
const HIDDEN_KEYS = new Set(['warning', 'error'])

const PRETTY = {
  OBJECT_ID: 'Intl. Designator',
  EPOCH: 'TLE Epoch',
  altitude_km: 'Mean Altitude Km',
  orbital_velocity_km_s: 'Circular Velocity Km S',
}

function prettyKey(key) {
  return PRETTY[key] || key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatValue(value) {
  if (typeof value === 'number') return formatNumber(value, 4)
  if (Array.isArray(value)) return value.join(', ')
  return String(value)
}

function InfoSection({ title, fields }) {
  if (fields.length === 0) return null
  return (
    <div style={{ marginBottom: 16 }}>
      <div className="info-label" style={{ marginBottom: 8 }}>{title}</div>
      <div className="info-grid">
        {fields.map(([key, value]) => (
          <div className="info-field" key={key}>
            <div className="info-label">{prettyKey(key)}</div>
            <div className="info-value">{formatValue(value)}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function ObjectInfoCard({ result }) {
  if (!result) return null

  if (result.error) {
    return (
      <div className="notice err">
        {result.error}
        {Array.isArray(result.available_parameters) && result.available_parameters.length > 0 && (
          <div style={{ marginTop: 6, color: 'var(--text-1)' }}>
            Available: {result.available_parameters.join(', ')}
          </div>
        )}
      </div>
    )
  }

  const warning = result.warning ? <div className="notice warn" style={{ marginBottom: 12 }}>{result.warning}</div> : null

  if (result.comparison) {
    const fields = Object.keys(result.comparison)
    const ids = fields.length > 0 ? Object.keys(result.comparison[fields[0]]) : []
    return (
      <div>
        {warning}
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Field</th>
                {ids.map((id) => (
                  <th key={id}>NORAD {id}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {fields.map((field) => (
                <tr key={field}>
                  <td>{prettyKey(field)}</td>
                  {ids.map((id) => (
                    <td key={id}>{formatValue(result.comparison[field][id])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  const entries = Object.entries(result).filter(
    ([k, v]) => !k.startsWith('_') && v !== null && v !== undefined && !TLE_KEYS.includes(k) && !HIDDEN_KEYS.has(k)
  )
  const objectFields = entries.filter(([k]) => OBJECT_KEYS.has(k))
  const orbitalFields = entries.filter(([k]) => ORBITAL_KEYS.has(k))
  const otherFields = entries.filter(([k]) => !OBJECT_KEYS.has(k) && !ORBITAL_KEYS.has(k))
  const hasTle = TLE_KEYS.every((k) => result[k])

  return (
    <div>
      {warning}
      <InfoSection title="Object Information" fields={objectFields} />
      <InfoSection title="Orbital Information" fields={orbitalFields} />
      <InfoSection title="Other Information" fields={otherFields} />
      {hasTle && (
        <div>
          <div className="info-label" style={{ marginBottom: 8 }}>TLE</div>
          <div className="tle-block">
            {result.TLE_LINE1}
            {'\n'}
            {result.TLE_LINE2}
          </div>
        </div>
      )}
      {entries.length === 0 && !hasTle && (
        <div className="notice">No structured fields were returned for this request.</div>
      )}
    </div>
  )
}
