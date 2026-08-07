/**对话 API：普通 POST + SSE 流式。*/
import { request } from './client'

export interface ChatRequest {
  message: string
  user_id?: number
  session_id?: string
  image_paths?: string[]
  image_b64s?: string[]
  idempotency_key?: string
}

export interface ChatOption {
  type?: string
  id?: number | string
  title: string
  subtitle?: string
  badge?: string
}

export interface ChatResponse {
  answer: string
  safety_triggered: boolean
  sources: any[]
  mode?: string
  options?: ChatOption[]
}

export async function sendChat(
  message: string,
  userId: number,
  sessionId?: string,
  idempotencyKey?: string,
): Promise<{ code: number; data: any; message: string }> {
  return request<ChatResponse>('/api/chat', {
    method: 'POST',
    body: JSON.stringify({
      message, user_id: userId, session_id: sessionId,
      idempotency_key: idempotencyKey,
    }),
  })
}

export interface StreamEvent {
  event: string
  data: any
}

export async function sendChatStream(
  message: string,
  userId: number,
  onEvent: (e: StreamEvent) => void,
  sessionId?: string,
): Promise<void> {
  const token = localStorage.getItem('token') || ''
  const res = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ message, user_id: userId, session_id: sessionId }),
  })
  if (!res.ok || !res.body) {
    onEvent({ event: 'error', data: { message: `HTTP ${res.status}` } })
    return
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 4)
      const lines = raw.split('\n')
      let eventName = 'message'
      let dataStr = ''
      for (const line of lines) {
        if (line.startsWith('event: ')) eventName = line.slice(7).trim()
        else if (line.startsWith('data: ')) dataStr += line.slice(6)
      }
      if (!dataStr) continue
      try {
        const data = JSON.parse(dataStr)
        onEvent({ event: eventName, data })
        if (eventName === 'done' || eventName === 'error') return
      } catch { /* ignore */ }
    }
  }
}
