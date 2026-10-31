import React, { useCallback, useEffect, useState } from 'react'
import Header from './components/Header'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import Agent1 from './pages/Agent1'
import Agent2 from './pages/Agent2'
import BatchAnalysis from './pages/BatchAnalysis'
import FleetView from './pages/FleetView'
import { AgentSessionProvider } from './context/AgentSessionContext'
import { getHealth } from './services/api'

function AppShell() {
  const [activePage, setActivePage] = useState('dashboard')
  const [presetQuery, setPresetQuery] = useState({ agent1: null, agent2: null })
  const [health, setHealth] = useState({ status: 'pending', data: null })

  useEffect(() => {
    let cancelled = false
    async function checkHealth() {
      try {
        const data = await getHealth()
        if (!cancelled) setHealth({ status: 'ok', data })
      } catch {
        if (!cancelled) setHealth({ status: 'err', data: null })
      }
    }
    checkHealth()
    const interval = setInterval(checkHealth, 15000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  function handleGlobalQuery(agent, text) {
    // A fresh object each time, so the same text can be sent twice in a row.
    setPresetQuery((prev) => ({ ...prev, [agent]: { text, key: Date.now() } }))
    setActivePage(agent)
  }

  // A page calls this as soon as it has sent the preset query. Clearing it here
  // means revisiting the page later does NOT send the same query again.
  const consumePreset = useCallback((agent) => {
    setPresetQuery((prev) => (prev[agent] ? { ...prev, [agent]: null } : prev))
  }, [])

  const h = health.data
  return (
    <div className="app-shell">
      <Header backendStatus={health.status} onGlobalQuery={handleGlobalQuery} />
      <Sidebar activePage={activePage} onNavigate={setActivePage} />
      <main className="app-main">
        {health.status === 'err' && (
          <div className="notice err" style={{ marginBottom: 20 }}>
            Unable to connect to the backend. Please make sure the FastAPI server is running
            (uvicorn app.main:app --reload) and that VITE_API_BASE_URL in .env points at it.
          </div>
        )}
        {h && !h.spacetrack_configured && (
          <div className="notice warn" style={{ marginBottom: 20 }}>
            Space-Track credentials are not configured on the backend. Set SPACETRACK_USERNAME and
            SPACETRACK_PASSWORD in the backend's .env file.
          </div>
        )}
        {h && h.model_ready === false && (
          <div className="notice warn" style={{ marginBottom: 20 }}>
            The classification model is not loaded: {h.model_error || 'unknown reason'}
          </div>
        )}
        {activePage === 'dashboard' && <Dashboard onNavigate={setActivePage} />}
        {activePage === 'agent1' && (
          <Agent1 presetQuery={presetQuery.agent1} onPresetConsumed={() => consumePreset('agent1')} />
        )}
        {activePage === 'agent2' && (
          <Agent2 presetQuery={presetQuery.agent2} onPresetConsumed={() => consumePreset('agent2')} />
        )}
        {activePage === 'batch' && <BatchAnalysis onNavigate={setActivePage} />}
        {activePage === 'fleet' && <FleetView onNavigate={setActivePage} />}
      </main>
    </div>
  )
}

export default function App() {
  return (
    <AgentSessionProvider>
      <AppShell />
    </AgentSessionProvider>
  )
}
