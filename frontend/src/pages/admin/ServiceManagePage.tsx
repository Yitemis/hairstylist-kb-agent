import { useState, useEffect } from 'react'
import AdminLayout from '../../components/admin/AdminLayout'
import { listServices, adminCreateService, adminUpdateService, type Service } from '../../utils/api'
import { showToast } from '../../utils/toast'

const CATEGORIES = ['剪发', '烫发', '染发', '护理', '造型']
const CATEGORY_COLORS: Record<string, { bg: string; color: string }> = {
  剪发: { bg: '#eff6ff', color: '#3b82f6' },
  烫发: { bg: '#fdf4ff', color: '#a855f7' },
  染发: { bg: '#fff7ed', color: '#f97316' },
  护理: { bg: '#f0fdf4', color: '#22c55e' },
  造型: { bg: '#fef3c7', color: '#f59e0b' },
}

interface FormData {
  name: string
  category: string
  duration_minutes: number
  price: number
  description: string
  is_active: boolean
}

const EMPTY: FormData = { name: '', category: '剪发', duration_minutes: 60, price: 0, description: '', is_active: true }

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
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: 20 }}>×</button>
        </div>
        <div style={{ padding: '20px 24px' }}>
          <div className="form-group">
            <label className="form-label">服务名称 *</label>
            <input className="input-field" value={data.name} onChange={e => onChange({ ...data, name: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label">服务分类 *</label>
            <select className="select-field" style={{ width: '100%' }} value={data.category} onChange={e => onChange({ ...data, category: e.target.value })}>
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div className="form-group">
              <label className="form-label">时长（分钟）*</label>
              <input className="input-field" type="number" min={15} max={480} value={data.duration_minutes} onChange={e => onChange({ ...data, duration_minutes: parseInt(e.target.value) || 15 })} />
            </div>
            <div className="form-group">
              <label className="form-label">价格（元）*</label>
              <input className="input-field" type="number" min={0} value={data.price} onChange={e => onChange({ ...data, price: parseFloat(e.target.value) || 0 })} />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">服务描述</label>
            <textarea className="input-field" rows={3} value={data.description} onChange={e => onChange({ ...data, description: e.target.value })} style={{ resize: 'vertical' }} />
          </div>
          <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <label className="switch">
              <input type="checkbox" checked={data.is_active} onChange={e => onChange({ ...data, is_active: e.target.checked })} />
              <span className="switch-slider" />
            </label>
            <span style={{ fontSize: 14, color: '#64748b' }}>{data.is_active ? '已上架' : '已下架'}</span>
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
  const [modalOpen, setModalOpen] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [form, setForm] = useState<FormData>(EMPTY)
  const [catFilter, setCatFilter] = useState<string>('all')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchServices() {
      try {
        const res = await listServices()
        if (res.code === 0) setServices(res.data || [])
      } catch (e) {
        showToast('网络错误', 'error')
      } finally {
        setLoading(false)
      }
    }
    fetchServices()
  }, [])

  const filtered = catFilter === 'all' ? services : services.filter(s => s.category === catFilter)

  const openCreate = () => { setEditId(null); setForm(EMPTY); setModalOpen(true) }
  const openEdit = (s: Service) => {
    setEditId(s.id)
    setForm({
      name: s.name,
      category: s.category,
      duration_minutes: s.duration_minutes,
      price: s.price || 0,
      description: s.description || '',
      is_active: s.is_active,
    })
    setModalOpen(true)
  }

  const handleSave = async () => {
    if (!form.name) { showToast('请填写服务名称', 'error'); return }
    try {
      if (editId !== null) {
        const res = await adminUpdateService(editId, form)
        if (res.code !== 0) { showToast(res.message || '更新失败', 'error'); return }
        showToast('服务已更新', 'success')
      } else {
        const res = await adminCreateService(form)
        if (res.code !== 0) { showToast(res.message || '新增失败', 'error'); return }
        setServices(prev => [...prev, res.data])
        showToast('服务已新增', 'success')
      }
      setModalOpen(false)
      const res = await listServices()
      if (res.code === 0) setServices(res.data || [])
    } catch (e) {
      showToast('网络错误', 'error')
    }
  }

  const handleToggle = async (id: number, current: boolean) => {
    try {
      const service = services.find(s => s.id === id)
      if (!service) return
      const res = await adminUpdateService(id, { ...service, is_active: !current })
      if (res.code !== 0) { showToast(res.message || '操作失败', 'error'); return }
      setServices(prev => prev.map(s => s.id === id ? { ...s, is_active: !current } : s))
      showToast(`已${!current ? '上架' : '下架'}`, 'info')
    } catch (e) {
      showToast('网络错误', 'error')
    }
  }

  return (
    <AdminLayout>
      <div style={{ padding: 28 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}>服务项目管理</h1>
            <p style={{ fontSize: 13, color: '#64748b', marginTop: 3 }}>共 {services.length} 个服务项目</p>
          </div>
          <button className="btn btn-primary" onClick={openCreate}>+ 新增服务</button>
        </div>

        <div style={{ display: 'flex', gap: 8, marginBottom: 18, flexWrap: 'wrap' }}>
          {['all', ...CATEGORIES].map(c => (
            <button
              key={c}
              onClick={() => setCatFilter(c)}
              style={{
                padding: '6px 14px', borderRadius: 999, fontSize: 13, fontWeight: 500, cursor: 'pointer', border: 'none',
                background: catFilter === c ? '#6366f1' : '#f1f5f9',
                color: catFilter === c ? '#fff' : '#64748b',
              }}
            >
              {c === 'all' ? '全部' : c}
            </button>
          ))}
        </div>

        <div className="card" style={{ overflow: 'hidden' }}>
          <table className="data-table">
            <thead>
              <tr>
                {['ID', '服务名称', '分类', '时长', '价格', '状态', '操作'].map(h => <th key={h}>{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} style={{ textAlign: 'center', padding: 30, color: '#94a3b8' }}>加载中...</td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={7} style={{ textAlign: 'center', padding: 30, color: '#94a3b8' }}>该分类暂无服务项目</td></tr>
              ) : (
                filtered.map(s => {
                  const catStyle = CATEGORY_COLORS[s.category] || { bg: '#f1f5f9', color: '#64748b' }
                  return (
                    <tr key={s.id}>
                      <td style={{ color: '#94a3b8', fontSize: 13 }}>#{s.id}</td>
                      <td>
                        <p style={{ fontWeight: 500 }}>{s.name}</p>
                        {s.description && <p style={{ fontSize: 12, color: '#94a3b8', marginTop: 1, maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.description}</p>}
                      </td>
                      <td>
                        <span style={{ fontSize: 12, padding: '3px 9px', borderRadius: 999, background: catStyle.bg, color: catStyle.color, fontWeight: 500 }}>{s.category}</span>
                      </td>
                      <td>{s.duration_minutes >= 60 ? `${Math.floor(s.duration_minutes / 60)}h${s.duration_minutes % 60 ? `${s.duration_minutes % 60}min` : ''}` : `${s.duration_minutes}min`}</td>
                      <td style={{ fontWeight: 600, color: '#6366f1' }}>¥{s.price}</td>
                      <td><span className={s.is_active ? 'badge badge-active' : 'badge badge-inactive'}>{s.is_active ? '● 上架' : '● 下架'}</span></td>
                      <td>
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button className="btn btn-ghost" style={{ padding: '5px 10px', fontSize: 12 }} onClick={() => openEdit(s)}>编辑</button>
                          <button className="btn btn-danger" style={{ padding: '5px 10px', fontSize: 12 }} onClick={() => handleToggle(s.id, s.is_active)}>
                            {s.is_active ? '下架' : '上架'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      <Modal
        open={modalOpen}
        title={editId !== null ? '编辑服务' : '新增服务'}
        data={form}
        onChange={setForm}
        onSave={handleSave}
        onClose={() => setModalOpen(false)}
      />
    </AdminLayout>
  )
}
