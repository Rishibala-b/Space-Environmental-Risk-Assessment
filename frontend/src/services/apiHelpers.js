// Pure functions only -- no axios, no browser/Vite globals -- so these can be
// unit-tested with plain Node, and so api.js stays thin.

/**
 * Frontend-side routing for the global "ask anything" search bar: picks which
 * agent page a free-text query belongs to, by simple keyword matching.
 * Only explicit classification wording goes to Agent 2 -- a query that merely
 * mentions "satellite" ("tell me about satellite 25544") is an information
 * request and stays with Agent 1.
 */
export function routeGlobalQuery(text) {
  const q = (text || '').toLowerCase()
  const classifyPatterns = [
    /\bclassif(y|ication|ied)\b/,
    /\bis (it|this|norad \d+|\d+) (a |an )?(debris|satellite|active)/,
    /\bdebris or\b/,
    /\bor debris\b/,
    /\bsatellite or\b/,
    /\bor (a |an )?(satellite|active)\b/,
  ]
  if (classifyPatterns.some((re) => re.test(q))) return 'agent2'
  return 'agent1'
}

/**
 * Extracts the first NORAD ID from free text, or null. Mirrors the backend's
 * rules: a number after "NORAD"/"ID"/"#" is always taken; otherwise it needs
 * 3-9 digits and must not look like a year (1957-2100) or part of a decimal/date.
 */
export function extractNoradId(text) {
  const s = text || ''
  const re = /\d+/g
  let m
  while ((m = re.exec(s)) !== null) {
    const digits = m[0]
    const before = s[m.index - 1] || ' '
    const after = s[m.index + digits.length] || ' '
    if ('.-/'.includes(before) || '.-/'.includes(after) || /[a-z]/i.test(before) || /[a-z]/i.test(after)) continue
    const window = s.slice(Math.max(0, m.index - 24), m.index)
    const labelled = /(norad|catalog|cat|id|no\.?|number|#)\s*[:#]?\s*(id|no\.?|number|#)?\s*[:#]?\s*$/i.test(window)
    const value = parseInt(digits, 10)
    if (!value || digits.length > 9) continue
    if (!labelled) {
      if (digits.length < 3) continue
      if (digits.length === 4 && value >= 1957 && value <= 2100) continue
    }
    return String(value)
  }
  return null
}

/** Parses a list of NORAD IDs typed/pasted by the user (commas, spaces,
 * semicolons, newlines). Returns { ids, invalid } with ids de-duplicated. */
export function parseNoradList(text) {
  const tokens = String(text || '').split(/[\s,;]+/).filter(Boolean)
  const ids = []
  const invalid = []
  for (const t of tokens) {
    if (/^\d+$/.test(t) && parseInt(t, 10) > 0) {
      const norm = String(parseInt(t, 10))
      if (!ids.includes(norm)) ids.push(norm)
    } else if (!invalid.includes(t)) {
      invalid.push(t)
    }
  }
  return { ids, invalid }
}

/** Frontend-side integer validation so obviously-invalid input never makes a round trip. */
export function validateNoradIdInput(value) {
  if (value === '' || value === null || value === undefined) {
    return { valid: false, error: 'Enter a NORAD ID.' }
  }
  if (!/^\d+$/.test(String(value).trim()) || parseInt(String(value).trim(), 10) <= 0) {
    return { valid: false, error: 'NORAD ID must be a positive whole number.' }
  }
  return { valid: true, error: null }
}

/** NORAD ID encoded in TLE line 1 (incl. Alpha-5 for IDs > 99999), or null. */
export function noradIdFromTleLine1(line1) {
  const raw = String(line1 || '').replace(/\r/g, '').trim().slice(2, 7)
  if (raw.length !== 5) return null
  if (/^\s*\d+$/.test(raw)) return String(parseInt(raw, 10))
  const letters = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
  const idx = letters.indexOf(raw[0].toUpperCase())
  if (idx >= 0 && /^\d{4}$/.test(raw.slice(1))) return String((idx + 10) * 10000 + parseInt(raw.slice(1), 10))
  return null
}

/** Turns an axios error into a clean, user-facing message. Never a stack trace. */
export function parseApiError(error) {
  if (!error) return 'An unknown error occurred.'
  if (error.code === 'ECONNABORTED') {
    return 'Request timed out. Space-Track may be slow right now -- please try again.'
  }
  if (!error.response) {
    return 'Unable to connect to the backend. Please make sure the FastAPI server is running.'
  }
  const data = error.response.data
  if (data && Array.isArray(data.detail) && data.detail.length > 0) {
    return data.detail.map((d) => d.msg).join('; ')
  }
  if (typeof data?.detail === 'string') return data.detail
  if (data?.error) return data.error
  if (data?.response) return data.response
  return `Request failed (HTTP ${error.response.status}).`
}

/** Fixed decimals, or 'N/A' if missing -- never a placeholder that looks like data. */
export function formatNumber(value, decimals = 3) {
  if (value === null || value === undefined || Number.isNaN(value)) return 'N/A'
  return Number(value).toFixed(decimals)
}

/**
 * Short display label from a real classification ("ACTIVE SATELLITE"/"SPACE
 * DEBRIS") or a real OBJECT_TYPE ("PAYLOAD"/"DEBRIS"). Never defaults to
 * "Satellite" for a missing value.
 */
export function objectTypeLabel(value) {
  if (!value) return 'Tracked Object'
  const v = String(value).toUpperCase()
  if (v.includes('DEBRIS')) return 'Debris'
  if (v.includes('PAYLOAD') || v.includes('SATELLITE')) return 'Satellite'
  if (v.includes('ROCKET')) return 'Rocket Body'
  return 'Tracked Object'
}

// Classification colours -- identical to --satellite / --debris in index.css.
export const CLASS_COLORS = {
  satellite: '#4fc3f7',
  debris: '#ff8c5a',
  unclassified: '#8a93a6',
}

/** 'satellite' | 'debris' | 'unclassified' for a batch row. */
export function classKey(row) {
  if (row?.status === 'classified' && row.label === 1) return 'debris'
  if (row?.status === 'classified' && row.label === 0) return 'satellite'
  return 'unclassified'
}

/** Batch rows -> CSV text (only the values the backend returned). */
export function batchRowsToCsv(rows) {
  const cols = [
    'norad_id', 'object_name', 'object_id', 'object_type', 'status', 'prediction', 'confidence',
    'altitude_km', 'inclination_deg', 'eccentricity', 'orbital_period_min',
    'epoch', 'decay_date', 'error',
  ]
  const esc = (v) => {
    if (v === null || v === undefined) return ''
    const s = String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  return [cols.join(','), ...rows.map((r) => cols.map((c) => esc(r[c])).join(','))].join('\n')
}

export const STATUS_LABELS = {
  classified: 'Classified',
  not_found: 'Not found',
  invalid_input: 'Invalid ID',
  invalid_tle: 'Invalid TLE',
  fetch_error: 'Fetch failed',
  model_error: 'Model error',
}
