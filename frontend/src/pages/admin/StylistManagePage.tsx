import { useState, useEffect } from 'react'
import { listStylists, listBranches, adminCreateStylist as createStylist, adminUpdateStylist as updateStylist, adminDeleteStylist as deleteStylist } from '../../api'
import AdminLayout from '../../components/admin/AdminLayout'
import { showToast } from '../../utils/toast'



type FormData = any
const EMPTY: any = { name: '', branch_id: 0, skills: '', bio: '', maxHoursPerDay: 8, avatarUrl: '', active: true }

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
  open: boolean; title: string; data: FormData
  onChange: (d: FormData) => void; onSave: () => void; onClose: () => void; branches: any[]
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
            <label className="form-label">所属分店 *</label>
            <select className="select-field" style={{ width: '100%' }} value={data.branch_id} onChange={e => onChange({ ...data, branch: e.target.value })}>
              {(branches || []).map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">发型师姓名 *</label>
            <input className="input-field" placeholder="请输入姓名" value={data.name} onChange={e => onChange({ ...data, name: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label">头像 URL（可选）</label>
            <input className="input-field" placeholder="https://..." value={data.avatar || ""} onChange={e => onChange({ ...data, avatarUrl: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label">擅长技能（逗号分隔）*</label>
            <input className="input-field" placeholder="烫发,染发,造型" value={(data.specialties || []).join(", ")} onChange={e => onChange({ ...data, skills: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label">个人简介</label>
            <textarea className="input-field" rows={3} placeholder="简单介绍发型师的风格和经验..." value={data.description || ""} onChange={e => onChange({ ...data, bio: e.target.value })} style={{ resize: 'vertical' }} />
          </div>
          <div className="form-group">
            <label className="form-label">每日最大工作小时数</label>
            <input className="input-field" type="number" min={1} max={12} value={data.max_daily_hours} onChange={e => onChange({ ...data, maxHoursPerDay: parseInt(e.target.value) || 1 })} />
          </div>
          <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <label className="switch">
              <input type="checkbox" checked={data.active} onChange={e => onChange({ ...data, active: e.target.checked })} />
              <span className="switch-slider" />
            </label>
            <span style={{ fontSize: 14, color: '#64748b' }}>{data.active ? '上班状态' : '休假/下线'}</span>
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
  const [stylists, setStylists] = useState<any[]>([])
  const [branches, setBranches] = useState<{ id: number; name: string }[]>([])
  useEffect(() => {
    listStylists().then((d: any) => setStylists(d as any)).catch(() => {})
    listBranches().then((data: any) => setBranches(data as any)).catch(() => {})
  }, [])
  const [modalOpen, setModalOpen] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [form, setForm] = useState<FormData>(EMPTY)

  const openCreate = () => { setEditId(null); setForm(EMPTY); setModalOpen(true) }
  const openEdit = (s: any) => { setEditId(s.id); setForm({ name: s.name, branch: s.branch, skills: s.skills, bio: s.bio, maxHoursPerDay: s.maxHoursPerDay, avatarUrl: s.avatarUrl, active: s.active }); setModalOpen(true) }

  const handleSave = () => {
    if (!form.name || !form.skills) { showToast('请填写必填项', 'error'); return }
    if (editId !== null) {
      setStylists(prev => prev.map(s => s.id === editId ? { ...s, ...form } : s))
      showToast('发型师信息已更新', 'success')
    } else {
      const newId = Math.max(...stylists.map(s => s.id)) + 1
      setStylists(prev => [...prev, { id: newId, ...form }])
      showToast('发型师已添加', 'success')
    }
    setModalOpen(false)
  }

  const handleToggle = (id: number) => {
    setStylists(prev => prev.map(s => s.id === id ? { ...s, active: !s.active } : s))
    showToast('状态已更新', 'info')
  }

  return (
    <AdminLayout>
      <div style={{ padding: 28 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}>发型师管理</h1>
            <p style={{ fontSize: 13, color: '#64748b', marginTop: 3 }}>共 {stylists.length} 位发型师</p>
          </div>
          <button className="btn btn-primary" onClick={openCreate}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 1V13M1 7H13" stroke="white" strokeWidth="2" strokeLinecap="round"/></svg>
            新增发型师
          </button>
        </div>

        <div className="card" style={{ overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  {['ID', '头像', '姓名', '所属分店', '擅长技能', '每日限时', '状态', '操作'].map(h => <th key={h}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {stylists.map(s => (
                  <tr key={s.id} className="animate-fade-up">
                    <td style={{ color: '#94a3b8', fontSize: 13 }}>#{s.id}</td>
                    <td><Avatar name={s.name} url={s.avatar} /></td>
                    <td>
                      <p style={{ fontWeight: 500 }}>{s.name}</p>
                      <p style={{ fontSize: 12, color: '#94a3b8', marginTop: 1 }}>{(s.description || "").slice(0, 22)}…</p>
                    </td>
                    <td>{branches.find(b => b.id === s.branch_id)?.name || "-"}</td>
                    <td>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                        {(s.specialties || []).join(',').split(',').map(sk => (
                          <span key={sk} style={{ fontSize: 11, padding: '2px 7px', borderRadius: 999, background: '#f5f3ff', color: '#6366f1', border: '1px solid #e0d9ff' }}>{sk}</span>
                        ))}
                      </div>
                    </td>
                    <td>
                      <span style={{ fontSize: 13, padding: '3px 10px', borderRadius: 999, background: '#eff6ff', color: '#3b82f6' }}>{s.max_daily_hours}h/天</span>
                    </td>
                    <td><span className={s.active ? 'badge badge-active' : 'badge badge-inactive'}>{s.active ? '● 在职' : '● 已下线'}</span></td>
                    <td>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button className="btn btn-ghost" style={{ padding: '5px 10px', fontSize: 12 }} onClick={() => openEdit(s)}>编辑</button>
                        <button className="btn btn-danger" style={{ padding: '5px 10px', fontSize: 12 }} onClick={() => handleToggle(s.id)}>
                          {s.active ? '下架' : '上架'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <Modal open={modalOpen} title={editId !== null ? '编辑发型师' : '新增发型师'} data={form} branches={branches} onChange={setForm} onSave={handleSave} onClose={() => setModalOpen(false)} />
    </AdminLayout>
  )
}
