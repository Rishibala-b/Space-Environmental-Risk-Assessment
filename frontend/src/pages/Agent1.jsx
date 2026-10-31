import React, { useEffect, useMemo, useRef, useState } from 'react'
import ChatInput from '../components/ChatInput'
import ChatMessage from '../components/ChatMessage'
import ObjectInfoCard from '../components/ObjectInfoCard'
import SpaceVisualization from '../components/SpaceVisualization'
import { observeAgent1 } from '../services/api'
import { useAgentSession } from '../context/AgentSessionContext'
import { objectTypeLabel } from '../services/apiHelpers'

const EXAMPLES = [
  'Give information about NORAD 25544',
  'What is the altitude of NORAD 25544?',
  'Compare NORAD 25544 and 20580',
]

export default function Agent1({ presetQuery, onPresetConsumed }) {
  const { agent1Messages, appendMessage, clearSession } = useAgentSession()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  // Which message's orbit is on the (single, shared) globe. null = latest.
  const [plotIndex, setPlotIndex] = useState(null)
  const handledPresetKey = useRef(null)

  // Send a query that came from the header search bar -- exactly once. The ref
  // guards against React StrictMode running this effect twice in development;
  // onPresetConsumed clears it in App so revisiting this page doesn't resend it.
  useEffect(() => {
    if (presetQuery?.text && handledPresetKey.current !== presetQuery.key) {
      handledPresetKey.current = presetQuery.key
      onPresetConsumed?.()
      handleSend(presetQuery.text)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presetQuery])

  async function handleSend(text) {
    setError('')
    appendMessage('agent1', { role: 'user', text, timestamp: Date.now() })
    setLoading(true)
    try {
      const data = await observeAgent1({ query: text })
      appendMessage('agent1', { role: 'agent', text: data.response, timestamp: Date.now(), result: data.result })
      setPlotIndex(null) // follow the newest orbit
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const plottableIndexes = useMemo(
    () => agent1Messages.map((m, i) => (m.result?.TLE_LINE1 && m.result?.TLE_LINE2 ? i : -1)).filter((i) => i >= 0),
    [agent1Messages]
  )
  const activeIndex = plotIndex ?? plottableIndexes[plottableIndexes.length - 1] ?? null
  const plotted = activeIndex !== null ? agent1Messages[activeIndex]?.result : null

  return (
    <div>
      <div className="page-title">AGENT 1 — SPACE OBJECT INFORMATION</div>
      <div className="page-subtitle">
        Ask about a NORAD ID or paste a TLE. Data is fetched live from Space-Track.org.
      </div>

      <div className="panel">
        <div className="chat-window">
          {agent1Messages.map((m, i) => (
            <div key={i}>
              <ChatMessage role={m.role} text={m.text} timestamp={m.timestamp} />
              {m.result && (
                <div style={{ marginTop: 8 }}>
                  <ObjectInfoCard result={m.result} />
                  {m.result.TLE_LINE1 && m.result.TLE_LINE2 && (
                    <button
                      className={`btn small ${i === activeIndex ? 'primary' : ''}`}
                      style={{ marginTop: 10 }}
                      onClick={() => setPlotIndex(i)}
                      disabled={i === activeIndex}
                    >
                      {i === activeIndex ? 'Shown on globe below' : 'Show this orbit on the globe'}
                    </button>
                  )}
                </div>
              )}
            </div>
          ))}
          {loading && <div className="chat-loading">Agent is processing...</div>}
          {error && <div className="chat-error">{error}</div>}
        </div>

        <ChatInput
          placeholder="Ask about a space object... e.g. Give information about NORAD 25544"
          examples={EXAMPLES}
          onSend={handleSend}
          onClear={() => {
            clearSession('agent1')
            setPlotIndex(null)
          }}
          disabled={loading}
        />
      </div>

      {plotted && (
        <div className="panel">
          <SpaceVisualization
            tleLine1={plotted.TLE_LINE1}
            tleLine2={plotted.TLE_LINE2}
            noradId={plotted.NORAD_CAT_ID}
            label={objectTypeLabel(plotted.OBJECT_TYPE)}
          />
        </div>
      )}
    </div>
  )
}
