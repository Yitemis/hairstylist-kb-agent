/** Chat 状态管理 hook (P1-6: 抽离 555 行 ChatPage)。*/
import { useState, useRef, useEffect, useCallback } from 'react'
import type { Message, StreamState, CardItem, AttachedImage } from '../types/chat'

function makeId() { return Math.random().toString(36).slice(2) }
function nowTime() {
  return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

export interface SendMessageArgs {
  message: string
  images?: AttachedImage[]
  sessionId?: string
}

export interface UseChatReturn {
  messages: Message[]
  input: string
  attachedImages: AttachedImage[]
  streamState: StreamState
  streamingMsgId: string | null
  isLoggedIn: boolean
  setInput: (v: string) => void
  setAttachedImages: (images: AttachedImage[]) => void
  send: (args: SendMessageArgs) => Promise<void>
  stop: () => void
  clearMessages: () => void
  removeImage: (id: string) => void
}

interface UseChatOptions {
  endpoint: (message: string, opts?: any) => Promise<any>
  sessionId?: string
  userId?: number
}

export function useChat(opts: UseChatOptions): UseChatReturn {
  const { endpoint, sessionId = 'default', userId } = opts

  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [attachedImages, setAttachedImages] = useState<AttachedImage[]>([])
  const [streamState, setStreamState] = useState<StreamState>('idle')
  const [streamingMsgId, setStreamingMsgId] = useState<string | null>(null)
  const stopRef = useRef(false)
  const isLoggedIn = !!userId

  const stop = useCallback(() => {
    stopRef.current = true
  }, [])

  const clearMessages = useCallback(() => {
    setMessages([])
  }, [])

  const removeImage = useCallback((id: string) => {
    setAttachedImages(prev => prev.filter(img => img.id !== id))
  }, [])

  const appendMessage = useCallback((msg: Message) => {
    setMessages(prev => [...prev, msg])
  }, [])

  const updateMessage = useCallback((id: string, patch: Partial<Message>) => {
    setMessages(prev => prev.map(m => m.id === id ? { ...m, ...patch } : m))
  }, [])

  const send = useCallback(async (args: SendMessageArgs) => {
    const { message, images, sessionId: argSid } = args
    if (!message.trim()) return

    const sid = argSid || sessionId
    const userMsgId = makeId()
    const startMs = Date.now()

    appendMessage({
      id: userMsgId,
      role: 'user',
      type: 'text',
      text: message,
      time: nowTime(),
    })

    setStreamState('thinking')
    const aiMsgId = makeId()
    appendMessage({
      id: aiMsgId,
      role: 'ai',
      type: 'text',
      thinking: '正在分析您的请求...',
      streamingText: '',
      time: nowTime(),
    })
    setStreamingMsgId(aiMsgId)

    try {
      const response = await endpoint(message, {
        images: images?.map(i => i.url),
        session_id: sid,
      })
      const data = response?.data ?? response

      if (stopRef.current) {
        updateMessage(aiMsgId, { text: '已中断', streamingText: undefined })
        return
      }

      const answer = data?.answer || data?.text || ''
      const cards = data?.options || data?.cards
      const mode = data?.mode
      const sourcesCount = data?.sources_count ?? 0

      setStreamState('streaming')

      let acc = ''
      for (const ch of answer) {
        if (stopRef.current) break
        acc += ch
        updateMessage(aiMsgId, { streamingText: acc })
        await new Promise(r => setTimeout(r, 20))
      }

      const ms = Date.now() - startMs
      updateMessage(aiMsgId, {
        streamingText: undefined,
        text: acc || answer,
        cards: cards && cards.length > 0 ? cards : undefined,
        type: cards && cards.length > 0 ? 'card-list' : 'text',
        stats: { tokens: Math.round((acc || answer).length * 0.72 + 12), ms },
        mode,
      })
    } catch (e: any) {
      updateMessage(aiMsgId, {
        streamingText: undefined,
        text: '请求失败：' + (e?.message || '网络错误'),
        error: true,
      })
    } finally {
      setStreamState('idle')
      setStreamingMsgId(null)
      stopRef.current = false
    }
  }, [endpoint, sessionId, appendMessage, updateMessage])

  return {
    messages,
    input,
    attachedImages,
    streamState,
    streamingMsgId,
    isLoggedIn,
    setInput,
    setAttachedImages,
    send,
    stop,
    clearMessages,
    removeImage,
  }
}
