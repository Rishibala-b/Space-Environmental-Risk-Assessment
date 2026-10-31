import React, { useEffect, useRef, useState } from 'react'
import {
  createViewer, destroyViewer, hasWebGL, loadOrbitLibraries, periodFromTleLine2,
  periodMinutes, positionAt, tleEpochToDate,
} from '../services/cesium'
import { CLASS_COLORS, noradIdFromTleLine1 } from '../services/apiHelpers'

// Live 3D orbit of ONE object: client-side SGP4 (satellite.js) over one orbital
// period from the TLE epoch, drawn on a Cesium globe.
//
// Fixes vs. the previous version:
//  * the label/colour now update when the classification arrives (the plot
//    effect depends on `label` too), instead of staying on the first value;
//  * a real fallback panel when WebGL is unavailable (VMs / remote desktops);
//  * no Cesium Ion base layer (no token needed).

function colorForLabel(label) {
  if (label === 'Debris') return CLASS_COLORS.debris
  if (label === 'Satellite') return CLASS_COLORS.satellite
  return CLASS_COLORS.unclassified
}

export default function SpaceVisualization({ tleLine1, tleLine2, noradId, label }) {
  const containerRef = useRef(null)
  const viewerRef = useRef(null)
  const [status, setStatus] = useState('Loading 3D viewer...')
  const [ready, setReady] = useState(false)
  const [fallback, setFallback] = useState(null) // reason string when 3D is unavailable

  // Load libraries + create the viewer once.
  useEffect(() => {
    let cancelled = false
    if (!hasWebGL()) {
      setFallback('This browser or machine has no WebGL support, which the 3D globe needs. This is common on virtual machines and remote desktops.')
      return undefined
    }
    loadOrbitLibraries()
      .then(() => {
        if (cancelled || !containerRef.current || viewerRef.current) return
        try {
          viewerRef.current = createViewer(containerRef.current)
          setReady(true)
          setStatus('Viewer ready.')
        } catch (err) {
          setFallback(`The 3D globe could not start (${err.message}). WebGL may be disabled or blocked.`)
        }
      })
      .catch((err) => !cancelled && setFallback(`Could not load the 3D libraries: ${err.message}. Check your internet connection.`))

    return () => {
      cancelled = true
      destroyViewer(viewerRef.current)
      viewerRef.current = null
    }
  }, [])

  // Plot (or re-plot) whenever the TLE OR the label changes.
  useEffect(() => {
    if (!ready || !tleLine1 || !tleLine2 || !viewerRef.current) return
    plotOrbit(viewerRef.current, tleLine1, tleLine2, label || 'Tracked Object', setStatus)
  }, [ready, tleLine1, tleLine2, label])

  if (!tleLine1 || !tleLine2) return null

  const title = `3D Orbit Visualization${noradId ? ` -- NORAD ${noradId}` : ''}`

  if (fallback) {
    const period = periodFromTleLine2(tleLine2)
    return (
      <div>
        <div className="info-label" style={{ marginBottom: 8 }}>{title}</div>
        <div className="viz-fallback">
          <div className="viz-fallback-title">3D view unavailable</div>
          <div>{fallback}</div>
          <div className="info-grid" style={{ marginTop: 12 }}>
            <div className="info-field">
              <div className="info-label">NORAD ID</div>
              <div className="info-value">{noradId || noradIdFromTleLine1(tleLine1) || 'N/A'}</div>
            </div>
            <div className="info-field">
              <div className="info-label">Shown as</div>
              <div className="info-value">{label || 'Tracked Object'}</div>
            </div>
            <div className="info-field">
              <div className="info-label">Orbital period (from TLE)</div>
              <div className="info-value">{period ? `${period.toFixed(2)} min` : 'N/A'}</div>
            </div>
          </div>
          <div className="chat-meta" style={{ marginTop: 10 }}>
            To see the globe: enable hardware acceleration in your browser settings, or open the app on a machine with a GPU.
          </div>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="info-label" style={{ marginBottom: 8 }}>{title}</div>
      <div className="viz-frame" style={{ height: 480 }}>
        <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      </div>
      <div className="chat-meta" style={{ marginTop: 6, whiteSpace: 'pre-line' }}>{status}</div>
    </div>
  )
}

function plotOrbit(viewer, tle1, tle2, label, setStatus) {
  const Cesium = window.Cesium
  const satellite = window.satellite
  try {
    const satrec = satellite.twoline2satrec(tle1.trim(), tle2.trim())
    const epochDate = tleEpochToDate(satrec)
    const period = periodMinutes(satrec)
    const color = Cesium.Color.fromCssColorString(colorForLabel(label))

    viewer.entities.removeAll()

    const numberOfPoints = 360
    const orbitPositions = []
    const sampled = new Cesium.SampledPositionProperty()
    for (let i = 0; i <= numberOfPoints; i++) {
      const date = new Date(epochDate.getTime() + ((period * i) / numberOfPoints) * 60000)
      const position = positionAt(satrec, date)
      if (!position) continue
      orbitPositions.push(position)
      sampled.addSample(Cesium.JulianDate.fromDate(date), position)
    }
    if (orbitPositions.length < 2) {
      setStatus('SGP4 could not propagate this TLE (the object may have decayed).')
      return
    }

    const orbitEntity = viewer.entities.add({
      name: `${label} orbit`,
      polyline: {
        positions: orbitPositions,
        width: 3,
        material: new Cesium.PolylineGlowMaterialProperty({ glowPower: 0.2, taperPower: 0.5, color }),
      },
    })
    viewer.entities.add({
      name: label,
      position: sampled,
      point: { pixelSize: 12, color, outlineColor: Cesium.Color.WHITE, outlineWidth: 2 },
      label: {
        text: label,
        font: '14px sans-serif',
        pixelOffset: new Cesium.Cartesian2(15, -15),
        showBackground: true,
        backgroundPadding: new Cesium.Cartesian2(8, 6),
      },
    })

    const start = Cesium.JulianDate.fromDate(epochDate)
    const stop = Cesium.JulianDate.addMinutes(start, period, new Cesium.JulianDate())
    viewer.clock.startTime = start
    viewer.clock.stopTime = stop
    viewer.clock.currentTime = start
    viewer.clock.clockRange = Cesium.ClockRange.LOOP_STOP
    viewer.clock.multiplier = 20
    viewer.clock.shouldAnimate = true
    if (viewer.timeline) viewer.timeline.zoomTo(start, stop)
    viewer.flyTo(orbitEntity, { duration: 2 })

    setStatus(
      `Orbit plotted from the TLE epoch (${epochDate.toISOString().replace('T', ' ').slice(0, 19)} UTC).\n` +
        `NORAD ID: ${noradIdFromTleLine1(tle1) || 'N/A'}   Orbital period: ${period.toFixed(2)} min   Points: ${orbitPositions.length}`
    )
  } catch (error) {
    console.error(error)
    setStatus('Error processing TLE. Check the browser console (F12).')
  }
}
