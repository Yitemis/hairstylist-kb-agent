import { useState, useEffect, useCallback } from 'react'
import AdminLayout from '../../components/admin/AdminLayout'
import { showToast } from '../../utils/toast'
import { getMetrics } from '../../api'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts'

/* ── Sparkline ──────────────────────────────────────────── */
function Sparkline({ data, color }: { data: number[]; color: string }) {
  const max = Math.max(...data)
  const min = Math.min(...data)
  const range = max - min || 1
  const w = 60, h = 30, pad = 3
  const pts = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (w - pad * 2)
    const y = h - pad - ((v - min) / range) * (h - pad * 2)
    return `${x},${y}`
  }).join(' ')

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} fill="none">
      <polyline points={pts} stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={pts.split(' ').at(-1)!.split(',')[0]} cy={pts.split(' ').at(-1)!.split(',')[1]} r="3" fill={color} />
    </svg>
  )
}

/* ── Stat card ──────────────────────────────────────────── */
interface StatCardProps {
  title: string; value: string; unit?: string; badge: string; badgeColor: string
  badgeBg: string; sub: string; spark: number[]; sparkColor: string; warning?: boolean
}
function StatCard({ title, value, unit, badge, badgeColor, badgeBg, sub, spark, sparkColor }: StatCardProps) {
  return (
    <div className="card" style={{ padding: 24, flex: 1, minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <p style={{ fontSize: 13, color: '#64748b', fontWeight: 500 }}>{title}</p>
        <span style={{ fontSize: 12, padding: '2px 8px', borderRadius: 999, background: badgeBg, color: badgeColor, fontWeight: 600 }}>{badge}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
        <div>
          <p style={{ fontSize: 42, fontWeight: 800, color: '#1e293b', lineHeight: 1, letterSpacing: '-1px' }}>
            {value}<span style={{ fontSize: 16, fontWeight: 500, color: '#94a3b8', marginLeft: 4 }}>{unit}</span>
          </p>
          <p style={{ fontSize: 13, color: '#94a3b8', marginTop: 6 }}>{sub}</p>
        </div>
        <Sparkline data={spark} color={sparkColor} />
      </div>
    </div>
  )
}

/* ── Mock data generators ───────────────────────────────── */
function genQps(): { t: string; qps: number }[] {
  return Array.from({ length: 12 }, (_, i) => ({
    t: `${(8 + Math.floor(i * 5 / 60)).toString().padStart(2,'0')}:${((i * 5) % 60).toString().padStart(2,'0')}`,
    qps: parseFloat((Math.random() * 20 + 30).toFixed(1)),
  }))
}

const LATENCY_DATA = [
  { label: 'p50', p50: 120, p90: 0, p99: 0 },
  { label: 'p90', p50: 0, p90: 280, p99: 0 },
  { label: 'p99', p50: 0, p90: 0, p99: 2300 },
]

const SLOW_QUERIES = [
  { endpoint: 'POST /api/rag/query — 发图片给你分析发质',  ms: 3240 },
  { endpoint: 'POST /api/rag/query — 多模态图像检索请求',  ms: 2980 },
  { endpoint: 'POST /api/chat/complete — 染色配方咨询',    ms: 2450 },
  { endpoint: 'GET  /api/orders/search — 历史订单全量查',  ms: 1870 },
  { endpoint: 'POST /api/knowledge/embed — 新增文档嵌入',  ms: 1650 },
]
const ERROR_ENDPOINTS = [
  { endpoint: 'POST /api/rag/query',          rate: '1.8%' },
  { endpoint: 'POST /api/image/analyze',      rate: '3.2%' },
  { endpoint: 'POST /api/auth/refresh',       rate: '0.4%' },
  { endpoint: 'GET  /api/branches/available', rate: '0.2%' },
  { endpoint: 'POST /api/booking/create',     rate: '0.1%' },
]
const SESSIONS = [
  { endpoint: '活跃 WebSocket 连接',   count: 218 },
  { endpoint: 'SSE 流式会话',          count: 43 },
  { endpoint: '今日独立用户',           count: 387 },
  { endpoint: '本小时新建会话',         count: 64 },
  { endpoint: '平均会话时长',           count: 12, unit: 'min' },
]

/* ── Page ───────────────────────────────────────────────── */
export default function MonitorPage() {
  const [sparklineData, setSparklineData] = useState<any>({cache: [], chat_qps: [], errors: []})
  const [metrics, setMetrics] = useState<any>(null)
  useEffect(() => { getMetrics().then(setMetrics).catch(() => {}) }, [])
  const [countdown, setCountdown] = useState(5)
  const [qpsData, setQpsData] = useState(genQps())
  const [lastRefresh, setLastRefresh] = useState(new Date())

  const doRefresh = useCallback(() => {
    setQpsData(genQps())
    setLastRefresh(new Date())
    setCountdown(5)
  }, [])

  // Auto-refresh every 5s
  useEffect(() => {
    const iv = setInterval(() => {
      setCountdown(c => {
        if (c <= 1) { doRefresh(); return 5 }
        return c - 1
      })
    }, 1000)
    return () => clearInterval(iv)
  }, [doRefresh])

  const handleExport = () => { showToast('监控数据已导出为 CSV', 'success') }

  return (
    <AdminLayout>
      <div style={{ padding: 28 }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}>实时监控</h1>
            <p style={{ fontSize: 13, color: '#64748b', marginTop: 3 }}>
              上次刷新：{lastRefresh.toLocaleTimeString('zh-CN')}
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 11, color: '#94a3b8', fontFamily: 'monospace' }}>
              {countdown}s 后自动刷新
            </span>
            <div style={{ width: 24, height: 24, position: 'relative' }}>
              <svg width="24" height="24" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="10" fill="none" stroke="#e2e8f0" strokeWidth="2.5" />
                <circle cx="12" cy="12" r="10" fill="none" stroke="#6366f1" strokeWidth="2.5"
                  strokeDasharray={62.8}
                  strokeDashoffset={62.8 * (1 - countdown / 5)}
                  strokeLinecap="round"
                  transform="rotate(-90 12 12)"
                  style={{ transition: 'stroke-dashoffset 0.9s linear' }}
                />
              </svg>
            </div>
            <button className="btn btn-ghost" style={{ padding: '7px 14px', fontSize: 13 }} onClick={handleExport}>⬇ 导出</button>
            <button className="btn btn-primary" style={{ padding: '7px 14px', fontSize: 13 }} onClick={doRefresh}>↻ 刷新</button>
          </div>
        </div>

        {/* Stat cards */}
        <div style={{ display: 'flex', gap: 16, marginBottom: 24 }}>
          <StatCard
            title="Chat QPS" value="42.3" badge="↑ 12%" badgeColor="#10b981" badgeBg="#ecfdf5"
            sub="当前每秒请求数" spark={[32,35,38,34,40,42,44,41,43,42,44,42]} sparkColor="#10b981"
          />
          <StatCard
            title="P99 延迟" value="2.3" unit="s" badge="⚠ 偏高" badgeColor="#f59e0b" badgeBg="#fffbeb"
            sub="建议阈值 < 1.5s" spark={[1.2,1.4,1.8,2.0,1.9,2.1,2.3,2.2,2.4,2.3,2.5,2.3]} sparkColor="#f59e0b"
          />
          <StatCard
            title="错误率" value="0.5" unit="%" badge="↑ 警告" badgeColor="#ef4444" badgeBg="#fef2f2"
            sub="阈值 1%，近边界" spark={[0.1,0.2,0.3,0.2,0.4,0.3,0.5,0.4,0.6,0.5,0.5,0.5]} sparkColor="#ef4444"
          />
          <StatCard
            title="缓存命中率" value="85" unit="%" badge="↑ 健康" badgeColor="#10b981" badgeBg="#ecfdf5"
            sub="Redis 语义缓存" spark={sparklineData.cache || []} sparkColor="#6366f1"
          />
        </div>

        {/* Charts */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
          {/* QPS Line */}
          <div className="card" style={{ padding: '18px 22px' }}>
            <p style={{ fontSize: 14, fontWeight: 600, color: '#1e293b', marginBottom: 14 }}>Chat QPS（5 分钟窗口）</p>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={qpsData} margin={{ top: 4, right: 12, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="t" tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} interval={2} />
                <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} width={32} domain={[0, 80]} />
                <Tooltip contentStyle={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 12 }} formatter={(v) => [Number(v).toFixed(1), 'QPS']} />
                <Line type="monotone" dataKey="qps" stroke="#6366f1" strokeWidth={2.5} dot={false} activeDot={{ r: 5 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Latency Bar */}
          <div className="card" style={{ padding: '18px 22px' }}>
            <p style={{ fontSize: 14, fontWeight: 600, color: '#1e293b', marginBottom: 14 }}>RAG 检索延迟分布</p>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={LATENCY_DATA} margin={{ top: 4, right: 12, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 12, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} width={36} unit="ms" />
                <Tooltip contentStyle={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 12 }} formatter={(v) => [`${Number(v)} ms`]} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="p50" fill="#10b981" radius={[4,4,0,0]} name="p50" />
                <Bar dataKey="p90" fill="#f59e0b" radius={[4,4,0,0]} name="p90" />
                <Bar dataKey="p99" fill="#ef4444" radius={[4,4,0,0]} name="p99" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Bottom 3 list cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 20 }}>
          {/* Slow queries */}
          <div className="card" style={{ padding: '18px 20px' }}>
            <p style={{ fontSize: 14, fontWeight: 600, color: '#1e293b', marginBottom: 14 }}>🐢 Top 5 慢查询</p>
            {SLOW_QUERIES.map((q, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 12 }}>
                <span style={{ width: 20, height: 20, borderRadius: 6, background: i < 2 ? '#fef2f2' : '#fffbeb', color: i < 2 ? '#ef4444' : '#f59e0b', fontSize: 11, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{i+1}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ fontSize: 12, color: '#1e293b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{q.endpoint}</p>
                  <p style={{ fontSize: 11, color: i < 2 ? '#ef4444' : '#f59e0b', fontWeight: 600, marginTop: 2 }}>{q.ms.toLocaleString()} ms</p>
                </div>
              </div>
            ))}
          </div>

          {/* Error endpoints */}
          <div className="card" style={{ padding: '18px 20px' }}>
            <p style={{ fontSize: 14, fontWeight: 600, color: '#1e293b', marginBottom: 14 }}>❌ Top 5 错误端点</p>
            {ERROR_ENDPOINTS.map((e, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <p style={{ fontSize: 12, color: '#374151', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontFamily: 'monospace' }}>{e.endpoint}</p>
                <span style={{ fontSize: 12, fontWeight: 700, color: parseFloat(e.rate) > 1 ? '#ef4444' : '#f59e0b', marginLeft: 8, whiteSpace: 'nowrap' }}>{e.rate}</span>
              </div>
            ))}
          </div>

          {/* Active sessions */}
          <div className="card" style={{ padding: '18px 20px' }}>
            <p style={{ fontSize: 14, fontWeight: 600, color: '#1e293b', marginBottom: 14 }}>👥 活跃 Session</p>
            {SESSIONS.map((s, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <p style={{ fontSize: 12, color: '#64748b' }}>{s.endpoint}</p>
                <span style={{ fontSize: 14, fontWeight: 700, color: '#6366f1' }}>{s.count}{s.unit ? ` ${s.unit}` : ''}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </AdminLayout>
  )
}
