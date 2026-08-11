/** 认证工具 (P1-4: token 走 HttpOnly Cookie，不再存 localStorage 防 XSS)。

- 兼容旧版本：如果 localStorage 已有 token，会清理掉
- 新登录：token 由后端 set_cookie 写入，浏览器自动管理
- getToken() 返回 null（前端不需要 token），但保留函数避免改太多代码
*/
export type Role = 'customer' | 'admin'

export interface UserInfo {
  name: string
  phone: string
  role: Role
}

const USER_KEY = 'hair_user'
const ROLE_KEY = 'hair_role'

// 旧版本 token key (P1-4: 清理)
const LEGACY_TOKEN_KEY = 'hair_token'

export function saveAuth(_token: string, user: UserInfo) {
  // P1-4: 不再存 token 到 localStorage（后端已 set HttpOnly Cookie）
  // 只存 user 信息（用于显示）
  localStorage.setItem(USER_KEY, JSON.stringify(user))
  localStorage.setItem(ROLE_KEY, user.role)
  // 清理旧版 token
  localStorage.removeItem(LEGACY_TOKEN_KEY)
}

export function getToken(): string | null {
  // P1-4: 永远返回 null（token 在 HttpOnly Cookie 里，前端拿不到也不需要拿）
  // fetch() 会自动带 cookie (credentials: 'include')
  return null
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
  localStorage.removeItem(USER_KEY)
  localStorage.removeItem(ROLE_KEY)
  localStorage.removeItem(LEGACY_TOKEN_KEY)
  // P1-4: 通知后端清 cookie
  fetch('/api/auth/logout', { method: 'POST', credentials: 'include' }).catch(() => {})
}

export function isLoggedIn(): boolean {
  // P1-4: 改为判断 user 是否存在（Cookie 由后端管）
  return !!getUser()
}
