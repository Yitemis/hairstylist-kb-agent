import { useState, useEffect, useRef } from 'react'
import AdminLayout from '../../components/admin/AdminLayout'
import { showToast } from '../../utils/toast'
import {
  listDocuments, uploadDocument, parseDocument, getDocumentChunks,
  publishDocument, deleteDocument, recallTest,
  type AdminDocument, type DocumentChunk,
} from '../../api'

const STATUS_MAP: Record<string, { label: string; color: string; bg: string }> = {
  pending:  { label: '待解析', color: '#94a3b8', bg: '#f1f5f9' },
  parsing:  { label: '解析中', color: '#f59e0b', bg: '#fffbeb' },
  parsed:   { label: '已解析', color: '#6366f1', bg: '#eef2ff' },
  indexed:  { label: '已索引', color: '#10b981', bg: '#ecfdf5' },
  failed:   { label: '解析失败', color: '#ef4444', bg: '#fef2f2' },
}

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_MAP[status] || { label: status, color: '#94a3b8', bg: '#f1f5f9' }
  return <span style={{ display: 'inline-block', padding: '2px 10px', borderRadius: 999, fontSize: 12, fontWeight: 500, background: s.bg, color: s.color }}>{s.label}</span>
}

/* 知识库组别 (与 KnowledgePage 保持一致) */
const GROUPS: { key: string; label: string; icon: string; color: string }[] = [
  { key: 'perming',  label: '烫发',   icon: '🌀', color: '#ec4899' },
  { key: 'cutting',  label: '剪发',   icon: '✂️', color: '#6366f1' },
  { key: 'coloring', label: '染发',   icon: '🎨', color: '#f59e0b' },
  { key: 'care',     label: '护理',   icon: '💆', color: '#10b981' },
  { key: 'general',  label: '通用',   icon: '📚', color: '#64748b' },
]
const GROUP_MAP: Record<string, { label: string; icon: string; color: string }> =
  Object.fromEntries(GROUPS.map(g => [g.key, g]))

function GroupBadge({ category }: { category: string }) {
  const g = GROUP_MAP[category] || { label: category, icon: '📄', color: '#94a3b8' }
  return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px', borderRadius: 6, fontSize: 11, fontWeight: 500, background: g.color + '15', color: g.color }}>{g.icon} {g.label}</span>
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(2) + ' MB'
}

function formatDate(s: string | null): string {
  if (!s) return '-'
  try { return new Date(s).toLocaleString('zh-CN', { hour12: false }) } catch { return s }
}

export default function DocumentManagePage() {
  const [docs, setDocs] = useState<AdminDocument[]>([])
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [filter, setFilter] = useState<'all' | 'published' | 'unpublished' | 'pending'>('all')
  const [groupFilter, setGroupFilter] = useState<string>('all')
  const [chunksModal, setChunksModal] = useState<{ docId: string; title: string } | null>(null)
  const [recallModal, setRecallModal] = useState<{ query: string; result: any } | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const loadDocs = async () => {
    setLoading(true)
    try {
      const data: any = await listDocuments()
      setDocs(data?.data || data || [])
    } catch (e: any) {
      showToast(e?.message || '加载文档失败', 'error')
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { loadDocs() }, [])

  const handleUpload = async (file: File) => {
    setUploading(true)
    try {
      // 上传到当前选中的组别
      const targetGroup = groupFilter === 'all' ? 'general' : groupFilter
      const res: any = await uploadDocument(file, targetGroup)
      const groupLabel = GROUP_MAP[targetGroup]?.label || targetGroup
      showToast('已上传到【' + groupLabel + '】: ' + res.filename + ' (请点「开始学习」解析)', 'success')
      loadDocs()
    } catch (e: any) {
      showToast(e?.message || '上传失败', 'error')
    } finally {
      setUploading(false)
    }
  }

  const handleParse = async (doc: AdminDocument) => {
    try {
      showToast('开始解析...', 'info')
      const res: any = await parseDocument(doc.document_id)
      const r = res?.data || res
      showToast('解析完成: ' + r.parents + ' 个父块 / ' + r.children + ' 个子块', 'success')
      loadDocs()
    } catch (e: any) {
      showToast(e?.message || '解析失败', 'error')
      loadDocs()
    }
  }

  const handlePublish = async (doc: AdminDocument) => {
    const target = !doc.is_published
    const msg = (target ? '发布' : '取消发布') + ' 「' + doc.filename + '」?'
    if (!confirm(msg)) return
    try {
      await publishDocument(doc.document_id, target)
      showToast(target ? '已发布' : '已取消发布', 'success')
      loadDocs()
    } catch (e: any) {
      showToast(e?.message || '操作失败', 'error')
    }
  }

  const handleDelete = async (doc: AdminDocument) => {
    if (!confirm('确认删除「' + doc.filename + '」?\n将清除数据库元信息、磁盘文件、Milvus 向量。\n操作不可恢复!')) return
    try {
      await deleteDocument(doc.document_id)
      showToast('已删除', 'success')
      loadDocs()
    } catch (e: any) {
      showToast(e?.message || '删除失败', 'error')
    }
  }

  const handleTestRecall = async (query: string) => {
    if (!query.trim()) return
    try {
      const res: any = await recallTest(query, 5)
      setRecallModal({ query, result: res?.data || res })
    } catch (e: any) {
      showToast(e?.message || '召回测试失败', 'error')
    }
  }

  const filtered = docs.filter(d => {
    if (filter === 'published' && !d.is_published) return false
    if (filter === 'unpublished' && d.is_published) return false
    if (filter === 'pending' && d.mineru_status !== 'pending' && d.mineru_status !== 'parsing') return false
    if (groupFilter !== 'all' && d.category !== groupFilter) return false
    return true
  })

  const stats = {
    total: docs.length,
    published: docs.filter(d => d.is_published).length,
    indexed: docs.filter(d => d.mineru_status === 'indexed').length,
    pending: docs.filter(d => d.mineru_status === 'pending' || d.mineru_status === 'parsing').length,
  }

  return (
    <AdminLayout>
      <div style={{ padding: 28 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}>文档管理</h1>
            <p style={{ fontSize: 13, color: '#64748b', marginTop: 3 }}>
              共 {stats.total} 个文档 · 已发布 {stats.published} · 已索引 {stats.indexed} · 待解析 {stats.pending}
            </p>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            {/* 一个下拉管两件事: 筛选当前组别 + 上传目标组别 */}
            <select
              className="select-field"
              value={groupFilter}
              onChange={e => setGroupFilter(e.target.value)}
              style={{ height: 36, minWidth: 140 }}
              title="选择组别: 筛选当前分组的文档，上传也会进入当前选中组别"
            >
              <option value="all">📚 全部</option>
              {GROUPS.map(g => <option key={g.key} value={g.key}>{g.icon} {g.label}</option>)}
            </select>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.doc,.xlsx,.xls,.md,.markdown,.txt,.jpg,.jpeg,.png"
              style={{ display: 'none' }}
              onChange={e => {
                const f = e.target.files?.[0]
                if (f) handleUpload(f)
                e.target.value = ''
              }}
            />
            <button className="btn btn-ghost" onClick={loadDocs}>刷新</button>
            <button
              className="btn btn-primary"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              {uploading ? '上传中...' : '+ 上传文档'}
            </button>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 20 }}>
          {[
            { label: '总文档', key: 'all', value: stats.total, color: '#6366f1' },
            { label: '已发布', key: 'published', value: stats.published, color: '#10b981' },
            { label: '已索引', key: 'indexed', value: stats.indexed, color: '#0ea5e9' },
            { label: '待解析', key: 'pending', value: stats.pending, color: '#f59e0b' },
          ].map(s => (
            <div
              key={s.key}
              className="card"
              style={{ padding: '14px 18px', cursor: 'pointer', border: '1px solid ' + (filter === s.key ? s.color + '40' : 'transparent') }}
              onClick={() => setFilter(s.key as typeof filter)}
            >
              <p style={{ fontSize: 26, fontWeight: 700, color: s.color }}>{s.value}</p>
              <p style={{ fontSize: 13, color: '#64748b', marginTop: 2 }}>{s.label}</p>
            </div>
          ))}
        </div>

        <div className="card" style={{ padding: 16, marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 13, fontWeight: 500, color: '#1e293b' }}>RAG 召回测试</span>
            <input
              type="text"
              className="input-field"
              style={{ flex: 1, height: 36 }}
              placeholder="输入问题, 例如: 烫发的原理"
              onKeyDown={e => { if (e.key === 'Enter') handleTestRecall((e.target as HTMLInputElement).value) }}
            />
            <button className="btn btn-primary" style={{ height: 36 }} onClick={e => {
              const input = (e.currentTarget.previousElementSibling as HTMLInputElement)
              handleTestRecall(input.value)
            }}>召回</button>
          </div>
          <p style={{ fontSize: 11, color: '#94a3b8', marginTop: 6 }}>
            只有 <strong style={{ color: '#10b981' }}>已发布</strong> 的文档会参与召回
          </p>
        </div>

        <div className="card" style={{ overflow: 'hidden' }}>
          <table className="data-table">
            <thead>
              <tr>
                {['文档ID', '文件名', '组别', '大小', '类型', '状态', '发布', '上传时间', '操作'].map(h => <th key={h}>{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={9} style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>加载中...</td></tr>
              )}
              {!loading && filtered.length === 0 && (
                <tr><td colSpan={9} style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>
                  {docs.length === 0 ? '暂无文档, 点右上角「上传文档」开始' : '当前筛选无结果'}
                </td></tr>
              )}
              {!loading && filtered.map(doc => (
                <tr key={doc.document_id}>
                  <td style={{ fontFamily: 'monospace', fontSize: 11, color: '#94a3b8' }}>{doc.document_id.slice(0, 14)}</td>
                  <td style={{ fontWeight: 500 }}>{doc.filename}</td>
                  <td><GroupBadge category={doc.category} /></td>
                  <td style={{ fontSize: 12, color: '#64748b' }}>{formatSize(doc.file_size)}</td>
                  <td style={{ fontSize: 12, color: '#64748b' }}>{doc.file_type}</td>
                  <td><StatusBadge status={doc.mineru_status} /></td>
                  <td>
                    {doc.is_published
                      ? <span style={{ display: 'inline-block', padding: '2px 10px', borderRadius: 999, fontSize: 12, fontWeight: 500, background: '#ecfdf5', color: '#10b981' }}>已发布</span>
                      : <span style={{ display: 'inline-block', padding: '2px 10px', borderRadius: 999, fontSize: 12, fontWeight: 500, background: '#f1f5f9', color: '#94a3b8' }}>未发布</span>
                    }
                  </td>
                  <td style={{ fontSize: 12, color: '#64748b' }}>{formatDate(doc.created_at)}</td>
                  <td>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      {(doc.mineru_status === 'pending' || doc.mineru_status === 'failed') && (
                        <button className="btn btn-primary" style={{ padding: '4px 10px', fontSize: 12 }} onClick={() => handleParse(doc)}>
                          开始学习
                        </button>
                      )}
                      {doc.mineru_status === 'indexed' && (
                        <button className="btn btn-ghost" style={{ padding: '4px 10px', fontSize: 12 }} onClick={() => setChunksModal({ docId: doc.document_id, title: doc.filename })}>
                          切块
                        </button>
                      )}
                      <button
                        className="btn btn-ghost"
                        style={{ padding: '4px 10px', fontSize: 12, color: doc.is_published ? '#f59e0b' : '#10b981' }}
                        onClick={() => handlePublish(doc)}
                        disabled={doc.mineru_status !== 'indexed'}
                      >
                        {doc.is_published ? '取消发布' : '发布'}
                      </button>
                      <button className="btn btn-ghost" style={{ padding: '4px 10px', fontSize: 12, color: '#ef4444' }} onClick={() => handleDelete(doc)}>
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {chunksModal && <ChunksModal docId={chunksModal.docId} title={chunksModal.title} onClose={() => setChunksModal(null)} />}
      {recallModal && <RecallResultModal query={recallModal.query} result={recallModal.result} onClose={() => setRecallModal(null)} />}
    </AdminLayout>
  )
}

function ChunksModal({ docId, title, onClose }: { docId: string; title: string; onClose: () => void }) {
  const [chunks, setChunks] = useState<DocumentChunk[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    (async () => {
      try {
        const r: any = await getDocumentChunks(docId, 50)
        const data = r?.data || r
        setChunks(data.chunks || [])
        setTotal(data.total || 0)
      } catch (e) {
        showToast('加载切块失败', 'error')
      } finally {
        setLoading(false)
      }
    })()
  }, [docId])

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }} onClick={onClose}>
      <div className="card" style={{ width: '100%', maxWidth: 720, maxHeight: '85vh', overflow: 'auto', padding: 24 }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div>
            <h2 style={{ fontSize: 18, fontWeight: 700, color: '#1e293b' }}>切块预览</h2>
            <p style={{ fontSize: 12, color: '#94a3b8', marginTop: 4 }}>{title} - 共 {total} 个 parent chunk</p>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: 4 }}>X</button>
        </div>
        {loading ? (
          <p style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>加载中...</p>
        ) : chunks.length === 0 ? (
          <p style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>暂无切块</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {chunks.map((c, i) => (
              <div key={c.parent_id} style={{ padding: 12, background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ fontSize: 11, color: '#6366f1', fontWeight: 600 }}>Chunk #{i + 1}</span>
                  <span style={{ fontSize: 11, color: '#94a3b8' }}>{c.token_num} tokens</span>
                </div>
                <p style={{ fontSize: 13, color: '#1e293b', lineHeight: 1.6, whiteSpace: 'pre-wrap', margin: 0 }}>{c.content}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function RecallResultModal({ query, result, onClose }: { query: string; result: any; onClose: () => void }) {
  const hits = result?.hits || result?.results || (Array.isArray(result) ? result : [])
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }} onClick={onClose}>
      <div className="card" style={{ width: '100%', maxWidth: 720, maxHeight: '85vh', overflow: 'auto', padding: 24 }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div>
            <h2 style={{ fontSize: 18, fontWeight: 700, color: '#1e293b' }}>召回结果</h2>
            <p style={{ fontSize: 12, color: '#94a3b8', marginTop: 4 }}>
              查询: <span style={{ color: '#6366f1' }}>"{query}"</span> - 命中 {hits.length} 条
            </p>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: 4 }}>X</button>
        </div>
        {hits.length === 0 ? (
          <p style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>
            未命中任何文档<br />
            <span style={{ fontSize: 12 }}>请确认: 1) 有文档处于「已发布」状态 2) 查询与文档内容相关</span>
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {hits.map((h: any, i: number) => (
              <div key={i} style={{ padding: 12, background: '#f0f9ff', borderRadius: 8, border: '1px solid #bae6fd' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ fontSize: 11, color: '#0284c7', fontWeight: 600 }}>Hit #{i + 1} - {h.source || h.filename || 'unknown'}</span>
                  <span style={{ fontSize: 11, color: '#0284c7' }}>score: {(h.score || h.distance || 0).toFixed(3)}</span>
                </div>
                <p style={{ fontSize: 13, color: '#1e293b', lineHeight: 1.6, margin: 0 }}>{h.content || h.excerpt || h.text || JSON.stringify(h).slice(0, 200)}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
