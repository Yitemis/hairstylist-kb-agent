import { useState, useEffect } from 'react'
import {
  adminListOrders,
  adminUpdateOrderStatus,
  adminCreateOrder,
  adminDeleteOrder,
  listBranches,
  listStylists,
  listServices,
  type Order,
} from '../../api'
import AdminLayout from '../../components/admin/AdminLayout'
import { showToast } from '../../utils/toast'

/** B 端可见的订单状态 (草稿仅 C 端对话流使用) */
type OrderStatus = 'pending' | 'confirmed' | 'done' | 'cancelled'

const STATUS_OPT: { value: OrderStatus; label: string; cls: string }[] = [
  { value: 'pending',   label: '待确认', cls: 'badge badge-pending' },
  { value: 'confirmed', label: '已确认', cls: 'badge badge-confirmed' },
  { value: 'done',      label: '已完成', cls: 'badge badge-done' },
  { value: 'cancelled', label: '已取消', cls: 'badge badge-cancelled' },
]

/** 状态机的合法转换 (B 端: 必须经过已确认才能到已完成) */
const ALLOWED_TRANSITIONS: Record<OrderStatus, OrderStatus[]> = {
  pending:   ['confirmed', 'cancelled'],
  confirmed: ['done', 'cancelled'],
  done:      [],
  cancelled: [],
}

const PAGE_SIZE = 5

function StatusSelect({
  value, onChange, orderId,
}: { value: OrderStatus; onChange: (id: number | string, v: OrderStatus) => void; orderId: number | string }) {
  const allowed = ALLOWED_TRANSITIONS[value] || []
  return (
    <select
      className="select-field"
      value={value}
      onChange={e => onChange(orderId, e.target.value as OrderStatus)}
      style={{ fontSize: 12 }}
    >
      <option value={value}>{STATUS_OPT.find(o => o.value === value)?.label || value}</option>
      {allowed.map(s => (
        <option key={s} value={s}>→ {STATUS_OPT.find(o => o.value === s)?.label}</option>
      ))}
    </select>
  )
}

export default function OrderManagePage() {
  const [orders, setOrders] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [filter, setFilter] = useState<'all' | OrderStatus>('all')
  const [page, setPage] = useState(1)
  const [showCreate, setShowCreate] = useState(false)

  const loadOrders = async () => {
    setLoading(true)
    try {
      const data: any = await adminListOrders()
      setOrders(data?.data || data || [])
    } catch (e: any) {
      showToast(e?.detail || e?.message || '加载订单失败', 'error')
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { loadOrders() }, [])

  const filtered = filter === 'all' ? orders : orders.filter((o: any) => o.status === filter)
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const paged = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const handleStatusChange = async (id: number | string, newStatus: OrderStatus) => {
    try {
      await adminUpdateOrderStatus(Number(id), newStatus)
      showToast('订单状态已更新', 'success')
      setOrders(prev => prev.map((o: any) => o.id === id ? { ...o, status: newStatus } : o))
    } catch (e: any) {
      showToast(e?.detail || e?.message || '状态更新失败', 'error')
      loadOrders()
    }
  }

  const handleDelete = async (id: number | string) => {
    if (!confirm('确认删除此订单?此操作不可恢复。')) return
    try {
      await adminDeleteOrder(Number(id))
      showToast('订单已删除', 'success')
      setOrders(prev => prev.filter((o: any) => o.id !== id))
    } catch (e: any) {
      showToast(e?.detail || e?.message || '删除失败', 'error')
    }
  }

  const statCounts = STATUS_OPT.reduce((acc, s) => ({ ...acc, [s.value]: orders.filter((o: any) => o.status === s.value).length }), {} as Record<string, number>)

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
            <button className="btn btn-ghost" onClick={loadOrders}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M12.5 7A5.5 5.5 0 1 1 7 1.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/><path d="M12.5 1.5V5.5H8.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></svg>
              刷新
            </button>
            <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 1.5v11M1.5 7h11" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>
              新建订单
            </button>
          </div>
        </div>

        {/* Stat cards: 4 status (B 端不显示草稿) */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 20 }}>
          {[
            { label: '待确认', key: 'pending',   color: '#f59e0b', bg: '#fffbeb' },
            { label: '已确认', key: 'confirmed', color: '#10b981', bg: '#ecfdf5' },
            { label: '已完成', key: 'done',      color: '#6366f1', bg: '#eef2ff' },
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
                  {['订单编号', '顾客', '电话', '分店', '发型师', '服务项目', '预约日期', '状态', '操作'].map(h => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr><td colSpan={9} style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>加载中…</td></tr>
                )}
                {!loading && paged.length === 0 && (
                  <tr><td colSpan={9} style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>暂无订单</td></tr>
                )}
                {!loading && paged.map((order: any) => {
                  const s = STATUS_OPT.find(x => x.value === order.status) || { value: 'pending', label: order.status, cls: 'badge badge-pending' }
                  return (
                    <tr key={order.id} className="animate-fade-up">
                      <td style={{ fontFamily: 'monospace', fontSize: 12, color: '#94a3b8' }}>{order.order_no?.slice(-10) || order.id}</td>
                      <td style={{ fontWeight: 500 }}>{order.customer_name || '未填写'}</td>
                      <td style={{ fontSize: 13, color: '#64748b' }}>{order.customer_phone || '-'}</td>
                      <td>{order.branch_name || '-'}</td>
                      <td>{order.stylist_name || '待分配'}</td>
                      <td>{order.service_type}</td>
                      <td style={{ fontSize: 13, color: '#64748b', whiteSpace: 'nowrap' }}>{order.appointment_date} {order.appointment_time || ''}</td>
                      <td><span className={s.cls}>{s.label}</span></td>
                      <td>
                        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                          <StatusSelect value={order.status} onChange={handleStatusChange} orderId={order.id} />
                          {order.status === 'cancelled' && (
                            <button
                              className="btn btn-ghost"
                              style={{ padding: '4px 10px', fontSize: 12, color: '#ef4444' }}
                              onClick={() => handleDelete(order.id)}
                              title="删除订单"
                            >
                              <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 3h8M4.5 3V1.5h3V3M3 3l.5 7h5l.5-7" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></svg>
                              删除
                            </button>
                          )}
                        </div>
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

      {showCreate && <CreateOrderModal onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); loadOrders() }} />}
    </AdminLayout>
  )
}

/* ============================================================
 * 新建订单弹窗（电话预约场景）
 * ============================================================ */
function CreateOrderModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [branches, setBranches] = useState<any[]>([])
  const [stylists, setStylists] = useState<any[]>([])
  const [services, setServices] = useState<any[]>([])
  const [submitting, setSubmitting] = useState(false)

  const [form, setForm] = useState({
    customer_name: '',
    customer_phone: '',
    branch_id: '' as string | number,
    stylist_id: '' as string | number,
    service_id: '' as string | number,
    service_type: '',
    appointment_date: new Date().toISOString().slice(0, 10),
    appointment_time: '10:00',
    note: '',
  })

  useEffect(() => {
    listBranches().then((d: any) => setBranches(d?.data || d || [])).catch(() => {})
    listServices().then((d: any) => setServices(d?.data || d || [])).catch(() => {})
  }, [])

  useEffect(() => {
    if (form.branch_id) {
      listStylists(Number(form.branch_id)).then((d: any) => setStylists(d?.data || d || [])).catch(() => setStylists([]))
    } else {
      setStylists([])
    }
  }, [form.branch_id])

  const handleSubmit = async () => {
    if (!form.customer_phone || form.customer_phone.length < 7) {
      showToast('请填写有效电话', 'error'); return
    }
    if (!form.branch_id || !form.stylist_id) {
      showToast('请选择分店和发型师', 'error'); return
    }
    if (!form.service_id && !form.service_type) {
      showToast('请选择服务项目或填写服务类型', 'error'); return
    }
    setSubmitting(true)
    try {
      const body: any = {
        customer_name: form.customer_name || undefined,
        customer_phone: form.customer_phone,
        branch_id: Number(form.branch_id),
        stylist_id: Number(form.stylist_id),
        service_id: form.service_id ? Number(form.service_id) : undefined,
        service_type: form.service_type || (services.find((s: any) => s.id === Number(form.service_id))?.name) || '电话预约',
        appointment_date: form.appointment_date,
        appointment_time: form.appointment_time,
        note: form.note || undefined,
      }
      await adminCreateOrder(body)
      showToast('订单已创建（已确认状态）', 'success')
      onCreated()
    } catch (e: any) {
      showToast(e?.detail || e?.message || '创建失败', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}
      onClick={onClose}
    >
      <div
        className="card animate-fade-up"
        style={{ width: '100%', maxWidth: 540, maxHeight: '90vh', overflow: 'auto', padding: 24 }}
        onClick={e => e.stopPropagation()}
      >
        <h2 style={{ fontSize: 18, fontWeight: 700, color: '#1e293b', marginBottom: 16 }}>新建订单（电话预约）</h2>
        <p style={{ fontSize: 12, color: '#94a3b8', marginBottom: 16 }}>订单创建后状态为「已确认」</p>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div className="form-group">
            <label className="form-label">顾客姓名</label>
            <input className="input-field" value={form.customer_name} onChange={e => setForm({ ...form, customer_name: e.target.value })} placeholder="选填" />
          </div>
          <div className="form-group">
            <label className="form-label">顾客电话 *</label>
            <input className="input-field" value={form.customer_phone} onChange={e => setForm({ ...form, customer_phone: e.target.value.replace(/\D/g, '') })} maxLength={11} placeholder="11 位手机号" />
          </div>
          <div className="form-group">
            <label className="form-label">分店 *</label>
            <select className="input-field" value={form.branch_id} onChange={e => setForm({ ...form, branch_id: e.target.value, stylist_id: '' })}>
              <option value="">请选择</option>
              {branches.map((b: any) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">发型师 *</label>
            <select className="input-field" value={form.stylist_id} onChange={e => setForm({ ...form, stylist_id: e.target.value })} disabled={!form.branch_id}>
              <option value="">{form.branch_id ? '请选择' : '请先选分店'}</option>
              {stylists.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">服务项目</label>
            <select
              className="input-field"
              value={form.service_id}
              onChange={e => {
                const sid = e.target.value
                const svc = services.find((x: any) => x.id === Number(sid))
                setForm({ ...form, service_id: sid, service_type: svc?.name || form.service_type })
              }}
            >
              <option value="">请选择（可手动填写）</option>
              {services.map((s: any) => <option key={s.id} value={s.id}>{s.name} ¥{s.price}</option>)}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">预约日期 *</label>
            <input className="input-field" type="date" value={form.appointment_date} onChange={e => setForm({ ...form, appointment_date: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label">预约时间 *</label>
            <input className="input-field" type="time" value={form.appointment_time} onChange={e => setForm({ ...form, appointment_time: e.target.value })} />
          </div>
          <div className="form-group" style={{ gridColumn: '1 / -1' }}>
            <label className="form-label">备注</label>
            <textarea className="input-field" rows={2} value={form.note} onChange={e => setForm({ ...form, note: e.target.value })} placeholder="选填" />
          </div>
        </div>

        <div style={{ display: 'flex', gap: 10, marginTop: 20, justifyContent: 'flex-end' }}>
          <button className="btn btn-ghost" onClick={onClose} disabled={submitting}>取消</button>
          <button className="btn btn-primary" onClick={handleSubmit} disabled={submitting}>
            {submitting ? '创建中…' : '创建订单'}
          </button>
        </div>
      </div>
    </div>
  )
}
