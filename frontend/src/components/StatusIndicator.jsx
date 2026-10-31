import React from 'react'

export default function StatusIndicator({ status, labelOk, labelErr, labelPending }) {
  // status: 'ok' | 'err' | 'pending'
  const label = status === 'ok' ? labelOk : status === 'err' ? labelErr : labelPending
  return (
    <div className="status-pill">
      <span className={`status-dot ${status}`} />
      <span>{label}</span>
    </div>
  )
}
