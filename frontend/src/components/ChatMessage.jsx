import React from 'react'

export default function ChatMessage({ role, text, timestamp }) {
  return (
    <div className={`chat-message ${role}`}>
      <div className="chat-bubble">{text}</div>
      {timestamp && <div className="chat-meta">{new Date(timestamp).toLocaleTimeString()}</div>}
    </div>
  )
}
