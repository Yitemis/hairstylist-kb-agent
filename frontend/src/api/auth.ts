/**认证 API：注册 / 登录 / Token。*/
import { request } from './client'

export interface RegisterRequest {
  name: string
  phone: string
  password: string
}

export interface LoginRequest {
  phone: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: {
    id: number
    phone: string
    name: string
    role: string
    avatar?: string | null
  }
}

export async function registerCustomer(data: RegisterRequest) {
  const r = await request<TokenResponse>('/api/auth/register', {
    method: 'POST', body: JSON.stringify(data),
  })
  return r
}

export async function loginCustomer(data: LoginRequest) {
  const r = await request<TokenResponse>('/api/auth/login', {
    method: 'POST', body: JSON.stringify(data),
  })
  return r
}

export async function loginStaff(data: LoginRequest) {
  const r = await request<TokenResponse>('/api/auth/staff/login', {
    method: 'POST', body: JSON.stringify(data),
  })
  return r
}
