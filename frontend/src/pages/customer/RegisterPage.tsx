import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { saveAuth } from '../../utils/auth'
import { showToast } from '../../utils/toast'
import { registerCustomer } from '../../utils/api'

export default function CustomerRegisterPage() {
  const nav = useNavigate()
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [showPwd, setShowPwd] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleRegister = async () => {
    if (!name.trim()) { showToast('请输入姓名', 'error'); return }
    if (phone.length !== 11) { showToast('请输入 11 位手机号', 'error'); return }
    if (password.length < 6) { showToast('密码至少 6 位', 'error'); return }
    setLoading(true)
    try {
      const res = await registerCustomer({ name, phone, password, role: 'user' })
      if (!res.data?.access_token) {
        showToast(res.message || '注册失败', 'error')
        return
      }
      saveAuth(res.data.access_token, res.data.user)
      showToast('注册成功', 'success')
      nav('/customer/chat')
    } catch (e: any) {
      showToast(e?.detail || e?.message || '网络错误，请重试', 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mobile-shell flex flex-col min-h-screen" style={{ background: '#f8fafc' }}>
      {/* Nav */}
      <div className="mobile-nav">
        <button
          style={{ background: 'none', border: 'none', padding: 4, marginRight: 8, color: '#1e293b' }}
          onClick={() => nav('/customer/login')}
        >
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M12 4L6 10L12 16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        <span className="font-semibold text-base" style={{ color: '#1e293b' }}>新用户注册</span>
      </div>

      {/* Form */}
      <div className="flex-1 px-6 pt-6 animate-fade-up">
        <div className="card p-6">
          {/* Name */}
          <div className="form-group">
            <label className="form-label">你的姓名</label>
            <input
              className="input-field"
              placeholder="请输入你的姓名"
              value={name}
              onChange={e => setName(e.target.value)}
            />
          </div>

          {/* Phone */}
          <div className="form-group">
            <label className="form-label">手机号</label>
            <input
              className="input-field"
              type="tel"
              maxLength={11}
              placeholder="请输入手机号"
              value={phone}
              onChange={e => setPhone(e.target.value.replace(/\D/g, ''))}
            />
          </div>

          {/* Password */}
          <div className="form-group">
            <label className="form-label">设置密码</label>
            <div style={{ position: 'relative' }}>
              <input
                className="input-field"
                style={{ paddingRight: 40 }}
                type={showPwd ? 'text' : 'password'}
                placeholder="请设置密码（至少 6 位）"
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
                  : <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M1 9C3 5 5.5 3 9 3s6 2 8 6c-2 4-4.5 6-8 6S3 13 1 9z" stroke="currentColor" strokeWidth="1.4"/></svg>
                }
              </button>
            </div>
            <p className="text-xs mt-1.5" style={{ color: '#94a3b8' }}>密码长度 6–20 位，建议包含数字和字母</p>
          </div>

          {/* Terms */}
          <p className="text-xs mt-2 mb-4" style={{ color: '#94a3b8' }}>
            注册即代表你同意{' '}
            <span style={{ color: '#6366f1' }}>《用户协议》</span>
            {' '}和{' '}
            <span style={{ color: '#6366f1' }}>《隐私政策》</span>
          </p>

          {/* Register btn */}
          <button
            className="btn btn-primary w-full"
            style={{ height: 48, fontSize: 16, borderRadius: 12 }}
            onClick={handleRegister}
            disabled={loading}
          >
            {loading
              ? <svg className="spin" width="18" height="18" viewBox="0 0 18 18" fill="none"><circle cx="9" cy="9" r="7" stroke="rgba(255,255,255,0.4)" strokeWidth="2"/><path d="M9 2a7 7 0 0 1 7 7" stroke="white" strokeWidth="2" strokeLinecap="round"/></svg>
              : '注册并登录'
            }
          </button>

          <p className="text-center mt-4 text-sm" style={{ color: '#94a3b8' }}>
            已有账号？{' '}
            <button
              style={{ background: 'none', border: 'none', color: '#6366f1', fontWeight: 500, padding: 0 }}
              onClick={() => nav('/customer/login')}
            >
              去登录 →
            </button>
          </p>
        </div>
      </div>
    </div>
  )
}
