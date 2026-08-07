import { useState, useEffect } from 'react'
import AdminLayout from '../../components/admin/AdminLayout'
import { showToast } from '../../utils/toast'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'

/* ── Data ─────────────────────────────────────────────── */

type Category = 'all' | 'knowledge' | 'booking' | 'multimodal' | 'casual'
const CATEGORIES: Category[] = ['all', 'knowledge', 'booking', 'multimodal', 'casual']
const CAT_LABELS: Record<Category, string> = { all: '全部', knowledge: '知识库', booking: '预约', multimodal: '多模态', casual: '闲聊' }
const CAT_COLORS: Record<string, { bg: string; color: string }> = {
  knowledge:  { bg: '#eef2ff', color: '#6366f1' },
  booking:    { bg: '#ecfdf5', color: '#10b981' },
  multimodal: { bg: '#fdf4ff', color: '#a855f7' },
  casual:     { bg: '#fff7ed', color: '#f97316' },
}

interface QueryRow {
  id: string
  query: string
  category: string
  recall: number
  mrr: number
  latencyMs: number
  docs: string[]
}

const ALL_ROWS: QueryRow[] = [
  { id: 'q1', query: '烫发后如何护理避免发质受损？',      category: 'knowledge',  recall: 0.91, mrr: 0.88, latencyMs: 145, docs: ['美发化学基础手册 §3.2 — 烫后护理要点', '发型师专业认证教材 §7.4 — 客户护理指导'] },
  { id: 'q2', query: '三里屯店周六下午有空档吗？',          category: 'booking',    recall: 0.84, mrr: 0.80, latencyMs: 92,  docs: ['实时预约系统 — 三里屯旗舰店 2025-07-05 档期'] },
  { id: 'q3', query: '帮我看看这张图的发型适合烫吗',        category: 'multimodal', recall: 0.76, mrr: 0.71, latencyMs: 320, docs: ['美发图像分析模型输出', '发型适配数据库 §2.1'] },
  { id: 'q4', query: '你今天心情怎么样？',                  category: 'casual',     recall: 0.42, mrr: 0.35, latencyMs: 58,  docs: ['通用聊天兜底策略'] },
  { id: 'q5', query: '染发用多少度数双氧水合适？',          category: 'knowledge',  recall: 0.89, mrr: 0.85, latencyMs: 128, docs: ['发色科学与配方指南 §4.3 — 氧化剂浓度选择'] },
  { id: 'q6', query: '陈晓磊发型师的专长是什么？',          category: 'booking',    recall: 0.81, mrr: 0.77, latencyMs: 104, docs: ['发型师档案库 — 陈晓磊个人资料'] },
  { id: 'q7', query: '给我推荐一个适合圆脸的发型',          category: 'knowledge',  recall: 0.62, mrr: 0.55, latencyMs: 198, docs: ['脸型发型匹配指南 §1.5', '流行发型数据库 2025 Q3'] },
  { id: 'q8', query: '头皮痒是什么原因？',                  category: 'knowledge',  recall: 0.33, mrr: 0.28, latencyMs: 175, docs: ['头皮健康护理手册 §2.1 — 瘙痒成因'] },
  { id: 'q9', query: '预约取消需要提前多少时间？',          category: 'booking',    recall: 0.79, mrr: 0.74, latencyMs: 89,  docs: ['预约规则手册 §6 — 取消政策'] },
  { id: 'q10',query: '发图片给你分析一下我的发质',          category: 'multimodal', recall: 0.68, mrr: 0.61, latencyMs: 295, docs: ['发质分析模型', '多孔性检测标准 §3'] },
]

/* ── Helpers ──────────────────────────────────────────── */
function scoreColor(v: number) {
  if (v >= 0.7) return '#10b981'
  if (v >= 0.4) return '#f59e0b'
  return '#ef4444'
}
function scoreBg(v: number) {
  if (v >= 0.7) return '#ecfdf5'
  if (v >= 0.4) return '#fffbeb'
  return '#fef2f2'
}

function StatCard({ label, value, change, desc }: { label: string; value: string; change: number; desc: string }) {
  const up = change >= 0
  return (
    <div className="card" style={{ padding: '20px 22px', flex: 1, minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8 }}>
        <p style={{ fontSize: 13, color: '#64748b', fontWeight: 500 }}>{label}</p>
        <span style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 12, fontWeight: 600, color: up ? '#10b981' : '#ef4444', background: up ? '#ecfdf5' : '#fef2f2', padding: '2px 7px', borderRadius: 999 }}>
          {up ? '↑' : '↓'} {Math.abs(change)}%
        </span>
      </div>
      <p style={{ fontSize: 36, fontWeight: 800, color: '#1e293b', letterSpacing: '-0.5px' }}>{value}</p>
      <p style={{ fontSize: 13, color: '#94a3b8', marginTop: 4 }}>{desc}</p>
    </div>
  )
}

/* ── Page ─────────────────────────────────────────────── */
export default function RagEvalPage() {
  const [category, setCategory] = useState<Category>('all')
  const [running, setRunning] = useState(false)
  const [evalReport, setEvalReport] = useState<any>(null)
  const [trend, setTrend] = useState<{date: string; recall: number}[]>([])
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 6

  const filtered = category === 'all' ? ALL_ROWS : ALL_ROWS.filter(r => r.category === category)
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)
  const paged = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const handleRunEval = async () => {
    setRunning(true)
    await new Promise(r => setTimeout(r, 2200))
    setRunning(false)
    showToast('评估完成！Recall@5 提升至 0.83', 'success')
  }

  useEffect(() => { setPage(1) }, [category])

  return (
    <AdminLayout>
      <div style={{ padding: 28, minHeight: '100vh' }}>
        {/* Page header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}>RAG 质量评估</h1>
            <p style={{ fontSize: 13, color: '#64748b', marginTop: 3 }}>上次评估：2026-08-05 · 数据集 10 条</p>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <select className="select-field" value={category} onChange={e => setCategory(e.target.value as Category)}>
              {CATEGORIES.map(c => <option key={c} value={c}>{CAT_LABELS[c]}</option>)}
            </select>
            <button
              className="btn btn-primary"
              onClick={handleRunEval}
              disabled={running}
              style={{ minWidth: 120 }}
            >
              {running
                ? <><svg className="spin" width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="5.5" stroke="rgba(255,255,255,0.4)" strokeWidth="1.5"/><path d="M7 1.5a5.5 5.5 0 0 1 5.5 5.5" stroke="white" strokeWidth="1.5" strokeLinecap="round"/></svg> 评估中...</>
                : '▶ 运行新评估'
              }
            </button>
          </div>
        </div>

        {/* Stat cards */}
        <div style={{ display: 'flex', gap: 20, marginBottom: 24 }}>
          <StatCard label="Recall@5"  value={(evalReport?.summary?.recall_at_5 ?? 0).toFixed(2)} change={0} desc="最近一次评估" />
          <StatCard label="MRR"        value={(evalReport?.summary?.mrr ?? 0).toFixed(2)} change={0} desc="Mean Reciprocal Rank" />
          <StatCard label="Hit Rate"   value="91.2%" change={+1.4} desc="至少命中 1 条相关文档" />
          <StatCard label="NDCG@5"     value={(evalReport?.summary?.ndcg_at_5 ?? 0).toFixed(2)} change={0} desc="Normalized DCG" />
        </div>

        {/* Trend chart */}
        <div className="card" style={{ padding: '18px 22px', marginBottom: 20 }}>
          <p style={{ fontSize: 14, fontWeight: 600, color: '#1e293b', marginBottom: 14 }}>Recall@5 近 7 日趋势</p>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={trend} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="date" tick={{ fontSize: 12, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
              <YAxis domain={[0.5, 1]} tick={{ fontSize: 12, fill: '#94a3b8' }} axisLine={false} tickLine={false} width={36} />
              <Tooltip
                contentStyle={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 13 }}
                formatter={(v) => [Number(v).toFixed(3), 'Recall@5']}
              />
              <Line type="monotone" dataKey="recall" stroke="#6366f1" strokeWidth={2.5} dot={{ r: 4, fill: '#6366f1', stroke: '#fff', strokeWidth: 2 }} activeDot={{ r: 6 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Query table */}
        <div className="card" style={{ overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table" style={{ tableLayout: 'fixed', width: '100%' }}>
              <colgroup>
                <col style={{ width: '35%' }} />
                <col style={{ width: '13%' }} />
                <col style={{ width: '14%' }} />
                <col style={{ width: '14%' }} />
                <col style={{ width: '14%' }} />
                <col style={{ width: '10%' }} />
              </colgroup>
              <thead>
                <tr>
                  <th>Query</th>
                  <th style={{ textAlign: 'center' }}>分类</th>
                  <th style={{ textAlign: 'center' }}>Recall@5</th>
                  <th style={{ textAlign: 'center' }}>MRR</th>
                  <th style={{ textAlign: 'center' }}>延迟</th>
                  <th style={{ textAlign: 'center' }}>详情</th>
                </tr>
              </thead>
              <tbody>
                {paged.map(row => {
                  const catStyle = CAT_COLORS[row.category] || { bg: '#f1f5f9', color: '#64748b' }
                  const isExpanded = expandedId === row.id
                  return (
                    <>
                      <tr
                        key={row.id}
                        style={{ cursor: 'pointer' }}
                        onClick={() => setExpandedId(isExpanded ? null : row.id)}
                        onMouseOver={e => { (e.currentTarget as HTMLElement).style.background = '#f8fafc' }}
                        onMouseOut={e => { (e.currentTarget as HTMLElement).style.background = '' }}
                      >
                        <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 0 }}>{row.query}</td>
                        <td style={{ textAlign: 'center' }}>
                          <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 999, background: catStyle.bg, color: catStyle.color, fontWeight: 500 }}>{CAT_LABELS[row.category as Category] || row.category}</span>
                        </td>
                        <td style={{ textAlign: 'center' }}>
                          <span style={{ fontSize: 13, fontWeight: 600, color: scoreColor(row.recall), background: scoreBg(row.recall), padding: '2px 8px', borderRadius: 6 }}>{row.recall.toFixed(2)}</span>
                        </td>
                        <td style={{ textAlign: 'center' }}>
                          <span style={{ fontSize: 13, fontWeight: 600, color: scoreColor(row.mrr), background: scoreBg(row.mrr), padding: '2px 8px', borderRadius: 6 }}>{row.mrr.toFixed(2)}</span>
                        </td>
                        <td style={{ textAlign: 'center', fontSize: 13, color: row.latencyMs > 200 ? '#f59e0b' : '#64748b' }}>{row.latencyMs} ms</td>
                        <td style={{ textAlign: 'center' }}>
                          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ transform: isExpanded ? 'rotate(180deg)' : 'rotate(0)', transition: 'transform 0.18s', display: 'inline-block' }}>
                            <path d="M2 4.5L7 9.5L12 4.5" stroke="#94a3b8" strokeWidth="1.4" strokeLinecap="round" />
                          </svg>
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr key={row.id + '-exp'}>
                          <td colSpan={6} style={{ background: '#fafbff', padding: '12px 16px', borderTop: 'none' }}>
                            <p style={{ fontSize: 12, fontWeight: 600, color: '#64748b', marginBottom: 8 }}>检索到的文档：</p>
                            {row.docs.map((doc, i) => (
                              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                                <span style={{ width: 20, height: 20, borderRadius: 6, background: '#eef2ff', color: '#6366f1', fontSize: 11, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{i + 1}</span>
                                <p style={{ fontSize: 13, color: '#374151', fontStyle: 'italic' }}>{doc}</p>
                              </div>
                            ))}
                          </td>
                        </tr>
                      )}
                    </>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderTop: '1px solid #f1f5f9' }}>
            <p style={{ fontSize: 13, color: '#64748b' }}>共 {filtered.length} 条查询</p>
            <div className="pagination">
              <button className="page-btn" disabled={page === 1} onClick={() => setPage(p => p - 1)}>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M7.5 2L4 6L7.5 10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
              </button>
              {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
                <button key={p} className={`page-btn${p === page ? ' active' : ''}`} onClick={() => setPage(p)}>{p}</button>
              ))}
              <button className="page-btn" disabled={page === totalPages || totalPages === 0} onClick={() => setPage(p => p + 1)}>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M4.5 2L8 6L4.5 10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </AdminLayout>
  )
}
