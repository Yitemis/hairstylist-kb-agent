import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { getToken, getRole, getUser } from './utils/auth'
import Toast from './components/Toast'

// P2-6: 路由懒加载（首屏只加载必要页面，admin 页面按需加载）
const CustomerLoginPage = lazy(() => import('./pages/customer/LoginPage'))
const CustomerRegisterPage = lazy(() => import('./pages/customer/RegisterPage'))
const CustomerChatPage = lazy(() => import('./pages/customer/ChatPage'))
const CustomerOrderListPage = lazy(() => import('./pages/customer/OrderListPage'))
const CustomerOrderDetailPage = lazy(() => import('./pages/customer/OrderDetailPage'))

// Admin pages
const AdminLoginPage = lazy(() => import('./pages/admin/AdminLoginPage'))
const KnowledgePage = lazy(() => import('./pages/admin/KnowledgePage'))
const OrderManagePage = lazy(() => import('./pages/admin/OrderManagePage'))
const BranchManagePage = lazy(() => import('./pages/admin/BranchManagePage'))
const StylistManagePage = lazy(() => import('./pages/admin/StylistManagePage'))
const ServiceManagePage = lazy(() => import('./pages/admin/ServiceManagePage'))
const RagEvalPage = lazy(() => import('./pages/admin/RagEvalPage'))
const ArchivePage = lazy(() => import('./pages/admin/ArchivePage'))
const MonitorPage = lazy(() => import('./pages/admin/MonitorPage'))

// Customer extra pages
const MemoryPage = lazy(() => import('./pages/customer/MemoryPage'))
import { ErrorBoundary } from './components/ErrorBoundary'

/* ── Guards ─────────────────────────────────────────────── */
// N5 修复: getToken() 现在永远返回 null (HttpOnly Cookie 模式)，
// 改用 getUser() 判断 user 信息是否存在。
function CustomerGuard({ children }: { children: React.ReactNode }) {
  if (!getUser()) return <Navigate to="/customer/login" replace />
  return <>{children}</>
}

function AdminGuard({ children }: { children: React.ReactNode }) {
  if (!getUser() || getRole() !== 'admin') return <Navigate to="/admin/login" replace />
  return <>{children}</>
}

/* ── Root redirect ──────────────────────────────────────── */
function RootRedirect() {
  const user = getUser()
  const role = getRole()
  if (!user) return <Navigate to="/customer/login" replace />
  if (role === 'admin') return <Navigate to="/admin/knowledge" replace />
  return <Navigate to="/customer/chat" replace />
}

/* ── Demo landing ───────────────────────────────────────── */
function DemoLanding() {
  return (
    <div style={{
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #eef2ff 0%, #f8fafc 50%, #fdf4ff 100%)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: 20,
      fontFamily: "'Inter', sans-serif",
    }}>
      <div style={{ maxWidth: 680, width: '100%' }}>
        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <div style={{
            width: 72, height: 72, borderRadius: 22, margin: '0 auto 20px',
            background: 'linear-gradient(135deg, #6366f1, #818cf8)',
            boxShadow: '0 8px 32px rgba(99,102,241,0.35)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <svg width="36" height="36" viewBox="0 0 36 36" fill="none">
              <path d="M18 4C13 4 9 8 9 13c0 3.2 1.6 5.9 4 7.6V23h10v-2.4c2.4-1.7 4-4.4 4-7.6 0-5-4-9-9-9z" fill="white"/>
              <path d="M14 23h8v2.5c0 .8-.7 1.5-1.5 1.5h-5c-.8 0-1.5-.7-1.5-1.5V23z" fill="rgba(255,255,255,0.6)"/>
            </svg>
          </div>
          <h1 style={{ fontSize: 28, fontWeight: 800, color: '#1e293b' }}>美发智能预约系统</h1>
          <p style={{ color: '#64748b', fontSize: 16, marginTop: 8 }}>选择你的身份进入对应端</p>
        </div>

        {/* Cards */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {/* Customer */}
          <a href="/customer/login" style={{ textDecoration: 'none' }}>
            <div style={{
              background: '#fff', borderRadius: 20, padding: 28, border: '2px solid #e0e7ff',
              cursor: 'pointer', transition: 'all 0.2s', boxShadow: '0 4px 20px rgba(0,0,0,0.06)',
            }}
            onMouseOver={e => { (e.currentTarget as HTMLElement).style.transform = 'translateY(-3px)'; (e.currentTarget as HTMLElement).style.borderColor = '#6366f1'; (e.currentTarget as HTMLElement).style.boxShadow = '0 8px 30px rgba(99,102,241,0.18)' }}
            onMouseOut={e => { (e.currentTarget as HTMLElement).style.transform = 'translateY(0)'; (e.currentTarget as HTMLElement).style.borderColor = '#e0e7ff'; (e.currentTarget as HTMLElement).style.boxShadow = '0 4px 20px rgba(0,0,0,0.06)' }}
            >
              <div style={{ fontSize: 40, marginBottom: 14 }}>📱</div>
              <h2 style={{ fontSize: 20, fontWeight: 700, color: '#1e293b', marginBottom: 8 }}>顾客端</h2>
              <p style={{ fontSize: 14, color: '#64748b', lineHeight: 1.6 }}>手机 H5 界面，AI 对话智能预约，订单查看与管理</p>
              <div style={{ marginTop: 18, display: 'inline-flex', alignItems: 'center', gap: 6, color: '#6366f1', fontWeight: 600, fontSize: 14 }}>
                进入顾客端 →
              </div>
            </div>
          </a>

          {/* Admin */}
          <a href="/admin/login" style={{ textDecoration: 'none' }}>
            <div style={{
              background: '#fff', borderRadius: 20, padding: 28, border: '2px solid #e0e7ff',
              cursor: 'pointer', transition: 'all 0.2s', boxShadow: '0 4px 20px rgba(0,0,0,0.06)',
            }}
            onMouseOver={e => { (e.currentTarget as HTMLElement).style.transform = 'translateY(-3px)'; (e.currentTarget as HTMLElement).style.borderColor = '#6366f1'; (e.currentTarget as HTMLElement).style.boxShadow = '0 8px 30px rgba(99,102,241,0.18)' }}
            onMouseOut={e => { (e.currentTarget as HTMLElement).style.transform = 'translateY(0)'; (e.currentTarget as HTMLElement).style.borderColor = '#e0e7ff'; (e.currentTarget as HTMLElement).style.boxShadow = '0 4px 20px rgba(0,0,0,0.06)' }}
            >
              <div style={{ fontSize: 40, marginBottom: 14 }}>🖥️</div>
              <h2 style={{ fontSize: 20, fontWeight: 700, color: '#1e293b', marginBottom: 8 }}>员工管理端</h2>
              <p style={{ fontSize: 14, color: '#64748b', lineHeight: 1.6 }}>PC 管理后台，知识库问答、订单/分店/发型师管理</p>
              <div style={{ marginTop: 18, display: 'inline-flex', alignItems: 'center', gap: 6, color: '#6366f1', fontWeight: 600, fontSize: 14 }}>
                进入管理后台 →
              </div>
            </div>
          </a>
        </div>

        {/* Quick links */}
        <div style={{ marginTop: 24, background: '#fff', borderRadius: 16, padding: '16px 20px', border: '1px solid #f1f5f9' }}>
          <p style={{ fontSize: 13, fontWeight: 600, color: '#94a3b8', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }}>快速预览</p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, fontSize: 13 }}>
            {[
              { href: '/customer/login', label: '顾客登录' },
              { href: '/customer/chat', label: 'AI 预约对话' },
              { href: '/customer/orders', label: '我的订单' },
              { href: '/admin/login', label: '员工登录' },
              { href: '/admin/knowledge', label: '知识库问答' },
              { href: '/admin/orders', label: '订单管理' },
              { href: '/admin/branches', label: '分店管理' },
              { href: '/admin/stylists', label: '发型师管理' },
              { href: '/admin/services', label: '服务项目' },
              { href: '/admin/rag-eval', label: 'RAG 评估' },
              { href: '/admin/archive',  label: '数据归档' },
              { href: '/admin/monitor',  label: '实时监控' },
              { href: '/customer/memory', label: '我的记忆' },
            ].map(l => (
              <a key={l.href} href={l.href} style={{ color: '#6366f1', textDecoration: 'none', padding: '6px 10px', borderRadius: 8, background: '#f5f3ff', display: 'block', textAlign: 'center', transition: 'all 0.12s' }}
                onMouseOver={e => { (e.target as HTMLElement).style.background = '#ede9fe' }}
                onMouseOut={e => { (e.target as HTMLElement).style.background = '#f5f3ff' }}
              >
                {l.label}
              </a>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

/* ── App ─────────────────────────────────────────────────── */
export default function App() {
  return (
    <BrowserRouter>
      <Toast />
      <Routes>
        {/* Demo landing */}
        <Route path="/" element={<DemoLanding />} />

        {/* Customer routes */}
        <Route path="/customer/login"      element={<Suspense fallback={null}><CustomerLoginPage /></Suspense>} />
        <Route path="/customer/register"   element={<Suspense fallback={null}><CustomerRegisterPage /></Suspense>} />
        <Route path="/customer/chat"       element={<CustomerGuard><Suspense fallback={null}><CustomerChatPage /></Suspense></CustomerGuard>} />
        <Route path="/customer/orders"     element={<CustomerGuard><Suspense fallback={null}><CustomerOrderListPage /></Suspense></CustomerGuard>} />
        <Route path="/customer/orders/:id" element={<CustomerGuard><CustomerOrderDetailPage /></CustomerGuard>} />
        <Route path="/customer/memory"     element={<CustomerGuard><MemoryPage /></CustomerGuard>} />

        {/* Admin routes */}
        <Route path="/admin/login"      element={<Suspense fallback={null}><AdminLoginPage /></Suspense>} />
        <Route path="/admin/knowledge"  element={<AdminGuard><ErrorBoundary><Suspense fallback={null}><KnowledgePage /></Suspense></ErrorBoundary></AdminGuard>} />
        <Route path="/admin/orders"     element={<AdminGuard><ErrorBoundary><Suspense fallback={null}><OrderManagePage /></Suspense></ErrorBoundary></AdminGuard>} />
        <Route path="/admin/branches"   element={<AdminGuard><ErrorBoundary><Suspense fallback={null}><BranchManagePage /></Suspense></ErrorBoundary></AdminGuard>} />
        <Route path="/admin/stylists"   element={<AdminGuard><ErrorBoundary><Suspense fallback={null}><StylistManagePage /></Suspense></ErrorBoundary></AdminGuard>} />
        <Route path="/admin/services"   element={<AdminGuard><ErrorBoundary><Suspense fallback={null}><ServiceManagePage /></Suspense></ErrorBoundary></AdminGuard>} />
        <Route path="/admin/rag-eval"   element={<AdminGuard><Suspense fallback={null}><RagEvalPage /></Suspense></AdminGuard>} />
        <Route path="/admin/archive"    element={<AdminGuard><Suspense fallback={null}><ArchivePage /></Suspense></AdminGuard>} />
        <Route path="/admin/monitor"    element={<AdminGuard><Suspense fallback={null}><MonitorPage /></Suspense></AdminGuard>} />

        {/* Fallback */}
        <Route path="*" element={<RootRedirect />} />
      </Routes>
    </BrowserRouter>
  )
}
