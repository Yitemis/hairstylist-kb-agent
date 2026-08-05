import { getToken } from './auth'

// 错误抛出：携带后端返回的 detail 信息
export class ApiError extends Error {
  status: number
  detail: string
  constructor(status: number, detail: string) {
    super(detail || `请求错误: ${status}`)
    this.status = status
    this.detail = detail
  }
}

// 统一响应格式：{code, data, message}，但后端接口没包装，这里做兼容
// 如果后端直接返回了非包装数据，自动包成 {code:0, data: 原始数据, message: 'ok'}
function wrap(data: any): { code: number; data: any; message: string } {
  if (data && typeof data === 'object' && 'code' in data && 'data' in data) {
    return data as any
  }
  return { code: 0, data, message: 'ok' }
}

// 基础请求封装
async function request<T = any>(
  url: string,
  options: RequestInit = {}
): Promise<{ code: number; data: T; message: string }> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(url, {
    ...options,
    headers,
  })

  const text = await response.text()
  let data: any = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    // 不是 JSON
  }

  if (!response.ok) {
    if (response.status === 401) {
      localStorage.clear()
      window.location.href = '/customer/login'
      throw new ApiError(401, data?.detail || '未授权，请重新登录')
    }
    throw new ApiError(response.status, data?.detail || `请求错误: ${response.status}`)
  }

  return wrap(data)
}

// ========== 认证接口 ==========

export interface RegisterRequest {
  name: string
  phone: string
  password: string
}

export interface LoginRequest {
  phone: string
  password: string
  role?: 'user' | 'staff'
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: {
    id: number
    name: string
    phone: string
    role: string
  }
}

export async function registerCustomer(data: RegisterRequest) {
  return request<TokenResponse>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function loginCustomer(data: LoginRequest) {
  return request<TokenResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function loginStaff(data: LoginRequest) {
  return request<TokenResponse>('/api/auth/staff/login', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// ========== 分店接口 ==========

export interface Branch {
  id: number
  name: string
  address: string
  phone: string | null
  description: string | null
  latitude: number | null
  longitude: number | null
  max_daily_appointments: number | null
  is_active: boolean
}

export async function listBranches() {
  return request<Branch[]>('/api/branches', {
    method: 'GET',
  })
}

// ========== 发型师接口 ==========

export interface Stylist {
  id: number
  branch_id: number | null
  name: string
  avatar: string | null
  specialties: string[]
  description: string | null
  max_daily_hours: number
  is_active: boolean
}

export async function listStylists(branchId?: number) {
  const url = branchId ? `/api/stylists?branch_id=${branchId}` : '/api/stylists'
  return request<Stylist[]>(url, {
    method: 'GET',
  })
}

// ========== 服务接口 ==========

export interface Service {
  id: number
  name: string
  category: string
  duration_minutes: number
  price: number | null
  description: string | null
  is_active: boolean
}

export async function listServices() {
  return request<Service[]>('/api/services', {
    method: 'GET',
  })
}

// ========== 订单接口 ==========

export interface Order {
  id: number
  order_no: string
  user_id: number
  branch_id: number | null
  branch_name: string | null
  stylist_id: number | null
  stylist_name: string | null
  service_id: number | null
  service_type: string | null
  service_details: string | null
  appointment_date: string | null
  appointment_time: string | null
  end_time: string | null
  duration_minutes: number | null
  total_price: number | null
  customer_phone: string | null
  customer_name: string | null
  address: string | null
  note: string | None
  status: string
  created_at: string
  updated_at: string
}

export async function listMyOrders() {
  return request<Order[]>('/api/orders', {
    method: 'GET',
  })
}

export async function getOrderDetail(orderId: number) {
  return request<Order>(`/api/orders/${orderId}`, {
    method: 'GET',
  })
}

// ========== 管理后台接口 ==========

// 订单管理
export async function adminListOrders(status?: string) {
  let url = '/api/admin/orders'
  if (status) {
    url += `?status=${status}`
  }
  return request<Order[]>(url, { method: 'GET' })
}

export async function adminUpdateOrderStatus(orderId: number, status: string, note?: string) {
  return request<Order>(`/api/admin/orders/${orderId}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status, note }),
  })
}

// 分店管理（仅admin）
export async function adminCreateBranch(data: Partial<Branch>) {
  return request<Branch>('/api/admin/branches', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function adminUpdateBranch(id: number, data: Partial<Branch>) {
  return request<Branch>(`/api/admin/branches/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function adminDeleteBranch(id: number) {
  return request(`/api/admin/branches/${id}`, {
    method: 'DELETE',
  })
}

// 发型师管理
export async function adminCreateStylist(data: Partial<Stylist>) {
  return request<Stylist>('/api/admin/stylists', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function adminUpdateStylist(id: number, data: Partial<Stylist>) {
  return request<Stylist>(`/api/admin/stylists/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function adminDeleteStylist(id: number) {
  return request(`/api/admin/stylists/${id}`, {
    method: 'DELETE',
  })
}

// 服务管理
export async function adminCreateService(data: Partial<Service>) {
  return request<Service>('/api/admin/services', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function adminUpdateService(id: number, data: Partial<Service>) {
  return request<Service>(`/api/admin/services/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function adminDeleteService(id: number) {
  return request(`/api/admin/services/${id}`, {
    method: 'DELETE',
  })
}

// ========== 对话接口 ==========

export interface ChatRequest {
  message: string
  session_id?: string
  user_id: number
}

export interface ChatOption {
  type: 'branch' | 'stylist' | 'service'
  id: number
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

export async function sendChat(message: string, userId: number, sessionId?: string) {
  return request<ChatResponse>('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ message, session_id: sessionId, user_id: userId }),
  })
}


/**
 * SSE 流式对话：实时接收 Agent 思考 / 工具调用 / 最终答案。
 * 用 fetch + ReadableStream 实现（EventSource 不支持 POST）。
 * 
 * 事件流（与后端 app/core/events.py 对应）：
 *   intent      {intent, mode}              意图识别结果
 *   thinking    {text}                       模型思考过程
 *   text        {delta}                      文本片段（增量）
 *   tool_call   {name, args}                 正在调用工具
 *   tool_result {name, summary}              工具返回结果摘要
 *   options     {items}                      可点击选项
 *   done        {answer, mode, options}      完成
 *   error       {message}                    出错
 */
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
      Authorization: token ? `Bearer ${token}` : '',
    },
    body: JSON.stringify({ message, session_id: sessionId, user_id: userId }),
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
    // SSE 消息以 

 分隔
    let idx: number
    while ((idx = buffer.indexOf('

')) !== -1) {
      const raw = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 4)
      // 解析 event: / data: 行
      const lines = raw.split('
')
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
      } catch (e) {
        // ignore parse error
      }
    }
  }
}


export default {
  registerCustomer,
  loginCustomer,
  loginStaff,
  listBranches,
  listStylists,
  listServices,
  listMyOrders,
  getOrderDetail,
  adminListOrders,
  adminUpdateOrderStatus,
  adminCreateBranch,
  adminUpdateBranch,
  adminDeleteBranch,
  adminCreateStylist,
  adminUpdateStylist,
  adminDeleteStylist,
  adminCreateService,
  adminUpdateService,
  adminDeleteService,
  sendChat,
}
