import { useState, useEffect } from 'react'
import AdminLayout from '../../components/admin/AdminLayout'
import { showToast } from '../../utils/toast'
import { getToken } from '../../utils/auth'
const API_BASE = ''
const STORAGE_KEY = 'kb_recall_history'
interface Document { document_id: string; filename: string | null; category: string | null; tenant_id: string | null; chunk_count: number }
interface Chunk { id: number; filename: string | null; document_id: string | null; category: string | null; content: string; content_length: number }
interface SearchHit { rank: number; score: number; content: string; filename?: string; document_id?: string; parent_id?: string; tenant_id?: string }
interface RecallTest { id: string; query: string; hits_count: number; top_score: number; elapsed_ms: number; created_at: string; hits: SearchHit[] }
export default function KnowledgeBasePage() {
  const [activeTab, setActiveTab] = useState<'docs'|'recall'|'history'>('docs')
  const [documents, setDocuments] = useState<Document[]>([])
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null)
  const [chunks, setChunks] = useState<Chunk[]>([])
  const [loadingDocs, setLoadingDocs] = useState(false)
  const [loadingChunks, setLoadingChunks] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [query, setQuery] = useState('')
  const [testResults, setTestResults] = useState<SearchHit[]>([])
  const [testMeta, setTestMeta] = useState({ elapsed: 0, total: 0 })
  const [testing, setTesting] = useState(false)
  const [history, setHistory] = useState<RecallTest[]>([])
  const loadDocuments = async () => { setLoadingDocs(true); try { const token = getToken(); const r = await fetch(API_BASE + '/api/rag/documents', { headers: { Authorization: 'Bearer ' + token } }); const data = await r.json(); if (data.code === 0) setDocuments(data.data?.documents || []); else showToast(data.message || '加载失败', 'error') } catch (e: any) { showToast(e?.message || '网络错误', 'error') } finally { setLoadingDocs(false) } }
  const loadChunks = async (doc: Document) => { setLoadingChunks(true); setSelectedDoc(doc); setChunks([]); try { const token = getToken(); const r = await fetch(API_BASE + '/api/rag/chunks?document_id=' + encodeURIComponent(doc.document_id) + '&limit=100', { headers: { Authorization: 'Bearer ' + token } }); const data = await r.json(); if (data.code === 0) setChunks(data.data?.chunks || []); else showToast(data.message || '加载 chunks 失败', 'error') } catch (e: any) { showToast(e?.message || '网络错误', 'error') } finally { setLoadingChunks(false) } }
  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => { const file = e.target.files?.[0]; if (!file) return; setUploading(true); try { const token = getToken(); const formData = new FormData(); formData.append('file', file); const r = await fetch(API_BASE + '/api/rag/upload?document_id=' + encodeURIComponent(file.name) + '&category=general', { method: 'POST', headers: { Authorization: 'Bearer ' + token }, body: formData }); const data = await r.json(); if (data.code === 0) { showToast('成功: ' + data.data?.child_chunks_indexed + ' 个 chunks', 'success'); loadDocuments() } else showToast(data.message || '上传失败', 'error') } catch (e: any) { showToast(e?.message || '网络错误', 'error') } finally { setUploading(false); e.target.value = '' } }
  const handleTestRecall = async () => { if (!query.trim()) { showToast('请输入问题', 'error'); return } setTesting(true); try { const token = getToken(); const params = new URLSearchParams({ query: query, top_k: '10' }); if (selectedDoc) params.append('filename', selectedDoc.filename || ''); const r = await fetch(API_BASE + '/api/rag/test-recall?' + params.toString(), { headers: { Authorization: 'Bearer ' + token } }); const data = await r.json(); if (data.code === 0) { const hits = data.data?.hits || []; setTestResults(hits); setTestMeta({ elapsed: data.data?.elapsed_ms || 0, total: data.data?.total_candidates || 0 }); showToast('命中 ' + hits.length + ' 条切片', 'success'); const newEntry: RecallTest = { id: String(Date.now()), query, hits_count: hits.length, top_score: hits[0]?.score || 0, elapsed_ms: data.data?.elapsed_ms || 0, created_at: new Date().toLocaleString('zh-CN'), hits }; const newHistory = [newEntry, ...history].slice(0, 50); setHistory(newHistory); localStorage.setItem(STORAGE_KEY, JSON.stringify(newHistory)) } else showToast(data.message || '检索失败', 'error') } catch (e: any) { showToast(e?.message || '网络错误', 'error') } finally { setTesting(false) } }
  useEffect(() => { const stored = localStorage.getItem(STORAGE_KEY); if (stored) { try { setHistory(JSON.parse(stored)) } catch {} } }, [])
  useEffect(() => { if (activeTab === 'docs') loadDocuments() }, [activeTab])
  return (<AdminLayout><div style={{ padding: 28 }}>
    <div style={{ display: 'flex', gap: 4, marginBottom: 16, borderBottom: '1px solid #e2e8f0' }}>
      <button onClick={() => setActiveTab("docs")} style={{ padding: "10px 20px", background: "none", border: "none", borderBottom: activeTab === "docs" ? "2px solid #6366f1" : "2px solid transparent", color: activeTab === "docs" ? "#6366f1" : "#64748b", fontWeight: activeTab === "docs" ? 600 : 400, fontSize: 14, cursor: "pointer", marginBottom: -1 }}>知识库管理</button>
      <button onClick={() => setActiveTab("recall")} style={{ padding: "10px 20px", background: "none", border: "none", borderBottom: activeTab === "recall" ? "2px solid #6366f1" : "2px solid transparent", color: activeTab === "recall" ? "#6366f1" : "#64748b", fontWeight: activeTab === "recall" ? 600 : 400, fontSize: 14, cursor: "pointer", marginBottom: -1 }}>命中测试</button>
      <button onClick={() => setActiveTab("history")} style={{ padding: "10px 20px", background: "none", border: "none", borderBottom: activeTab === "history" ? "2px solid #6366f1" : "2px solid transparent", color: activeTab === "history" ? "#6366f1" : "#64748b", fontWeight: activeTab === "history" ? 600 : 400, fontSize: 14, cursor: "pointer", marginBottom: -1 }}>发布历史</button>
    </div>
    {activeTab === "docs" && (
      <div>
        <div className="card" style={{ padding: 20, marginBottom: 16 }}>
          <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>上传文档</h2>
          <input type="file" accept=".pdf,.docx,.xlsx,.md" onChange={handleUpload} disabled={uploading} style={{ padding: 8, border: "1px dashed #cbd5e1", borderRadius: 8, width: "100%", cursor: uploading ? "not-allowed" : "pointer" }} />
          {uploading && <p style={{ color: "#6366f1", fontSize: 13, marginTop: 8 }}>正在解析并索引...</p>}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: 16 }}>
          <div className="card" style={{ padding: 14, height: "fit-content" }}>
            <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 10 }}>已索引 {documents.length} 个文档</h3>
            {documents.length === 0 ? <p style={{ color: "#94a3b8", fontSize: 12, textAlign: "center", padding: 12 }}>暂无</p> : (
              <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 600, overflowY: "auto" }}>
                {documents.map(doc => (
                  <div key={doc.document_id} onClick={() => loadChunks(doc)}
                    style={{ padding: 8, border: "1px solid", borderColor: selectedDoc?.document_id === doc.document_id ? "#6366f1" : "#e2e8f0", background: selectedDoc?.document_id === doc.document_id ? "#eef2ff" : "#fff", borderRadius: 4, cursor: "pointer" }}>
                    <p style={{ fontSize: 12, fontWeight: 500, color: "#1e293b", marginBottom: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{(doc.filename || doc.document_id).slice(0, 24)}</p>
                    <p style={{ fontSize: 10, color: "#64748b" }}>{doc.chunk_count} chunks</p>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="card" style={{ padding: 16 }}>
            {selectedDoc ? (
              <>
                <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 10 }}>{selectedDoc.filename} 的切分结果({chunks.length} 个)</h3>
                {loadingChunks ? <p style={{ textAlign: "center", color: "#94a3b8", padding: 20 }}>加载中...</p> : chunks.length === 0 ? <p style={{ textAlign: "center", color: "#94a3b8", padding: 20 }}>暂无 chunks</p> : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 600, overflowY: "auto" }}>
                    {chunks.map((chunk, i) => (
                      <div key={chunk.id} style={{ padding: 10, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 4 }}>
                        <p style={{ fontSize: 10, color: "#64748b", marginBottom: 4 }}>#{i + 1} · {chunk.content_length} 字符</p>
                        <pre style={{ margin: 0, fontSize: 11, color: "#1e293b", whiteSpace: "pre-wrap", wordBreak: "break-word", fontFamily: "inherit" }}>{chunk.content}</pre>
                      </div>
                    ))}
                  </div>
                )}
              </>
            ) : <p style={{ textAlign: "center", color: "#94a3b8", padding: 60 }}>← 选择左侧文档查看切分</p>}
          </div>
        </div>
      </div>
    )}
    {activeTab === "recall" && (
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div className="card" style={{ padding: 20, height: "fit-content" }}>
          <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>问题</h2>
          <textarea value={query} onChange={e => setQuery(e.target.value)} placeholder="例如：染发会伤头发吗？" style={{ width: "100%", minHeight: 200, padding: 12, border: "1px solid #cbd5e1", borderRadius: 8, fontSize: 14, lineHeight: 1.6, fontFamily: "inherit", resize: "vertical" }} />
          <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
            <button onClick={handleTestRecall} disabled={testing} style={{ flex: 1, padding: "10px", background: "#6366f1", color: "#fff", border: "none", borderRadius: 8, fontSize: 14, fontWeight: 500, cursor: testing ? "not-allowed" : "pointer" }}>{testing ? "召回中..." : "命中测试"}</button>
            <button onClick={() => setQuery("")} style={{ padding: "10px 20px", background: "#f1f5f9", color: "#475569", border: "none", borderRadius: 8, fontSize: 14, cursor: "pointer" }}>清空</button>
          </div>
        </div>
        <div className="card" style={{ padding: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <h2 style={{ fontSize: 16, fontWeight: 600 }}>测试预览</h2>
            {testResults.length > 0 && <span style={{ fontSize: 11, color: "#64748b" }}>耗时 {testMeta.elapsed}ms · 候选 {testMeta.total} 条</span>}
          </div>
          {testResults.length === 0 ? <p style={{ textAlign: "center", color: "#94a3b8", padding: 60, fontSize: 13 }}>输入问题并点击「命中测试」查看切片排序</p> : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 500, overflowY: "auto" }}>
              {testResults.map(hit => (
                <div key={hit.rank} style={{ padding: 12, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 6, borderLeft: "3px solid " + (hit.score > 0.8 ? "#10b981" : hit.score > 0.6 ? "#6366f1" : "#94a3b8") }}>
                  <p style={{ fontSize: 11, color: "#64748b", marginBottom: 4, display: "flex", justifyContent: "space-between" }}><span>#{hit.rank} · {hit.filename}</span><span style={{ color: hit.score > 0.8 ? "#10b981" : hit.score > 0.6 ? "#6366f1" : "#94a3b8", fontWeight: 600 }}>{(hit.score * 100).toFixed(1)}%</span></p>
                  <p style={{ fontSize: 12, color: "#1e293b", lineHeight: 1.6 }}>{hit.content}</p>
                </div>
              ))}
            </div>
          )}
        </div>
        {history.length > 0 && (
          <div className="card" style={{ padding: 20, gridColumn: "1 / -1" }}>
            <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>测试历史</h3>
            <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
              <thead><tr style={{ background: "#f8fafc" }}><th style={{ padding: 8, textAlign: "left", borderBottom: "1px solid #e2e8f0" }}>问题</th><th style={{ padding: 8, textAlign: "left", borderBottom: "1px solid #e2e8f0" }}>命中</th><th style={{ padding: 8, textAlign: "left", borderBottom: "1px solid #e2e8f0" }}>最高分</th><th style={{ padding: 8, textAlign: "left", borderBottom: "1px solid #e2e8f0" }}>耗时</th><th style={{ padding: 8, textAlign: "left", borderBottom: "1px solid #e2e8f0" }}>时间</th></tr></thead>
              <tbody>
                {history.slice(0, 10).map(h => (
                  <tr key={h.id} style={{ borderBottom: "1px solid #f1f5f9" }}>
                    <td style={{ padding: 8 }}>{h.query}</td>
                    <td style={{ padding: 8, color: "#6366f1", fontWeight: 500 }}>{h.hits_count}</td>
                    <td style={{ padding: 8, color: "#10b981" }}>{(h.top_score * 100).toFixed(1)}%</td>
                    <td style={{ padding: 8, color: "#64748b" }}>{h.elapsed_ms}ms</td>
                    <td style={{ padding: 8, color: "#94a3b8" }}>{h.created_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    )}
    {activeTab === "history" && (
      <div className="card" style={{ padding: 20 }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>命中测试历史</h2>
        {history.length === 0 ? <p style={{ textAlign: "center", color: "#94a3b8", padding: 40 }}>暂无历史</p> : (
          <div>
            {history.map(h => (
              <details key={h.id} style={{ marginBottom: 8, padding: 12, background: "#f8fafc", borderRadius: 6 }}>
                <summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 500 }}>{h.query} · {h.hits_count} 命中 · {(h.top_score * 100).toFixed(1)}% · {h.created_at}</summary>
                <div style={{ marginTop: 8, paddingLeft: 16 }}>
                  {h.hits.slice(0, 3).map(hit => (
                    <div key={hit.rank} style={{ padding: 8, marginBottom: 4, background: "#fff", borderRadius: 4, fontSize: 11 }}>
                      <p style={{ color: "#64748b", marginBottom: 2 }}>#{hit.rank} {(hit.score * 100).toFixed(1)}% · {hit.filename}</p>
                      <p style={{ color: "#1e293b" }}>{hit.content.slice(0, 200)}...</p>
                    </div>
                  ))}
                </div>
              </details>
            ))}
            <button onClick={() => { if (confirm("清空？")) { setHistory([]); localStorage.removeItem(STORAGE_KEY) } }} style={{ marginTop: 12, padding: "6px 14px", background: "#fee2e2", color: "#dc2626", border: "none", borderRadius: 6, fontSize: 12, cursor: "pointer" }}>清空历史</button>
          </div>
        )}
      </div>
    )}
  </div></AdminLayout>); }
}
