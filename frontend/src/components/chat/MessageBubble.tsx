/** 聊天气泡组件 (P1-6: 抽离 ChatPage)。*/
import type { Message } from '../../types/chat'
import { TypingDots } from './TypingDots'
import { CardList } from './CardList'

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

export function MessageBubble({
  msg, onCardSelect, onRetry, isStreaming,
}: {
  msg: Message
  onCardSelect?: (c: any) => void
  onRetry?: () => void
  isStreaming?: boolean
}) {
  const isUser = msg.role === 'user'

  if (isUser) {
    return (
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginBottom: 14 }}>
        <div style={{ maxWidth: '78%', background: '#1e293b', color: '#fff', padding: '10px 14px', borderRadius: 14, borderTopRightRadius: 4, fontSize: 14, lineHeight: 1.6 }}>
          {msg.text}
        </div>
        <UserAvatar name="我" />
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
      <AiAvatar />
      <div style={{ maxWidth: '78%' }}>
        {msg.thinking && !msg.streamingText && (
          <div style={{ background: '#f1f5f9', color: '#64748b', padding: '8px 14px', borderRadius: 14, borderTopLeftRadius: 4, fontSize: 13, fontStyle: 'italic' }}>
            {msg.thinking}<TypingDots />
          </div>
        )}
        {(msg.streamingText !== undefined || msg.text) && (
          <div style={{ background: '#fff', color: '#1e293b', padding: '10px 14px', borderRadius: 14, borderTopLeftRadius: 4, fontSize: 14, lineHeight: 1.6, border: '1px solid #e2e8f0' }}>
            {msg.streamingText !== undefined ? msg.streamingText : msg.text}
            {isStreaming && <span style={{ display: 'inline-block', width: 6, height: 14, background: '#6366f1', marginLeft: 2, animation: 'blink 1s infinite' }} />}
          </div>
        )}
        {msg.cards && msg.cards.length > 0 && (
          <CardList cards={msg.cards} onSelect={onCardSelect || (() => {})} />
        )}
        {msg.stats && !isStreaming && (
          <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 4, paddingLeft: 4 }}>
            {msg.stats.tokens} tokens · {msg.stats.ms}ms
            {msg.mode && ` · ${msg.mode}`}
          </div>
        )}
        {msg.error && onRetry && (
          <button onClick={onRetry} style={{ marginTop: 6, fontSize: 12, color: '#dc2626', background: 'none', border: 'none', cursor: 'pointer' }}>
            ↻ 重试
          </button>
        )}
      </div>
    </div>
  )
}
