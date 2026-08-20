import { useState, useRef, useEffect } from 'react'
import AdminLayout from '../../components/admin/AdminLayout'
import { listDocuments, type AdminDocument } from '../../api'
import { sendChatStream } from '../../api/chat'
import { showToast } from '../../utils/toast'

/* ── Types ─────────────────────────────────────────────── */
interface Source {
  id: string; title: string; excerpt: string; page: string; icon: string
}
interface Message {
  id: string; role: 'user' | 'assistant'; content: string; sources?: Source[]; timestamp: string
  toolsUsed?: string[]
  steps?: { name: string; toolName?: string; args?: any; status: 'pending' | 'running' | 'done'; preview?: string }[]
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

function SourceTag({ source, expanded, onToggle }: { source: any; expanded: boolean; onToggle: () => void }) {
  // 支持两种格式: Source 接口 (knowledge panel 用) 和 工具结果 (chat 用)
  const isTool = source.tool || source.preview
  const title = isTool ? (source.tool || '工具') : source.title
  const subtitle = isTool ? '' : source.page
  const excerpt = isTool ? (source.preview || '') : source.excerpt
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
        <span>{isTool ? '🔧' : source.icon}</span>
        <span>{title}</span>
        {subtitle && <span style={{ opacity: 0.6 }}>{subtitle}</span>}
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" style={{ transform: expanded ? 'rotate(180deg)' : 'rotate(0)', transition: 'transform 0.18s' }}>
          <path d="M2 3.5L5 6.5L8 3.5" stroke="#6366f1" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </button>
      {expanded && excerpt && (
        <div style={{ marginTop: 6, padding: '10px 12px', borderRadius: 10, background: '#f5f3ff', border: '1px solid #e0d9ff', fontSize: 12, color: '#4c1d95', lineHeight: 1.6, maxWidth: 500, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
          {excerpt}
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

/* ============================================================
 * AgentScope 风格的轨迹 (P0-3: 借鉴 agentscope-main/examples/web_ui)
 *
 * 核心: 连续 tool_call 合并成一组, 每组有 1 个折叠, 展开后是每个调用的卡片
 *      每张卡: 类型 pill (Read/Bash/Think) + 主参数 + 状态 icon
 *      点开: 输入 args + 输出结果
 * ============================================================ */

// 工具类型映射 (P0-3: 模仿 AgentScope tool-renderers/)
function getToolStyle(toolName: string, status: string): { icon: string; label: string; color: string; bg: string } {
  const base = {
    done: { color: '#10b981', bg: '#ecfdf5' },
    running: { color: '#f59e0b', bg: '#fffbeb' },
    pending: { color: '#9ca3af', bg: '#f3f4f6' },
  }[status] || { color: '#9ca3af', bg: '#f3f4f6' }
  const map: Record<string, { icon: string; label: string }> = {
    'search_hair_knowledge': { icon: '🔍', label: 'Read' },
    'web_search': { icon: '🌐', label: 'Web' },
    'list_orders': { icon: '📋', label: 'Orders' },
    'get_order_detail': { icon: '📄', label: 'Order' },
    'update_order_status': { icon: '✏️', label: 'Status' },
    'list_branches': { icon: '🏢', label: 'Branch' },
    'list_staffs': { icon: '👥', label: 'Staff' },
    'list_users': { icon: '👤', label: 'Users' },
    'get_business_stats': { icon: '📊', label: 'Stats' },
    'bash': { icon: '🖥', label: 'Bash' },
    'read': { icon: '📄', label: 'Read' },
    'write': { icon: '✏️', label: 'Write' },
    'edit': { icon: '✏️', label: 'Edit' },
    'think': { icon: '⚙️', label: 'Think' },
    'reasoning': { icon: '⚙️', label: 'Think' },
    'query_rewrite': { icon: '✍️', label: 'Rewrite' },
  }
  const name = (toolName || '').toLowerCase()
  const style = map[name] || { icon: '🛠', label: toolName || 'Tool' }
  return { ...style, ...base }
}

// 提取主参数 (类似 AgentScope 工具的 "primary argument" 概念)
function getPrimaryArg(toolName: string, args: any): string {
  if (!args) return ''
  if (typeof args === 'string') return args
  const a = (toolName || '').toLowerCase()
  if (a.includes('search') || a.includes('read')) return args.query || args.file || args.path || JSON.stringify(args).slice(0, 60)
  if (a.includes('write') || a.includes('edit')) return args.file_path || args.path || args.file || JSON.stringify(args).slice(0, 60)
  if (a.includes('bash')) return args.command || args.cmd || JSON.stringify(args).slice(0, 60)
  return JSON.stringify(args).slice(0, 60)
}

// 单个工具调用卡片 (类似 AgentScope renderToolCall)
function ToolCallCard({ step, index }: { step: any; index: number }) {
  const [open, setOpen] = useState(false)
  const toolName = step.toolName || step.name || ''
  const style = getToolStyle(toolName, step.status)
  const isWeb = toolName === 'web_search'
  const isSearch = toolName === 'search_hair_knowledge'
  // 解析 args
  let args: any = step.args || {}
  if (typeof args === 'string') {
    try { args = JSON.parse(args) } catch { args = { raw: args } }
  }
  const primaryArg = getPrimaryArg(toolName, args)
  const stateIcon = step.status === 'done' ? '✅' : step.status === 'running' ? '⏳' : '⭕'

  return (
    <div
      onClick={() => setOpen(!open)}
      style={{
        background: '#fff',
        border: `1px solid ${open ? style.color : '#e2e8f0'}`,
        borderLeft: `3px solid ${style.color}`,
        borderRadius: 6,
        overflow: 'hidden',
        cursor: 'pointer',
        transition: 'all 0.15s',
        fontSize: 13,
      }}
    >
      {/* Trigger row: [icon] [label pill] [primary arg] [state] [chevron] */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '6px 10px',
        background: open ? style.bg : 'transparent',
        fontSize: 12,
      }}>
        <span style={{ fontSize: 13 }}>{style.icon}</span>
        <span style={{
          fontSize: 11, fontWeight: 600, padding: '1px 6px', borderRadius: 3,
          background: style.color, color: '#fff', flexShrink: 0,
        }}>{style.label}</span>
        <span style={{
          fontSize: 12, color: '#1f2937', fontWeight: 450, flex: 1, minWidth: 0,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>{primaryArg}</span>
        <span style={{ fontSize: 11, flexShrink: 0 }}>{stateIcon}</span>
        <span style={{ fontSize: 9, color: '#9ca3af', flexShrink: 0, transition: 'transform 0.15s', transform: open ? 'rotate(90deg)' : 'rotate(0)' }}>▶</span>
      </div>
      {/* Body: 输入 + 输出 */}
      {open && (
        <div style={{ borderTop: '1px solid #f3f4f6', background: '#fafafa' }}>
          {Object.keys(args).length > 0 && (
            <div style={{ padding: '6px 10px', borderBottom: '1px solid #f3f4f6' }}>
              <div style={{ fontSize: 10, color: '#9ca3af', marginBottom: 3, textTransform: 'uppercase', letterSpacing: 0.5 }}>Input</div>
              <pre style={{
                margin: 0, fontSize: 11, color: '#374151', fontFamily: 'monospace',
                whiteSpace: 'pre-wrap', wordBreak: 'break-word', lineHeight: 1.5,
                maxHeight: 120, overflow: 'auto',
              }}>{JSON.stringify(args, null, 2)}</pre>
            </div>
          )}
          {step.preview && (
            <div style={{ padding: '6px 10px' }}>
              <div style={{ fontSize: 10, color: '#9ca3af', marginBottom: 3, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                Output {isWeb && '🌐'} {isSearch && '🔍'}
              </div>
              <pre style={{
                margin: 0, fontSize: 11, color: '#374151', fontFamily: isWeb || isSearch ? 'inherit' : 'monospace',
                whiteSpace: 'pre-wrap', wordBreak: 'break-word', lineHeight: 1.5,
                maxHeight: 400, overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              }}>{step.preview}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// 连续 tool_call 合并成一组 (AgentScope tool_call_group 模式)
function groupToolSteps(steps: any[]): { type: 'tool_group' | 'normal'; steps: any[] }[] {
  const groups: { type: 'tool_group' | 'normal'; steps: any[] }[] = []
  let currentTool: any[] = []
  for (const s of steps) {
    const isTool = s.toolName || (s.name && (s.name.includes('search') || s.name.includes('rewrite') || s.name.includes('read') || s.name.includes('write')))
    if (isTool) {
      currentTool.push(s)
    } else {
      if (currentTool.length > 0) {
        groups.push({ type: 'tool_group', steps: currentTool })
        currentTool = []
      }
      groups.push({ type: 'normal', steps: [s] })
    }
  }
  if (currentTool.length > 0) {
    groups.push({ type: 'tool_group', steps: currentTool })
  }
  return groups
}

// 轨迹主组件 (类似 AgentScope 完整 ThoughtChain 实现)
function TrajectoryView({ steps }: { steps: any[] }) {
  const groups = groupToolSteps(steps)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, width: '100%' }}>
      {groups.map((g, gi) => {
        if (g.type === 'normal') {
          return g.steps.map((step, si) => (
            <NormalStep key={`n-${gi}-${si}`} step={step} />
          ))
        } else {
          // 工具组: 折叠展示
          return <ToolStepGroup key={`t-${gi}`} steps={g.steps} />
        }
      })}
    </div>
  )
}

// 非工具步骤 (Think / Reply Start / LLM Call 等)
function NormalStep({ step }: { step: any }) {
  const lowerName = (step.name || '').toLowerCase()
  let icon = '⚡'
  if (lowerName.includes('think') || lowerName.includes('reasoning')) icon = '⚙️'
  else if (lowerName.includes('reply')) icon = '🚀'
  else if (lowerName.includes('llm_call')) icon = '🧠'
  else if (lowerName.includes('llm_done')) icon = '✓'
  else if (lowerName.includes('rag')) icon = '📊'
  else if (lowerName.includes('rewrite')) icon = '✍️'

  const stateColor = step.status === 'done' ? '#10b981' : step.status === 'running' ? '#f59e0b' : '#9ca3af'
  const stateIcon = step.status === 'done' ? '✅' : step.status === 'running' ? '⏳' : '⭕'

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6,
      padding: '4px 8px', fontSize: 11, color: '#6b7280',
      background: '#f9fafb', borderRadius: 4,
    }}>
      <span>{icon}</span>
      <span style={{ color: stateColor, fontWeight: 500 }}>{step.name}</span>
      <span style={{ marginLeft: 'auto' }}>{stateIcon}</span>
    </div>
  )
}

// 工具组: 折叠卡片
function ToolStepGroup({ steps }: { steps: any[] }) {
  const [open, setOpen] = useState(true)
  const allDone = steps.every(s => s.status === 'done')
  const hasRunning = steps.some(s => s.status === 'running')
  // 摘要: 工具名 + 数量
  const toolNames = Array.from(new Set(steps.map(s => s.toolName || s.name)))
  const summary = toolNames.length === 1 ? toolNames[0] : `${toolNames.length} tools`

  return (
    <div style={{
      background: '#fff',
      border: '1px solid #e2e8f0',
      borderRadius: 8,
      overflow: 'hidden',
    }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          width: '100%', padding: '8px 12px',
          background: allDone ? '#ecfdf5' : hasRunning ? '#fffbeb' : '#f9fafb',
          border: 'none', cursor: 'pointer', textAlign: 'left',
          display: 'flex', alignItems: 'center', gap: 8, fontSize: 12,
        }}
      >
        <span style={{ fontSize: 10, color: '#6b7280', transition: 'transform 0.15s', transform: open ? 'rotate(90deg)' : 'rotate(0)' }}>▶</span>
        <span style={{ fontSize: 12, fontWeight: 600, color: '#1e293b' }}>技能调用</span>
        <span style={{ fontSize: 11, color: '#6b7280' }}>· {summary} × {steps.length}</span>
        <span style={{ marginLeft: 'auto', fontSize: 11 }}>
          {allDone ? '✅' : hasRunning ? '⏳' : '⭕'}
        </span>
      </button>
      {open && (
        <div style={{ padding: 6, background: '#fafafa', display: 'flex', flexDirection: 'column', gap: 4 }}>
          {steps.map((step, i) => (
            <ToolCallCard key={i} step={step} index={i} />
          ))}
        </div>
      )}
    </div>
  )
}

/* ============================================================
 * 引用文档卡片 (P0-3: 用户点开看原文 = 召回的父块)
 * ============================================================ */
function CitationCards({ sources }: { sources: any[] }) {
  const [openIdx, setOpenIdx] = useState<number | null>(null)
  if (!sources || sources.length === 0) return null
  return (
    <div style={{ marginTop: 10, width: '100%' }}>
      <p style={{ fontSize: 11, color: '#9ca3af', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 4 }}>
        <span>📎</span> 引用文档 ({sources.length})
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxWidth: 500 }}>
        {sources.map((s, i) => {
          const isWeb = s.type === 'web'
          const isOpen = openIdx === i
          const accent = isWeb ? '#10b981' : '#6366f1'
          const accentBg = isWeb ? '#ecfdf5' : '#eef2ff'
          const tag = isWeb ? '🌐 网络' : '📚 知识库'
          return (
            <div
              key={i}
              style={{
                background: '#fff',
                border: `1px solid ${isOpen ? accent : '#e2e8f0'}`,
                borderLeft: `3px solid ${accent}`,
                borderRadius: 8,
                overflow: 'hidden',
                transition: 'all 0.15s',
              }}
            >
              <button
                onClick={() => setOpenIdx(isOpen ? null : i)}
                style={{
                  width: '100%', padding: '8px 12px', background: accentBg,
                  border: 'none', cursor: 'pointer', textAlign: 'left',
                  display: 'flex', alignItems: 'center', gap: 8,
                }}
              >
                <span style={{
                  fontSize: 10, fontWeight: 600, padding: '2px 6px', borderRadius: 4,
                  background: accent, color: '#fff',
                }}>{tag}</span>
                <span style={{ fontSize: 13, fontWeight: 500, color: '#1e293b', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {s.title || s.tool}
                </span>
                <span style={{ fontSize: 10, color: '#94a3b8' }}>{isOpen ? '▲' : '▼'}</span>
              </button>
              {isOpen && (
                <div style={{ padding: 12, maxHeight: 320, overflow: 'auto', background: '#fafafa' }}>
                  <pre style={{
                    margin: 0, fontSize: 12, lineHeight: 1.7, color: '#374151',
                    fontFamily: 'inherit', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                  }}>{s.content || s.preview || '(无内容)'}</pre>
                </div>
              )}
              {!isOpen && s.preview && (
                <div style={{ padding: '6px 12px', fontSize: 11, color: '#6b7280', lineHeight: 1.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {s.preview}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function MsgBubble({ msg, isStreaming }: { msg: Message; isStreaming?: boolean }) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const [view, setView] = useState<'chat' | 'trajectory'>('chat')  // P0-3: 轨迹 tab
  const isUser = msg.role === 'user'
  const steps = msg.steps || []
  const hasSteps = !isUser && steps.length > 0

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
      <div style={{ maxWidth: '78%', display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start', width: '100%' }}>
        {/* P0-3: Tab 切换 (对话 / 轨迹) — 借鉴火山方舟 UI */}
        {hasSteps && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 0,
            marginBottom: 6, borderBottom: '1px solid #e0e7ff', width: '100%',
          }}>
            <button
              onClick={() => setView('chat')}
              style={{
                padding: '6px 14px', background: 'transparent', border: 'none',
                borderBottom: view === 'chat' ? '2px solid #6366f1' : '2px solid transparent',
                color: view === 'chat' ? '#6366f1' : '#6b7280',
                fontSize: 12, fontWeight: view === 'chat' ? 600 : 400, cursor: 'pointer',
              }}
            >
              💬 对话
            </button>
            <button
              onClick={() => setView('trajectory')}
              style={{
                padding: '6px 14px', background: 'transparent', border: 'none',
                borderBottom: view === 'trajectory' ? '2px solid #6366f1' : '2px solid transparent',
                color: view === 'trajectory' ? '#6366f1' : '#6b7280',
                fontSize: 12, fontWeight: view === 'trajectory' ? 600 : 400, cursor: 'pointer',
              }}
            >
              📍 轨迹 ({steps.length})
            </button>
            <div style={{ flex: 1 }} />
            <span style={{ fontSize: 10, color: '#9ca3af', paddingRight: 4 }}>Session log ⬇</span>
          </div>
        )}

        {/* 轨迹 tab: AgentScope 风格的 ThoughtChain 模式 (P0-3) */}
        {hasSteps && view === 'trajectory' && (
          <div style={{ width: '100%', marginBottom: 6 }}>
            <TrajectoryView steps={steps} />
          </div>
        )}

        {/* 对话 tab: 正常消息 + 流式光标 */}
        {(!hasSteps || view === 'chat') && (
          <>
            <div style={{
              padding: '10px 14px', fontSize: 14, lineHeight: 1.65,
              borderRadius: isUser ? '14px 14px 3px 14px' : '3px 14px 14px 14px',
              background: isUser ? 'linear-gradient(135deg, #6366f1, #818cf8)' : '#fff',
              color: isUser ? '#fff' : '#1e293b',
              boxShadow: isUser ? '0 2px 12px rgba(99,102,241,0.25)' : '0 1px 6px rgba(0,0,0,0.06)',
            }}>
              {isUser ? msg.content : formatContent(msg.content)}
              {isStreaming && (
                <span style={{
                  display: 'inline-block', width: 8, height: 14, background: '#6366f1',
                  marginLeft: 2, verticalAlign: 'middle', animation: 'blink 1s infinite',
                }} />
              )}
            </div>
            {msg.sources && msg.sources.length > 0 && (
              <CitationCards sources={msg.sources} />
            )}
            <span style={{ fontSize: 11, color: '#d1d5db', marginTop: 4 }}>{msg.timestamp}</span>
          </>
        )}
      </div>
    </div>
  )
}

/* ── 知识库分组 (与后端 category 字段对齐) ─────────────────── */
const KNOWLEDGE_GROUPS: { key: string; label: string; icon: string; color: string; bg: string; desc: string }[] = [
  { key: 'perming',  label: '烫发',   icon: '🌀', color: '#ec4899', bg: '#fdf2f8', desc: '烫发类型、原理、护理' },
  { key: 'cutting',  label: '剪发',   icon: '✂️', color: '#6366f1', bg: '#eef2ff', desc: '剪发技法、脸型搭配' },
  { key: 'coloring', label: '染发',   icon: '🎨', color: '#f59e0b', bg: '#fffbeb', desc: '染发技术、色板、过敏应急' },
  { key: 'care',     label: '护理',   icon: '💆', color: '#10b981', bg: '#ecfdf5', desc: '洗护、护发素、修复' },
  { key: 'general',  label: '通用',   icon: '📚', color: '#64748b', bg: '#f1f5f9', desc: '其他美发知识' },
]

export default function KnowledgePage() {
  const [docs, setDocs] = useState<AdminDocument[]>([])
  const [expandedGroup, setExpandedGroup] = useState<string | null>('perming')
  const [messages, setMessages] = useState<Message[]>([])
  const [sessions, setSessions] = useState<any[]>([])
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState(false)
  const [activeSession, setActiveSession] = useState('1')
  const [showKb, setShowKb] = useState(true)
  const [streamingText, setStreamingText] = useState('')

  // 加载已发布文档 (按 group 分类展示)
  useEffect(() => {
    (async () => {
      try {
        const data: any = await listDocuments()
        const list: AdminDocument[] = data?.data || data || []
        // 只展示已发布且已索引的文档
        setDocs(list.filter((d: AdminDocument) => d.is_published && d.mineru_status === 'indexed'))
      } catch { /* ignore */ }
    })()
  }, [])

  const groupCounts = KNOWLEDGE_GROUPS.map(g => ({
    ...g,
    count: docs.filter(d => d.category === g.key).length,
  }))
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, typing])

  // 持久化消息 (切页面不丢) — key 用 admin 当前用户
  const userId = 'admin_default'
  useEffect(() => {
    try {
      const saved = localStorage.getItem(`chat_${userId}`)
      if (saved) setMessages(JSON.parse(saved))
    } catch {}
  }, [userId])
  useEffect(() => {
    try {
      localStorage.setItem(`chat_${userId}`, JSON.stringify(messages))
    } catch {}
  }, [messages, userId])

  const handleSend = async () => {
    const text = input.trim()
    if (!text || typing) return
    setInput('')
    const userMsg: Message = { id: makeId(), role: 'user', content: text, timestamp: nowTime() }
    setMessages(prev => [...prev, userMsg])
    setTyping(true)
    setStreamingText('')

    // 临时 AI 消息 (流式填充), 自带 tools 数组
    const aiMsgId = makeId()
    const messageTools: string[] = []
    const messageSteps: { name: string; status: 'pending' | 'running' | 'done'; preview?: string }[] = []
    setMessages(prev => [...prev, {
      id: aiMsgId, role: 'assistant', timestamp: nowTime(),
      content: '', sources: [], toolsUsed: messageTools, steps: messageSteps,
    }])

    // P0-3 关键修复: 用 ref 跟踪 buffer, 避免 React 18 批处理导致 setMessages 嵌套调用错乱
    const textBufferRef = { current: '' }

    const updateMessage = (patch: Partial<Message>) => {
      setMessages(prevMsgs => prevMsgs.map(m =>
        m.id === aiMsgId ? { ...m, ...patch, toolsUsed: [...messageTools], steps: [...messageSteps] } : m
      ))
    }

    try {
      await sendChatStream(
        text,
        0,  // admin 用户的 ID (后端从 token 取)
        (event) => {
          if (event.event === 'intent') {
            const data = event.data as any
            showToast(`Agent 模式: ${data.mode || data.intent}`, 'info')
          } else if (event.event === 'rewrite') {
            const data = event.data as any
            console.log('Rewrite candidates:', data.candidates)
            messageTools.push('query_rewrite')
            updateMessage({})
          } else if (event.event === 'thinking') {
            const data = event.data as any
            const stage = data.stage || 'thinking'
            // 不重复 push 相同的 stage
            if (messageSteps.length === 0 || messageSteps[messageSteps.length - 1].name !== stage) {
              messageSteps.push({ name: stage, status: 'done' })
            }
            updateMessage({})
          } else if (event.event === 'tool_call') {
            const data = event.data as any
            const toolName = data.name || '工具'
            const toolArgs = data.args || {}
            const status = data.status || 'start'
            // 找到或创建对应的 step (按 toolCallId 或 toolName 配对)
            const existing = messageSteps.findIndex(s => s.toolName === toolName && s.status === 'running')
            if (status === 'start') {
              if (existing === -1) {
                messageSteps.push({ name: toolName, toolName, args: toolArgs, status: 'running' })
              } else {
                messageSteps[existing].args = toolArgs  // 持续收集 args
              }
            } else if (status === 'end') {
              if (existing === -1) {
                messageSteps.push({ name: toolName, toolName, args: toolArgs, status: 'done' })
              } else {
                messageSteps[existing].status = 'done'
                messageSteps[existing].args = toolArgs
              }
            }
            messageTools.push(toolName)
            updateMessage({})
          } else if (event.event === 'tool_result') {
            const data = event.data as any
            const toolName = data.name || ''
            const preview = data.preview || ''
            // 找最近的同名 running 步骤, 配对
            const idx = messageSteps.findLastIndex(s => s.toolName === toolName && s.status === 'running')
            if (idx !== -1) {
              messageSteps[idx].status = 'done'
              messageSteps[idx].preview = preview
            } else {
              // 找不到 running 的就找 done 的覆盖 preview
              const idx2 = messageSteps.findLastIndex(s => s.toolName === toolName)
              if (idx2 !== -1) messageSteps[idx2].preview = preview
            }
            updateMessage({})
          } else if (event.event === 'text') {
            const data = event.data as any
            const delta = data.delta || ''
            if (delta) {
              // P0-3 关键修复: 用 ref 累积 + 直接 setMessages 一次, 避免乱序
              textBufferRef.current += delta
              updateMessage({ content: textBufferRef.current })
            }
          } else if (event.event === 'sources') {
            const data = event.data as any
            updateMessage({ sources: data.items || [] })
          } else if (event.event === 'done') {
            const data = event.data as any
            // P0-3: 用 done 事件的完整 answer 覆盖, 确保文本完整
            if (data.answer && data.answer.length > textBufferRef.current.length) {
              textBufferRef.current = data.answer
              updateMessage({ content: data.answer })
            }
          } else if (event.event === 'error') {
            showToast('Agent 出错: ' + (event.data as any).message, 'error')
          }
        },
      )
    } catch (e: any) {
      showToast('请求失败: ' + e.message, 'error')
      updateMessage({ content: '⚠️ ' + (e.message || '请求失败') })
    } finally {
      setTyping(false)
      setStreamingText('')
    }
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
                <p style={{ fontWeight: 600, fontSize: 14, color: '#1e293b' }}>当前会话</p>
                <p style={{ fontSize: 12, color: '#94a3b8' }}>引用 {messages.reduce((a, m) => a + (m.sources?.length || 0), 0)} 个知识来源 · {messages.length} 条消息</p>
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
              {messages.map(m => <MsgBubble key={m.id} msg={m} isStreaming={typing && m.id === messages[messages.length - 1]?.id} />)}
              {/* P0-3 修复: 去掉单独的 TypingDots 气泡 (MsgBubble 的 isStreaming 已经有闪烁光标) */}
              <div ref={bottomRef} />
            </div>
          </div>

          {/* Suggestions + Input */}
          <div style={{ background: '#fff', borderTop: '1px solid #f1f5f9', padding: '12px 20px 16px', flexShrink: 0 }}>
            <div style={{ maxWidth: 740, margin: '0 auto' }}>
              <div style={{ display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
                {messages.length === 0 ? (
                  // 首次进入: 显示快捷指令卡片 (类似火山方舟)
                  <>
                    <button
                      onClick={() => setInput('头发多孔性测试方法')}
                      style={{ padding: '8px 14px', borderRadius: 10, background: '#f5f3ff', color: '#6366f1', border: '1px solid #ddd6fe', cursor: 'pointer', fontSize: 13, fontWeight: 500, textAlign: 'left', display: 'flex', alignItems: 'center', gap: 6 }}
                    >
                      <span>🧪</span> 头发多孔性测试方法
                    </button>
                    <button
                      onClick={() => setInput('冷烫 vs 热烫有什么区别？')}
                      style={{ padding: '8px 14px', borderRadius: 10, background: '#f5f3ff', color: '#6366f1', border: '1px solid #ddd6fe', cursor: 'pointer', fontSize: 13, fontWeight: 500, textAlign: 'left', display: 'flex', alignItems: 'center', gap: 6 }}
                    >
                      <span>🔥</span> 冷烫 vs 热烫有什么区别？
                    </button>
                    <button
                      onClick={() => setInput('染发过敏怎么应急处理？')}
                      style={{ padding: '8px 14px', borderRadius: 10, background: '#f5f3ff', color: '#6366f1', border: '1px solid #ddd6fe', cursor: 'pointer', fontSize: 13, fontWeight: 500, textAlign: 'left', display: 'flex', alignItems: 'center', gap: 6 }}
                    >
                      <span>⚠️</span> 染发过敏怎么应急处理？
                    </button>
                  </>
                ) : (
                  // 已对话: 显示紧凑建议
                  ['烫发后怎么护理？', '染发后多久能洗头？', '头发干枯用什么护理产品？'].map(s => (
                    <button
                      key={s}
                      onClick={() => setInput(s)}
                      style={{ fontSize: 12, padding: '5px 12px', borderRadius: 999, background: '#f5f3ff', color: '#6366f1', border: '1px solid #e0d9ff', cursor: 'pointer', transition: 'all 0.12s' }}
                      onMouseOver={e => { e.currentTarget.style.background = '#ede9fe' }}
                      onMouseOut={e => { e.currentTarget.style.background = '#f5f3ff' }}
                    >
                      {s}
                    </button>
                  ))
                )}
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

        {/* Knowledge panel - 按组别分类, 只读预览 */}
        {showKb && (
          <div className="animate-slide-right" style={{ width: 300, background: '#fff', borderLeft: '1px solid #f1f5f9', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
            <div style={{ padding: '14px 16px', borderBottom: '1px solid #f1f5f9', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <p style={{ fontWeight: 600, fontSize: 14, color: '#1e293b' }}>知识库</p>
                <p style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>{docs.length} 份已发布文档 · {groupCounts.length} 个组别</p>
              </div>
              <button onClick={() => setShowKb(false)} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: 4 }}>
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M1 1L13 13M13 1L1 13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>
              </button>
            </div>
            {/* Groups (按 category 字段分组) */}
            <div className="flex-1 scrollbar-thin" style={{ overflowY: 'auto', padding: '10px 12px' }}>
              {groupCounts.map(group => {
                const groupDocs = docs.filter(d => d.category === group.key)
                const isOpen = expandedGroup === group.key
                return (
                  <div key={group.key} style={{ borderRadius: 12, border: '1px solid #f1f5f9', marginBottom: 8, overflow: 'hidden' }}>
                    <button
                      onClick={() => setExpandedGroup(p => p === group.key ? null : group.key)}
                      style={{
                        width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', border: 'none', cursor: 'pointer', textAlign: 'left',
                        background: isOpen ? group.bg : '#fff', transition: 'background 0.12s',
                      }}
                    >
                      <span style={{ fontSize: 18 }}>{group.icon}</span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <p style={{ fontSize: 13, fontWeight: 500, color: '#1e293b' }}>{group.label}</p>
                        <p style={{ fontSize: 11, color: '#94a3b8', marginTop: 1 }}>{group.count} 份文档 · {group.desc}</p>
                      </div>
                      <span style={{ fontSize: 12, color: group.color, fontWeight: 600, minWidth: 24, textAlign: 'right' }}>{group.count}</span>
                      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" style={{ transform: isOpen ? 'rotate(180deg)' : 'rotate(0)', transition: 'transform 0.18s', flexShrink: 0 }}>
                        <path d="M2 4L6 8L10 4" stroke="#9ca3af" strokeWidth="1.5" strokeLinecap="round"/>
                      </svg>
                    </button>
                    {isOpen && groupDocs.length > 0 && (
                      <div style={{ padding: '4px 12px 10px', background: group.bg, borderTop: '1px solid rgba(0,0,0,0.04)' }}>
                        {groupDocs.map(doc => (
                          <div key={doc.document_id} style={{ padding: '6px 0', borderBottom: '1px dashed rgba(0,0,0,0.06)' }}>
                            <p style={{ fontSize: 12, color: '#1e293b', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>📄 {doc.filename}</p>
                            <p style={{ fontSize: 10, color: '#94a3b8', marginTop: 2 }}>{doc.page_count || 1} 页 · {((doc.file_size || 0) / 1024).toFixed(1)} KB</p>
                          </div>
                        ))}
                      </div>
                    )}
                    {isOpen && groupDocs.length === 0 && (
                      <div style={{ padding: '10px 12px', background: group.bg, borderTop: '1px solid rgba(0,0,0,0.04)' }}>
                        <p style={{ fontSize: 11, color: '#94a3b8', fontStyle: 'italic' }}>该组别暂无文档</p>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
            {/* 提示: 文档管理入口 */}
            <div style={{ padding: '10px 12px', borderTop: '1px solid #f1f5f9', fontSize: 11, color: '#94a3b8', lineHeight: 1.5 }}>
              💡 上传/管理文档请到 <strong style={{ color: '#6366f1' }}>「文档管理」</strong> 页面
            </div>
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
