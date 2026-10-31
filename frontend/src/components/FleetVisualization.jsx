import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  createViewer, destroyViewer, hasWebGL, loadOrbitLibraries, periodMinutes, positionAt,
} from '../services/cesium'
import { CLASS_COLORS, classKey, formatNumber } from '../services/apiHelpers'

// Fleet view: many objects on one Cesium globe, colour-coded by the model's
// classification (satellite / debris / not classified). Debris is drawn as a
// diamond and satellites as a circle, so the classes are distinguishable
// without relying on colour alone.
//
// All objects are propagated client-side (satellite.js SGP4) from "now", so
// objects with different TLE epochs share one clock and move together.

const CATEGORY_META = {
  satellite: { label: 'Active satellite', color: CLASS_COLORS.satellite },
  debris: { label: 'Space debris', color: CLASS_COLORS.debris },
  unclassified: { label: 'Not classified', color: CLASS_COLORS.unclassified },
}

const ORBIT_POINTS = 90      // per orbit polyline
const TRACK_SAMPLES = 60     // per animated position track
const MAX_WINDOW_MIN = 1440  // animation window cap (one day)
const AUTO_ORBIT_LIMIT = 150 // above this many objects, orbit lines start hidden

// Marker images drawn once on a canvas: circle (satellite), diamond (debris),
// hollow ring (not classified).
const markerCache = {}
function markerImage(kind) {
  if (markerCache[kind]) return markerCache[kind]
  const size = 20
  const c = document.createElement('canvas')
  c.width = size
  c.height = size
  const g = c.getContext('2d')
  const color = CATEGORY_META[kind].color
  g.lineWidth = 2
  g.strokeStyle = '#0a0e14'
  g.fillStyle = color
  if (kind === 'debris') {
    g.beginPath()
    g.moveTo(size / 2, 2)
    g.lineTo(size - 2, size / 2)
    g.lineTo(size / 2, size - 2)
    g.lineTo(2, size / 2)
    g.closePath()
    g.fill()
    g.stroke()
  } else if (kind === 'satellite') {
    g.beginPath()
    g.arc(size / 2, size / 2, size / 2 - 3, 0, Math.PI * 2)
    g.fill()
    g.stroke()
  } else {
    g.beginPath()
    g.arc(size / 2, size / 2, size / 2 - 4, 0, Math.PI * 2)
    g.strokeStyle = color
    g.lineWidth = 3
    g.stroke()
  }
  markerCache[kind] = c.toDataURL()
  return markerCache[kind]
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]))
}

function describe(row) {
  const rows = [
    ['NORAD ID', row.norad_id],
    ['Name', row.object_name],
    ['Intl. designator', row.object_id],
    ['Catalogue type', row.object_type],
    ['Model prediction', row.prediction || 'Not classified'],
    ['Confidence', row.confidence != null ? `${formatNumber(row.confidence, 2)}%` : null],
    ['Altitude (mean)', row.altitude_km != null ? `${formatNumber(row.altitude_km, 1)} km` : null],
    ['Inclination', row.inclination_deg != null ? `${formatNumber(row.inclination_deg, 2)}°` : null],
    ['TLE epoch', row.epoch],
    ['Note', row.error || row.warning],
  ].filter(([, v]) => v !== null && v !== undefined && v !== '')
  return `<table class="cesium-infoBox-defaultTable"><tbody>${rows
    .map(([k, v]) => `<tr><th>${escapeHtml(k)}</th><td>${escapeHtml(v)}</td></tr>`)
    .join('')}</tbody></table>`
}

export default function FleetVisualization({ objects }) {
  const containerRef = useRef(null)
  const viewerRef = useRef(null)
  const groupsRef = useRef({ satellite: [], debris: [], unclassified: [] })
  const [ready, setReady] = useState(false)
  const [fallback, setFallback] = useState(null)
  const [status, setStatus] = useState('Loading 3D viewer...')
  const [visible, setVisible] = useState({ satellite: true, debris: true, unclassified: true })
  const [showOrbits, setShowOrbits] = useState(true)
  const [plotStats, setPlotStats] = useState(null)

  const plottable = useMemo(
    () => (objects || []).filter((o) => o.TLE_LINE1 && o.TLE_LINE2 && !o.decay_date),
    [objects]
  )

  // Default orbit lines off for big fleets (visual clutter + performance).
  useEffect(() => {
    setShowOrbits(plottable.length <= AUTO_ORBIT_LIMIT)
  }, [plottable])

  // Viewer lifecycle.
  useEffect(() => {
    let cancelled = false
    if (!hasWebGL()) {
      setFallback('This browser or machine has no WebGL support, which the 3D globe needs (common on VMs and remote desktops). The altitude-inclination chart below still works.')
      return undefined
    }
    loadOrbitLibraries()
      .then(() => {
        if (cancelled || !containerRef.current || viewerRef.current) return
        try {
          viewerRef.current = createViewer(containerRef.current)
          setReady(true)
        } catch (err) {
          setFallback(`The 3D globe could not start (${err.message}). The chart below still works.`)
        }
      })
      .catch((err) => !cancelled && setFallback(`Could not load the 3D libraries: ${err.message}.`))
    return () => {
      cancelled = true
      destroyViewer(viewerRef.current)
      viewerRef.current = null
    }
  }, [])

  // Plot the fleet whenever the object list changes.
  useEffect(() => {
    if (!ready || !viewerRef.current) return
    const stats = plotFleet(viewerRef.current, plottable, groupsRef, setStatus)
    setPlotStats(stats)
  }, [ready, plottable])

  // Apply filters / orbit toggle without re-propagating anything.
  useEffect(() => {
    for (const [kind, entries] of Object.entries(groupsRef.current)) {
      for (const { point, orbit } of entries) {
        point.show = visible[kind]
        if (orbit) orbit.show = visible[kind] && showOrbits
      }
    }
    if (viewerRef.current) viewerRef.current.scene.requestRender()
  }, [visible, showOrbits, plotStats])

  const counts = useMemo(() => {
    const c = { satellite: 0, debris: 0, unclassified: 0 }
    for (const o of plottable) c[classKey(o)] += 1
    return c
  }, [plottable])

  const skipped = (objects || []).length - plottable.length

  return (
    <div>
      <div className="fleet-toolbar">
        <div className="fleet-legend" role="group" aria-label="Show or hide categories">
          {Object.entries(CATEGORY_META).map(([kind, meta]) => (
            <label key={kind} className={`legend-toggle ${visible[kind] ? '' : 'off'}`}>
              <input
                type="checkbox"
                checked={visible[kind]}
                onChange={(e) => setVisible((v) => ({ ...v, [kind]: e.target.checked }))}
              />
              <span className={`legend-swatch ${kind}`} />
              {meta.label} <span className="legend-count">{counts[kind]}</span>
            </label>
          ))}
        </div>
        <label className="legend-toggle">
          <input type="checkbox" checked={showOrbits} onChange={(e) => setShowOrbits(e.target.checked)} />
          Orbit paths
        </label>
      </div>

      {fallback ? (
        <div className="viz-fallback">
          <div className="viz-fallback-title">3D view unavailable</div>
          <div>{fallback}</div>
        </div>
      ) : (
        <>
          <div className="viz-frame" style={{ height: 560 }}>
            <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
          </div>
          <div className="chat-meta" style={{ marginTop: 6, whiteSpace: 'pre-line' }}>
            {status}
            {skipped > 0 &&
              `\n${skipped} object(s) not plotted: no TLE returned, or already decayed (re-entered).`}
          </div>
        </>
      )}
    </div>
  )
}

function plotFleet(viewer, rows, groupsRef, setStatus) {
  const Cesium = window.Cesium
  const satellite = window.satellite
  viewer.entities.removeAll()
  groupsRef.current = { satellite: [], debris: [], unclassified: [] }
  if (!rows.length) {
    setStatus('Nothing to plot.')
    return { plotted: 0, failed: 0 }
  }

  const now = new Date()
  const parsed = []
  let failed = 0
  for (const row of rows) {
    try {
      const satrec = satellite.twoline2satrec(row.TLE_LINE1.trim(), row.TLE_LINE2.trim())
      if (satrec.error) throw new Error(`sgp4 error ${satrec.error}`)
      parsed.push({ row, satrec, period: periodMinutes(satrec) })
    } catch {
      failed += 1
    }
  }
  const windowMin = Math.min(
    MAX_WINDOW_MIN,
    Math.max(60, ...parsed.map((p) => (Number.isFinite(p.period) ? p.period : 0)))
  )

  viewer.entities.suspendEvents()
  let plotted = 0
  for (const { row, satrec, period } of parsed) {
    const kind = classKey(row)
    const color = Cesium.Color.fromCssColorString(CATEGORY_META[kind].color)

    // Animated position over the shared window.
    const track = new Cesium.SampledPositionProperty()
    track.setInterpolationOptions({
      interpolationDegree: 3,
      interpolationAlgorithm: Cesium.LagrangePolynomialApproximation,
    })
    let samples = 0
    for (let i = 0; i <= TRACK_SAMPLES; i++) {
      const date = new Date(now.getTime() + ((windowMin * i) / TRACK_SAMPLES) * 60000)
      const pos = positionAt(satrec, date)
      if (pos) {
        track.addSample(Cesium.JulianDate.fromDate(date), pos)
        samples += 1
      }
    }
    if (samples < 4) {
      failed += 1
      continue
    }

    // One full orbit of this object, starting now.
    const orbitPositions = []
    for (let i = 0; i <= ORBIT_POINTS; i++) {
      const pos = positionAt(satrec, new Date(now.getTime() + ((period * i) / ORBIT_POINTS) * 60000))
      if (pos) orbitPositions.push(pos)
    }

    const name = row.object_name ? `${row.object_name} (${row.norad_id})` : `NORAD ${row.norad_id}`
    const point = viewer.entities.add({
      id: `obj-${row.norad_id}`,
      name,
      description: describe(row),
      position: track,
      billboard: {
        image: markerImage(kind),
        width: kind === 'debris' ? 14 : 12,
        height: kind === 'debris' ? 14 : 12,
      },
    })
    const orbit = orbitPositions.length > 1
      ? viewer.entities.add({
          id: `orbit-${row.norad_id}`,
          name: `${name} orbit`,
          description: describe(row),
          polyline: { positions: orbitPositions, width: 1.5, material: color.withAlpha(0.45) },
        })
      : null
    groupsRef.current[kind].push({ point, orbit })
    plotted += 1
  }
  viewer.entities.resumeEvents()

  const start = Cesium.JulianDate.fromDate(now)
  const stop = Cesium.JulianDate.addMinutes(start, windowMin, new Cesium.JulianDate())
  viewer.clock.startTime = start
  viewer.clock.stopTime = stop
  viewer.clock.currentTime = start
  viewer.clock.clockRange = Cesium.ClockRange.LOOP_STOP
  viewer.clock.multiplier = 30
  viewer.clock.shouldAnimate = true
  if (viewer.timeline) viewer.timeline.zoomTo(start, stop)
  viewer.flyTo(viewer.entities, { duration: 2 })

  setStatus(
    `${plotted} object(s) plotted, propagated from now (${now.toISOString().slice(11, 19)} UTC) over ${windowMin.toFixed(0)} min.` +
      (failed ? `  ${failed} could not be propagated by SGP4.` : '') +
      '\nClick any object or orbit for its details.'
  )
  return { plotted, failed }
}
