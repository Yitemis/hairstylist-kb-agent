import { useState, useRef, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { getUser, clearAuth, getToken } from '../../utils/auth'
import { sendChatStream, listBranches, type ChatOption } from '../../utils/api'
import { showToast } from '../../utils/toast'

interface Message {
  id: string
  role: 'ai' | 'user'
  text: string
  time: string
  options?: ChatOption[]  // 可点击选项（点选卡片）
}

function makeId() { return Math.random().toString(36).slice(2) }
function nowTime() { return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }

function AiAvatar() {
  return (
    <div style={{ width: 34, height: 34, borderRadius: 10, flexShrink: 0, background: 'linear-gradient(135deg, #6366f1, #818cf8)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M8 2C5.8 2 4 3.8 4 6c0 1.5.8 2.8 2 3.5V11h4V9.5c1.2-.7 2-2 2-3.5 0-2.2-1.8-4-4-4z" fill="white" />
      </svg>
    </div>
  )
}

function UserAvatar({ name }: { name: string }) {
  return (
    <div style={{ width: 34, height: 34, borderRadius: 10, flexShrink: 0, background: '#1e293b', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 13, fontWeight: 600 }}>
      {name.slice(-1)}
    </div>
  )
}

export default function CustomerChatPage() {
  const nav = useNavigate()
  const [searchParams] = useSearchParams()
  const editOrderId = searchParams.get('edit')
  const user = getUser()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [loadingHistory, setLoadingHistory] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, typing])

  // 加载历史对话（Agent 长期记忆）
  useEffect(() => {
    if (!user) return
    setLoadingHistory(true)
    fetch('/api/chat/history', {
      headers: { 'Authorization': `Bearer ${getToken()}` },
    })
      .then(r => r.json())
      .then(data => {
        const list = (data.data?.messages || data.messages || []) as any[]
        const loaded: Message[] = list.map((m: any) => ({
          id: String(m.id),
          role: m.role,
          text: m.content,
          time: new Date(m.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
        }))
        if (loaded.length === 0) {
          // 没有历史，显示欢迎语
          loaded.push({
            id: makeId(), role: 'ai',
            text: '你好！我是美发智能顾问，可以帮你解答美发知识或者帮你一步步预约门店服务。请问今天有什么可以帮你的？',
            time: nowTime(),
          })
        }
        setMessages(loaded)
      })
      .catch(e => console.error('加载历史失败', e))
      .finally(() => setLoadingHistory(false))
  }, [user?.id])

  // 自动从长期记忆中加载"已注入的事实"，但显示在欢迎语里
  const [userFacts, setUserFacts] = useState<Array<{ key: string; value: string }>>([])
  useEffect(() => {
    if (!user) return
    fetch('/api/user/facts', {
      headers: { 'Authorization': `Bearer ${getToken()}` },
    })
      .then(r => r.json())
      .then(data => {
        if (Array.isArray(data)) setUserFacts(data)
      })
      .catch(() => {})
  }, [user?.id])

  // 如果从"继续编辑"按钮进来，自动让 Agent 继续编辑草稿（防重）
  const editTriggeredRef = useRef<string | null>(null)
  useEffect(() => {
    if (!editOrderId || !user) return
    if (editTriggeredRef.current === editOrderId) return
    editTriggeredRef.current = editOrderId
    // 短暂延迟等 history 加载完
    setTimeout(() => {
      handleSend('继续编辑')
    }, 800)
    // 清掉 search param，避免刷新又触发
    setTimeout(() => {
      window.history.replaceState({}, '', '/customer/chat')
    }, 100)
  }, [editOrderId, user?.id])

  const addMsg = (msg: Partial<Message>) => {
    const full: Message = { id: makeId(), time: nowTime(), ...msg } as Message
    setMessages(prev => [...prev, full])
  }

  const handleSend = async (overrideText?: string) => {
    const text = (overrideText ?? input).trim()
    if (!text || typing || !user) return
    if (!overrideText) setInput('')
    addMsg({ role: 'user', text })
    setTyping(true)
    // 准备一个 AI 消息占位，后续流式拼接
    const aiMsgId = Date.now() + Math.random()
    let aiText = ''
    let aiOptions: any[] | undefined
    let aiMode: string | undefined
    addMsg({ id: aiMsgId as any, role: 'ai', text: '' })
    try {
      await sendChatStream(text, user.id!, (e) => {
        if (e.event === 'text') {
          aiText += e.data.delta || ''
          // 实时更新消息（更新最后一条 AI 消息）
          setMessages((prev) => prev.map((m) => 
            m.id === aiMsgId ? { ...m, text: aiText } : m
          ))
        } else if (e.event === 'tool_call') {
          // 显示工具调用状态
          setMessages((prev) => prev.map((m) => 
            m.id === aiMsgId ? { ...m, text: aiText + `

🔧 正在调用 ${e.data.name}...` } : m
          ))
        } else if (e.event === 'options') {
          aiOptions = e.data.items
        } else if (e.event === 'done') {
          aiMode = e.data.mode
          setMessages((prev) => prev.map((m) => 
            m.id === aiMsgId ? { ...m, text: aiText, options: aiOptions || e.data.options, mode: aiMode } : m
          ))
        } else if (e.event === 'error') {
          showToast(e.data.message || '对话失败', 'error')
        }
      })
    } catch (e: any) {
      showToast(e?.detail || e?.message || '网络错误，请重试', 'error')
    } finally {
      setTyping(false)
    }
  }

  // 点击选项卡片：把 title 当作用户输入发送
  const handleOptionClick = (opt: ChatOption) => {
    handleSend(opt.title)
  }

  const handleLogout = () => {
    clearAuth()
    nav('/customer/login')
  }

  return (
    <div className="mobile-shell flex flex-col" style={{ height: '100vh', background: '#f8fafc', position: 'relative' }}>
      {/* Nav */}
      <div className="mobile-nav" style={{ justifyContent: 'space-between' }}>
        <button style={{ background: 'none', border: 'none', padding: 6 }} onClick={() => setDrawerOpen(true)}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M2 5H18M2 10H18M2 15H18" stroke="#1e293b" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#10b981' }} />
          <span style={{ fontWeight: 600, fontSize: 16, color: '#1e293b' }}>美发智能顾问</span>
        </div>
        <button style={{ background: 'none', border: 'none', padding: 6, color: '#6366f1' }} onClick={() => nav('/customer/orders')}>
          <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
            <rect x="3" y="2" width="16" height="18" rx="2" stroke="currentColor" strokeWidth="1.6" />
            <path d="M7 7H15M7 11H15M7 15H11" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      {/* Drawer */}
      {drawerOpen && (
        <>
          <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 30 }} onClick={() => setDrawerOpen(false)} />
          <div style={{ position: 'absolute', top: 0, left: 0, bottom: 0, width: 260, background: '#1e293b', zIndex: 40, padding: '20px' }}>
            <div style={{ padding: '20px 0', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
              <div style={{ width: 52, height: 52, borderRadius: 16, background: 'linear-gradient(135deg, #6366f1, #818cf8)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 20, fontWeight: 700, marginBottom: 12 }}>
                {user?.name?.slice(-1) || '?'}
              </div>
              <p style={{ color: '#f1f5f9', fontWeight: 600, fontSize: 16 }}>{user?.name || '游客'}</p>
              <p style={{ color: '#64748b', fontSize: 13, marginTop: 2 }}>{user?.phone}</p>
            </div>
            <button onClick={() => { setDrawerOpen(false); nav('/customer/orders') }} style={{ width: '100%', padding: '11px 14px', borderRadius: 10, border: 'none', background: 'transparent', color: '#94a3b8', fontSize: 14, textAlign: 'left', marginTop: 12, cursor: 'pointer' }}>
              我的订单
            </button>
            <button onClick={() => {
              if (!confirm('确定清空所有对话历史？')) return
              fetch('/api/chat/history', {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${getToken()}` },
              })
                .then(r => r.json())
                .then(() => {
                  setMessages([{
                    id: makeId(), role: 'ai',
                    text: '对话已清空。有什么可以帮你的？',
                    time: nowTime(),
                  }])
                  showToast('已清空', 'success')
                  setDrawerOpen(false)
                })
                .catch(() => showToast('清空失败', 'error'))
            }} style={{ width: '100%', padding: '11px 14px', borderRadius: 10, border: 'none', background: 'transparent', color: '#f59e0b', fontSize: 14, textAlign: 'left', marginTop: 4, cursor: 'pointer' }}>
              清空对话
            </button>
            <button onClick={handleLogout} style={{ width: '100%', padding: '11px 14px', borderRadius: 10, border: 'none', background: 'transparent', color: '#ef4444', fontSize: 14, textAlign: 'left', cursor: 'pointer' }}>
              退出登录
            </button>
          </div>
        </>
      )}

      {/* Messages */}
      <div className="flex-1 scrollbar-hide" style={{ overflowY: 'auto', padding: '16px 14px' }}>
        {/* 长期记忆已记忆的事实 */}
        {userFacts.length > 0 && (
          <div style={{
            background: 'linear-gradient(135deg, #f5f3ff 0%, #ede9fe 100%)',
            borderRadius: 12,
            padding: '10px 14px',
            marginBottom: 14,
            border: '1px solid #e0d9ff',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M7 1a3 3 0 0 0-3 3v1H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1h-1V4a3 3 0 0 0-3-3zM5 4a2 2 0 1 1 4 0v1H5V4z" fill="#6366f1" />
              </svg>
              <span style={{ fontSize: 12, color: '#4c1d95', fontWeight: 600 }}>我已记住你的：</span>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {userFacts.slice(0, 5).map((f, i) => (
                <span key={i} style={{
                  fontSize: 11,
                  padding: '2px 8px',
                  borderRadius: 999,
                  background: '#fff',
                  color: '#6366f1',
                  border: '1px solid #c7d2fe',
                }}>
                  {f.key}: {f.value.length > 20 ? f.value.slice(0, 20) + '...' : f.value}
                </span>
              ))}
            </div>
          </div>
        )}
        {messages.map(msg => (
          <div key={msg.id} style={{ display: 'flex', flexDirection: msg.role === 'user' ? 'row-reverse' : 'row', alignItems: 'flex-start', gap: 10, marginBottom: 16 }}>
            {msg.role === 'ai' ? <AiAvatar /> : <UserAvatar name={user?.name || '我'} />}
            <div style={{ maxWidth: '78%' }}>
              <div className={msg.role === 'ai' ? 'bubble-ai' : 'bubble-user'}>
                {msg.text.split('\n').map((line, i) => (
                  <span key={i}>{line}{i < msg.text.split('\n').length - 1 && <br />}</span>
                ))}
              </div>
              {/* 可点击选项卡片 */}
              {msg.options && msg.options.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
                  {msg.options.map((opt, i) => (
                    <button
                      key={`${opt.type}-${opt.id}-${i}`}
                      onClick={() => handleOptionClick(opt)}
                      disabled={typing}
                      style={{
                        background: '#fff',
                        border: '1.5px solid #e0e7ff',
                        borderRadius: 10,
                        padding: '10px 12px',
                        textAlign: 'left',
                        cursor: typing ? 'not-allowed' : 'pointer',
                        opacity: typing ? 0.5 : 1,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: 8,
                        transition: 'all 0.15s',
                      }}
                      onMouseOver={e => { (e.currentTarget as HTMLElement).style.borderColor = '#6366f1'; (e.currentTarget as HTMLElement).style.background = '#f5f3ff' }}
                      onMouseOut={e => { (e.currentTarget as HTMLElement).style.borderColor = '#e0e7ff'; (e.currentTarget as HTMLElement).style.background = '#fff' }}
                    >
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <p style={{ fontWeight: 600, fontSize: 14, color: '#1e293b', marginBottom: 2 }}>{opt.title}</p>
                        {opt.subtitle && <p style={{ fontSize: 12, color: '#64748b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{opt.subtitle}</p>}
                      </div>
                      {opt.badge && (
                        <span style={{ fontSize: 11, padding: '3px 8px', borderRadius: 999, background: '#eef2ff', color: '#6366f1', fontWeight: 500, whiteSpace: 'nowrap' }}>{opt.badge}</span>
                      )}
                    </button>
                  ))}
                </div>
              )}
              <p style={{ fontSize: 11, color: '#cbd5e1', marginTop: 4, textAlign: msg.role === 'user' ? 'right' : 'left' }}>{msg.time}</p>
            </div>
          </div>
        ))}
        {typing && (
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 16 }}>
            <AiAvatar />
            <div className="bubble-ai">
              <div style={{ display: 'flex', gap: 5, padding: '4px 0' }}>
                <span className="dot-bounce" style={{ width: 7, height: 7, borderRadius: '50%', background: '#6366f1', display: 'inline-block' }} />
                <span className="dot-bounce" style={{ width: 7, height: 7, borderRadius: '50%', background: '#6366f1', display: 'inline-block' }} />
                <span className="dot-bounce" style={{ width: 7, height: 7, borderRadius: '50%', background: '#6366f1', display: 'inline-block' }} />
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ background: '#fff', borderTop: '1px solid #f1f5f9', padding: '10px 14px', display: 'flex', alignItems: 'flex-end', gap: 10 }}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
          placeholder="输入你的问题或预约需求..."
          rows={1}
          style={{ flex: 1, border: '1.5px solid #e2e8f0', borderRadius: 22, padding: '9px 16px', fontSize: 15, outline: 'none', resize: 'none', background: '#f8fafc', color: '#1e293b', lineHeight: 1.5, maxHeight: 96 }}
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || typing}
          style={{
            width: 42, height: 42, borderRadius: '50%', border: 'none', flexShrink: 0,
            background: input.trim() && !typing ? 'linear-gradient(135deg, #6366f1, #818cf8)' : '#e2e8f0',
            color: input.trim() && !typing ? '#fff' : '#94a3b8',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: input.trim() && !typing ? 'pointer' : 'not-allowed',
          }}
        >
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M16 2L2 7L8 9M16 2L11 16L8 9M16 2L8 9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  )
}
