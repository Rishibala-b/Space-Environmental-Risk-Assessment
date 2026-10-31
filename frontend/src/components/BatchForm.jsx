import React, { useEffect, useState } from 'react'
import { getBatchEvents } from '../services/api'
import { parseNoradList } from '../services/apiHelpers'

// Batch request form, shared by the Batch Analysis and Fleet View pages.
// Three ways to pick objects: a NORAD ID list, a preset fragmentation event,
// or any launch's international designator.

const MODES = [
  { id: 'ids', label: 'NORAD ID list' },
  { id: 'event', label: 'Fragmentation event' },
  { id: 'intldes', label: 'Launch designator' },
]

const EXAMPLE_IDS = '25544, 20580, 48274, 43013, 33591, 27424, 36508, 22675'

export default function BatchForm({ onRun, loading }) {
  const [mode, setMode] = useState('ids')
  const [idsText, setIdsText] = useState('')
  const [events, setEvents] = useState([])
  const [eventsError, setEventsError] = useState('')
  const [eventKey, setEventKey] = useState('')
  const [intldes, setIntldes] = useState('')
  const [includeDecayed, setIncludeDecayed] = useState(false)
  const [limit, setLimit] = useState(200)
  const [formError, setFormError] = useState('')

  useEffect(() => {
    let cancelled = false
    getBatchEvents()
      .then((list) => {
        if (cancelled) return
        setEvents(list)
        if (list.length) setEventKey((k) => k || list[0].key)
      })
      .catch((err) => !cancelled && setEventsError(err.message))
    return () => {
      cancelled = true
    }
  }, [])

  const parsed = parseNoradList(idsText)
  const selectedEvent = events.find((e) => e.key === eventKey)

  function submit() {
    setFormError('')
    const lim = parseInt(limit, 10)
    if (!(lim > 0)) {
      setFormError('Max objects must be a positive number.')
      return
    }
    if (mode === 'ids') {
      if (parsed.ids.length === 0) {
        setFormError('Enter at least one NORAD ID.')
        return
      }
      onRun({ norad_ids: parsed.ids, limit: lim })
    } else if (mode === 'event') {
      if (!eventKey) {
        setFormError('Choose an event.')
        return
      }
      onRun({ event: eventKey, include_decayed: includeDecayed, limit: lim })
    } else {
      const d = intldes.trim().toUpperCase()
      if (!/^\d{4}-\d{3}[A-Z]{0,3}$/.test(d)) {
        setFormError("Enter an international designator like '1993-036' (year-launch number).")
        return
      }
      onRun({ intldes: d, include_decayed: includeDecayed, limit: lim })
    }
  }

  return (
    <div>
      <div className="segmented" role="tablist">
        {MODES.map((m) => (
          <button
            key={m.id}
            role="tab"
            aria-selected={mode === m.id}
            className={`segmented-item ${mode === m.id ? 'active' : ''}`}
            onClick={() => setMode(m.id)}
          >
            {m.label}
          </button>
        ))}
      </div>

      {mode === 'ids' && (
        <div className="form-field" style={{ marginBottom: 14 }}>
          <label>NORAD IDs (separated by commas, spaces or new lines)</label>
          <textarea
            className="textarea"
            rows={4}
            value={idsText}
            onChange={(e) => setIdsText(e.target.value)}
            placeholder={EXAMPLE_IDS}
          />
          <div className="chat-meta" style={{ marginTop: 6 }}>
            {parsed.ids.length} valid ID(s)
            {parsed.invalid.length > 0 && ` · ignored: ${parsed.invalid.slice(0, 5).join(', ')}${parsed.invalid.length > 5 ? '…' : ''}`}
            {' · '}
            <span className="link" onClick={() => setIdsText(EXAMPLE_IDS)}>use example list</span>
          </div>
        </div>
      )}

      {mode === 'event' && (
        <div style={{ marginBottom: 14 }}>
          {eventsError && <div className="notice err">Could not load events: {eventsError}</div>}
          <div className="form-grid" style={{ marginBottom: 8 }}>
            <div className="form-field">
              <label>Event</label>
              <select value={eventKey} onChange={(e) => setEventKey(e.target.value)} disabled={!events.length}>
                {events.map((ev) => (
                  <option key={ev.key} value={ev.key}>{ev.label}</option>
                ))}
              </select>
            </div>
          </div>
          {selectedEvent && (
            <div className="chat-meta">
              {selectedEvent.description} All catalogued objects from launch {selectedEvent.intldes} (parent,
              rocket body, fragments).
            </div>
          )}
        </div>
      )}

      {mode === 'intldes' && (
        <div className="form-grid" style={{ marginBottom: 8 }}>
          <div className="form-field">
            <label>International designator prefix</label>
            <input value={intldes} onChange={(e) => setIntldes(e.target.value)} placeholder="e.g. 1993-036" />
          </div>
        </div>
      )}

      <div className="form-row">
        <div className="form-field" style={{ width: 140 }}>
          <label>Max objects</label>
          <input type="number" min="1" max="500" value={limit} onChange={(e) => setLimit(e.target.value)} />
        </div>
        {mode !== 'ids' && (
          <label className="legend-toggle" style={{ alignSelf: 'flex-end', marginBottom: 10 }}>
            <input type="checkbox" checked={includeDecayed} onChange={(e) => setIncludeDecayed(e.target.checked)} />
            Include objects that have already re-entered
          </label>
        )}
        <button className="btn primary" style={{ alignSelf: 'flex-end' }} onClick={submit} disabled={loading}>
          {loading ? 'Analyzing...' : 'Run batch analysis'}
        </button>
      </div>
      {formError && <div className="field-error">{formError}</div>}
      <div className="chat-meta" style={{ marginTop: 8 }}>
        Objects are fetched from Space-Track in groups of up to 100 per request, and every request is rate-limited
        to stay within Space-Track's usage policy.
      </div>
    </div>
  )
}
