import React, { useState } from 'react'

export default function ChatInput({ placeholder, examples, onSend, onClear, disabled }) {
  const [text, setText] = useState('')

  function send() {
    const trimmed = text.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setText('')
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div>
      {examples && examples.length > 0 && (
        <div className="quick-examples">
          {examples.map((ex) => (
            <span key={ex} className="quick-chip" onClick={() => setText(ex)}>
              {ex}
            </span>
          ))}
        </div>
      )}
      <div className="chat-input-row">
        <textarea
          rows={2}
          placeholder={placeholder}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
        />
        <button className="btn primary" onClick={send} disabled={disabled}>
          Send
        </button>
        <button className="btn ghost" onClick={onClear} disabled={disabled} title="Clear session">
          Clear
        </button>
      </div>
    </div>
  )
}
