import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { listMyOrders, type Order } from '../../utils/api'
import { showToast } from '../../utils/toast'

type OrderStatus = 'draft' | 'pending' | 'confirmed' | 'completed' | 'cancelled'

const STATUS_MAP: Record<string, { label: string; cls: string }> = {
  draft:     { label: '草稿',   cls: 'badge badge-draft' },
  pending:   { label: '待确认', cls: 'badge badge-pending' },
  confirmed: { label: '已确认', cls: 'badge badge-confirmed' },
  completed: { label: '已完成', cls: 'badge badge-done' },
  cancelled:{ label: '已取消', cls: 'badge badge-cancelled' },
}

const TABS: { key: 'all' | OrderStatus; label: string }[] = [
  { key: 'all',       label: '全部' },
  { key: 'draft',     label: '草稿' },
  { key: 'pending',   label: '待确认' },
  { key: 'confirmed', label: '已确认' },
  { key: 'completed', label: '已完成' },
  { key: 'cancelled', label: '已取消' },
]

export default function CustomerOrderListPage() {
  const nav = useNavigate()
  const [tab, setTab] = useState<'all' | OrderStatus>('all')
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchOrders() {
      try {
        const res = await listMyOrders()
        if (res.code !== 0) {
          showToast(res.message || '获取订单失败', 'error')
          return
        }
        setOrders(res.data || [])
      } catch (e) {
        showToast('网络错误', 'error')
      } finally {
        setLoading(false)
      }
    }
    fetchOrders()
  }, [])

  const filtered = tab === 'all'
    ? orders
    : orders.filter(o => o.status === tab)

  return (
    <div className="mobile-shell flex flex-col min-h-screen" style={{ background: '#f8fafc' }}>
      {/* Nav */}
      <div className="mobile-nav" style={{ boxShadow: '0 1px 0 #f1f5f9' }}>
        <button
          style={{ background: 'none', border: 'none', padding: 4, marginRight: 8, color: '#1e293b' }}
          onClick={() => nav('/customer/chat')}
        >
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M12 4L6 10L12 16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        <span className="font-semibold text-base" style={{ color: '#1e293b' }}>我的预约</span>
      </div>

      {/* Tabs */}
      <div className="tab-bar" style={{ background: '#fff', borderBottom: '1px solid #f1f5f9' }}>
        {TABS.map(t => (
          <button
            key={t.key}
            className={`tab-item${tab === t.key ? ' active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Orders */}
      <div className="flex-1 scrollbar-hide" style={{ overflowY: 'auto', padding: '12px 14px' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px 20px', color: '#94a3b8' }}>
            <p style={{ fontSize: 15 }}>加载中...</p>
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '60px 20px', color: '#94a3b8' }}>
            <p style={{ fontSize: 40, marginBottom: 12 }}>📋</p>
            <p style={{ fontSize: 15 }}>暂无相关订单</p>
          </div>
        ) : (
          filtered.map((order, idx) => (
            <div
              key={order.id}
              className="card animate-fade-up"
              style={{ padding: '14px 16px', marginBottom: 10, cursor: 'pointer', animationDelay: `${idx * 0.04}s` }}
              onClick={() => nav(`/customer/orders/${order.id}`)}
            >
              {/* Header */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                <span style={{ fontSize: 12, color: '#94a3b8', fontFamily: 'monospace' }}>{order.order_no}</span>
                <span className={STATUS_MAP[order.status]?.cls || STATUS_MAP.draft.cls}>{STATUS_MAP[order.status]?.label || order.status}</span>
              </div>

              {/* Content */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 1C4.8 1 3 2.8 3 5c0 3 4 8 4 8s4-5 4-8c0-2.2-1.8-4-4-4z" stroke="#6366f1" strokeWidth="1.3"/><circle cx="7" cy="5" r="1.5" stroke="#6366f1" strokeWidth="1.3"/></svg>
                  <span style={{ fontSize: 14, fontWeight: 600, color: '#1e293b' }}>{order.branch_name || `分店 #${order.branch_id}`}</span>
                </div>
                <div style={{ display: 'flex', gap: 16, fontSize: 13, color: '#64748b' }}>
                  <span>💇 {order.stylist_name || `发型师 #${order.stylist_id}`}</span>
                  <span>✂️ {order.service_type}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 4 }}>
                  <span style={{ fontSize: 13, color: '#64748b' }}>📅 {order.appointment_date} {order.appointment_time}</span>
                  {order.total_price && (
                    <span style={{ fontSize: 16, fontWeight: 700, color: '#6366f1' }}>¥{order.total_price}</span>
                  )}
                </div>
              </div>

              {/* Arrow */}
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M6 4L10 8L6 12" stroke="#cbd5e1" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
            </div>
          ))
        )}
      </div>

      {/* New appointment */}
      <div style={{ padding: '12px 14px', background: '#fff', borderTop: '1px solid #f1f5f9' }}>
        <button
          className="btn btn-primary w-full"
          style={{ height: 46, fontSize: 15, borderRadius: 12 }}
          onClick={() => nav('/customer/chat')}
        >
          + 新建预约
        </button>
      </div>
    </div>
  )
}
