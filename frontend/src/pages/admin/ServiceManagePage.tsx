import { useState, useEffect } from 'react'
import { listServices, adminCreateService as createService, adminUpdateService as updateService, adminDeleteService as deleteService } from '../../api'
import AdminLayout from '../../components/admin/AdminLayout'
import { showToast } from '../../utils/toast'

type Category = '剪发' | '烫发' | '染发' | '护理' | '造型'
const CATEGORIES: Category[] = ['剪发', '烫发', '染发', '护理', '造型']

interface Service {
  id: number; name: string; category: Category; duration: number; price: number; desc: string; active: boolean
}

const CATEGORY_COLORS: Record<Category, { bg: string; color: string }> = {
  剪发: { bg: '#eff6ff', color: '#3b82f6' },
  烫发: { bg: '#fdf4ff', color: '#a855f7' },
  染发: { bg: '#fff7ed', color: '#f97316' },
  护理: { bg: '#f0fdf4', color: '#22c55e' },
  造型: { bg: '#fef3c7', color: '#f59e0b' },
}

type FormData = Omit<Service, 'id'>
const EMPTY: FormData = { name: '', category: '剪发', duration: 60, price: 0, desc: '', active: true }

function Modal({ open, title, data, onChange, onSave, onClose }: {
  open: boolean; title: string; data: FormData
  onChange: (d: FormData) => void; onSave: () => void; onClose: () => void
}) {
  if (!open) return null
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={e => e.stopPropagation()}>
        <div style={{ padding: '20px 24px', borderBottom: '1px solid #f1f5f9', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h3 style={{ fontSize: 17, fontWeight: 600, color: '#1e293b' }}>{title}</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}>
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M2 2L16 16M16 2L2 16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>
          </button>
        </div>
        <div style={{ padding: '20px 24px' }}>
          <div className="form-group">
            <label className="form-label">服务名称 *</label>
            <input className="input-field" placeholder="例：数码烫（大波浪）" value={data.name} onChange={e => onChange({ ...data, name: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label">服务分类 *</label>
            <select className="select-field" style={{ width: '100%' }} value={data.category} onChange={e => onChange({ ...data, category: e.target.value as Category })}>
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div className="form-group">
              <label className="form-label">时长（分钟）*</label>
              <input className="input-field" type="number" min={15} max={480} step={15} value={data.duration} onChange={e => onChange({ ...data, duration: parseInt(e.target.value) || 15 })} />
            </div>
            <div className="form-group">
              <label className="form-label">价格（元）*</label>
              <input className="input-field" type="number" min={0} step={1} value={data.price} onChange={e => onChange({ ...data, price: parseFloat(e.target.value) || 0 })} />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">服务描述</label>
            <textarea className="input-field" rows={3} placeholder="简单描述服务内容、特点和适合人群..." value={data.desc} onChange={e => onChange({ ...data, desc: e.target.value })} style={{ resize: 'vertical' }} />
          </div>
          <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <label className="switch">
              <input type="checkbox" checked={data.active} onChange={e => onChange({ ...data, active: e.target.checked })} />
              <span className="switch-slider" />
            </label>
            <span style={{ fontSize: 14, color: '#64748b' }}>{data.active ? '已上架' : '已下架'}</span>
          </div>
        </div>
        <div style={{ padding: '14px 24px', borderTop: '1px solid #f1f5f9', display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <button className="btn btn-ghost" onClick={onClose}>取消</button>
          <button className="btn btn-primary" onClick={onSave}>保存</button>
        </div>
      </div>
    </div>
  )
}

export default function ServiceManagePage() {
  const [services, setServices] = useState<Service[]>([])
  useEffect(() => { listServices().then((d: any) => setServices(d as any)).catch(() => {}) }, [])
  const [modalOpen, setModalOpen] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [form, setForm] = useState<FormData>(EMPTY)
  const [catFilter, setCatFilter] = useState<'all' | Category>('all')

  const filtered = catFilter === 'all' ? services : services.filter(s => s.category === catFilter)

  const openCreate = () => { setEditId(null); setForm(EMPTY); setModalOpen(true) }
  const openEdit = (s: Service) => { setEditId(s.id); setForm({ name: s.name, category: s.category, duration: s.duration, price: s.price, desc: s.desc, active: s.active }); setModalOpen(true) }

  const handleSave = () => {
    if (!form.name) { showToast('请填写服务名称', 'error'); return }
    if (editId !== null) {
      setServices(prev => prev.map(s => s.id === editId ? { ...s, ...form } : s))
      showToast('服务已更新', 'success')
    } else {
      const newId = Math.max(...services.map(s => s.id)) + 1
      setServices(prev => [...prev, { id: newId, ...form }])
      showToast('服务已新增', 'success')
    }
    setModalOpen(false)
  }

  const handleToggle = (id: number) => {
    setServices(prev => prev.map(s => s.id === id ? { ...s, active: !s.active } : s))
    showToast('状态已更新', 'info')
  }

  return (
    <AdminLayout>
      <div style={{ padding: 28 }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}>服务项目管理</h1>
            <p style={{ fontSize: 13, color: '#64748b', marginTop: 3 }}>共 {services.length} 个服务项目</p>
          </div>
          <button className="btn btn-primary" onClick={openCreate}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 1V13M1 7H13" stroke="white" strokeWidth="2" strokeLinecap="round"/></svg>
            新增服务
          </button>
        </div>

        {/* Category filters */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 18, flexWrap: 'wrap' }}>
          {(['all', ...CATEGORIES] as const).map(c => (
            <button
              key={c}
              onClick={() => setCatFilter(c)}
              style={{
                padding: '6px 14px', borderRadius: 999, fontSize: 13, fontWeight: 500, cursor: 'pointer', border: 'none',
                background: catFilter === c ? '#6366f1' : '#f1f5f9',
                color: catFilter === c ? '#fff' : '#64748b',
                transition: 'all 0.12s',
              }}
            >
              {c === 'all' ? '全部' : c}
              {c !== 'all' && (
                <span style={{ marginLeft: 5, fontSize: 11, opacity: 0.8 }}>({services.filter(s => s.category === c).length})</span>
              )}
            </button>
          ))}
        </div>

        {/* Table */}
        <div className="card" style={{ overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  {['ID', '服务名称', '分类', '时长', '价格', '状态', '操作'].map(h => <th key={h}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {filtered.map(s => {
                  const catStyle = CATEGORY_COLORS[s.category]
                  return (
                    <tr key={s.id} className="animate-fade-up">
                      <td style={{ color: '#94a3b8', fontSize: 13 }}>#{s.id}</td>
                      <td>
                        <p style={{ fontWeight: 500 }}>{s.name}</p>
                        {s.desc && <p style={{ fontSize: 12, color: '#94a3b8', marginTop: 1, maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.desc}</p>}
                      </td>
                      <td>
                        <span style={{ fontSize: 12, padding: '3px 9px', borderRadius: 999, background: catStyle.bg, color: catStyle.color, fontWeight: 500 }}>{s.category}</span>
                      </td>
                      <td style={{ fontSize: 13, color: '#64748b' }}>
                        {s.duration >= 60 ? `${Math.floor(s.duration / 60)}h${s.duration % 60 ? `${s.duration % 60}min` : ''}` : `${s.duration}min`}
                      </td>
                      <td style={{ fontWeight: 600, color: '#6366f1', fontSize: 15 }}>¥{s.price}</td>
                      <td><span className={s.active ? 'badge badge-active' : 'badge badge-inactive'}>{s.active ? '● 上架' : '● 下架'}</span></td>
                      <td>
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button className="btn btn-ghost" style={{ padding: '5px 10px', fontSize: 12 }} onClick={() => openEdit(s)}>编辑</button>
                          <button className="btn btn-danger" style={{ padding: '5px 10px', fontSize: 12 }} onClick={() => handleToggle(s.id)}>
                            {s.active ? '下架' : '上架'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {filtered.length === 0 && (
            <div style={{ padding: '40px 0', textAlign: 'center', color: '#94a3b8' }}>
              <p style={{ fontSize: 32, marginBottom: 10 }}>✂️</p>
              <p>该分类暂无服务项目</p>
            </div>
          )}
        </div>
      </div>

      <Modal open={modalOpen} title={editId !== null ? '编辑服务' : '新增服务'} data={form} onChange={setForm} onSave={handleSave} onClose={() => setModalOpen(false)} />
    </AdminLayout>
  )
}
