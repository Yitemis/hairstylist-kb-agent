import { useState, useEffect, useRef } from 'react'

interface HitlConfirmProps {
  open: boolean
  action: string           // e.g. "删除全部记忆"
  detail?: string          // optional extra detail line
  countdownSec?: number    // default 5
  onConfirm: () => void
  onCancel: () => void
}

const RADIUS = 20
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

export default function HitlConfirm({
  open, action, detail, countdownSec = 5, onConfirm, onCancel,
}: HitlConfirmProps) {
  const [remaining, setRemaining] = useState(countdownSec)
  const [canClick, setCanClick] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!open) { setRemaining(countdownSec); setCanClick(false); return }
    setRemaining(countdownSec)
    setCanClick(false)
    intervalRef.current = setInterval(() => {
      setRemaining(r => {
        if (r <= 1) {
          clearInterval(intervalRef.current!)
          setCanClick(true)
          return 0
        }
        return r - 1
      })
    }, 1000)
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [open, countdownSec])

  if (!open) return null

  const progress = remaining / countdownSec   // 1 → 0
  const dashOffset = CIRCUMFERENCE * (1 - progress)  // ring fills in as time passes

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}
      onClick={onCancel}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: 400, maxWidth: '100%', background: '#fff', borderRadius: 14,
          boxShadow: '0 10px 30px rgba(0,0,0,0.08)', overflow: 'hidden',
          animation: 'hitl-slide-up 0.2s ease both',
        }}
      >
        <style>{`
          @keyframes hitl-slide-up {
            from { opacity: 0; transform: translateY(20px); }
            to   { opacity: 1; transform: translateY(0); }
          }
        `}</style>

        {/* Header area */}
        <div style={{ padding: '32px 28px 20px', textAlign: 'center' }}>
          {/* Orange warning circle */}
          <div style={{
            width: 56, height: 56, borderRadius: '50%', background: '#fef3c7',
            display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 18px',
            border: '2px solid #fbbf24',
          }}>
            <svg width="26" height="26" viewBox="0 0 26 26" fill="none">
              <path d="M13 3L2 22h22L13 3z" fill="#f59e0b" stroke="#f59e0b" strokeWidth="0.5" strokeLinejoin="round" />
              <path d="M13 10v5M13 17.5v1" stroke="white" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </div>

          <h3 style={{ fontSize: 18, fontWeight: 700, color: '#1e293b', marginBottom: 8 }}>需要您的确认</h3>
          <p style={{ fontSize: 14, color: '#64748b', lineHeight: 1.55, maxHeight: 44, overflow: 'hidden', textOverflow: 'ellipsis' }}>
            您确定要<strong style={{ color: '#1e293b' }}>「{action}」</strong>吗？
          </p>
          {detail && (
            <p style={{ fontSize: 13, color: '#94a3b8', marginTop: 6, lineHeight: 1.5 }}>{detail}</p>
          )}
        </div>

        {/* Divider */}
        <div style={{ height: 1, background: '#f1f5f9', margin: '0 0 20px' }} />

        {/* Buttons */}
        <div style={{ display: 'flex', gap: 12, padding: '0 24px 20px' }}>
          {/* Cancel */}
          <button
            onClick={onCancel}
            style={{ flex: 1, height: 44, borderRadius: 10, border: 'none', background: '#f1f5f9', color: '#64748b', fontSize: 15, fontWeight: 500, cursor: 'pointer', transition: 'background 0.12s' }}
            onMouseOver={e => { e.currentTarget.style.background = '#e2e8f0' }}
            onMouseOut={e => { e.currentTarget.style.background = '#f1f5f9' }}
          >
            取消
          </button>

          {/* Confirm with countdown ring */}
          <button
            onClick={() => { if (canClick) onConfirm() }}
            style={{
              flex: 1, height: 44, borderRadius: 10, border: 'none',
              background: canClick ? '#f59e0b' : '#fde68a',
              color: canClick ? '#fff' : '#92400e',
              fontSize: 15, fontWeight: 600,
              cursor: canClick ? 'pointer' : 'not-allowed',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              transition: 'all 0.2s',
              boxShadow: canClick ? '0 2px 12px rgba(245,158,11,0.35)' : 'none',
            }}
          >
            {!canClick && (
              <svg width="28" height="28" viewBox="0 0 48 48" style={{ flexShrink: 0 }}>
                {/* Track */}
                <circle cx="24" cy="24" r={RADIUS} fill="none" stroke="rgba(146,64,14,0.2)" strokeWidth="4" />
                {/* Progress arc */}
                <circle
                  cx="24" cy="24" r={RADIUS}
                  fill="none" stroke="#92400e" strokeWidth="4"
                  strokeDasharray={CIRCUMFERENCE}
                  strokeDashoffset={dashOffset}
                  strokeLinecap="round"
                  transform="rotate(-90 24 24)"
                  style={{ transition: 'stroke-dashoffset 0.9s linear' }}
                />
                <text x="24" y="28" textAnchor="middle" fontSize="13" fontWeight="700" fill="#92400e">{remaining}</text>
              </svg>
            )}
            {canClick ? '确认执行' : `等待中`}
          </button>
        </div>

        {/* Audit note */}
        <p style={{ textAlign: 'center', fontSize: 12, color: '#cbd5e1', paddingBottom: 16 }}>
          此操作将被系统记录审计
        </p>
      </div>
    </div>
  )
}
