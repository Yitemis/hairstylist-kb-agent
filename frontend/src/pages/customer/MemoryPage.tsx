import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import HitlConfirm from '../../components/HitlConfirm'
import { showToast } from '../../utils/toast'

type MemoryCategory = 'person' | 'location' | 'preference'

interface MemoryItem {
  id: string
  category: MemoryCategory
  label: string
  content: string
  confidence: number   // 0–1
}

const INIT_MEMORIES: MemoryItem[] = [
  { id: 'm1', category: 'preference', label: '发型偏好',  content: '喜欢自然系大波浪烫，不要太紧的卷', confidence: 0.92 },
  { id: 'm2', category: 'location',   label: '常去门店',  content: '三里屯旗舰店（朝阳区）',           confidence: 0.85 },
  { id: 'm3', category: 'person',     label: '指定发型师', content: '陈晓磊，10年经验烫发专家',         confidence: 0.78 },
  { id: 'm4', category: 'preference', label: '预约习惯',  content: '偏好周六上午10:00档期',            confidence: 0.66 },
  { id: 'm5', category: 'preference', label: '发质类型',  content: '细软发，容易塌，多孔性中等',        confidence: 0.54 },
  { id: 'm6', category: 'preference', label: '价格范围',  content: '单次预算 500–800 元',              confidence: 0.38 },
]

const CATEGORY_ICONS: Record<MemoryCategory, React.ReactNode> = {
  person: (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <circle cx="9" cy="6" r="3.5" stroke="white" strokeWidth="1.5" />
      <path d="M2 16c0-3.3 3.1-6 7-6s7 2.7 7 6" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  ),
  location: (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path d="M9 2C6.2 2 4 4.2 4 7c0 4 5 9 5 9s5-5 5-9c0-2.8-2.2-5-5-5z" stroke="white" strokeWidth="1.5" />
      <circle cx="9" cy="7" r="2" stroke="white" strokeWidth="1.3" />
    </svg>
  ),
  preference: (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path d="M9 2L11 7H16L12 10.5L13.5 16L9 13L4.5 16L6 10.5L2 7H7L9 2Z" stroke="white" strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  ),
}

const CATEGORY_LABELS: Record<MemoryCategory, string> = {
  person:     '人物',
  location:   '地点',
  preference: '偏好',
}

function ConfidenceBar({ value }: { value: number }) {
  const color = value >= 0.7 ? '#10b981' : value >= 0.4 ? '#f59e0b' : '#ef4444'
  return (
    <div style={{ height: 5, background: '#f1f5f9', borderRadius: 99, overflow: 'hidden', marginTop: 8 }}>
      <div style={{ height: '100%', width: `${value * 100}%`, background: color, borderRadius: 99, transition: 'width 0.4s ease' }} />
    </div>
  )
}

export default function MemoryPage() {
  const nav = useNavigate()
  const [memories, setMemories] = useState<MemoryItem[]>(INIT_MEMORIES)
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null)
  const [clearAll, setClearAll] = useState(false)
  const [hoverDeleteId, setHoverDeleteId] = useState<string | null>(null)
  const [showInfo, setShowInfo] = useState(false)

  const handleDeleteOne = (id: string) => {
    setMemories(prev => prev.filter(m => m.id !== id))
    setDeleteTargetId(null)
    showToast('记忆已删除', 'info')
  }

  const handleClearAll = () => {
    setMemories([])
    setClearAll(false)
    showToast('全部记忆已清空', 'info')
  }

  const deleteTarget = memories.find(m => m.id === deleteTargetId)

  return (
    <div className="mobile-shell" style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', background: '#f8fafc' }}>
      {/* Nav */}
      <div className="mobile-nav" style={{ justifyContent: 'space-between', background: '#fff', boxShadow: '0 1px 0 #f1f5f9' }}>
        <button onClick={() => nav('/customer/chat')} style={{ background: 'none', border: 'none', padding: 6, color: '#1e293b', display: 'flex', alignItems: 'center' }}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M12 4L6 10L12 16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        <span style={{ fontSize: 16, fontWeight: 700, color: '#1e293b' }}>我的记忆</span>
        <button
          onClick={() => setShowInfo(s => !s)}
          style={{ background: 'none', border: 'none', padding: 6, color: '#94a3b8', display: 'flex', alignItems: 'center' }}
        >
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <circle cx="10" cy="10" r="8.5" stroke="currentColor" strokeWidth="1.4" />
            <path d="M10 9V14M10 6.5V7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      {/* Info tooltip */}
      {showInfo && (
        <div style={{ background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 10, margin: '10px 14px 0', padding: '10px 14px' }}>
          <p style={{ fontSize: 13, color: '#92400e', lineHeight: 1.55 }}>
            🧠 AI 会在对话中自动学习你的偏好和习惯，并记录在这里用于个性化推荐。你可以随时删除不准确的记忆。
          </p>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 scrollbar-hide" style={{ overflowY: 'auto', padding: '12px 14px', flex: 1 }}>
        {memories.length === 0 ? (
          /* Empty state */
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 320, textAlign: 'center', padding: 32 }}>
            <div style={{ width: 80, height: 80, borderRadius: '50%', background: 'rgba(99,102,241,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 20 }}>
              <svg width="38" height="38" viewBox="0 0 38 38" fill="none">
                <ellipse cx="19" cy="15" rx="10" ry="11" stroke="#6366f1" strokeWidth="2" />
                <path d="M12 20c-2 2-3 4-3 6M26 20c2 2 3 4 3 6" stroke="#6366f1" strokeWidth="2" strokeLinecap="round" />
                <path d="M15 26v4M23 26v4" stroke="#6366f1" strokeWidth="2" strokeLinecap="round" />
                <circle cx="15" cy="13" r="1.5" fill="#6366f1" />
                <circle cx="23" cy="13" r="1.5" fill="#6366f1" />
                <path d="M15 18c1.2 1.3 6.8 1.3 8 0" stroke="#6366f1" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </div>
            <p style={{ fontSize: 16, fontWeight: 600, color: '#64748b', marginBottom: 8 }}>AI 还没记住你的偏好</p>
            <p style={{ fontSize: 13, color: '#94a3b8', lineHeight: 1.6 }}>多跟 AI 对话，它会学习你的喜好<br />并帮你更快完成预约</p>
            <button className="btn btn-primary" style={{ marginTop: 20, borderRadius: 24 }} onClick={() => nav('/customer/chat')}>
              开始对话
            </button>
          </div>
        ) : (
          <>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10, padding: '0 2px' }}>
              <p style={{ fontSize: 13, color: '#94a3b8' }}>共 {memories.length} 条记忆</p>
              <p style={{ fontSize: 12, color: '#94a3b8' }}>置信度越高，推荐越精准</p>
            </div>

            {memories.map((m, idx) => (
              <div
                key={m.id}
                className="card animate-fade-up"
                style={{ padding: 16, marginBottom: 10, display: 'flex', gap: 12, alignItems: 'flex-start', animationDelay: `${idx * 0.04}s` }}
              >
                {/* Category icon */}
                <div style={{ width: 40, height: 40, borderRadius: '50%', background: 'linear-gradient(135deg,#6366f1,#818cf8)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  {CATEGORY_ICONS[m.category]}
                </div>

                {/* Content */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                    <span style={{ fontSize: 11, padding: '1px 7px', borderRadius: 999, background: '#f5f3ff', color: '#6366f1', fontWeight: 500 }}>{CATEGORY_LABELS[m.category]}</span>
                    <span style={{ fontSize: 14, fontWeight: 600, color: '#1e293b' }}>{m.label}</span>
                  </div>
                  <p style={{ fontSize: 13, color: '#64748b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.content}</p>
                  <ConfidenceBar value={m.confidence} />
                  <p style={{ fontSize: 11, color: '#94a3b8', marginTop: 4 }}>置信度 {Math.round(m.confidence * 100)}%</p>
                </div>

                {/* Delete */}
                <button
                  onClick={() => setDeleteTargetId(m.id)}
                  onMouseEnter={() => setHoverDeleteId(m.id)}
                  onMouseLeave={() => setHoverDeleteId(null)}
                  style={{ background: 'none', border: 'none', padding: 4, cursor: 'pointer', flexShrink: 0, color: hoverDeleteId === m.id ? '#ef4444' : '#cbd5e1', transition: 'color 0.15s' }}
                >
                  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                    <path d="M3 5H15M7 5V3H11V5M6 5L6.5 14.5H11.5L12 5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
              </div>
            ))}
          </>
        )}
      </div>

      {/* Clear all button */}
      {memories.length > 0 && (
        <div style={{ padding: '12px 14px', background: '#fff', borderTop: '1px solid #f1f5f9', textAlign: 'center' }}>
          <button
            onClick={() => setClearAll(true)}
            style={{ background: 'none', border: 'none', color: '#ef4444', fontSize: 14, fontWeight: 500, cursor: 'pointer', padding: '8px 20px' }}
          >
            清空全部记忆
          </button>
        </div>
      )}

      {/* HITL — delete one */}
      <HitlConfirm
        open={!!deleteTargetId}
        action={`删除「${deleteTarget?.label || ''}」`}
        detail="删除后 AI 将不再记住这条偏好，无法恢复。"
        countdownSec={3}
        onConfirm={() => deleteTargetId && handleDeleteOne(deleteTargetId)}
        onCancel={() => setDeleteTargetId(null)}
      />

      {/* HITL — clear all */}
      <HitlConfirm
        open={clearAll}
        action="清空全部记忆"
        detail={`将删除全部 ${memories.length} 条记忆，AI 将重新学习你的偏好。`}
        countdownSec={5}
        onConfirm={handleClearAll}
        onCancel={() => setClearAll(false)}
      />
    </div>
  )
}
