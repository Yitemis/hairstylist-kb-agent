import { useState, useEffect } from 'react'
import AdminLayout from '../../components/admin/AdminLayout'
import { listStylists, adminCreateStylist, adminUpdateStylist, type Stylist, type Branch } from '../../utils/api'
import { showToast } from '../../utils/toast'

interface FormData {
  name: string
  branch_id: number | null
  avatar: string
  specialties: string
  description: string
  max_daily_hours: number
  is_active: boolean
}

const EMPTY: FormData = {
  name: '',
  branch_id: null,
  avatar: '',
  specialties: '',
  description: '',
  max_daily_hours: 8,
  is_active: true,
}

function Avatar({ name, url }: { name: string; url?: string }) {
  if (url) return <img src={url} alt={name} style={{ width: 36, height: 36, borderRadius: 10, objectFit: 'cover' }} />
  const colors = ['#6366f1', '#8b5cf6', '#ec4899', '#14b8a6', '#f59e0b']
  const bg = colors[name.charCodeAt(0) % colors.length]
  return (
    <div style={{ width: 36, height: 36, borderRadius: 10, background: bg, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 14, fontWeight: 600 }}>
      {name.slice(-1)}
    </div>
  )
}

function Modal({ open, title, data, branches, onChange, onSave, onClose }: {
  open: boolean; title: string; data: FormData; branches: Branch[];
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
            <label className="form-label">所属分店 *</label>
            <select className="select-field" style={{ width: '100%' }} value={data.branch_id || ''} onChange={e => onChange({ ...data, branch_id: parseInt(e.target.value) || null })}>
              <option value="">请选择分店</option>
              {branches.filter(b => b.is_active).map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">发型师姓名 *</label>
            <input className="input-field" value={data.name} onChange={e => onChange({ ...data, name: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label">擅长技能（逗号分隔）*</label>
            <input className="input-field" value={data.specialties} onChange={e => onChange({ ...data, specialties: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label">个人简介</label>
            <textarea className="input-field" rows={3} value={data.description} onChange={e => onChange({ ...data, description: e.target.value })} style={{ resize: 'vertical' }} />
          </div>
          <div className="form-group">
            <label className="form-label">每日最大工作小时数</label>
            <input className="input-field" type="number" min={1} max={12} value={data.max_daily_hours} onChange={e => onChange({ ...data, max_daily_hours: parseInt(e.target.value) || 8 })} />
          </div>
          <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <label className="switch">
              <input type="checkbox" checked={data.is_active} onChange={e => onChange({ ...data, is_active: e.target.checked })} />
              <span className="switch-slider" />
            </label>
            <span style={{ fontSize: 14, color: '#64748b' }}>{data.is_active ? '在职' : '下线'}</span>
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

export default function StylistManagePage() {
  const [stylists, setStylists] = useState<Stylist[]>([])
  const [branches, setBranches] = useState<Branch[]>([])
  const [modalOpen, setModalOpen] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [form, setForm] = useState<FormData>(EMPTY)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchData() {
      try {
        const [stylistRes, branchRes] = await Promise.all([
          listStylists(),
          import('../../utils/api').then(m => m.listBranches()),
        ])
        if (stylistRes.code === 0) setStylists(stylistRes.data || [])
        if (branchRes.code === 0) setBranches(branchRes.data || [])
      } catch (e) {
        showToast('网络错误', 'error')
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  const openCreate = () => { setEditId(null); setForm(EMPTY); setModalOpen(true) }
  const openEdit = (s: Stylist) => {
    setEditId(s.id)
    setForm({
      name: s.name,
      branch_id: s.branch_id,
      avatar: s.avatar || '',
      specialties: s.specialties?.join(',') || '',
      description: s.description || '',
      max_daily_hours: s.max_daily_hours,
      is_active: s.is_active,
    })
    setModalOpen(true)
  }

  const handleSave = async () => {
    if (!form.name || !form.branch_id || !form.specialties) {
      showToast('请填写必填项', 'error')
      return
    }
    const submitData = {
      ...form,
      specialties: form.specialties.split(',').map(s => s.trim()).filter(Boolean),
    }
    try {
      if (editId !== null) {
        const res = await adminUpdateStylist(editId, submitData)
        if (res.code !== 0) { showToast(res.message || '更新失败', 'error'); return }
        showToast('发型师信息已更新', 'success')
      } else {
        const res = await adminCreateStylist(submitData)
        if (res.code !== 0) { showToast(res.message || '新增失败', 'error'); return }
        setStylists(prev => [...prev, res.data])
        showToast('发型师已添加', 'success')
      }
      setModalOpen(false)
      const res = await listStylists()
      if (res.code === 0) setStylists(res.data || [])
    } catch (e) {
      showToast('网络错误', 'error')
    }
  }

  const handleToggle = async (id: number, current: boolean) => {
    try {
      const stylist = stylists.find(s => s.id === id)
      if (!stylist) return
      const res = await adminUpdateStylist(id, { ...stylist, is_active: !current })
      if (res.code !== 0) { showToast(res.message || '操作失败', 'error'); return }
      setStylists(prev => prev.map(s => s.id === id ? { ...s, is_active: !current } : s))
      showToast(`已${!current ? '上架' : '下架'}`, 'info')
    } catch (e) {
      showToast('网络错误', 'error')
    }
  }

  return (
    <AdminLayout>
      <div style={{ padding: 28 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}>发型师管理</h1>
            <p style={{ fontSize: 13, color: '#64748b', marginTop: 3 }}>共 {stylists.length} 位发型师</p>
          </div>
          <button className="btn btn-primary" onClick={openCreate}>+ 新增发型师</button>
        </div>

        <div className="card" style={{ overflow: 'hidden' }}>
          <table className="data-table">
            <thead>
              <tr>
                {['ID', '头像', '姓名', '所属分店', '擅长技能', '每日限时', '状态', '操作'].map(h => <th key={h}>{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} style={{ textAlign: 'center', padding: 30, color: '#94a3b8' }}>加载中...</td></tr>
              ) : stylists.length === 0 ? (
                <tr><td colSpan={8} style={{ textAlign: 'center', padding: 30, color: '#94a3b8' }}>暂无发型师</td></tr>
              ) : (
                stylists.map(s => (
                  <tr key={s.id}>
                    <td style={{ color: '#94a3b8', fontSize: 13 }}>#{s.id}</td>
                    <td><Avatar name={s.name} url={s.avatar || undefined} /></td>
                    <td>
                      <p style={{ fontWeight: 500 }}>{s.name}</p>
                      {s.description && <p style={{ fontSize: 12, color: '#94a3b8', marginTop: 1 }}>{s.description.slice(0, 22)}…</p>}
                    </td>
                    <td>{branches.find(b => b.id === s.branch_id)?.name || '-'}</td>
                    <td>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                        {(s.specialties || []).map(sk => (
                          <span key={sk} style={{ fontSize: 11, padding: '2px 7px', borderRadius: 999, background: '#f5f3ff', color: '#6366f1', border: '1px solid #e0d9ff' }}>{sk}</span>
                        ))}
                      </div>
                    </td>
                    <td><span style={{ fontSize: 13, padding: '3px 10px', borderRadius: 999, background: '#eff6ff', color: '#3b82f6' }}>{s.max_daily_hours}h/天</span></td>
                    <td><span className={s.is_active ? 'badge badge-active' : 'badge badge-inactive'}>{s.is_active ? '● 在职' : '● 已下线'}</span></td>
                    <td>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button className="btn btn-ghost" style={{ padding: '5px 10px', fontSize: 12 }} onClick={() => openEdit(s)}>编辑</button>
                        <button className="btn btn-danger" style={{ padding: '5px 10px', fontSize: 12 }} onClick={() => handleToggle(s.id, s.is_active)}>
                          {s.is_active ? '下架' : '上架'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <Modal
        open={modalOpen}
        title={editId !== null ? '编辑发型师' : '新增发型师'}
        data={form}
        branches={branches}
        onChange={setForm}
        onSave={handleSave}
        onClose={() => setModalOpen(false)}
      />
    </AdminLayout>
  )
}
