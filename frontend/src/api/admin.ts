/**Admin API：订单管理 / 数据归档 / RAG 评估 / 监控。*/
import { request } from './client'
import type { Order } from './booking'

export interface ArchiveStats {
  total_chat: number
  old_chat: number
  total_order: number
  last_run: string | null
  saved_space_mb: number
}

export interface ArchiveRecord {
  id: string
  time: string
  type: 'chat' | 'order'
  count: number
  saved_mb: number
  duration_sec: number
  status: 'success' | 'failed'
}

export async function getArchiveStats(): Promise<ArchiveStats> {
  const r = await request<ArchiveStats>('/api/admin/archive/stats')
  return r.data || ({} as ArchiveStats)
}

export async function triggerArchive(): Promise<{ deleted_chat: number; deleted_orders: number }> {
  const r = await request<{ archived: { chat_messages_deleted: number; orders_deleted: number } }>(
    '/api/admin/archive', { method: 'POST' }
  )
  const a = r.data?.archived
  return a ? { deleted_chat: a.chat_messages_deleted, deleted_orders: a.orders_deleted } : { deleted_chat: 0, deleted_orders: 0 }
}

export async function adminListOrders(status?: string): Promise<Order[]> {
  const url = status ? `/api/admin/orders?status=${status}` : '/api/admin/orders'
  const r = await request<Order[]>(url)
  return r.data || []
}

export async function adminUpdateOrderStatus(
  orderId: number, newStatus: string, note?: string,
) {
  return request(`/api/admin/orders/${orderId}/status`, {
    method: 'POST', body: JSON.stringify({ new_status: newStatus, note }),
  })
}

export interface RagEvalResult {
  query: string
  category: string
  recall_at_5: number
  mrr: number
  hit_rate_at_5: number
  ndcg_at_5: number
  latency_ms: number
}

export interface RagEvalSummary {
  count: number
  recall_at_5: number
  recall_at_10: number
  mrr: number
  hit_rate_at_5: number
  ndcg_at_5: number
}

export interface RagEvalReport {
  summary: RagEvalSummary
  by_category: Record<string, RagEvalSummary>
  per_query: RagEvalResult[]
}

export async function runRagEval(): Promise<RagEvalReport> {
  const r = await request<RagEvalReport>('/api/rag/eval', { method: 'POST' })
  return r.data || ({ summary: {} as RagEvalSummary, by_category: {}, per_query: [] } as RagEvalReport)
}

export interface ServiceHealth {
  status: string
  version: string
  uptime_seconds: number
  checks: {
    database: { status: string }
    vector_store: { status: string; error?: string }
    models: { chat: string; embedding: string }
  }
}

export async function getHealth(): Promise<ServiceHealth> {
  const r = await request<ServiceHealth>('/health')
  return r.data
}

export async function getMetrics(): Promise<string> {
  const r = await request<string>('/metrics', { headers: { Accept: 'text/plain' } })
  return r.data as unknown as string || ''
}

export async function getRagSupportedFormats(): Promise<{
  supported: string[]
  categories: Record<string, string[]>
  max_size_mb: number
}> {
  const r = await request<{
    supported: string[]
    categories: Record<string, string[]>
    max_size_mb: number
  }>('/api/rag/supported-formats')
  return r.data
}

export async function uploadRagDocument(
  file: File, documentId: string, tenantId: string, category: string = 'general',
) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('document_id', documentId)
  formData.append('tenant_id', tenantId)
  formData.append('category', category)
  const token = localStorage.getItem('token') || ''
  const r = await fetch('/api/rag/upload', {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error(err.detail || `Upload failed: ${r.status}`)
  }
  return await r.json()
}

export async function getRagStats(tenantId?: string) {
  const url = tenantId ? `/api/rag/stats?tenant_id=${tenantId}` : '/api/rag/stats'
  const r = await request<any>(url)
  return r.data
}
