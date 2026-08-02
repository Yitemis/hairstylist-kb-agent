import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getOrderDetail } from '../../utils/api'
import { showToast } from '../../utils/toast'
import type { Order } from '../../utils/api'

const STATUS_MAP: Record<string, { label: string; cls: string; desc: string }> = {
  draft:     { label: '草稿',   cls: 'badge badge-draft',      desc: '预约尚未提交，可继续编辑后提交' },
  pending:   { label: '待确认', cls: 'badge badge-pending',    desc: '门店正在审核你的预约，通常 30 分钟内回复' },
  confirmed: { label: '已确认', cls: 'badge badge-confirmed',  desc: '预约已确认，请按时到店' },
  completed: { label: '已完成', cls: 'badge badge-done',       desc: '服务已完成，感谢光临！' },
  cancelled:{ label: '已取消', cls: 'badge badge-cancelled',  desc: '本次预约已取消' },
}

function InfoRow({ icon, label, value }: { icon: string; label: string; value: string }) {
  return (
    <div style={{ display: 'flex', gap: 12, padding: '11px 0', borderBottom: '1px solid #f1f5f9' }}>
      <span style={{ fontSize: 16, flexShrink: 0, width: 22, textAlign: 'center' }}>{icon}</span>
      <div style={{ flex: 1 }}>
        <p style={{ fontSize: 12, color: '#94a3b8', marginBottom: 2 }}>{label}</p>
        <p style={{ fontSize: 14, color: '#1e293b', fontWeight: 500 }}>{value}</p>
      </div>
    </div>
  )
}

export default function CustomerOrderDetailPage() {
  const { id } = useParams<{ id: string }>()
  const nav = useNavigate()
  const [order, setOrder] = useState<Order | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchDetail() {
      if (!id) return
      try {
        const res = await getOrderDetail(parseInt(id))
        if (res.code !== 0) {
          showToast(res.message || '获取订单详情失败', 'error')
          return
        }
        setOrder(res.data)
      } catch (e) {
        showToast('网络错误', 'error')
      } finally {
        setLoading(false)
      }
    }
    fetchDetail()
  }, [id])

  if (loading) {
    return (
      <div className="mobile-shell flex flex-col items-center justify-center min-h-screen">
        <p style={{ color: '#64748b' }}>加载中...</p>
      </div>
    )
  }

  if (!order) {
    return (
      <div className="mobile-shell flex flex-col items-center justify-center min-h-screen">
        <p style={{ fontSize: 40, marginBottom: 12 }}>🔍</p>
        <p style={{ color: '#64748b' }}>找不到此订单</p>
        <button className="btn btn-primary" style={{ marginTop: 16 }} onClick={() => nav('/customer/orders')}>返回订单列表</button>
      </div>
    )
  }

  const s = STATUS_MAP[order.status] || STATUS_MAP.draft

  const formatTimeRange = () => {
    if (!order.appointment_date) return ''
    let str = order.appointment_date
    if (order.appointment_time && order.end_time) {
      str += `  ${order.appointment_time} – ${order.end_time}`
    }
    return str
  }

  return (
    <div className="mobile-shell flex flex-col min-h-screen" style={{ background: '#f8fafc' }}>
      {/* Nav */}
      <div className="mobile-nav" style={{ boxShadow: '0 1px 0 #f1f5f9' }}>
        <button
          style={{ background: 'none', border: 'none', padding: 4, marginRight: 8, color: '#1e293b' }}
          onClick={() => nav('/customer/orders')}
        >
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M12 4L6 10L12 16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        <span className="font-semibold text-base" style={{ color: '#1e293b' }}>订单详情</span>
      </div>

      <div className="flex-1 scrollbar-hide animate-fade-up" style={{ overflowY: 'auto', padding: '14px' }}>
        {/* Status banner */}
        <div
          className="card"
          style={{ padding: '16px 18px', marginBottom: 12, background: 'linear-gradient(135deg, #6366f1 0%, #818cf8 100%)', border: 'none' }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={{ color: 'rgba(255,255,255,0.75)', fontSize: 12 }}>{order.order_no}</span>
            <span style={{
              fontSize: 12, padding: '3px 10px', borderRadius: 999,
              background: 'rgba(255,255,255,0.2)', color: '#fff', fontWeight: 500,
            }}>
              {s.label}
            </span>
          </div>
          <p style={{ color: '#fff', fontWeight: 600, fontSize: 18 }}>{order.service_type}</p>
          <p style={{ color: 'rgba(255,255,255,0.75)', fontSize: 13, marginTop: 4 }}>{s.desc}</p>
        </div>

        {/* Details card */}
        <div className="card" style={{ padding: '4px 16px', marginBottom: 12 }}>
          {order.branch_name && <InfoRow icon="📍" label="门店" value={order.branch_name} />}
          {order.branch_id && order.address && <InfoRow icon="🗺" label="地址" value={order.address} />}
          {order.stylist_name && <InfoRow icon="💇" label="发型师" value={order.stylist_name} />}
          {order.service_type && <InfoRow icon="✂️" label="服务项目" value={order.service_type} />}
          <InfoRow icon="📅" label="预约时间" value={formatTimeRange()} />
          {order.duration_minutes && <InfoRow icon="⏱" label="预计时长" value={`约 ${order.duration_minutes} 分钟`} />}
          {order.total_price && <InfoRow icon="💰" label="总价" value={`¥${order.total_price}`} />}
          {order.customer_phone && <InfoRow icon="📞" label="联系电话" value={order.customer_phone} />}
          {order.note && <InfoRow icon="📝" label="备注" value={order.note} />}
        </div>
      </div>

      {/* Actions */}
      {(order.status === 'draft' || order.status === 'confirmed' || order.status === 'pending') && (
        <div style={{ padding: '12px 14px', background: '#fff', borderTop: '1px solid #f1f5f9', display: 'flex', gap: 10 }}>
          {order.status === 'draft' && (
            <button
              className="btn btn-primary"
              style={{ flex: 1, height: 46, borderRadius: 12, fontSize: 15 }}
              onClick={() => nav('/customer/chat?edit=' + order.id)}
            >
              继续编辑
            </button>
          )}
          {(order.status === 'confirmed' || order.status === 'pending') && (
            <button
              className="btn btn-danger"
              style={{ flex: 1, height: 46, borderRadius: 12, fontSize: 15 }}
              onClick={() => {
                showToast('请联系门店取消预约', 'info')
              }}
            >
              取消预约
            </button>
          )}
        </div>
      )}
    </div>
  )
}
