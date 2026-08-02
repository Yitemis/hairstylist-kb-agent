import { useState, useEffect } from 'react'
import AdminLayout from '../../components/admin/AdminLayout'
import { adminListOrders, adminUpdateOrderStatus, type Order } from '../../utils/api'
import { showToast } from '../../utils/toast'

type OrderStatus = 'pending' | 'confirmed' | 'completed' | 'cancelled'

const STATUS_OPT: { value: OrderStatus; label: string; cls: string }[] = [
  { value: 'pending',   label: '待确认', cls: 'badge badge-pending' },
  { value: 'confirmed', label: '已确认', cls: 'badge badge-confirmed' },
  { value: 'completed',      label: '已完成', cls: 'badge badge-done' },
  { value: 'cancelled', label: '已取消', cls: 'badge badge-cancelled' },
]

const PAGE_SIZE = 10

function StatusSelect({ value, onChange, orderId }: { value: OrderStatus; onChange: (id: number, v: OrderStatus) => void; orderId: number }) {
  return (
    <select
      className="select-field"
      value={value}
      onChange={e => onChange(orderId, e.target.value as OrderStatus)}
      style={{ fontSize: 12 }}
    >
      {STATUS_OPT.map(o => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  )
}

export default function OrderManagePage() {
  const [orders, setOrders] = useState<Order[]>([])
  const [filter, setFilter] = useState<'all' | OrderStatus>('all')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchOrders() {
      try {
        const res = await adminListOrders(filter === 'all' ? undefined : filter)
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
  }, [filter])

  const handleStatusChange = async (id: number, newStatus: OrderStatus) => {
    try {
      const res = await adminUpdateOrderStatus(id, newStatus)
      if (res.code !== 0) {
        showToast(res.message || '更新失败', 'error')
        return
      }
      setOrders(prev => prev.map(o => o.id === id ? { ...o, status: newStatus } : o))
      showToast('订单状态已更新', 'success')
    } catch (e) {
      showToast('网络错误', 'error')
    }
  }

  const filtered = filter === 'all' ? orders : orders.filter(o => o.status === filter)
  const pages = Math.ceil(filtered.length / PAGE_SIZE)
  const paged = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const statCounts = STATUS_OPT.reduce((acc, s) => ({
    ...acc,
    [s.value]: orders.filter(o => o.status === s.value).length
  }), {} as Record<string, number>)

  return (
    <AdminLayout>
      <div style={{ padding: 28 }}>
        {/* Page header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}>订单管理</h1>
            <p style={{ fontSize: 13, color: '#64748b', marginTop: 3 }}>共 {orders.length} 个订单</p>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <select
              className="select-field"
              value={filter}
              onChange={e => { setFilter(e.target.value as typeof filter); setPage(1) }}
            >
              <option value="all">全部状态</option>
              {STATUS_OPT.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <button className="btn btn-ghost" onClick={() => { setFilter('all'); setPage(1) }}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M12.5 7A5.5 5.5 0 1 1 7 1.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/><path d="M12.5 1.5V5.5H8.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></svg>
              刷新
            </button>
          </div>
        </div>

        {/* Stat cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 20 }}>
          {[
            { label: '待确认', key: 'pending', color: '#f59e0b', bg: '#fffbeb' },
            { label: '已确认', key: 'confirmed', color: '#10b981', bg: '#ecfdf5' },
            { label: '已完成', key: 'completed', color: '#6366f1', bg: '#eef2ff' },
            { label: '已取消', key: 'cancelled', color: '#ef4444', bg: '#fef2f2' },
          ].map(s => (
            <div
              key={s.key}
              className="card"
              style={{ padding: '14px 18px', cursor: 'pointer', border: `1px solid ${filter === s.key ? s.color + '40' : 'transparent'}`, background: s.bg }}
              onClick={() => { setFilter(s.key as typeof filter); setPage(1) }}
            >
              <p style={{ fontSize: 26, fontWeight: 700, color: s.color }}>{statCounts[s.key] || 0}</p>
              <p style={{ fontSize: 13, color: '#64748b', marginTop: 2 }}>{s.label}</p>
            </div>
          ))}
        </div>

        {/* Table */}
        <div className="card" style={{ overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  {['订单编号', '顾客', '分店', '发型师', '服务项目', '预约日期', '电话', '状态', '操作'].map(h => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={9} style={{ textAlign: 'center', padding: 30, color: '#94a3b8' }}>加载中...</td></tr>
                ) : paged.length === 0 ? (
                  <tr><td colSpan={9} style={{ textAlign: 'center', padding: 30, color: '#94a3b8' }}>暂无订单</td></tr>
                ) : (
                  paged.map(order => {
                    const s = STATUS_OPT.find(x => x.value === order.status)!
                    return (
                      <tr key={order.id} className="animate-fade-up">
                        <td style={{ fontFamily: 'monospace', fontSize: 12, color: '#94a3b8' }}>{order.order_no}</td>
                        <td style={{ fontWeight: 500 }}>{order.customer_name || order.customer_phone}</td>
                        <td>{order.branch_name || `#${order.branch_id}`}</td>
                        <td>{order.stylist_name || `#${order.stylist_id}`}</td>
                        <td>{order.service_type}</td>
                        <td style={{ fontSize: 13, color: '#64748b', whiteSpace: 'nowrap' }}>
                          {order.appointment_date} {order.appointment_time}
                        </td>
                        <td style={{ fontSize: 13, color: '#64748b' }}>{order.customer_phone}</td>
                        <td><span className={s.cls}>{s.label}</span></td>
                        <td>
                          <StatusSelect orderId={order.id} value={order.status as OrderStatus} onChange={handleStatusChange} />
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderTop: '1px solid #f1f5f9' }}>
            <p style={{ fontSize: 13, color: '#64748b' }}>
              显示 {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, filtered.length)} / 共 {filtered.length} 条
            </p>
            <div className="pagination">
              <button className="page-btn" disabled={page === 1} onClick={() => setPage(p => p - 1)}>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M7.5 2L4 6L7.5 10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></svg>
              </button>
              {Array.from({ length: pages }, (_, i) => i + 1).map(p => (
                <button key={p} className={`page-btn${p === page ? ' active' : ''}`} onClick={() => setPage(p)}>{p}</button>
              ))}
              <button className="page-btn" disabled={page === pages} onClick={() => setPage(p => p + 1)}>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M4.5 2L8 6L4.5 10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </AdminLayout>
  )
}
