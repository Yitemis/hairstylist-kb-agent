import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getUser, clearAuth } from '../../utils/auth'
import { sendChat, listBranches, listBranchesNearby, listStylists, createOrder, getAvailableSlots, type ChatOption } from '../../utils/api'
import { showToast } from '../../utils/toast'

/* ── Types ─────────────────────────────────────────── */
type MessageType = 'text' | 'card-list'
type StreamState = 'idle' | 'thinking' | 'streaming' | 'done' | 'error'

interface CardItem { id: string; title: string; subtitle: string; badge?: string }
interface AttachedImage { id: string; url: string }

interface Message {
  id: string
  role: 'ai' | 'user'
  type: MessageType
  text?: string
  streamingText?: string
  thinking?: string
  cards?: CardItem[]
  images?: string[]
  time: string
  stats?: { tokens: number; ms: number }
  error?: boolean
}

/* ── Mock data ──────────────────────────────────────── */
const BRANCHES: CardItem[] = [
  { id: 'b1', title: '三里屯旗舰店', subtitle: '朝阳区三里屯路19号', badge: '5 位发型师' },
  { id: 'b2', title: '国贸中心店',   subtitle: '朝阳区建国路87号',   badge: '3 位发型师' },
  { id: 'b3', title: '西单商场店',   subtitle: '西城区西单北大街120号', badge: '4 位发型师' },
]
const STYLISTS: CardItem[] = [
  { id: 's1', title: '陈晓磊', subtitle: '擅长烫发·染发·10年经验', badge: '¥200/h' },
  { id: 's2', title: '王芳芳', subtitle: '擅长剪发·造型·8年经验',  badge: '¥160/h' },
  { id: 's3', title: '刘志远', subtitle: '擅长染色·护理·6年经验',  badge: '¥140/h' },
]
function makeId() { return Math.random().toString(36).slice(2) }
function nowTime() { return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }

/* ── UI helpers ─────────────────────────────────────── */
function AiAvatar() {
  return (
    <div style={{ width: 34, height: 34, borderRadius: 10, flexShrink: 0, background: 'linear-gradient(135deg,#6366f1,#818cf8)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M8 2C5.8 2 4 3.8 4 6c0 1.5.8 2.8 2 3.5V11h4V9.5c1.2-.7 2-2 2-3.5 0-2.2-1.8-4-4-4z" fill="white" />
        <path d="M6 11h4v1.5c0 .3-.2.5-.5.5h-3c-.3 0-.5-.2-.5-.5V11z" fill="rgba(255,255,255,0.65)" />
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
function TypingDots() {
  return (
    <div style={{ display: 'flex', gap: 5, padding: '4px 0' }}>
      {[0,1,2].map(i => (
        <span key={i} className="dot-bounce" style={{ width: 7, height: 7, borderRadius: '50%', background: '#6366f1', display: 'inline-block', animationDelay: `${i * 0.15}s` }} />
      ))}
    </div>
  )
}
function CardList({ cards, onSelect }: { cards: CardItem[]; onSelect: (c: CardItem) => void }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 4 }}>
      {cards.map(c => (
        <button key={c.id} onClick={() => onSelect(c)} style={{ background: '#fff', border: '1.5px solid #e0e7ff', borderRadius: 12, padding: '10px 14px', textAlign: 'left', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between', transition: 'all 0.15s' }}
          onMouseOver={e => { e.currentTarget.style.borderColor='#6366f1'; e.currentTarget.style.background='#f5f3ff' }}
          onMouseOut={e => { e.currentTarget.style.borderColor='#e0e7ff'; e.currentTarget.style.background='#fff' }}>
          <div>
            <p style={{ fontWeight: 600, fontSize: 14, color: '#1e293b', marginBottom: 2 }}>{c.title}</p>
            <p style={{ fontSize: 12, color: '#64748b' }}>{c.subtitle}</p>
          </div>
          {c.badge && <span style={{ fontSize: 11, padding: '3px 8px', borderRadius: 999, background: '#eef2ff', color: '#6366f1', fontWeight: 500, whiteSpace: 'nowrap', marginLeft: 8 }}>{c.badge}</span>}
        </button>
      ))}
    </div>
  )
}

function MessageBubble({ msg, onCardSelect, onRetry, isStreaming }: {
  msg: Message; onCardSelect: (c: CardItem) => void; onRetry?: () => void; isStreaming?: boolean
}) {
  const isUser = msg.role === 'user'
  const displayText = msg.streamingText ?? msg.text ?? ''

  return (
    <div className="animate-fade-up" style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 16, flexDirection: isUser ? 'row-reverse' : 'row' }}>
      {isUser ? <UserAvatar name="我" /> : <AiAvatar />}
      <div style={{ maxWidth: '78%', display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start' }}>

        {/* Thinking block */}
        {!isUser && msg.thinking && (
          <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 10, padding: '8px 12px', marginBottom: 8 }}>
            <p style={{ fontSize: 12, color: '#94a3b8', fontStyle: 'italic', lineHeight: 1.5 }}>💭 {msg.thinking}</p>
          </div>
        )}

        {/* Error card */}
        {msg.error && (
          <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 12, padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 10 }}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="#ef4444" strokeWidth="1.4"/><path d="M8 4.5V8.5M8 10.5V11" stroke="#ef4444" strokeWidth="1.4" strokeLinecap="round"/></svg>
            <p style={{ fontSize: 13, color: '#dc2626', flex: 1 }}>回复生成失败，请重试</p>
            {onRetry && <button onClick={onRetry} style={{ background: '#ef4444', color: '#fff', border: 'none', borderRadius: 8, padding: '5px 10px', fontSize: 12, cursor: 'pointer' }}>重试</button>}
          </div>
        )}

        {/* Main bubble */}
        {!msg.error && (msg.type === 'text' || msg.streamingText !== undefined) && (
          <div style={{ padding: '10px 14px', fontSize: 15, lineHeight: 1.65, borderRadius: isUser ? '16px 16px 4px 16px' : '4px 16px 16px 16px', background: isUser ? 'linear-gradient(135deg,#6366f1,#818cf8)' : '#f1f5f9', color: isUser ? '#fff' : '#1e293b', boxShadow: isUser ? '0 2px 12px rgba(99,102,241,0.25)' : 'none', wordBreak: 'break-word' }}>
            {/* User images */}
            {isUser && msg.images && msg.images.length > 0 && (
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: displayText ? 8 : 0 }}>
                {msg.images.map((url, i) => <img key={i} src={url} alt="" style={{ width: 80, height: 80, borderRadius: 12, objectFit: 'cover' }} />)}
              </div>
            )}
            {displayText && (
              <span style={{ whiteSpace: 'pre-wrap' }}>
                {displayText.replace(/\*\*(.*?)\*\*/g, '$1')}
                {isStreaming && <span style={{ display: 'inline-block', width: 2, height: 14, background: '#6366f1', marginLeft: 2, verticalAlign: 'middle', animation: 'blink-cur 0.8s step-end infinite' }} />}
              </span>
            )}
            {!isUser && msg.images && msg.images.map((url, i) => <img key={i} src={url} alt="" style={{ display: 'block', width: '100%', borderRadius: 12, marginTop: 8 }} />)}
          </div>
        )}

        {/* Cards */}
        {msg.type === 'card-list' && msg.cards && <CardList cards={msg.cards} onSelect={onCardSelect} />}

        {/* Stats */}
        {msg.stats && !isStreaming && (
          <p style={{ fontSize: 11, color: '#d1d5db', marginTop: 4 }}>已生成完 · {msg.stats.tokens} token · {(msg.stats.ms / 1000).toFixed(1)}s</p>
        )}
        {!msg.stats && !msg.error && (
          <span style={{ fontSize: 11, color: '#d1d5db', marginTop: 4 }}>{msg.time}</span>
        )}
      </div>
    </div>
  )
}

function ImageStrip({ images, onRemove }: { images: AttachedImage[]; onRemove: (id: string) => void }) {
  if (!images.length) return null
  return (
    <div style={{ display: 'flex', gap: 8, padding: '8px 14px 4px', overflowX: 'auto', scrollbarWidth: 'none' }}>
      {images.map(img => (
        <div key={img.id} style={{ position: 'relative', flexShrink: 0 }}>
          <img src={img.url} alt="" style={{ width: 64, height: 64, borderRadius: 8, objectFit: 'cover', display: 'block' }} />
          <button onClick={() => onRemove(img.id)} style={{ position: 'absolute', top: -6, right: -6, width: 18, height: 18, background: '#ef4444', color: '#fff', border: 'none', borderRadius: '50%', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700 }}>×</button>
        </div>
      ))}
    </div>
  )
}

/* ── Main ───────────────────────────────────────────── */
export default function CustomerChatPage() {
  const nav = useNavigate()
  const user = getUser()
  const [messages, setMessages] = useState<Message[]>([])
  const [hasGreeted, setHasGreeted] = useState(() => !!localStorage.getItem('chat_greeted_v1'))
  // 加载时 AI 主动发欢迎语 (调真实 /api/chat)
  useEffect(() => {
    if (hasGreeted) return
    setHasGreeted(true); localStorage.setItem('chat_greeted_v1', String(Date.now()))
    const greet = async () => {
      const u = getUser()
      const userId = (u as any)?.id || parseInt(localStorage.getItem('user_id') || '1')
      try {
        const resp = await sendChat('你好，请介绍你自己', userId, 'greeting')
        const respData: any = resp.data || resp; const inner: any = respData.data || respData
        const text: string = inner.answer || '你好！我是美发智能顾问 ✂️'
        const msgId = makeId()
        setMessages([{ id: msgId, role: 'ai', type: 'text', time: nowTime(), text, thinking: '正在为你准备欢迎语...' }])
        // type out
        let acc = ''
        for (const i of text) {
          acc += i
          setMessages(prev => prev.map(m => m.id === msgId ? { ...m, text: acc } : m))
          await new Promise(r => setTimeout(r, 25))
        }
      } catch (e) { /* silent */ }
    }
    greet()
  }, [hasGreeted])

  const [input, setInput] = useState('')
  const [attachedImages, setAttachedImages] = useState<AttachedImage[]>([])
  const [streamState, setStreamState] = useState<StreamState>('idle')
  const [streamingMsgId, setStreamingMsgId] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [step, setStep] = useState<'branch'|'stylist'|'time'|'done'>('branch')
  const [selectedBranch, setSelectedBranch] = useState<CardItem | null>(null)
  const stopRef = useRef(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const cameraRef = useRef<HTMLInputElement>(null)
  const albumRef  = useRef<HTMLInputElement>(null)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, streamState])

  // 浏览器 Geolocation 拿用户位置 (失败降级)
  const getUserLocation = (): Promise<{ lat: number; lng: number } | null> => {
    return new Promise((resolve) => {
      if (!navigator.geolocation) return resolve(null)
      navigator.geolocation.getCurrentPosition(
        (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
        () => resolve(null),
        { timeout: 5000, maximumAge: 60000 },
      )
    })
  }

  // 计算两点距离 (km, 用 Haversine)
  const haversineKm = (a: { lat: number; lng: number }, b: { lat: number; lng: number }) => {
    const R = 6371
    const dLat = (b.lat - a.lat) * Math.PI / 180
    const dLng = (b.lng - a.lng) * Math.PI / 180
    const x = Math.sin(dLat / 2) ** 2 +
      Math.cos(a.lat * Math.PI / 180) * Math.cos(b.lat * Math.PI / 180) * Math.sin(dLng / 2) ** 2
    return 2 * R * Math.asin(Math.sqrt(x))
  }

  /* SSE simulation */
  const streamAiReply = async (idx: number, extraCards?: CardItem[]) => {
    stopRef.current = false
    const msgId = makeId()
    const startMs = Date.now()

    setStreamState('thinking')
    setMessages(prev => [...prev, { id: msgId, role: 'ai', type: 'text', time: nowTime(), thinking: '正在分析您的请求...', streamingText: '' }])
    setStreamingMsgId(msgId)
    await new Promise(r => setTimeout(r, 600))

    if (stopRef.current) {
      setMessages(prev => prev.map(m => m.id === msgId ? { ...m, streamingText: undefined, text: '已中断' } : m))
      setStreamState('idle'); setStreamingMsgId(null); return
    }

    setStreamState('streaming')
    const user = getUser()
    const userId = (user as any)?.id || parseInt(localStorage.getItem('user_id') || '1')
    const finalSessionId = (() => { try { return JSON.parse(localStorage.getItem('user') || '{}').session_id || 'default' } catch { return 'default' } })()
    try {
      console.log('[ChatPage] sendChat start, userId=' + userId + ', sessionId=' + finalSessionId)
      const resp = await sendChat(input, userId, finalSessionId)
      console.log('[ChatPage] sendChat resp=', JSON.stringify(resp).slice(0, 200))
      const respData: any = resp.data || resp
      const inner: any = (respData && respData.data) || respData
      console.log('[ChatPage] resp keys=', Object.keys(resp || {}), 'inner keys=', Object.keys(inner || {}))
      if (!inner) {
        throw new Error('empty inner response: ' + JSON.stringify(resp).slice(0, 200))
      }
      const answer: string = inner.answer || (typeof resp === 'string' ? resp : JSON.stringify(resp))
      const mode: string = inner.mode || 'casual'
      const options: ChatOption[] = inner.options || []

      // type out the answer
      let acc = ''
      for (let i = 0; i < answer.length; i++) {
        if (stopRef.current) {
          showToast('生成已中断', 'info')
          setMessages(prev => prev.map(m => m.id === msgId ? { ...m, streamingText: undefined, text: acc } : m))
          setStreamState('idle'); setStreamingMsgId(null); return
        }
        acc += answer[i]
        setMessages(prev => prev.map(m => m.id === msgId ? { ...m, streamingText: acc } : m))
        await new Promise(r => setTimeout(r, 28))
      }

      const ms = Date.now() - startMs
      // save the mode (e.g. booking) on the bubble
      setMessages(prev => prev.map(m => m.id === msgId ? { ...m, streamingText: undefined, text: acc, stats: { tokens: Math.round(acc.length * 0.72 + 12), ms }, mode: mode } : m))

      // booking mode → 按用户位置取最近分店
      if (mode === 'booking' && options.length === 0) {
        try {
          const loc = await getUserLocation()
          let list: any[] = []
          if (loc) {
            const r = await listBranchesNearby(loc.lat, loc.lng)
            list = r || []
          } else {
            // 拒绝定位/无定位 → 降级到全部分店
            const r = await listBranches()
            list = r.data || []
          }
          const cards: CardItem[] = list.map((b: any) => {
            let badge = b.is_active !== false ? '营业中' : '已下架'
            if (loc && b.latitude != null && b.longitude != null) {
              const km = haversineKm(loc, { lat: Number(b.latitude), lng: Number(b.longitude) })
              badge = km < 1 ? `营业中 · ${Math.round(km * 1000)} m` : `营业中 · ${km.toFixed(1)} km`
            }
            return { id: String(b.id), title: b.name, subtitle: b.address || '', badge }
          })
          setMessages(prev => [...prev, { id: makeId(), role: 'ai', type: 'card-list', cards, time: nowTime() }])
          if (loc) {
            setMessages(prev => [...prev, { id: makeId(), role: 'ai', type: 'text', time: nowTime(), text: '📍 已按你的位置显示最近的分店' }])
          }
        } catch (e) { /* silent */ }
      } else if (options.length > 0) {
        const cards: CardItem[] = options.map((o: ChatOption) => ({ id: String(o.id || o.title), title: o.title, subtitle: o.subtitle || '', badge: o.badge }))
        setMessages(prev => [...prev, { id: makeId(), role: 'ai', type: 'card-list', cards, time: nowTime() }])
      }
    } catch (e: any) {
      console.error('chat error details:', e?.response?.data || e?.message || e)
      const errMsg = e?.response?.data?.detail || e?.response?.data?.message || e?.message || '网络错误'
      setMessages(prev => prev.map(m => m.id === msgId ? { ...m, streamingText: undefined, text: '回复生成失败：' + errMsg, error: true } : m))
    } finally {
      setStreamState('idle'); setStreamingMsgId(null)
    }
  }
  const handleStop = () => { stopRef.current = true }

  const handleImageFiles = (files: FileList | null) => {
    if (!files) return
    Array.from(files).slice(0, 3 - attachedImages.length).forEach(f => {
      const reader = new FileReader()
      reader.onload = e => setAttachedImages(prev => [...prev, { id: makeId(), url: e.target?.result as string }])
      reader.readAsDataURL(f)
    })
  }

  const handleSend = async () => {
    const text = input.trim()
    if ((!text && !attachedImages.length) || streamState !== 'idle') return
    const imgUrls = attachedImages.map(i => i.url)
    setMessages(prev => [...prev, { id: makeId(), role: 'user', type: 'text', time: nowTime(), text: text || undefined, images: imgUrls.length ? imgUrls : undefined }])
    setInput(''); setAttachedImages([])
    await streamAiReply(imgUrls.length > 0 ? 1 : 0)
  }

  const handleCardSelect = async (card: CardItem) => {
    if (streamState !== 'idle') return
    const u = getUser()
    const userId = (u as any)?.id || parseInt(localStorage.getItem('user_id') || '1')

    if (step === 'branch') {
      // 选分店 → 调 listStylists(branch_id) 真实 API
      setSelectedBranch(card)
      setMessages(prev => [...prev, { id: makeId(), role: 'user', type: 'text', text: `选择「${card.title}」`, time: nowTime() }])
      setStep('stylist')
      setStreamState('thinking')
      try {
        const r: any = await listStylists(Number(card.id))
        const list: any[] = r.data || (Array.isArray(r) ? r : [])
        const cards: CardItem[] = list.map((s) => ({ id: String(s.id), title: s.name, subtitle: s.specialties || '', badge: s.is_active !== false ? '在岗' : '休息' }))
        setMessages(prev => [...prev,
          { id: makeId(), role: 'ai', type: 'text', time: nowTime(), text: `${card.title} 共有 ${cards.length} 位发型师：` },
          { id: makeId(), role: 'ai', type: 'card-list', time: nowTime(), cards: cards.length > 0 ? cards : [{ id: '0', title: '暂无可用发型师', subtitle: '请联系门店', badge: '请稍后' }] },
        ])
      } catch (e) {
        setMessages(prev => [...prev, { id: makeId(), role: 'ai', type: 'text', time: nowTime(), text: `查询发型师失败: ${(e as any)?.message}` }])
      } finally {
        setStreamState('idle')
      }
    } else if (step === 'stylist') {
      // 选发型师 → 调 getAvailableSlots 真实 API
      setMessages(prev => [...prev, { id: makeId(), role: 'user', type: 'text', text: `选择「${card.title}」`, time: nowTime() }])
      setStep('time')
      setStreamState('thinking')
      try {
        const branchId = selectedBranch ? Number(selectedBranch.id) : 0
        const stylistId = Number(card.id)
        // 查下个周末的可用时段
        const now = new Date()
        const nextSat = new Date(now)
        nextSat.setDate(now.getDate() + (6 - now.getDay()))
        const dateStr = nextSat.toISOString().slice(0, 10)
        const slots = await getAvailableSlots(branchId, stylistId, dateStr)
        // 拼接周末两天
        const nextSun = new Date(nextSat)
        nextSun.setDate(nextSat.getDate() + 1)
        const sunStr = nextSun.toISOString().slice(0, 10)
        const sunSlots = await getAvailableSlots(branchId, stylistId, sunStr)
        const allSlots = [...slots.map(s => `${s.time}`), ...sunSlots.map(s => `${s.time}`)]
        // 取前 8 个时段
        const picked = allSlots.slice(0, 8)
        const cards: CardItem[] = picked.map((t, i) => {
          const isSat = i < slots.length
          return {
            id: `${isSat ? dateStr : sunStr} ${t}`,
            title: `${isSat ? dateStr : sunStr} ${t}`,
            subtitle: card.title + (isSat ? ' (周六)' : ' (周日)'),
            badge: i < 4 ? '可预约' : '剩 1 位'
          }
        })
        setMessages(prev => [...prev,
          { id: makeId(), role: 'ai', type: 'text', time: nowTime(), text: `${card.title} 本周末可预约时段（每 30 分钟）` },
          { id: makeId(), role: 'ai', type: 'card-list', time: nowTime(), cards: cards.length > 0 ? cards : [{ id: '0', title: '暂无可预约时段', subtitle: '请明天再试', badge: '' }] },
        ])
      } catch (e) {
        setMessages(prev => [...prev, { id: makeId(), role: 'ai', type: 'text', time: nowTime(), text: `查询档期失败: ${(e as any)?.message}` }])
      } finally {
        setStreamState('idle')
      }
    } else if (step === 'time') {
      // 选时段 → 调 createOrder 真实 API
      setMessages(prev => [...prev, { id: makeId(), role: 'user', type: 'text', text: `选择「${card.title}」`, time: nowTime() }])
      setStep('done')
      setStreamState('thinking')
      try {
        // 解析 "YYYY-MM-DD HH:MM" 格式
        const [date, time] = (card.id || '').split(' ')
        const u2 = getUser()
        const phone = u2?.phone || '13800000001'
        const customerName = u2?.name || '顾客'
        const r: any = await createOrder({
          branch_id: selectedBranch ? Number(selectedBranch.id) : 0,
          stylist_id: Number((card.id || '0').split(' ')[0]) || 0,
          service_type: '美发',
          appointment_date: date || new Date().toISOString().slice(0, 10),
          appointment_time: time || '10:00',
          customer_phone: phone,
          customer_name: customerName,
        })
        const order = r.data || r
        setMessages(prev => [...prev,
          { id: makeId(), role: 'ai', type: 'text', time: nowTime(), text: `✅ 预约成功！订单号: ${order.order_no || order.id || '已生成'}（${date} ${time}）` },
        ])
      } catch (e) {
        setMessages(prev => [...prev, { id: makeId(), role: 'ai', type: 'text', time: nowTime(), text: `预约失败: ${(e as any)?.response?.data?.detail || (e as any)?.message || '请重试'}` }])
      } finally {
        setStreamState('idle')
      }
    }
  }

  const isBusy = streamState === 'thinking' || streamState === 'streaming'
  const canSend = (input.trim().length > 0 || attachedImages.length > 0) && !isBusy

  return (
    <div className="mobile-shell" style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: '#f8fafc', position: 'relative' }}>

      {/* Drawer overlay */}
      {drawerOpen && <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 30 }} onClick={() => setDrawerOpen(false)} />}

      {/* Drawer */}
      <div style={{ position: 'absolute', top: 0, left: 0, bottom: 0, width: 260, background: '#1e293b', zIndex: 40, display: 'flex', flexDirection: 'column', transform: drawerOpen ? 'translateX(0)' : 'translateX(-100%)', transition: 'transform 0.25s ease' }}>
        <div style={{ padding: '40px 20px 24px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
          <div style={{ width: 52, height: 52, borderRadius: 16, background: 'linear-gradient(135deg,#6366f1,#818cf8)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 20, fontWeight: 700, marginBottom: 12 }}>{user?.name?.slice(-1) || '?'}</div>
          <p style={{ color: '#f1f5f9', fontWeight: 600, fontSize: 16 }}>{user?.name || '游客'}</p>
          <p style={{ color: '#64748b', fontSize: 13, marginTop: 2 }}>{user?.phone}</p>
        </div>
        <div style={{ padding: '12px 8px', flex: 1 }}>
          {[
            { label: '首页对话', icon: '💬', active: true,  cb: () => setDrawerOpen(false) },
            { label: '我的订单', icon: '📋', active: false, cb: () => { setDrawerOpen(false); nav('/customer/orders') } },
            { label: '我的记忆', icon: '🧠', active: false, cb: () => { setDrawerOpen(false); nav('/customer/memory') } },
          ].map(item => (
            <button key={item.label} onClick={item.cb} style={{ width: '100%', padding: '11px 14px', borderRadius: 10, border: 'none', display: 'flex', alignItems: 'center', gap: 10, background: item.active ? 'rgba(99,102,241,0.2)' : 'transparent', color: item.active ? '#a5b4fc' : '#94a3b8', fontSize: 14, fontWeight: 500, cursor: 'pointer', marginBottom: 2, textAlign: 'left' }}>
              <span>{item.icon}</span><span>{item.label}</span>
            </button>
          ))}
        </div>
        <div style={{ padding: '16px 8px', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
          <button onClick={() => { clearAuth(); nav('/customer/login') }} style={{ width: '100%', padding: '10px 14px', borderRadius: 10, border: 'none', display: 'flex', alignItems: 'center', gap: 10, background: 'transparent', color: '#ef4444', fontSize: 14, fontWeight: 500, cursor: 'pointer', textAlign: 'left' }}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M6 2H3a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3M11 11l3-3-3-3M14 8H6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></svg>
            退出登录
          </button>
        </div>
      </div>

      {/* Top nav */}
      <div className="mobile-nav" style={{ justifyContent: 'space-between', boxShadow: '0 1px 0 #f1f5f9', background: '#fff' }}>
        <button style={{ background: 'none', border: 'none', padding: 6, color: '#1e293b' }} onClick={() => setDrawerOpen(true)}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M2 5H18M2 10H18M2 15H18" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: isBusy ? '#f59e0b' : '#10b981', transition: 'background 0.3s' }} />
          <span style={{ fontWeight: 600, fontSize: 16, color: '#1e293b' }}>美发智能顾问</span>
        </div>
        <button style={{ background: 'none', border: 'none', padding: 6, color: '#6366f1' }} onClick={() => nav('/customer/orders')}>
          <svg width="22" height="22" viewBox="0 0 22 22" fill="none"><rect x="3" y="2" width="16" height="18" rx="2" stroke="currentColor" strokeWidth="1.6"/><path d="M7 7H15M7 11H15M7 15H11" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
        </button>
      </div>

      {/* Streaming indicator badge */}
      {isBusy && (
        <div style={{ position: 'absolute', top: 62, right: 14, zIndex: 10, background: 'rgba(255,255,255,0.92)', backdropFilter: 'blur(4px)', borderRadius: 20, padding: '4px 12px', border: '1px solid #e2e8f0', boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}>
          <p style={{ fontSize: 12, color: '#94a3b8', fontStyle: 'italic', margin: 0 }}>▌ AI 正在思考...</p>
        </div>
      )}

      {/* Messages */}
      <div className="scrollbar-hide" style={{ overflowY: 'auto', padding: '16px 14px', flex: 1 }}>
        {messages.map(msg => (
          <MessageBubble
            key={msg.id}
            msg={msg}
            onCardSelect={handleCardSelect}
            onRetry={msg.error ? () => streamAiReply(0) : undefined}
            isStreaming={msg.id === streamingMsgId && isBusy}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Image strip + chip */}
      {attachedImages.length > 0 && (
        <div style={{ background: '#fff', borderTop: '1px solid #f1f5f9', paddingTop: 6 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 14px' }}>
            <span style={{ fontSize: 11, padding: '3px 9px', borderRadius: 999, background: '#eef2ff', color: '#6366f1', border: '1px solid #c7d2fe', fontWeight: 500 }}>📷 图片模式</span>
            <span style={{ fontSize: 12, color: '#94a3b8' }}>{attachedImages.length}/3 张</span>
          </div>
          <ImageStrip images={attachedImages} onRemove={id => setAttachedImages(prev => prev.filter(i => i.id !== id))} />
        </div>
      )}

      {/* Hidden inputs */}
      <input ref={cameraRef} type="file" accept="image/*" capture="environment" style={{ display: 'none' }} onChange={e => handleImageFiles(e.target.files)} />
      <input ref={albumRef}  type="file" accept="image/*" multiple style={{ display: 'none' }} onChange={e => handleImageFiles(e.target.files)} />

      {/* Input bar */}
      <div style={{ background: '#fff', borderTop: '1px solid #f1f5f9', padding: '10px 12px', display: 'flex', alignItems: 'center', gap: 8, boxShadow: '0 -2px 12px rgba(0,0,0,0.04)', minHeight: 56 }}>
        {/* Camera */}
        <button onClick={() => cameraRef.current?.click()} disabled={attachedImages.length >= 3} style={{ width: 36, height: 36, borderRadius: '50%', border: 'none', flexShrink: 0, background: 'linear-gradient(135deg,#6366f1,#818cf8)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', opacity: attachedImages.length >= 3 ? 0.4 : 1, transition: 'opacity 0.15s' }}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M1 5.5C1 4.7 1.7 4 2.5 4h1.3L5 2h6l1.2 2H13.5c.8 0 1.5.7 1.5 1.5v7c0 .8-.7 1.5-1.5 1.5h-11C1.7 14 1 13.3 1 12.5v-7z" stroke="white" strokeWidth="1.3"/>
            <circle cx="8" cy="9" r="2.2" stroke="white" strokeWidth="1.3"/>
          </svg>
        </button>
        {/* Album */}
        <button onClick={() => albumRef.current?.click()} disabled={attachedImages.length >= 3} style={{ width: 36, height: 36, borderRadius: '50%', border: 'none', flexShrink: 0, background: '#f1f5f9', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', opacity: attachedImages.length >= 3 ? 0.4 : 1, transition: 'opacity 0.15s' }}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <rect x="1" y="1" width="14" height="14" rx="2.5" stroke="#64748b" strokeWidth="1.3"/>
            <circle cx="5" cy="5" r="1.5" fill="#64748b"/>
            <path d="M1 11L5 7L8 10L11 7L15 11" stroke="#64748b" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
        {/* Inline chip */}
        {attachedImages.length > 0 && (
          <span style={{ fontSize: 11, padding: '3px 8px', borderRadius: 999, background: '#eef2ff', color: '#6366f1', border: '1px solid #c7d2fe', fontWeight: 500, whiteSpace: 'nowrap', flexShrink: 0 }}>图片模式</span>
        )}
        {/* Text input */}
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); handleSend() } }}
          placeholder="说点什么...可发图片"
          disabled={isBusy}
          style={{ flex: 1, border: '1.5px solid', borderRadius: 14, padding: '9px 14px', fontSize: 15, outline: 'none', background: '#f8fafc', color: '#1e293b', borderColor: input ? '#6366f1' : '#e2e8f0', transition: 'border-color 0.15s', opacity: isBusy ? 0.65 : 1 }}
        />
        {/* Send / Stop */}
        {isBusy ? (
          <button onClick={handleStop} style={{ width: 36, height: 36, borderRadius: '50%', border: 'none', flexShrink: 0, background: '#ef4444', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', boxShadow: '0 2px 10px rgba(239,68,68,0.35)' }}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <rect x="3" y="3" width="3" height="8" rx="1" fill="white"/>
              <rect x="8" y="3" width="3" height="8" rx="1" fill="white"/>
            </svg>
          </button>
        ) : (
          <button onClick={handleSend} disabled={!canSend} style={{ width: 36, height: 36, borderRadius: '50%', border: 'none', flexShrink: 0, background: canSend ? 'linear-gradient(135deg,#6366f1,#818cf8)' : '#e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: canSend ? 'pointer' : 'not-allowed', boxShadow: canSend ? '0 2px 10px rgba(99,102,241,0.3)' : 'none', transition: 'all 0.15s' }}>
            <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
              <path d="M14 1L1 5.5L7 7.5M14 1L9.5 14L7 7.5M14 1L7 7.5" stroke={canSend ? 'white' : '#94a3b8'} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        )}
      </div>
    </div>
  )
}
