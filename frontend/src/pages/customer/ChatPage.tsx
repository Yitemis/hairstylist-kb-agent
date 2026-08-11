/** ChatPage - P1-6 重构版 (用 useChat hook + 抽离的子组件)。*/
import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getUser, clearAuth } from '../../utils/auth'
import { sendChat, listBranches, listBranchesNearby, listStylists, createOrder, getAvailableSlots, type ChatOption } from '../../utils/api'
import { showToast } from '../../utils/toast'
import { useChat } from '../../hooks/useChat'
import { MessageBubble } from '../../components/chat/MessageBubble'
import { ChatInput } from '../../components/chat/ChatInput'
import type { CardItem, AttachedImage } from '../../types/chat'

export default function CustomerChatPage() {
  const navigate = useNavigate()
  const user = getUser()
  // P1-4: 不再从 localStorage 取 user_id（攻击者可改）
  // 后端用 HttpOnly Cookie 自动识别当前用户
  const [serverUser, setServerUser] = useState<{ id: number; role: string } | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [step, setStep] = useState<'branch' | 'stylist' | 'time' | 'done'>('branch')
  const [selectedBranch, setSelectedBranch] = useState<CardItem | null>(null)
  const [hasGreeted, setHasGreeted] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  // 启动时从 /api/auth/me 拿真实 user（不依赖 localStorage）
  useEffect(() => {
    fetch('/api/auth/me', { credentials: 'include' })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.id) setServerUser(data) })
      .catch(() => {})
  }, [])

  // 业务相关：分店 → 发型师 → 时段 的预订流程
  async function handleCardSelect(card: CardItem) {
    if (step === 'branch' && card.title) {
      setSelectedBranch(card)
      setStep('stylist')
      await chat.send({ message: `已选分店：${card.title}` })
    } else if (step === 'stylist') {
      setStep('time')
      await chat.send({ message: `已选发型师：${card.title}` })
    }
  }

  const chat = useChat({
    endpoint: async (msg, opts) => {
      // 优先用带位置的分店列表
      if (!hasGreeted) return { answer: '您好，我是您的美发顾问，请问需要什么服务？', options: [] }
      // P1-4: 不再传 user_id（后端从 cookie 取，杜绝 localStorage 篡改）
      return sendChat(msg, opts)
    },
    sessionId: 'default',
    userId: serverUser?.id || 0,
  })

  // 初始问候
  useEffect(() => {
    if (!hasGreeted && user) {
      setHasGreeted(true)
      chat.send({ message: '__greet__' })
    }
  }, [user, hasGreeted, chat])

  // 自动滚到底
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [chat.messages])

  if (!user) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <p>请先登录</p>
        <button onClick={() => navigate('/customer/login')}>去登录</button>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: '#f8fafc' }}>
      {/* 顶部 */}
      <header style={{ padding: '14px 20px', background: '#fff', borderBottom: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 36, height: 36, borderRadius: 10, background: 'linear-gradient(135deg,#6366f1,#818cf8)' }} />
          <div>
            <h1 style={{ fontSize: 16, fontWeight: 700, color: '#1e293b', margin: 0 }}>美发智能顾问</h1>
            <p style={{ fontSize: 12, color: '#94a3b8', margin: 0 }}>{user.name || user.phone}</p>
          </div>
        </div>
        <button onClick={() => { clearAuth(); navigate('/customer/login') }} style={{ fontSize: 12, color: '#64748b', background: 'none', border: 'none', cursor: 'pointer' }}>退出</button>
      </header>

      {/* 消息列表 */}
      <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
        {chat.messages.map(msg => (
          <MessageBubble
            key={msg.id}
            msg={msg}
            isStreaming={chat.streamingMsgId === msg.id}
            onCardSelect={handleCardSelect}
          />
        ))}
      </div>

      {/* 输入区 */}
      <ChatInput
        value={chat.input}
        onChange={chat.setInput}
        onSend={() => chat.send({ message: chat.input, images: chat.attachedImages })}
        onAttach={(file) => {
          const url = URL.createObjectURL(file)
          chat.setAttachedImages([...chat.attachedImages, { id: Math.random().toString(36).slice(2), url }])
        }}
        onRemoveImage={chat.removeImage}
        images={chat.attachedImages}
        disabled={chat.streamState !== 'idle'}
      />
    </div>
  )
}
