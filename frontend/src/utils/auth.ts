export const AUTH_KEY = 'hair_token'
export const USER_KEY = 'hair_user'
export const ROLE_KEY = 'hair_role'

export type Role = 'customer' | 'admin' | 'worker'

export interface UserInfo {
  name: string
  phone: string
  role: Role
}

export function saveAuth(token: string, user: UserInfo) {
  localStorage.setItem(AUTH_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
  localStorage.setItem(ROLE_KEY, user.role)
}

export function getToken(): string | null {
  return localStorage.getItem(AUTH_KEY)
}

export function getUser(): UserInfo | null {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}

export function getRole(): Role | null {
  return localStorage.getItem(ROLE_KEY) as Role | null
}

export function clearAuth() {
  localStorage.removeItem(AUTH_KEY)
  localStorage.removeItem(USER_KEY)
  localStorage.removeItem(ROLE_KEY)
}

export function isLoggedIn(): boolean {
  return !!getToken()
}
