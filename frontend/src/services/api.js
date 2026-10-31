import axios from 'axios'
import { parseApiError } from './apiHelpers'

// Single source of truth for the backend URL -- never hard-coded elsewhere.
export const API_BASE_URL = (import.meta.env && import.meta.env.VITE_API_BASE_URL) || 'http://127.0.0.1:8000'

// 60 s covers the backend's worst case for one lookup (rate-limit wait +
// Space-Track timeout + one re-login). Batch requests get longer below.
const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
})

const BATCH_TIMEOUT_MS = 180000

// Resolves with the response body on success; rejects with a clean,
// user-facing message (never a raw axios error / stack trace) on failure.
async function request(promise) {
  try {
    const response = await promise
    return response.data
  } catch (error) {
    throw new Error(parseApiError(error))
  }
}

/** GET /agent/health */
export function getHealth() {
  return request(client.get('/agent/health', { timeout: 10000 }))
}

/** POST /agent/observe -- Agent 1. Prefer `norad_id` when you already have one:
 * it is looked up directly, with no language parsing (and no LLM call). */
export function observeAgent1({ query, norad_id, tle_line1, tle_line2, compare_with_norad_id } = {}) {
  return request(client.post('/agent/observe', { query, norad_id, tle_line1, tle_line2, compare_with_norad_id }))
}

/** POST /agent/classify -- Agent 2. `enrich: false` skips the backend's
 * name/type lookup for a pasted TLE (use it when you already have that record). */
export function classifyAgent2({ line1, line2, norad_id, query, enrich } = {}) {
  return request(client.post('/agent/classify', { line1, line2, norad_id, query, enrich }))
}

/** GET /agent/batch/events -- preset fragmentation events. */
export function getBatchEvents() {
  return request(client.get('/agent/batch/events'))
}

/** POST /agent/batch -- batch / fleet analysis.
 * Pass ONE of: norad_ids (array or string), event (preset key), intldes (e.g. "1993-036"). */
export function runBatchAnalysis({ norad_ids, event, intldes, include_decayed, limit } = {}) {
  return request(
    client.post(
      '/agent/batch',
      { norad_ids, event, intldes, include_decayed, limit },
      { timeout: BATCH_TIMEOUT_MS }
    )
  )
}
