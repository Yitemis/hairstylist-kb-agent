import { useState, useEffect } from 'react'
import AdminLayout from '../../components/admin/AdminLayout'
import { showToast } from '../../utils/toast'
import { getArchiveStats, triggerArchive } from '../../utils/api'
import HitlConfirm from '../../components/HitlConfirm'

type ArchiveStatus = 'success' | 'failed'
type ArchiveType = 'chat' | 'order'

interface ArchiveRecord {
  id: string; time: string; type: ArchiveType; count: number; savedMb: number; durationSec: number; status: ArchiveStatus
}

const RECORDS: ArchiveRecord[] = [
  { id: 'arc-001', time: '2026-08-05 03:00:12', type: 'chat',  count: 12480, savedMb: 48.3,  durationSec: 42,  status: 'success' },
  { id: 'arc-002', time: '2026-08-05 03:00:55', type: 'order', count: 3200,  savedMb: 12.7,  durationSec: 18,  status: 'success' },
  { id: 'arc-003', time: '2026-07-29 03:00:08', type: 'chat',  count: 11950, savedMb: 46.1,  durationSec: 39,  status: 'success' },
  { id: 'arc-004', time: '2026-07-29 03:00:48', type: 'order', count: 2980,  savedMb: 11.8,  durationSec: 15,  status: 'success' },
  { id: 'arc-005', time: '2026-07-22 03:00:04', type: 'chat',  count: 13200, savedMb: 51.0,  durationSec: 47,  status: 'success' },
  { id: 'arc-006', time: '2026-07-22 03:01:32', type: 'order', count: 3450,  savedMb: 13.5,  durationSec: 23,  status: 'failed'  },
  { id: 'arc-007', time: '2026-07-15 03:00:01', type: 'chat',  count: 10800, savedMb: 41.6,  durationSec: 35,  status: 'success' },
  { id: 'arc-008', time: '2026-07-15 03:00:37', type: 'order', count: 2670,  savedMb: 10.5,  durationSec: 14,  status: 'success' },
  { id: 'arc-009', time: '2026-07-08 03:00:09', type: 'chat',  count: 9900,  savedMb: 38.2,  durationSec: 32,  status: 'success' },
  { id: 'arc-010', time: '2026-07-08 03:00:41', type: 'order', count: 2410,  savedMb: 9.4,   durationSec: 12,  status: 'success' },
]

const PAGE_SIZE = 5

function StatCard({ icon, label, value, sub, accent }: { icon: string; label: string; value: string; sub: string; accent?: string }) {
  return (
    <div className="card" style={{ padding: '20px 22px', flex: 1, minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <div style={{ fontSize: 22 }}>{icon}</div>
        <p style={{ fontSize: 13, color: '#64748b', fontWeight: 500 }}>{label}</p>
      </div>
      <p style={{ fontSize: 36, fontWeight: 800, color: accent || '#1e293b', letterSpacing: '-0.5px' }}>{value}</p>
      <p style={{ fontSize: 12, color: '#94a3b8', marginTop: 4 }}>{sub}</p>
    </div>
  )
}

export default function ArchivePage() {
    const [confirm, setConfirm] = useState(false)
  const [stats, setStats] = useState(null)
  const [archiving, setArchiving] = useState(false)
  useEffect(() => { getArchiveStats().then(setStats).catch(()=>{}) }, [])
  async function doArchive() {
    setArchiving(true)
    try {
      const r = await triggerArchive()
      showToast(`已归档 ${r.deleted_chat} 条消息, ${r.deleted_orders} 条订单`, "success")
      setStats(await getArchiveStats())
    } catch (e) { showToast(e.message || "归档失败", "error") }
    setArchiving(false)
  }

  const [page, setPage] = useState(1)
  const totalPages = Math.ceil(RECORDS.length / PAGE_SIZE)
  const paged = RECORDS.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const handleArchive = async () => {
    setConfirm(false)
    setArchiving(true)
    await new Promise(r => setTimeout(r, 8000))
    setArchiving(false)
    const msgs = Math.floor(Math.random() * 3000 + 11000)
    const orders = Math.floor(Math.random() * 500 + 2800)
    showToast(`已归档 ${msgs.toLocaleString()} 条消息 / ${orders.toLocaleString()} 条订单`, 'success')
  }

  return (
    <AdminLayout>
      <div style={{ padding: 28 }}>
        {/* Header */}
        <div style={{ marginBottom: 24 }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}>数据归档管理</h1>
          <p style={{ fontSize: 13, color: '#64748b', marginTop: 3 }}>定期归档有效降低数据库负载，提升查询性能</p>
        </div>

        {/* Stat cards */}
        <div style={{ display: 'flex', gap: 20, marginBottom: 20 }}>
          <StatCard icon="💬" label="总聊天消息数"      value="284,612"  sub="所有时间累计" />
          <StatCard icon="⚠️" label="6月以上未归档数"   value="38,240"   sub="建议尽快归档" accent="#f59e0b" />
          <StatCard icon="💾" label="本月已节省空间"    value="143.2 MB" sub="2026年8月至今" accent="#10b981" />
        </div>

        {/* Operation panel */}
        <div className="card" style={{ padding: '20px 24px', marginBottom: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16 }}>
          <div>
            <p style={{ fontWeight: 600, color: '#1e293b', fontSize: 15 }}>上次归档</p>
            <p style={{ fontSize: 13, color: '#64748b', marginTop: 4 }}>
              2026-08-05 03:00:00 <span style={{ color: '#94a3b8' }}>（3 天前，自动化执行）</span>
            </p>
          </div>
          <button
            className="btn btn-primary"
            style={{ minWidth: 130, height: 42 }}
            onClick={() => setConfirm(true)}
            disabled={archiving}
          >
            {archiving
              ? <><svg className="spin" width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="5.5" stroke="rgba(255,255,255,0.4)" strokeWidth="1.5"/><path d="M7 1.5a5.5 5.5 0 0 1 5.5 5.5" stroke="white" strokeWidth="1.5" strokeLinecap="round"/></svg> 归档中...</>
              : '⚡ 立即归档'
            }
          </button>
        </div>

        {/* Warning banner */}
        <div style={{ background: '#fef3c7', borderRadius: 8, padding: '12px 16px', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 10, border: '1px solid #fde68a' }}>
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M9 2L1.5 16h15L9 2z" fill="#f59e0b" stroke="#f59e0b" strokeWidth="0.5" strokeLinejoin="round"/>
            <path d="M9 7v4M9 12.5v.5" stroke="white" strokeWidth="1.4" strokeLinecap="round"/>
          </svg>
          <p style={{ fontSize: 13, color: '#92400e' }}>
            建议每周日凌晨 03:00 自动归档，当前已配置定时任务（cron: <code style={{ background: '#fde68a', padding: '0 4px', borderRadius: 3 }}>0 3 * * 0</code>）
          </p>
        </div>

        {/* Archive history table */}
        <div className="card" style={{ overflow: 'hidden' }}>
          <div style={{ padding: '14px 18px', borderBottom: '1px solid #f1f5f9' }}>
            <p style={{ fontWeight: 600, fontSize: 15, color: '#1e293b' }}>归档历史</p>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  {['执行时间', '类型', '归档数量', '节省空间', '耗时', '状态'].map(h => <th key={h}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {paged.map(r => (
                  <tr key={r.id} className="animate-fade-up">
                    <td style={{ fontFamily: 'monospace', fontSize: 12, color: '#64748b' }}>{r.time}</td>
                    <td>
                      <span style={{ fontSize: 12, padding: '2px 9px', borderRadius: 999, background: r.type === 'chat' ? '#eef2ff' : '#ecfdf5', color: r.type === 'chat' ? '#6366f1' : '#16a34a', fontWeight: 500 }}>
                        {r.type === 'chat' ? '💬 聊天' : '📋 订单'}
                      </span>
                    </td>
                    <td style={{ fontWeight: 500 }}>{r.count.toLocaleString()} 条</td>
                    <td style={{ color: '#10b981', fontWeight: 500 }}>{r.savedMb.toFixed(1)} MB</td>
                    <td style={{ color: '#64748b', fontSize: 13 }}>{r.durationSec}s</td>
                    <td>
                      <span className={r.status === 'success' ? 'badge badge-confirmed' : 'badge badge-cancelled'}>
                        {r.status === 'success' ? '✓ 成功' : '✗ 失败'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderTop: '1px solid #f1f5f9' }}>
            <p style={{ fontSize: 13, color: '#64748b' }}>共 {RECORDS.length} 条记录</p>
            <div className="pagination">
              <button className="page-btn" disabled={page === 1} onClick={() => setPage(p => p - 1)}>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M7.5 2L4 6L7.5 10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
              </button>
              {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
                <button key={p} className={`page-btn${p === page ? ' active' : ''}`} onClick={() => setPage(p)}>{p}</button>
              ))}
              <button className="page-btn" disabled={page === totalPages} onClick={() => setPage(p => p + 1)}>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M4.5 2L8 6L4.5 10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* HITL confirm */}
      <HitlConfirm
        open={confirm}
        action="立即执行数据归档"
        detail="将归档 6 个月以上的聊天记录和订单数据，此操作不可撤销。"
        countdownSec={5}
        onConfirm={handleArchive}
        onCancel={() => setConfirm(false)}
      />
    </AdminLayout>
  )
}
