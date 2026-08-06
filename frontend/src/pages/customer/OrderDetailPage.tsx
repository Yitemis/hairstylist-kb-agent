import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { showToast } from '../../utils/toast'

type OrderStatus = 'draft' | 'pending' | 'confirmed' | 'done' | 'cancelled'

interface OrderDetail {
  id: string
  branch: string
  address: string
  stylist: string
  service: string
  date: string
  duration: string
  price: number
  phone: string
  note: string
  status: OrderStatus
}

const ORDER_DB: Record<string, OrderDetail> = {
  'ORD-20250701-001': {
    id: 'ORD-20250701-001',
    branch: '三里屯旗舰店',
    address: '朝阳区三里屯路19号，尚街LOFT B座2层',
    stylist: '陈晓磊 (高级发型师)',
    service: '烫发（数码烫）',
    date: '2025年7月5日  10:00 – 13:00',
    duration: '约 3 小时',
    price: 580,
    phone: '010-8888-1234',
    note: '希望烫出自然蓬松的大波浪，不要太卷',
    status: 'confirmed',
  },
  'ORD-20250623-008': {
    id: 'ORD-20250623-008',
    branch: '国贸中心店',
    address: '朝阳区建国路87号，CCTV旁',
    stylist: '王芳芳 (资深发型师)',
    service: '剪发 + 造型',
    date: '2025年6月23日  14:00 – 16:00',
    duration: '约 2 小时',
    price: 220,
    phone: '010-8888-5678',
    note: '',
    status: 'done',
  },
}

const STATUS_MAP: Record<OrderStatus, { label: string; cls: string; desc: string }> = {
  draft:     { label: '草稿',   cls: 'badge badge-draft',      desc: '预约尚未提交，可继续编辑后提交' },
  pending:   { label: '待确认', cls: 'badge badge-pending',    desc: '门店正在审核你的预约，通常 30 分钟内回复' },
  confirmed: { label: '已确认', cls: 'badge badge-confirmed',  desc: '预约已确认，请按时到店' },
  done:      { label: '已完成', cls: 'badge badge-done',       desc: '服务已完成，感谢光临！' },
  cancelled: { label: '已取消', cls: 'badge badge-cancelled',  desc: '本次预约已取消' },
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
  const [cancelling, setCancelling] = useState(false)

  const order = id ? ORDER_DB[id] : null

  if (!order) {
    return (
      <div className="mobile-shell flex flex-col items-center justify-center min-h-screen">
        <p style={{ fontSize: 40, marginBottom: 12 }}>🔍</p>
        <p style={{ color: '#64748b' }}>找不到此订单</p>
        <button className="btn btn-primary" style={{ marginTop: 16 }} onClick={() => nav('/customer/orders')}>返回订单列表</button>
      </div>
    )
  }

  const s = STATUS_MAP[order.status]

  const handleCancel = async () => {
    setCancelling(true)
    await new Promise(r => setTimeout(r, 1000))
    setCancelling(false)
    showToast('订单已取消', 'info')
    nav('/customer/orders')
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
            <span style={{ color: 'rgba(255,255,255,0.75)', fontSize: 12 }}>{order.id}</span>
            <span style={{
              fontSize: 12, padding: '3px 10px', borderRadius: 999,
              background: 'rgba(255,255,255,0.2)', color: '#fff', fontWeight: 500,
            }}>
              {s.label}
            </span>
          </div>
          <p style={{ color: '#fff', fontWeight: 600, fontSize: 18 }}>{order.service}</p>
          <p style={{ color: 'rgba(255,255,255,0.75)', fontSize: 13, marginTop: 4 }}>{s.desc}</p>
        </div>

        {/* Details card */}
        <div className="card" style={{ padding: '4px 16px', marginBottom: 12 }}>
          <InfoRow icon="📍" label="门店" value={order.branch} />
          <InfoRow icon="🗺" label="地址" value={order.address} />
          <InfoRow icon="💇" label="发型师" value={order.stylist} />
          <InfoRow icon="✂️" label="服务项目" value={order.service} />
          <InfoRow icon="📅" label="预约时间" value={order.date} />
          <InfoRow icon="⏱" label="预计时长" value={order.duration} />
          <InfoRow icon="💰" label="总价" value={`¥${order.price}`} />
          <InfoRow icon="📞" label="门店电话" value={order.phone} />
          {order.note && <InfoRow icon="📝" label="备注" value={order.note} />}
        </div>

        {/* Timeline */}
        <div className="card" style={{ padding: '14px 16px' }}>
          <p style={{ fontWeight: 600, fontSize: 14, color: '#1e293b', marginBottom: 12 }}>预约进度</p>
          {[
            { label: '提交预约', done: true, time: '2025-07-01 10:32' },
            { label: '门店确认', done: order.status !== 'draft' && order.status !== 'pending', time: order.status === 'confirmed' || order.status === 'done' ? '2025-07-01 10:58' : '-' },
            { label: '服务中', done: order.status === 'done', time: order.status === 'done' ? '2025-07-05 10:05' : '-' },
            { label: '服务完成', done: order.status === 'done', time: order.status === 'done' ? '2025-07-05 12:50' : '-' },
          ].map((step, i) => (
            <div key={i} style={{ display: 'flex', gap: 12, paddingBottom: i < 3 ? 14 : 0, position: 'relative' }}>
              {i < 3 && (
                <div style={{
                  position: 'absolute', left: 11, top: 22, width: 2, height: 14,
                  background: step.done ? '#6366f1' : '#e2e8f0',
                }} />
              )}
              <div style={{
                width: 24, height: 24, borderRadius: '50%', flexShrink: 0,
                background: step.done ? '#6366f1' : '#e2e8f0',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                {step.done
                  ? <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 6L4.5 8.5L10 3.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  : <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#cbd5e1' }} />
                }
              </div>
              <div>
                <p style={{ fontSize: 14, fontWeight: 500, color: step.done ? '#1e293b' : '#94a3b8' }}>{step.label}</p>
                <p style={{ fontSize: 12, color: '#94a3b8', marginTop: 1 }}>{step.time}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Actions */}
      {(order.status === 'draft' || order.status === 'confirmed' || order.status === 'pending') && (
        <div style={{ padding: '12px 14px', background: '#fff', borderTop: '1px solid #f1f5f9', display: 'flex', gap: 10 }}>
          {order.status === 'draft' && (
            <button
              className="btn btn-primary"
              style={{ flex: 1, height: 46, borderRadius: 12, fontSize: 15 }}
              onClick={() => nav('/customer/chat')}
            >
              继续编辑
            </button>
          )}
          {(order.status === 'confirmed' || order.status === 'pending') && (
            <button
              className="btn btn-danger"
              style={{ flex: 1, height: 46, borderRadius: 12, fontSize: 15 }}
              onClick={handleCancel}
              disabled={cancelling}
            >
              {cancelling
                ? <svg className="spin" width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" strokeDasharray="8 6"/></svg>
                : '取消预约'
              }
            </button>
          )}
        </div>
      )}
    </div>
  )
}
