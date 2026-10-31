// Shared CesiumJS / satellite.js plumbing for SpaceVisualization (one object)
// and FleetVisualization (many objects).
//
// Both libraries are loaded from CDN at runtime (not npm packages) and cached
// on `window`, exactly as before -- this module just makes sure they are loaded
// once, and that every viewer is created the same way.

const CESIUM_VERSION = '1.145'
export const CESIUM_JS_URL = `https://cesium.com/downloads/cesiumjs/releases/${CESIUM_VERSION}/Build/Cesium/Cesium.js`
export const CESIUM_CSS_URL = `https://cesium.com/downloads/cesiumjs/releases/${CESIUM_VERSION}/Build/Cesium/Widgets/widgets.css`
export const SATELLITE_JS_URL = 'https://cdn.jsdelivr.net/npm/satellite.js@6.0.1/dist/satellite.min.js'

let loadingPromise = null

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${src}"]`)
    if (existing) {
      if (existing.dataset.loaded === 'true') return resolve()
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', () => reject(new Error(`Failed to load ${src}`)))
      return
    }
    const script = document.createElement('script')
    script.src = src
    script.async = true
    script.onload = () => {
      script.dataset.loaded = 'true'
      resolve()
    }
    script.onerror = () => reject(new Error(`Failed to load ${src}`))
    document.body.appendChild(script)
  })
}

/** Loads Cesium + satellite.js once per page. Resolves when both are ready. */
export function loadOrbitLibraries() {
  if (window.Cesium && window.satellite) return Promise.resolve()
  if (loadingPromise) return loadingPromise
  if (!document.querySelector(`link[href="${CESIUM_CSS_URL}"]`)) {
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = CESIUM_CSS_URL
    document.head.appendChild(link)
  }
  loadingPromise = loadScript(CESIUM_JS_URL)
    .then(() => loadScript(SATELLITE_JS_URL))
    .catch((err) => {
      loadingPromise = null // allow a retry later
      throw err
    })
  return loadingPromise
}

/** True if this browser can create a WebGL context (VMs / remote desktops often can't). */
export function hasWebGL() {
  try {
    const canvas = document.createElement('canvas')
    return !!(canvas.getContext('webgl2') || canvas.getContext('webgl') || canvas.getContext('experimental-webgl'))
  } catch {
    return false
  }
}

/**
 * Creates a Cesium viewer with OpenStreetMap imagery and NO Cesium Ion base
 * layer (so no Ion access token is needed and no Ion requests are made).
 * Throws if WebGL initialisation fails -- callers show their fallback UI.
 */
export function createViewer(container, { animation = true, timeline = true } = {}) {
  const Cesium = window.Cesium
  const viewer = new Cesium.Viewer(container, {
    baseLayer: false,
    baseLayerPicker: false,
    terrainProvider: new Cesium.EllipsoidTerrainProvider(),
    geocoder: false,
    homeButton: true,
    sceneModePicker: true,
    navigationHelpButton: false,
    fullscreenButton: true,
    infoBox: true,
    selectionIndicator: true,
    animation,
    timeline,
  })
  viewer.imageryLayers.addImageryProvider(
    new Cesium.OpenStreetMapImageryProvider({ url: 'https://tile.openstreetmap.org/' })
  )
  return viewer
}

export function destroyViewer(viewer) {
  try {
    if (viewer && !viewer.isDestroyed()) viewer.destroy()
  } catch {
    /* already gone */
  }
}

/** Converts a TLE epoch (2-digit year + fractional day-of-year) to a JS Date. */
export function tleEpochToDate(satrec) {
  const yy = satrec.epochyr
  const fullYear = yy < 57 ? 2000 + yy : 1900 + yy
  const dayOfYear = satrec.epochdays
  const date = new Date(Date.UTC(fullYear, 0, 1, 0, 0, 0, 0))
  date.setUTCDate(Math.floor(dayOfYear))
  date.setTime(date.getTime() + (dayOfYear - Math.floor(dayOfYear)) * 86400000)
  return date
}

/** Orbital period in minutes from a satrec (satrec.no is rad/min). */
export function periodMinutes(satrec) {
  return (2 * Math.PI) / satrec.no
}

/**
 * Earth-fixed Cesium position for a satrec at `date`, or null if SGP4 fails
 * (satellite.js 6 may return null / false positions on error).
 */
export function positionAt(satrec, date) {
  const Cesium = window.Cesium
  const satellite = window.satellite
  const pv = satellite.propagate(satrec, date)
  const p = pv && pv.position
  if (!p || typeof p !== 'object' || Number.isNaN(p.x)) return null
  const ecf = satellite.eciToEcf(p, satellite.gstime(date))
  return Cesium.Cartesian3.fromElements(ecf.x * 1000, ecf.y * 1000, ecf.z * 1000)
}

/** Period in minutes read straight from TLE line 2 (mean motion, rev/day) -- no libraries needed. */
export function periodFromTleLine2(line2) {
  const mm = parseFloat(String(line2 || '').slice(52, 63))
  return mm > 0 ? 1440 / mm : null
}
