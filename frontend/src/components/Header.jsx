import React, { useState } from 'react'
import StatusIndicator from './StatusIndicator'
import { routeGlobalQuery } from '../services/apiHelpers'

export default function Header({ backendStatus, onGlobalQuery }) {
  const [query, setQuery] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    const trimmed = query.trim()
    if (!trimmed) return
    const agent = routeGlobalQuery(trimmed)
    onGlobalQuery(agent, trimmed)
    setQuery('')
  }

  return (
    <header className="app-header">
      <div className="brand">
        <div className="brand-icon">🛰️</div>
        <div>
          <div className="brand-title">SPACE DEBRIS INTELLIGENCE SYSTEM</div>
          <div className="brand-subtitle">Space Object Detection • Classification</div>
        </div>
      </div>

      <form className="global-search" onSubmit={handleSubmit}>
        <span>🔎</span>
        <input
          placeholder="Ask anything about a space object..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </form>

      <StatusIndicator
        status={backendStatus}
        labelOk="Backend Connected"
        labelErr="Backend Offline"
        labelPending="Checking..."
      />
    </header>
  )
}
