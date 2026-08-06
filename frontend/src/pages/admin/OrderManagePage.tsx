import { useState } from 'react'
import AdminLayout from '../../components/admin/AdminLayout'
import { showToast } from '../../utils/toast'

type OrderStatus = 'pending' | 'confirmed' | 'done' | 'cancelled'

interface Order {
  id: string; customer: string; branch: string; stylist: string; service: string; date: string; phone: string; status: OrderStatus; price: number
}

const STATUS_OPT: { value: OrderStatus; label: string; cls: string }[] = [
  { value: 'pending',   label: '待确认', cls: 'badge badge-pending' },
  { value: 'confirmed', label: '已确认', cls: 'badge badge-confirmed' },
  { value: 'done',      label: '已完成', cls: 'badge badge-done' },
  { value: 'cancelled', label: '已取消', cls: 'badge badge-cancelled' },
]

const INIT_ORDERS: Order[] = [
  { id: 'ORD-20250701-001', customer: '李美华', branch: '三里屯旗舰店', stylist: '陈晓磊', service: '烫发（数码烫）', date: '2025-07-05 10:00', phone: '138****0001', status: 'confirmed', price: 580 },
  { id: 'ORD-20250701-002', customer: '王小明', branch: '国贸中心店',   stylist: '王芳芳',  service: '剪发',          date: '2025-07-06 09:00', phone: '139****0002', status: 'pending',   price: 120 },
  { id: 'ORD-20250702-001', customer: '张丽华', branch: '三里屯旗舰店', stylist: '待分配',  service: '染发全头',      date: '2025-07-07 14:00', phone: '186****0003', status: 'pending',   price: 460 },
  { id: 'ORD-20250623-008', customer: '刘晓东', branch: '国贸中心店',   stylist: '王芳芳',  service: '剪发+造型',     date: '2025-06-23 14:00', phone: '135****0004', status: 'done',      price: 220 },
  { id: 'ORD-20250618-003', customer: '陈芳',   branch: '西单商场店',   stylist: '刘志远',  service: '护发护理',      date: '2025-06-18 11:30', phone: '180****0005', status: 'done',      price: 180 },
  { id: 'ORD-20250610-007', customer: '赵磊',   branch: '三里屯旗舰店', stylist: '陈晓磊',  service: '烫发（冷烫）', date: '2025-06-10 15:00', phone: '159****0006', status: 'cancelled', price: 380 },
  { id: 'ORD-20250609-002', customer: '孙芸',   branch: '西单商场店',   stylist: '刘志远',  service: '染发挑染',      date: '2025-06-09 10:00', phone: '177****0007', status: 'done',      price: 320 },
]

const PAGE_SIZE = 5

function StatusSelect({ value, onChange }: { value: OrderStatus; onChange: (v: OrderStatus) => void }) {
  return (
    <select
      className="select-field"
      value={value}
      onChange={e => onChange(e.target.value as OrderStatus)}
      style={{ fontSize: 12 }}
    >
      {STATUS_OPT.map(o => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  )
}

export default function OrderManagePage() {
  const [orders, setOrders] = useState<Order[]>(INIT_ORDERS)
  const [filter, setFilter] = useState<'all' | OrderStatus>('all')
  const [page, setPage] = useState(1)

  const filtered = filter === 'all' ? orders : orders.filter(o => o.status === filter)
  const pages = Math.ceil(filtered.length / PAGE_SIZE)
  const paged = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const handleStatusChange = (id: string, newStatus: OrderStatus) => {
    setOrders(prev => prev.map(o => o.id === id ? { ...o, status: newStatus } : o))
    showToast('订单状态已更新', 'success')
  }

  const statCounts = STATUS_OPT.reduce((acc, s) => ({ ...acc, [s.value]: orders.filter(o => o.status === s.value).length }), {} as Record<string, number>)

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
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M12.5 7A5.5 5.5 0 1 1 7 1.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/><path d="M12.5 1.5V5.5H8.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></svg>
              刷新
            </button>
          </div>
        </div>

        {/* Stat cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 20 }}>
          {[
            { label: '待确认', key: 'pending', color: '#f59e0b', bg: '#fffbeb' },
            { label: '已确认', key: 'confirmed', color: '#10b981', bg: '#ecfdf5' },
            { label: '已完成', key: 'done', color: '#6366f1', bg: '#eef2ff' },
            { label: '已取消', key: 'cancelled', color: '#ef4444', bg: '#fef2f2' },
          ].map(s => (
            <div
              key={s.key}
              className="card"
              style={{ padding: '14px 18px', cursor: 'pointer', border: `1px solid ${filter === s.key ? s.color + '40' : 'transparent'}` }}
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
                  {['订单编号', '顾客姓名', '分店', '发型师', '服务项目', '预约日期', '电话', '状态', '操作'].map(h => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {paged.map(order => {
                  const s = STATUS_OPT.find(x => x.value === order.status)!
                  return (
                    <tr key={order.id} className="animate-fade-up">
                      <td style={{ fontFamily: 'monospace', fontSize: 12, color: '#94a3b8' }}>{order.id.split('-').slice(-1)[0]}</td>
                      <td style={{ fontWeight: 500 }}>{order.customer}</td>
                      <td>{order.branch}</td>
                      <td>{order.stylist}</td>
                      <td>{order.service}</td>
                      <td style={{ fontSize: 13, color: '#64748b', whiteSpace: 'nowrap' }}>{order.date}</td>
                      <td style={{ fontSize: 13, color: '#64748b' }}>{order.phone}</td>
                      <td><span className={s.cls}>{s.label}</span></td>
                      <td>
                        <StatusSelect value={order.status} onChange={v => handleStatusChange(order.id, v)} />
                      </td>
                    </tr>
                  )
                })}
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
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M7.5 2L4 6L7.5 10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
              </button>
              {Array.from({ length: pages }, (_, i) => i + 1).map(p => (
                <button key={p} className={`page-btn${p === page ? ' active' : ''}`} onClick={() => setPage(p)}>{p}</button>
              ))}
              <button className="page-btn" disabled={page === pages} onClick={() => setPage(p => p + 1)}>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M4.5 2L8 6L4.5 10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </AdminLayout>
  )
}
