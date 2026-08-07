import { useState, useRef, useEffect } from 'react'
import AdminLayout from '../../components/admin/AdminLayout'

/* ── Types ─────────────────────────────────────────────── */
interface Source {
  id: string; title: string; excerpt: string; page: string; icon: string
}
interface Message {
  id: string; role: 'user' | 'assistant'; content: string; sources?: Source[]; timestamp: string
}
interface Session {
  id: string; title: string; preview: string; time: string
}

/* ── Data ───────────────────────────────────────────────── */
function makeId() { return Math.random().toString(36).slice(2) }
function nowTime() { return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }

function TypingDots() {
  return (
    <div style={{ display: 'flex', gap: 5, padding: '4px 0' }}>
      <span className="dot-bounce" style={{ width: 7, height: 7, borderRadius: '50%', background: '#6366f1', display: 'inline-block' }} />
      <span className="dot-bounce" style={{ width: 7, height: 7, borderRadius: '50%', background: '#6366f1', display: 'inline-block' }} />
      <span className="dot-bounce" style={{ width: 7, height: 7, borderRadius: '50%', background: '#6366f1', display: 'inline-block' }} />
    </div>
  )
}

function SourceTag({ source, expanded, onToggle }: { source: Source; expanded: boolean; onToggle: () => void }) {
  return (
    <div style={{ marginBottom: 6 }}>
      <button
        onClick={onToggle}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 5,
          padding: '3px 10px', borderRadius: 999, fontSize: 12, fontWeight: 500,
          background: expanded ? '#ede9fe' : '#f5f3ff',
          color: '#6366f1', border: '1px solid #ddd6fe', cursor: 'pointer',
          transition: 'all 0.12s',
        }}
      >
        <span>{source.icon}</span>
        <span>{source.title}</span>
        <span style={{ opacity: 0.6 }}>{source.page}</span>
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" style={{ transform: expanded ? 'rotate(180deg)' : 'rotate(0)', transition: 'transform 0.18s' }}>
          <path d="M2 3.5L5 6.5L8 3.5" stroke="#6366f1" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </button>
      {expanded && (
        <div style={{ marginTop: 6, padding: '10px 12px', borderRadius: 10, background: '#f5f3ff', border: '1px solid #e0d9ff', fontSize: 12, color: '#4c1d95', lineHeight: 1.6 }}>
          {source.excerpt}
        </div>
      )}
    </div>
  )
}

function formatContent(text: string) {
  return text.split('\n').map((line, i) => {
    if (line.startsWith('**') && line.endsWith('**') && line.length > 4) {
      return <p key={i} style={{ fontWeight: 600, color: '#111827', margin: '6px 0 2px' }}>{line.slice(2, -2)}</p>
    }
    if (line.startsWith('• ')) return <p key={i} style={{ paddingLeft: 10, margin: '2px 0', color: '#374151' }}>• {line.slice(2)}</p>
    if (line.trim() === '') return <div key={i} style={{ height: 6 }} />
    return <p key={i} style={{ margin: '2px 0', color: '#374151', lineHeight: 1.65 }}>{line.replace(/\*\*/g, '')}</p>
  })
}

function MsgBubble({ msg }: { msg: Message }) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const isUser = msg.role === 'user'
  return (
    <div className="animate-fade-up" style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 18, flexDirection: isUser ? 'row-reverse' : 'row' }}>
      {/* Avatar */}
      <div style={{
        width: 32, height: 32, borderRadius: 9, flexShrink: 0,
        background: isUser ? '#1e293b' : 'linear-gradient(135deg, #6366f1, #818cf8)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        color: '#fff', fontSize: 12, fontWeight: 600,
      }}>
        {isUser ? '张' : 'AI'}
      </div>
      <div style={{ maxWidth: '68%', display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start' }}>
        <div style={{
          padding: '10px 14px', fontSize: 14, lineHeight: 1.65,
          borderRadius: isUser ? '14px 14px 3px 14px' : '3px 14px 14px 14px',
          background: isUser ? 'linear-gradient(135deg, #6366f1, #818cf8)' : '#fff',
          color: isUser ? '#fff' : '#1e293b',
          boxShadow: isUser ? '0 2px 12px rgba(99,102,241,0.25)' : '0 1px 6px rgba(0,0,0,0.06)',
        }}>
          {isUser ? msg.content : formatContent(msg.content)}
        </div>
        {msg.sources && (
          <div style={{ marginTop: 8 }}>
            <p style={{ fontSize: 11, color: '#9ca3af', marginBottom: 5 }}>知识库来源</p>
            {msg.sources.map(s => (
              <SourceTag key={s.id} source={s} expanded={expanded === s.id} onToggle={() => setExpanded(p => p === s.id ? null : s.id)} />
            ))}
          </div>
        )}
        <span style={{ fontSize: 11, color: '#d1d5db', marginTop: 4 }}>{msg.timestamp}</span>
      </div>
    </div>
  )
}

export default function KnowledgePage() {
  const [docs, setDocs] = useState<{ id: string; title: string; icon?: string; pages: number; tags?: string[]; desc?: string }[]>([])
  const [messages, setMessages] = useState<Message[]>([])
  const [sessions, setSessions] = useState<any[]>([])
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState(false)
  const [activeSession, setActiveSession] = useState('1')
  const [showKb, setShowKb] = useState(true)
  const [expandedDoc, setExpandedDoc] = useState<string | null>('doc1')
  const bottomRef = useRef<HTMLDivElement>(null)
  useEffect(() => { /* 文档列表待后端 API */ }, [])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, typing])

  const handleSend = async () => {
    const text = input.trim()
    if (!text || typing) return
    setInput('')
    const userMsg: Message = { id: makeId(), role: 'user', content: text, timestamp: nowTime() }
    setMessages(prev => [...prev, userMsg])
    setTyping(true)
    await new Promise(r => setTimeout(r, 1500))
    setTyping(false)
    setMessages(prev => [...prev, {
      id: makeId(), role: 'assistant', timestamp: nowTime(),
      content: '感谢您的提问！根据知识库中的专业资料，我为您整理了详细解答。如需进一步了解，请随时追问。',
      sources: [],
    }])
  }

  return (
    <AdminLayout>
      <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
        {/* Sessions sidebar */}
        <div style={{ width: 240, background: '#fff', borderRight: '1px solid #f1f5f9', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
          <div style={{ padding: '16px 14px 12px', borderBottom: '1px solid #f1f5f9' }}>
            <button
              className="btn btn-primary"
              style={{ width: '100%', fontSize: 13, padding: '8px 14px' }}
            >
              + 新建对话
            </button>
          </div>
          <p style={{ fontSize: 11, color: '#94a3b8', padding: '10px 14px 6px', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 500 }}>最近对话</p>
          <div className="flex-1 scrollbar-thin" style={{ overflowY: 'auto', padding: '0 8px 8px' }}>
            {sessions.map(s => (
              <button
                key={s.id}
                onClick={() => setActiveSession(s.id)}
                style={{
                  width: '100%', padding: '10px 12px', borderRadius: 10, border: 'none', textAlign: 'left', cursor: 'pointer',
                  background: activeSession === s.id ? '#eef2ff' : 'transparent',
                  marginBottom: 2, transition: 'background 0.12s',
                }}
                onMouseOver={e => { if (activeSession !== s.id) e.currentTarget.style.background = '#f8fafc' }}
                onMouseOut={e => { if (activeSession !== s.id) e.currentTarget.style.background = 'transparent' }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                  <span style={{ fontSize: 13, fontWeight: activeSession === s.id ? 600 : 400, color: activeSession === s.id ? '#6366f1' : '#1e293b' }}>{s.title}</span>
                  <span style={{ fontSize: 11, color: '#94a3b8' }}>{s.time}</span>
                </div>
                <span style={{ fontSize: 12, color: '#94a3b8' }}>{s.preview}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Chat area */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
          {/* Chat header */}
          <div style={{ background: '#fff', borderBottom: '1px solid #f1f5f9', padding: '12px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ width: 36, height: 36, borderRadius: 10, background: '#f5f3ff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 2C5.8 2 4 3.8 4 6c0 1.5.8 2.8 2 3.5V11h4V9.5c1.2-.7 2-2 2-3.5 0-2.2-1.8-4-4-4z" fill="#6366f1"/><path d="M6 11h4v1.5c0 .3-.2.5-.5.5h-3c-.3 0-.5-.2-.5-.5V11z" fill="#818cf8"/></svg>
              </div>
              <div>
                <p style={{ fontWeight: 600, fontSize: 14, color: '#1e293b' }}>烫发化学原理</p>
                <p style={{ fontSize: 12, color: '#94a3b8' }}>引用 2 个知识来源 · {messages.length} 条消息</p>
              </div>
            </div>
            <button
              onClick={() => setShowKb(s => !s)}
              style={{
                display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px', borderRadius: 999, fontSize: 12, fontWeight: 500, cursor: 'pointer',
                background: showKb ? '#ede9fe' : '#f1f5f9',
                color: showKb ? '#6366f1' : '#64748b',
                border: `1px solid ${showKb ? '#ddd6fe' : '#e2e8f0'}`,
                transition: 'all 0.15s',
              }}
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="1" width="4" height="10" rx="1" fill={showKb ? '#6366f1' : '#9ca3af'}/><rect x="7" y="1" width="4" height="5" rx="1" fill={showKb ? '#818cf8' : '#d1d5db'}/><rect x="7" y="7.5" width="4" height="3.5" rx="1" fill={showKb ? '#818cf8' : '#d1d5db'}/></svg>
              知识库
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 scrollbar-thin" style={{ overflowY: 'auto', padding: '20px', flex: 1 }}>
            <div style={{ maxWidth: 740, margin: '0 auto' }}>
              {messages.map(m => <MsgBubble key={m.id} msg={m} />)}
              {typing && (
                <div style={{ display: 'flex', gap: 10, marginBottom: 18 }} className="animate-fade-up">
                  <div style={{ width: 32, height: 32, borderRadius: 9, background: 'linear-gradient(135deg, #6366f1, #818cf8)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 12, fontWeight: 600 }}>AI</div>
                  <div style={{ padding: '10px 14px', borderRadius: '3px 14px 14px 14px', background: '#fff', boxShadow: '0 1px 6px rgba(0,0,0,0.06)' }}><TypingDots /></div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          </div>

          {/* Suggestions + Input */}
          <div style={{ background: '#fff', borderTop: '1px solid #f1f5f9', padding: '12px 20px 16px', flexShrink: 0 }}>
            <div style={{ maxWidth: 740, margin: '0 auto' }}>
              <div style={{ display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
                {['头发多孔性测试方法', '冷烫 vs 热烫区别', '染发过敏应急处理'].map(s => (
                  <button
                    key={s}
                    onClick={() => setInput(s)}
                    style={{ fontSize: 12, padding: '5px 12px', borderRadius: 999, background: '#f5f3ff', color: '#6366f1', border: '1px solid #e0d9ff', cursor: 'pointer', transition: 'all 0.12s' }}
                    onMouseOver={e => { e.currentTarget.style.background = '#ede9fe' }}
                    onMouseOut={e => { e.currentTarget.style.background = '#f5f3ff' }}
                  >
                    {s}
                  </button>
                ))}
              </div>
              <div style={{
                display: 'flex', alignItems: 'flex-end', gap: 10, padding: '10px 14px', borderRadius: 28,
                background: '#f8fafc', border: `1.5px solid ${input ? '#6366f1' : '#e2e8f0'}`,
                boxShadow: input ? '0 0 0 3px rgba(99,102,241,0.08)' : 'none', transition: 'all 0.15s',
              }}>
                <button style={{ background: 'none', border: 'none', color: '#94a3b8', padding: 6, flexShrink: 0 }}>
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M13.5 8.5L7.5 14.5C5.8 16.2 3.1 16.2 1.5 14.5C-.2 12.8-.2 10.1 1.5 8.5L9 1C10.2-.2 12.1-.2 13.3 1C14.5 2.2 14.5 4.1 13.3 5.3L6.3 12.3C5.6 13 4.5 13 3.8 12.3C3.1 11.6 3.1 10.5 3.8 9.8L10.3 3.3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
                </button>
                <textarea
                  value={input}
                  onChange={e => { setInput(e.target.value); e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px' }}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
                  placeholder="向美发助手提问，例如：如何避免烫发后发质干枯？"
                  rows={1}
                  style={{ flex: 1, border: 'none', outline: 'none', background: 'transparent', fontSize: 14, resize: 'none', lineHeight: 1.5, maxHeight: 120, color: '#1e293b' }}
                />
                <button
                  onClick={handleSend}
                  disabled={!input.trim() || typing}
                  style={{
                    width: 36, height: 36, borderRadius: '50%', border: 'none', flexShrink: 0,
                    background: input.trim() && !typing ? 'linear-gradient(135deg, #6366f1, #818cf8)' : '#e2e8f0',
                    color: input.trim() && !typing ? '#fff' : '#94a3b8',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: input.trim() && !typing ? 'pointer' : 'not-allowed',
                    transition: 'all 0.15s',
                    boxShadow: input.trim() && !typing ? '0 2px 10px rgba(99,102,241,0.3)' : 'none',
                  }}
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M13 1L1 5.5L6 7M13 1L8.5 13L6 7M13 1L6 7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </button>
              </div>
              <p style={{ textAlign: 'center', fontSize: 11, color: '#d1d5db', marginTop: 8 }}>AI 回复基于知识库内容，专业操作请咨询认证发型师</p>
            </div>
          </div>
        </div>

        {/* Knowledge panel */}
        {showKb && (
          <div className="animate-slide-right" style={{ width: 280, background: '#fff', borderLeft: '1px solid #f1f5f9', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
            <div style={{ padding: '14px 16px', borderBottom: '1px solid #f1f5f9', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <p style={{ fontWeight: 600, fontSize: 14, color: '#1e293b' }}>知识库</p>
                <p style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>4 份文档 · 826 页</p>
              </div>
              <button onClick={() => setShowKb(false)} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: 4 }}>
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M1 1L13 13M13 1L1 13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>
              </button>
            </div>
            {/* Stats */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, padding: '10px 12px', borderBottom: '1px solid #f1f5f9' }}>
              {[['3', '本次引用'], ['2', '相关文档']].map(([v, l]) => (
                <div key={l} style={{ textAlign: 'center', background: '#f5f3ff', borderRadius: 10, padding: '10px 0' }}>
                  <p style={{ fontSize: 18, fontWeight: 700, color: '#6366f1' }}>{v}</p>
                  <p style={{ fontSize: 11, color: '#7c3aed', marginTop: 2 }}>{l}</p>
                </div>
              ))}
            </div>
            {/* Docs */}
            <div className="flex-1 scrollbar-thin" style={{ overflowY: 'auto', padding: '10px 12px' }}>
              {docs.map(doc => (
                <div key={doc.id} style={{ borderRadius: 12, border: '1px solid #f1f5f9', marginBottom: 8, overflow: 'hidden' }}>
                  <button
                    style={{
                      width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', border: 'none', cursor: 'pointer', textAlign: 'left',
                      background: expandedDoc === doc.id ? '#faf5ff' : '#fff', transition: 'background 0.12s',
                    }}
                    onClick={() => setExpandedDoc(p => p === doc.id ? null : doc.id)}
                    onMouseOver={e => { if (expandedDoc !== doc.id) e.currentTarget.style.background = '#f9fafb' }}
                    onMouseOut={e => { if (expandedDoc !== doc.id) e.currentTarget.style.background = '#fff' }}
                  >
                    <span style={{ fontSize: 20 }}>{doc.icon}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ fontSize: 13, fontWeight: 500, color: '#1e293b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{doc.title}</p>
                      <p style={{ fontSize: 11, color: '#94a3b8', marginTop: 1 }}>{doc.pages} 页</p>
                    </div>
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" style={{ transform: expandedDoc === doc.id ? 'rotate(180deg)' : 'rotate(0)', transition: 'transform 0.18s', flexShrink: 0 }}>
                      <path d="M2 4L6 8L10 4" stroke="#9ca3af" strokeWidth="1.5" strokeLinecap="round"/>
                    </svg>
                  </button>
                  {expandedDoc === doc.id && (
                    <div style={{ padding: '0 12px 10px', background: '#faf5ff', borderTop: '1px solid #ede9fe' }}>
                      <p style={{ fontSize: 12, color: '#6b7280', lineHeight: 1.6, marginTop: 8 }}>{doc.desc}</p>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 8 }}>
                        {doc.tags.map(t => (
                          <span key={t} style={{ fontSize: 11, padding: '2px 8px', borderRadius: 999, background: '#ede9fe', color: '#6366f1' }}>{t}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
            {/* Upload */}
            <div style={{ padding: '12px', borderTop: '1px solid #f1f5f9' }}>
              <button className="btn btn-primary" style={{ width: '100%', fontSize: 13 }}>
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M6.5 1V9M4 4L6.5 1L9 4" stroke="white" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/><path d="M1 10.5H12" stroke="white" strokeWidth="1.4" strokeLinecap="round" opacity="0.6"/></svg>
                上传文档
              </button>
            </div>
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
