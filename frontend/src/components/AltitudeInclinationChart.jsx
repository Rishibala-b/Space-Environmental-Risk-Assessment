import React, { useMemo, useState } from 'react'
import { CLASS_COLORS, classKey, formatNumber } from '../services/apiHelpers'

// 2D "fleet map": mean altitude (log scale) vs inclination, one mark per object,
// coloured AND shaped by classification (circle = satellite, diamond = debris,
// ring = not classified). Plain SVG, so it works where WebGL does not.
// Hover any mark for its details.

const W = 760
const H = 340
const M = { top: 16, right: 20, bottom: 44, left: 52 }
const X_MIN = 100
const X_MAX = 50000
const X_TICKS = [200, 500, 1000, 2000, 5000, 10000, 20000, 35786]
const Y_TICKS = [0, 30, 60, 90, 120, 150, 180]

const KINDS = {
  satellite: { label: 'Active satellite', color: CLASS_COLORS.satellite },
  debris: { label: 'Space debris', color: CLASS_COLORS.debris },
  unclassified: { label: 'Not classified', color: CLASS_COLORS.unclassified },
}

const x = (alt) => {
  const a = Math.min(X_MAX, Math.max(X_MIN, alt))
  return M.left + ((Math.log10(a) - Math.log10(X_MIN)) / (Math.log10(X_MAX) - Math.log10(X_MIN))) * (W - M.left - M.right)
}
const y = (inc) => M.top + (1 - Math.min(180, Math.max(0, inc)) / 180) * (H - M.top - M.bottom)

function Mark({ kind, cx, cy }) {
  const k = KINDS[kind]
  if (kind === 'debris') {
    const r = 5
    return (
      <path
        d={`M${cx},${cy - r} L${cx + r},${cy} L${cx},${cy + r} L${cx - r},${cy} Z`}
        fill={k.color}
        stroke="var(--bg-1)"
        strokeWidth="2"
      />
    )
  }
  if (kind === 'satellite') {
    return <circle cx={cx} cy={cy} r={4.5} fill={k.color} stroke="var(--bg-1)" strokeWidth="2" />
  }
  return <circle cx={cx} cy={cy} r={3.5} fill="none" stroke={k.color} strokeWidth="2" />
}

export default function AltitudeInclinationChart({ objects }) {
  const [hover, setHover] = useState(null)

  const points = useMemo(
    () =>
      (objects || [])
        .filter((o) => o.altitude_km != null && o.inclination_deg != null)
        .map((o) => ({ row: o, kind: classKey(o), cx: x(o.altitude_km), cy: y(o.inclination_deg) })),
    [objects]
  )

  if (points.length === 0) {
    return <div className="notice">No orbital elements available to chart.</div>
  }

  const counts = points.reduce((acc, p) => ({ ...acc, [p.kind]: (acc[p.kind] || 0) + 1 }), {})

  return (
    <div className="chart-wrap">
      <div className="chart-legend">
        {Object.entries(KINDS)
          .filter(([kind]) => counts[kind])
          .map(([kind, k]) => (
            <span key={kind} className="chart-legend-item">
              <svg width="14" height="14" aria-hidden="true">
                <Mark kind={kind} cx={7} cy={7} />
              </svg>
              {k.label} ({counts[kind]})
            </span>
          ))}
      </div>
      <div style={{ position: 'relative' }}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          width="100%"
          role="img"
          aria-label="Scatter chart of mean altitude versus inclination for each object, by classification"
          onMouseLeave={() => setHover(null)}
        >
          {/* grid + axes (recessive) */}
          {Y_TICKS.map((t) => (
            <g key={`y${t}`}>
              <line x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} className="chart-grid" />
              <text x={M.left - 8} y={y(t) + 4} className="chart-tick" textAnchor="end">{t}°</text>
            </g>
          ))}
          {X_TICKS.map((t) => (
            <g key={`x${t}`}>
              <line x1={x(t)} x2={x(t)} y1={M.top} y2={H - M.bottom} className="chart-grid" />
              <text x={x(t)} y={H - M.bottom + 16} className="chart-tick" textAnchor="middle">
                {t >= 1000 ? `${t / 1000}k` : t}
              </text>
            </g>
          ))}
          <text x={(M.left + W - M.right) / 2} y={H - 6} className="chart-axis-title" textAnchor="middle">
            Mean altitude (km, log scale) -- 35,786 km = geostationary
          </text>
          <text
            x={14}
            y={(M.top + H - M.bottom) / 2}
            className="chart-axis-title"
            textAnchor="middle"
            transform={`rotate(-90 14 ${(M.top + H - M.bottom) / 2})`}
          >
            Inclination
          </text>

          {/* marks: draw satellites first so debris sits on top */}
          {['unclassified', 'satellite', 'debris'].flatMap((kind) =>
            points
              .filter((p) => p.kind === kind)
              .map((p) => (
                <g key={p.row.norad_id}>
                  <Mark kind={kind} cx={p.cx} cy={p.cy} />
                  <circle
                    cx={p.cx}
                    cy={p.cy}
                    r={9}
                    fill="transparent"
                    style={{ cursor: 'pointer' }}
                    onMouseEnter={() => setHover(p)}
                  />
                </g>
              ))
          )}
          {hover && <circle cx={hover.cx} cy={hover.cy} r={8} fill="none" stroke="var(--text-0)" strokeWidth="1.5" />}
        </svg>

        {hover && (
          <div
            className="chart-tooltip"
            style={{
              left: `${(hover.cx / W) * 100}%`,
              top: `${(hover.cy / H) * 100}%`,
              transform: hover.cx > W * 0.7 ? 'translate(calc(-100% - 12px), -50%)' : 'translate(12px, -50%)',
            }}
          >
            <div className="chart-tooltip-title">{hover.row.object_name || `NORAD ${hover.row.norad_id}`}</div>
            <div>NORAD {hover.row.norad_id} · {hover.row.object_type || 'type N/A'}</div>
            <div>
              {hover.row.prediction
                ? `${hover.row.prediction} (${formatNumber(hover.row.confidence, 1)}%)`
                : 'Not classified'}
            </div>
            <div>
              {formatNumber(hover.row.altitude_km, 0)} km · {formatNumber(hover.row.inclination_deg, 2)}°
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
