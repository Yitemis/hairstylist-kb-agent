import { useNavigate, useLocation } from 'react-router-dom'
import { clearAuth, getUser } from '../../utils/auth'

const NAV_ITEMS = [
  {
    path: '/admin/knowledge',
    label: '知识库问答',
    group: 'AI',
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <path d="M2 3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3z" stroke="currentColor" strokeWidth="1.4" />
        <path d="M6 6h6M6 9h6M6 12h3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    path: '/admin/documents',
    label: '文档管理',
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <path d="M3 2h8l4 4v10a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round"/>
        <path d="M11 2v4h4" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round"/>
        <path d="M5 9h8M5 12h8M5 15h5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    path: '/admin/orders',
    label: '订单管理',
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <rect x="2" y="2" width="14" height="14" rx="2" stroke="currentColor" strokeWidth="1.4" />
        <path d="M5 6H13M5 9H13M5 12H9" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    path: '/admin/branches',
    label: '分店管理',
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <path d="M9 2C6.2 2 4 4.2 4 7c0 4 5 9 5 9s5-5 5-9c0-2.8-2.2-5-5-5z" stroke="currentColor" strokeWidth="1.4" />
        <circle cx="9" cy="7" r="2" stroke="currentColor" strokeWidth="1.3" />
      </svg>
    ),
  },
  {
    path: '/admin/stylists',
    label: '发型师管理',
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <circle cx="9" cy="6" r="3.5" stroke="currentColor" strokeWidth="1.4" />
        <path d="M2 16c0-3.3 3.1-6 7-6s7 2.7 7 6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    path: '/admin/services',
    label: '服务项目管理',
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <path d="M9 2L11 7H16L12 10.5L13.5 16L9 13L4.5 16L6 10.5L2 7H7L9 2Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    path: '/admin/rag-eval',
    label: 'RAG 质量评估',
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <polyline points="2,14 6,8 10,11 14,4 16,6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="16" cy="6" r="1.5" fill="currentColor" />
      </svg>
    ),
  },
  {
    path: '/admin/archive',
    label: '数据归档管理',
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <rect x="2" y="4" width="14" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.4" />
        <path d="M2 7h14" stroke="currentColor" strokeWidth="1.3" />
        <path d="M6 2h6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        <path d="M7 11h4M9 9v4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    path: '/admin/monitor',
    label: '实时监控',
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <rect x="1" y="2" width="16" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.4" />
        <path d="M5 15h8M9 13v2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        <path d="M4 10l2.5-4L9 9l2.5-3L14 8" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
]

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const nav = useNavigate()
  const loc = useLocation()
  const user = getUser()

  const handleLogout = () => {
    clearAuth()
    nav('/admin/login')
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      {/* Sidebar */}
      <aside className="admin-sidebar">
        {/* Logo */}
        <div style={{ padding: '22px 20px 18px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 10,
              background: 'linear-gradient(135deg, #6366f1, #818cf8)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path d="M9 2C6.5 2 4.5 4 4.5 6.5c0 1.8.9 3.3 2.3 4.2V13h4.4v-2.3c1.4-.9 2.3-2.4 2.3-4.2C13.5 4 11.5 2 9 2z" fill="white" />
                <path d="M6.8 13h4.4v1.5c0 .5-.4.9-.9.9H7.7c-.5 0-.9-.4-.9-.9V13z" fill="rgba(255,255,255,0.6)" />
              </svg>
            </div>
            <div>
              <p style={{ color: '#f1f5f9', fontWeight: 700, fontSize: 14 }}>美发管理后台</p>
              <p style={{ color: '#475569', fontSize: 11 }}>Hair Admin v2.0</p>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: '12px 10px', overflowY: 'auto' }}>
          {/* Business section */}
          <p style={{ fontSize: 10, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 600, padding: '6px 12px 4px', marginBottom: 2 }}>业务管理</p>
          {NAV_ITEMS.slice(0, 6).map(item => {
            const active = loc.pathname === item.path
            return (
              <button
                key={item.path}
                onClick={() => nav(item.path)}
                style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', borderRadius: 10, border: 'none', background: active ? 'rgba(99,102,241,0.18)' : 'transparent', color: active ? '#a5b4fc' : '#64748b', fontSize: 14, fontWeight: active ? 600 : 400, cursor: 'pointer', marginBottom: 2, textAlign: 'left', transition: 'all 0.12s' }}
                onMouseOver={e => { if (!active) e.currentTarget.style.background = 'rgba(255,255,255,0.04)' }}
                onMouseOut={e => { if (!active) e.currentTarget.style.background = 'transparent' }}
              >
                <span style={{ opacity: active ? 1 : 0.6 }}>{item.icon}</span>
                {item.label}
              </button>
            )
          })}
          {/* System section */}
          <p style={{ fontSize: 10, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 600, padding: '14px 12px 4px', marginBottom: 2 }}>系统工具</p>
          {NAV_ITEMS.slice(6).map(item => {
            const active = loc.pathname === item.path
            return (
              <button
                key={item.path}
                onClick={() => nav(item.path)}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '10px 12px',
                  borderRadius: 10,
                  border: 'none',
                  background: active ? 'rgba(99,102,241,0.18)' : 'transparent',
                  color: active ? '#a5b4fc' : '#64748b',
                  fontSize: 14,
                  fontWeight: active ? 600 : 400,
                  cursor: 'pointer',
                  marginBottom: 2,
                  textAlign: 'left',
                  transition: 'all 0.12s',
                }}
                onMouseOver={e => { if (!active) e.currentTarget.style.background = 'rgba(255,255,255,0.04)' }}
                onMouseOut={e => { if (!active) e.currentTarget.style.background = 'transparent' }}
              >
                <span style={{ opacity: active ? 1 : 0.6 }}>{item.icon}</span>
                {item.label}
              </button>
            )
          })}
        </nav>

        {/* User */}
        <div style={{ padding: '14px 10px', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', borderRadius: 10 }}>
            <div style={{
              width: 34, height: 34, borderRadius: 10, flexShrink: 0,
              background: '#334155',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: '#94a3b8', fontSize: 13, fontWeight: 600,
            }}>
              {user?.name?.slice(-1) || 'A'}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ color: '#f1f5f9', fontSize: 13, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {user?.name || '管理员'}
              </p>
              <p style={{ color: '#475569', fontSize: 11 }}>{user?.phone}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '8px 12px',
              borderRadius: 8,
              border: 'none',
              background: 'transparent',
              color: '#ef4444',
              fontSize: 13,
              cursor: 'pointer',
              marginTop: 4,
            }}
            onMouseOver={e => { e.currentTarget.style.background = 'rgba(239,68,68,0.08)' }}
            onMouseOut={e => { e.currentTarget.style.background = 'transparent' }}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M5 2H2.5a.5.5 0 0 0-.5.5v9a.5.5 0 0 0 .5.5H5M9 10l3-3-3-3M12 7H5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            退出登录
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="admin-main" style={{ flex: 1 }}>
        {children}
      </main>
    </div>
  )
}
