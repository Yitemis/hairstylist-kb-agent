/**HTTP 客户端基础。*/
import { getToken } from '../utils/auth'

export class ApiError extends Error {
  status: number
  detail: string
  constructor(status: number, detail: string) {
    super(detail || `请求错误: ${status}`)
    this.status = status
    this.detail = detail
  }
}

function wrap(data: any): { code: number; data: any; message: string } {
  if (data && typeof data === 'object' && 'code' in data && 'data' in data) return data as any
  return { code: 0, data, message: 'ok' }
}

export async function request<T = any>(
  url: string,
  options: RequestInit = {}
): Promise<{ code: number; data: T; message: string }> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const response = await fetch(url, { ...options, headers })
  const text = await response.text()
  let data: any = null
  try { data = text ? JSON.parse(text) : null } catch { /* not JSON */ }

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
