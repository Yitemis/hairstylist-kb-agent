import { useState, useEffect } from 'react'
import { subscribeToasts, type ToastEvent } from '../utils/toast'

const icons = {
  success: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="8" r="7" fill="#10b981" />
      <path d="M4.5 8L6.5 10L11.5 5.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  error: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="8" r="7" fill="#ef4444" />
      <path d="M5.5 5.5L10.5 10.5M10.5 5.5L5.5 10.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  ),
  info: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="8" r="7" fill="#6366f1" />
      <path d="M8 7V11M8 5.5V5" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  ),
}

export default function Toast() {
  const [toasts, setToasts] = useState<ToastEvent[]>([])

  useEffect(() => subscribeToasts(setToasts), [])

  if (!toasts.length) return null

  return (
    <div className="toast-container">
      {toasts.map(t => (
        <div key={t.id} className={`toast toast-${t.type}`}>
          {icons[t.type]}
          <span>{t.message}</span>
        </div>
      ))}
    </div>
  )
}
