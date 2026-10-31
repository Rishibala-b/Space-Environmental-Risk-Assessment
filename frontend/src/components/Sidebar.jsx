import React from 'react'

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', icon: '🏠' },
  { id: 'agent1', label: 'Agent 1 — Object Information', icon: '🛰️' },
  { id: 'agent2', label: 'Agent 2 — Classification', icon: '🧪' },
  { id: 'batch', label: 'Batch Analysis', icon: '📋' },
  { id: 'fleet', label: 'Fleet View', icon: '🌐' },
]

export default function Sidebar({ activePage, onNavigate }) {
  return (
    <nav className="app-sidebar">
      {NAV_ITEMS.map((item) => (
        <div
          key={item.id}
          className={`nav-item ${activePage === item.id ? 'active' : ''}`}
          onClick={() => onNavigate(item.id)}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onNavigate(item.id)}
        >
          <span>{item.icon}</span>
          <span>{item.label}</span>
        </div>
      ))}
    </nav>
  )
}
