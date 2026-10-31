import React, { createContext, useCallback, useContext, useRef, useState } from 'react'
import { runBatchAnalysis } from '../services/api'

const AgentSessionContext = createContext(null)

export function AgentSessionProvider({ children }) {
  // Each agent keeps its own message list so switching pages never loses a
  // conversation. Nothing is persisted -- it lives only for this page load.
  const [agent1Messages, setAgent1Messages] = useState([])
  const [agent2Messages, setAgent2Messages] = useState([])

  // Batch / fleet state is shared by the Batch Analysis and Fleet View pages,
  // so one Space-Track query powers both (no re-fetch when switching pages).
  const [batch, setBatch] = useState({ result: null, loading: false, error: '', request: null })
  const batchSeq = useRef(0)

  const appendMessage = useCallback((agent, message) => {
    const setter = { agent1: setAgent1Messages, agent2: setAgent2Messages }[agent]
    setter((prev) => [...prev, message])
  }, [])

  const clearSession = useCallback((agent) => {
    const setter = { agent1: setAgent1Messages, agent2: setAgent2Messages }[agent]
    setter([])
  }, [])

  const runBatch = useCallback(async (request) => {
    const seq = ++batchSeq.current
    setBatch((b) => ({ ...b, loading: true, error: '', request }))
    try {
      const result = await runBatchAnalysis(request)
      if (seq !== batchSeq.current) return // a newer run started meanwhile
      setBatch({ result, loading: false, error: result.error || '', request })
    } catch (err) {
      if (seq !== batchSeq.current) return
      setBatch((b) => ({ ...b, loading: false, error: err.message }))
    }
  }, [])

  const clearBatch = useCallback(() => {
    batchSeq.current += 1
    setBatch({ result: null, loading: false, error: '', request: null })
  }, [])

  const value = {
    agent1Messages, agent2Messages, appendMessage, clearSession,
    batch, runBatch, clearBatch,
  }

  return <AgentSessionContext.Provider value={value}>{children}</AgentSessionContext.Provider>
}

export function useAgentSession() {
  const ctx = useContext(AgentSessionContext)
  if (!ctx) throw new Error('useAgentSession must be used within AgentSessionProvider')
  return ctx
}
