import React, { useEffect, useRef, useState } from 'react'
import ChatInput from '../components/ChatInput'
import ChatMessage from '../components/ChatMessage'
import ClassificationCard from '../components/ClassificationCard'
import { classifyAgent2 } from '../services/api'
import { useAgentSession } from '../context/AgentSessionContext'

const EXAMPLES = ['Classify NORAD 25544', 'Is NORAD 22675 satellite or debris?']

export default function Agent2({ presetQuery, onPresetConsumed }) {
  const { agent2Messages, appendMessage, clearSession } = useAgentSession()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const handledPresetKey = useRef(null)

  // Header-search query: sent exactly once (see Agent1.jsx for why).
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
    appendMessage('agent2', { role: 'user', text, timestamp: Date.now() })
    setLoading(true)
    try {
      // Accepts a NORAD ID (TLE fetched live) or a pasted TLE, in the same free text.
      const data = await classifyAgent2({ query: text })
      appendMessage('agent2', { role: 'agent', text: data.response, timestamp: Date.now(), result: data })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <div className="page-title">AGENT 2 — SPACE DEBRIS CLASSIFICATION</div>
      <div className="page-subtitle">
        Give a NORAD ID or paste a TLE to classify it as an active satellite or space debris.
      </div>

      <div className="panel">
        <div className="chat-window">
          {agent2Messages.map((m, i) => (
            <div key={i}>
              <ChatMessage role={m.role} text={m.text} timestamp={m.timestamp} />
              {m.result && <div style={{ marginTop: 8 }}><ClassificationCard result={m.result} /></div>}
            </div>
          ))}
          {loading && <div className="chat-loading">Agent is processing...</div>}
          {error && <div className="chat-error">{error}</div>}
        </div>

        <ChatInput
          placeholder={'Classify NORAD 25544, or paste a TLE:\n1 25544U 98067A   24001.50000000 ...\n2 25544  51.6400 208.9163 ...'}
          examples={EXAMPLES}
          onSend={handleSend}
          onClear={() => clearSession('agent2')}
          disabled={loading}
        />
      </div>
    </div>
  )
}
