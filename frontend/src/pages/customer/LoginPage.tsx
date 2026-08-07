import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { saveAuth } from '../../utils/auth'
import { loginCustomer } from '../../utils/api'
import { showToast } from '../../utils/toast'

export default function CustomerLoginPage() {
  const nav = useNavigate()
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [showPwd, setShowPwd] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleLogin = async () => {
    if (phone.length !== 11) { showToast('请输入 11 位手机号', 'error'); return }
    if (password.length < 6) { showToast('密码至少 6 位', 'error'); return }
    setLoading(true)
    try {
      const res: any = await loginCustomer({ phone, password })
      const data = res.data || res
      if (!data?.access_token) {
        showToast(res.message || data?.detail || '登录失败', 'error')
        return
      }
      saveAuth(data.access_token, data.user || { name: '用户', phone, role: 'customer' })
      showToast('登录成功', 'success')
      nav('/customer/chat')
    } catch (e: any) {
      showToast(e?.detail || e?.message || '登录失败', 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mobile-shell flex flex-col min-h-screen" style={{ background: 'linear-gradient(160deg, #f0f0ff 0%, #f8fafc 50%, #fff 100%)' }}>
      {/* Top illustration */}
      <div className="flex flex-col items-center pt-16 pb-8 px-8 animate-fade-up">
        <div
          className="w-20 h-20 rounded-3xl flex items-center justify-center mb-4"
          style={{ background: 'linear-gradient(135deg, #6366f1, #818cf8)', boxShadow: '0 8px 24px rgba(99,102,241,0.35)' }}
        >
          <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
            <path d="M20 6C14.5 6 10 10.5 10 16c0 3.8 2 7 5 8.8V28h10v-3.2c3-1.8 5-5 5-8.8 0-5.5-4.5-10-10-10z" fill="white" />
            <path d="M15 28h10v3.5c0 .8-.7 1.5-1.5 1.5h-7c-.8 0-1.5-.7-1.5-1.5V28z" fill="rgba(255,255,255,0.65)" />
            <circle cx="17" cy="14" r="1.5" fill="rgba(99,102,241,0.5)" />
            <circle cx="23" cy="14" r="1.5" fill="rgba(99,102,241,0.5)" />
          </svg>
        </div>
        <h1 className="text-2xl font-bold" style={{ color: '#1e293b' }}>美发智能助手</h1>
        <p className="text-sm mt-1.5" style={{ color: '#94a3b8' }}>智能预约 · 专业咨询</p>
      </div>

      {/* Card */}
      <div className="flex-1 px-6 animate-fade-up" style={{ animationDelay: '0.08s' }}>
        <div className="card p-6">
          <h2 className="text-lg font-semibold mb-5" style={{ color: '#1e293b' }}>顾客登录</h2>

          {/* Phone */}
          <div className="form-group">
            <label className="form-label">手机号</label>
            <div style={{ position: 'relative' }}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)' }}>
                <rect x="3" y="1" width="10" height="14" rx="2" stroke="#94a3b8" strokeWidth="1.4" />
                <circle cx="8" cy="12" r="0.8" fill="#94a3b8" />
              </svg>
              <input
                className="input-field"
                style={{ paddingLeft: 36 }}
                type="tel"
                maxLength={11}
                placeholder="请输入手机号"
                value={phone}
                onChange={e => setPhone(e.target.value.replace(/\D/g, ''))}
              />
            </div>
          </div>

          {/* Password */}
          <div className="form-group">
            <label className="form-label">密码</label>
            <div style={{ position: 'relative' }}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)' }}>
                <rect x="3" y="7" width="10" height="8" rx="1.5" stroke="#94a3b8" strokeWidth="1.4" />
                <path d="M5 7V5a3 3 0 0 1 6 0v2" stroke="#94a3b8" strokeWidth="1.4" />
              </svg>
              <input
                className="input-field"
                style={{ paddingLeft: 36, paddingRight: 40 }}
                type={showPwd ? 'text' : 'password'}
                placeholder="请输入密码"
                value={password}
                onChange={e => setPassword(e.target.value)}
              />
              <button
                type="button"
                onClick={() => setShowPwd(s => !s)}
                style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', padding: 2, color: '#94a3b8' }}
              >
                {showPwd
                  ? <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M1 9C3 5 5.5 3 9 3s6 2 8 6c-2 4-4.5 6-8 6S3 13 1 9z" stroke="currentColor" strokeWidth="1.4"/><circle cx="9" cy="9" r="2.5" stroke="currentColor" strokeWidth="1.4"/><path d="M2 2L16 16" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
                  : <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M1 9C3 5 5.5 3 9 3s6 2 8 6c-2 4-4.5 6-8 6S3 13 1 9z" stroke="currentColor" strokeWidth="1.4"/><circle cx="9" cy="9" r="2.5" stroke="currentColor" strokeWidth="1.4"/></svg>
                }
              </button>
            </div>
          </div>

          {/* Login btn */}
          <button
            className="btn btn-primary w-full mt-2"
            style={{ height: 48, fontSize: 16, borderRadius: 12 }}
            onClick={handleLogin}
            disabled={loading}
          >
            {loading
              ? <svg className="spin" width="18" height="18" viewBox="0 0 18 18" fill="none"><circle cx="9" cy="9" r="7" stroke="rgba(255,255,255,0.4)" strokeWidth="2"/><path d="M9 2a7 7 0 0 1 7 7" stroke="white" strokeWidth="2" strokeLinecap="round"/></svg>
              : '登 录'
            }
          </button>

          <p className="text-center mt-4 text-sm" style={{ color: '#94a3b8' }}>
            没有账号？{' '}
            <button
              style={{ background: 'none', border: 'none', color: '#6366f1', fontWeight: 500, padding: 0 }}
              onClick={() => nav('/customer/register')}
            >
              立即注册 →
            </button>
          </p>
        </div>

        {/* Quick demo */}
        <button
          className="w-full mt-3 text-sm"
          style={{ background: 'none', border: 'none', color: '#94a3b8', padding: '8px 0' }}
          onClick={() => {
            // demo phone removed
            setPassword('123456')
          }}
        >
          使用演示账号填充
        </button>
      </div>

      <p className="text-center text-xs pb-6 mt-4" style={{ color: '#cbd5e1' }}>
        © 2025 美发智能助手 · 安全登录
      </p>
    </div>
  )
}
