/** 共享类型：Chat 消息、卡片、流状态。P2-7: 全项目复用一份。*/

export type MessageType = 'text' | 'card-list'
export type StreamState = 'idle' | 'thinking' | 'streaming' | 'done' | 'error'

export interface CardItem {
  id: string
  title: string
  subtitle: string
  badge?: string
}

export interface AttachedImage {
  id: string
  url: string
}

export interface MessageStats {
  tokens: number
  ms: number
}

export interface Message {
  id: string
  role: 'ai' | 'user'
  type: MessageType
  text?: string
  streamingText?: string
  thinking?: string
  cards?: CardItem[]
  images?: string[]
  time: string
  stats?: MessageStats
  error?: boolean
  mode?: string
}
