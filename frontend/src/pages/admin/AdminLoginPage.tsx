import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { saveAuth } from '../../utils/auth'
import { showToast } from '../../utils/toast'
import { loginStaff } from '../../api/auth'

export default function AdminLoginPage() {
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
      const res: any = await loginStaff({ phone, password })
      const data = res.data || res
      if (!data?.access_token) {
        showToast(res.message || data?.detail || '登录失败', 'error')
        return
      }
      saveAuth(data.access_token, data.user || { name: phone, phone, role: 'admin' })
      showToast('登录成功', 'success')
      nav('/admin/knowledge')
    } catch (e: any) {
      showToast(e?.detail || e?.message || '登录失败', 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #f0f0ff 0%, #f8fafc 60%, #fff 100%)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: 20,
    }}>
      <div style={{ width: '100%', maxWidth: 440 }}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 32 }} className="animate-fade-up">
          <div style={{
            width: 64, height: 64, borderRadius: 20,
            background: 'linear-gradient(135deg, #6366f1, #818cf8)',
            boxShadow: '0 8px 24px rgba(99,102,241,0.35)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 16px',
          }}>
            <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
              <path d="M16 4C11 4 7 8 7 13c0 3.2 1.6 5.9 4 7.6V22h10v-1.4c2.4-1.7 4-4.4 4-7.6 0-5-4-9-9-9z" fill="white" />
              <path d="M12 22h8v2.5c0 .8-.7 1.5-1.5 1.5h-5c-.8 0-1.5-.7-1.5-1.5V22z" fill="rgba(255,255,255,0.6)" />
            </svg>
          </div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}>管理后台登录</h1>
          <p style={{ fontSize: 14, color: '#94a3b8', marginTop: 6 }}>美发智能管理系统 · 员工专用</p>
        </div>

        {/* Card */}
        <div
          className="card animate-fade-up"
          style={{ padding: 32, animationDelay: '0.08s' }}
        >
          {/* Phone */}
          <div className="form-group">
            <label className="form-label">手机号</label>
            <input
              className="input-field"
              type="tel"
              maxLength={11}
              placeholder="请输入员工手机号"
              value={phone}
              onChange={e => setPhone(e.target.value.replace(/\D/g, ''))}
            />
          </div>

          {/* Password */}
          <div className="form-group">
            <label className="form-label">密码</label>
            <div style={{ position: 'relative' }}>
              <input
                className="input-field"
                style={{ paddingRight: 42 }}
                type={showPwd ? 'text' : 'password'}
                placeholder="请输入密码"
                value={password}
                onChange={e => setPassword(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleLogin() }}
              />
              <button
                type="button"
                onClick={() => setShowPwd(s => !s)}
                style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', padding: 2, color: '#94a3b8', cursor: 'pointer' }}
              >
                {showPwd
                  ? <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M1 9C3 5 5.5 3 9 3s6 2 8 6c-2 4-4.5 6-8 6S3 13 1 9z" stroke="currentColor" strokeWidth="1.4"/><circle cx="9" cy="9" r="2.5" stroke="currentColor" strokeWidth="1.4"/><path d="M2 2L16 16" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
                  : <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M1 9C3 5 5.5 3 9 3s6 2 8 6c-2 4-4.5 6-8 6S3 13 1 9z" stroke="currentColor" strokeWidth="1.4"/><circle cx="9" cy="9" r="2.5" stroke="currentColor" strokeWidth="1.4"/></svg>
                }
              </button>
            </div>
          </div>

          <button
            className="btn btn-primary w-full"
            style={{ height: 46, fontSize: 15, marginTop: 8 }}
            onClick={handleLogin}
            disabled={loading}
          >
            {loading
              ? <svg className="spin" width="18" height="18" viewBox="0 0 18 18" fill="none"><circle cx="9" cy="9" r="7" stroke="rgba(255,255,255,0.4)" strokeWidth="2"/><path d="M9 2a7 7 0 0 1 7 7" stroke="white" strokeWidth="2" strokeLinecap="round"/></svg>
              : '登 录'
            }
          </button>

          <button
            className="w-full"
            style={{ marginTop: 12, background: 'none', border: 'none', color: '#94a3b8', fontSize: 13, cursor: 'pointer', padding: '6px 0' }}
            onClick={() => { setPhone('13800138001'); setPassword('admin123') }}
          >
            使用演示账号填充
          </button>
        </div>

        <p style={{ textAlign: 'center', color: '#cbd5e1', fontSize: 12, marginTop: 20 }}>
          © 2025 美发管理系统 · 仅限授权员工访问
        </p>
      </div>
    </div>
  )
}
