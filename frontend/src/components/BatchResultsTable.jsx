import React, { useMemo, useState } from 'react'
import { STATUS_LABELS, classKey, formatNumber } from '../services/apiHelpers'

// Sortable, filterable table of batch results. Every value shown came from
// Space-Track or the model; missing values show as "N/A".

const FILTERS = [
  { id: 'all', label: 'All', test: () => true },
  { id: 'satellite', label: 'Satellites', test: (r) => classKey(r) === 'satellite' },
  { id: 'debris', label: 'Debris', test: (r) => classKey(r) === 'debris' },
  { id: 'failed', label: 'Not classified', test: (r) => r.status !== 'classified' },
]

const COLUMNS = [
  { key: 'norad_id', label: 'NORAD', num: true },
  { key: 'object_name', label: 'Name' },
  { key: 'object_type', label: 'Catalogue type' },
  { key: 'prediction', label: 'Model prediction' },
  { key: 'confidence', label: 'Conf. %', num: true, fmt: (v) => formatNumber(v, 1) },
  { key: 'altitude_km', label: 'Alt. km', num: true, fmt: (v) => formatNumber(v, 0) },
  { key: 'inclination_deg', label: 'Incl. °', num: true, fmt: (v) => formatNumber(v, 2) },
  { key: 'eccentricity', label: 'Ecc.', num: true, fmt: (v) => formatNumber(v, 4) },
  { key: 'status', label: 'Status' },
]

function Cell({ col, row }) {
  const v = row[col.key]
  if (col.key === 'prediction') {
    if (!v) return <span className="muted">—</span>
    const k = classKey(row)
    return (
      <span className="pred-cell">
        <span className={`legend-swatch ${k}`} />
        {v}
      </span>
    )
  }
  if (col.key === 'status') {
    const label = STATUS_LABELS[v] || v
    return (
      <span title={row.error || row.warning || ''} className={v === 'classified' ? '' : 'status-bad'}>
        {label}
        {row.warning ? ' ⚠' : ''}
      </span>
    )
  }
  if (v === null || v === undefined || v === '') return <span className="muted">N/A</span>
  return col.fmt ? col.fmt(v) : String(v)
}

export default function BatchResultsTable({ rows }) {
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState({ key: null, dir: 1 })

  const counts = useMemo(
    () => Object.fromEntries(FILTERS.map((f) => [f.id, rows.filter(f.test).length])),
    [rows]
  )

  const visible = useMemo(() => {
    const f = FILTERS.find((x) => x.id === filter) || FILTERS[0]
    const q = search.trim().toLowerCase()
    let out = rows.filter(f.test)
    if (q) {
      out = out.filter((r) =>
        [r.norad_id, r.object_name, r.object_id].some((v) => v && String(v).toLowerCase().includes(q))
      )
    }
    if (sort.key) {
      const col = COLUMNS.find((c) => c.key === sort.key)
      out = [...out].sort((a, b) => {
        const va = a[sort.key]
        const vb = b[sort.key]
        if (va === null || va === undefined) return 1
        if (vb === null || vb === undefined) return -1
        if (col?.num) return (Number(va) - Number(vb)) * sort.dir
        return String(va).localeCompare(String(vb)) * sort.dir
      })
    }
    return out
  }, [rows, filter, search, sort])

  function toggleSort(key) {
    setSort((s) => (s.key === key ? { key, dir: -s.dir } : { key, dir: 1 }))
  }

  return (
    <div>
      <div className="table-toolbar">
        <div className="quick-examples" style={{ margin: 0 }}>
          {FILTERS.map((f) => (
            <span
              key={f.id}
              className={`quick-chip ${filter === f.id ? 'active' : ''}`}
              onClick={() => setFilter(f.id)}
            >
              {f.label} ({counts[f.id]})
            </span>
          ))}
        </div>
        <input
          className="search-input"
          placeholder="Search name, NORAD or designator"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="table-wrap" style={{ maxHeight: 520 }}>
        <table className="data-table">
          <thead>
            <tr>
              {COLUMNS.map((c) => (
                <th key={c.key} onClick={() => toggleSort(c.key)} className="sortable">
                  {c.label}
                  {sort.key === c.key ? (sort.dir === 1 ? ' ▲' : ' ▼') : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((r) => (
              <tr key={r.norad_id} className={r.status !== 'classified' ? 'invalid-row' : ''}>
                {COLUMNS.map((c) => (
                  <td key={c.key}>
                    <Cell col={c} row={r} />
                  </td>
                ))}
              </tr>
            ))}
            {visible.length === 0 && (
              <tr>
                <td colSpan={COLUMNS.length} className="muted">No objects match this filter.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="chat-meta" style={{ marginTop: 6 }}>
        Hover a status for the reason an object wasn't classified. ⚠ = decayed (re-entered) object.
      </div>
    </div>
  )
}
