import { useState, useEffect } from 'react'
import AdminLayout from '../../components/admin/AdminLayout'
import { listBranches, adminCreateBranch, adminUpdateBranch, adminDeleteBranch, type Branch } from '../../utils/api'
import { showToast } from '../../utils/toast'

const EMPTY: Omit<Branch, 'id' | 'is_active'> = {
  name: '',
  address: '',
  phone: '',
  latitude: undefined,
  longitude: undefined,
  max_daily_appointments: 20,
  is_active: true,
}

function Modal({
  open, title, data, onChange, onSave, onClose
}: {
  open: boolean; title: string; data: Omit<Branch, 'id'>;
  onChange: (d: Omit<Branch, 'id'>) => void; onSave: () => void; onClose: () => void
}) {
  if (!open) return null
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={e => e.stopPropagation()}>
        <div style={{ padding: '20px 24px', borderBottom: '1px solid #f1f5f9', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h3 style={{ fontSize: 17, fontWeight: 600, color: '#1e293b' }}>{title}</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}>
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M2 2L16 16M16 2L2 16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </button>
        </div>
        <div style={{ padding: '20px 24px' }}>
          <div className="form-group">
            <label className="form-label">分店名称 *</label>
            <input className="input-field" placeholder="例：三里屯旗舰店" value={data.name} onChange={e => onChange({ ...data, name: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label">详细地址 *</label>
            <input className="input-field" placeholder="区县 + 街道 + 门牌号" value={data.address} onChange={e => onChange({ ...data, address: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label">联系电话 *</label>
            <input className="input-field" placeholder="010-XXXX-XXXX" value={data.phone || ''} onChange={e => onChange({ ...data, phone: e.target.value })} />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div className="form-group">
              <label className="form-label">纬度（可选）</label>
              <input className="input-field" placeholder="39.9000" value={data.latitude || ''} onChange={e => onChange({ ...data, latitude: parseFloat(e.target.value) || undefined })} />
            </div>
            <div className="form-group">
              <label className="form-label">经度（可选）</label>
              <input className="input-field" placeholder="116.4000" value={data.longitude || ''} onChange={e => onChange({ ...data, longitude: parseFloat(e.target.value) || undefined })} />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">每日最大预约数</label>
            <input className="input-field" type="number" min={1} max={200} value={data.max_daily_appointments || 20} onChange={e => onChange({ ...data, max_daily_appointments: parseInt(e.target.value) || undefined })} />
          </div>
          <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <label className="switch">
              <input type="checkbox" checked={data.is_active} onChange={e => onChange({ ...data, is_active: e.target.checked })} />
              <span className="switch-slider" />
            </label>
            <span style={{ fontSize: 14, color: '#64748b' }}>{data.is_active ? '正常营业' : '暂停营业'}</span>
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

export default function BranchManagePage() {
  const [branches, setBranches] = useState<Branch[]>([])
  const [modalOpen, setModalOpen] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [form, setForm] = useState<Omit<Branch, 'id'>>(EMPTY)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchBranches() {
      try {
        const res = await listBranches()
        if (res.code !== 0) {
          showToast(res.message || '获取分店失败', 'error')
          return
        }
        setBranches(res.data || [])
      } catch (e) {
        showToast('网络错误', 'error')
      } finally {
        setLoading(false)
      }
    }
    fetchBranches()
  }, [])

  const openCreate = () => { setEditId(null); setForm(EMPTY); setModalOpen(true) }
  const openEdit = (b: Branch) => {
    setEditId(b.id)
    setForm({
      name: b.name,
      address: b.address,
      phone: b.phone,
      latitude: b.latitude,
      longitude: b.longitude,
      max_daily_appointments: b.max_daily_appointments,
      is_active: b.is_active,
    })
    setModalOpen(true)
  }

  const handleSave = async () => {
    if (!form.name || !form.address) { showToast('请填写必填项', 'error'); return }
    try {
      if (editId !== null) {
        const res = await adminUpdateBranch(editId, form)
        if (res.code !== 0) {
          showToast(res.message || '更新失败', 'error')
          return
        }
        setBranches(prev => prev.map(b => b.id === editId ? { ...b, ...form } : b))
        showToast('分店信息已更新', 'success')
      } else {
        const res = await adminCreateBranch(form)
        if (res.code !== 0) {
          showToast(res.message || '新增失败', 'error')
          return
        }
        setBranches(prev => [...prev, res.data])
        showToast('分店已新增', 'success')
      }
      setModalOpen(false)
      // reload list
      const res = await listBranches()
      if (res.code === 0) setBranches(res.data || [])
    } catch (e) {
      showToast('网络错误', 'error')
    }
  }

  const handleToggleActive = async (id: number, current: boolean) => {
    try {
      const branch = branches.find(b => b.id === id)
      if (!branch) return
      const res = await adminUpdateBranch(id, { ...branch, is_active: !current })
      if (res.code !== 0) {
        showToast(res.message || '操作失败', 'error')
        return
      }
      setBranches(prev => prev.map(b => b.id === id ? { ...b, is_active: !current } : b))
      showToast(`已${!current ? '上架' : '下架'}`, 'info')
    } catch (e) {
      showToast('网络错误', 'error')
    }
  }

  return (
    <AdminLayout>
      <div style={{ padding: 28 }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}>分店管理</h1>
            <p style={{ fontSize: 13, color: '#64748b', marginTop: 3 }}>共 {branches.length} 家门店</p>
          </div>
          <button className="btn btn-primary" onClick={openCreate}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 1V13M1 7H13" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
            新增分店
          </button>
        </div>

        {/* Table */}
        <div className="card" style={{ overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  {['ID', '分店名称', '地址', '联系电话', '每日限额', '状态', '操作'].map(h => <th key={h}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={7} style={{ textAlign: 'center', padding: 30, color: '#94a3b8' }}>加载中...</td></tr>
                ) : branches.length === 0 ? (
                  <tr><td colSpan={7} style={{ textAlign: 'center', padding: 30, color: '#94a3b8' }}>暂无分店</td></tr>
                ) : (
                  branches.map(b => (
                    <tr key={b.id} className="animate-fade-up">
                      <td style={{ color: '#94a3b8', fontSize: 13 }}>#{b.id}</td>
                      <td style={{ fontWeight: 500 }}>{b.name}</td>
                      <td style={{ color: '#64748b', fontSize: 13, maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.address}</td>
                      <td style={{ fontFamily: 'monospace', fontSize: 13 }}>{b.phone}</td>
                      <td>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 10px', borderRadius: 999, background: '#f0fdf4', color: '#166534', fontSize: 13, fontWeight: 500 }}>
                          {b.max_daily_appointments} 单/日
                        </span>
                      </td>
                      <td>
                        <span className={b.is_active ? 'badge badge-active' : 'badge badge-inactive'}>
                          {b.is_active ? '● 营业中' : '● 已停业'}
                        </span>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button className="btn btn-ghost" style={{ padding: '5px 10px', fontSize: 12 }} onClick={() => openEdit(b)}>编辑</button>
                          <button className="btn btn-danger" style={{ padding: '5px 10px', fontSize: 12 }} onClick={() => handleToggleActive(b.id, b.is_active)}>
                            {b.is_active ? '下架' : '上架'}
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
      </div>

      <Modal
        open={modalOpen}
        title={editId !== null ? '编辑分店' : '新增分店'}
        data={form}
        onChange={setForm}
        onSave={handleSave}
        onClose={() => setModalOpen(false)}
      />
    </AdminLayout>
  )
}
