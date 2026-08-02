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
    <div style={{
      position: 'fixed',
      top: '20px',
      right: '20px',
      zIndex: 9999,
      display: 'flex',
      flexDirection: 'column',
      gap: '8px',
    }}>
      {toasts.map(t => (
        <div key={t.id} style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '12px 16px',
          borderRadius: '8px',
          background: '#fff',
          boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
          minWidth: '200px',
        }}>
          {icons[t.type]}
          <span style={{ fontSize: '14px', color: '#1e293b' }}>{t.message}</span>
        </div>
      ))}
    </div>
  )
}
