/** 输入区（带图片附件）。*/
import type { AttachedImage } from '../../types/chat'

export function ChatInput({
  value, onChange, onSend, onAttach, onRemoveImage,
  images, disabled, placeholder = '问点什么…',
}: {
  value: string
  onChange: (v: string) => void
  onSend: () => void
  onAttach: (file: File) => void
  onRemoveImage: (id: string) => void
  images: AttachedImage[]
  disabled?: boolean
  placeholder?: string
}) {
  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend()
    }
  }

  return (
    <div style={{ padding: '12px 16px', background: '#fff', borderTop: '1px solid #e2e8f0' }}>
      {images.length > 0 && (
        <div style={{ display: 'flex', gap: 6, marginBottom: 8, flexWrap: 'wrap' }}>
          {images.map(img => (
            <div key={img.id} style={{ position: 'relative', width: 56, height: 56 }}>
              <img src={img.url} alt="" style={{ width: 56, height: 56, borderRadius: 8, objectFit: 'cover' }} />
              <button
                onClick={() => onRemoveImage(img.id)}
                style={{ position: 'absolute', top: -6, right: -6, width: 18, height: 18, borderRadius: '50%', background: '#1e293b', color: '#fff', border: 'none', cursor: 'pointer', fontSize: 11 }}
              >×</button>
            </div>
          ))}
        </div>
      )}
      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
        <label style={{ width: 36, height: 36, borderRadius: 8, background: '#f1f5f9', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0 }}>
          <input type="file" accept="image/*" multiple style={{ display: 'none' }} onChange={e => e.target.files?.[0] && onAttach(e.target.files[0])} />
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M14 11.5l-4.5-9-3 2 3 6" stroke="#64748b" strokeWidth="1.4" strokeLinecap="round" />
            <circle cx="4" cy="11" r="2.5" stroke="#64748b" strokeWidth="1.4" />
          </svg>
        </label>
        <textarea
          value={value}
          onChange={e => onChange(e.target.value)}
          onKeyDown={handleKey}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
          style={{
            flex: 1, padding: '8px 12px', borderRadius: 10,
            border: '1px solid #e2e8f0', fontSize: 14,
            resize: 'none', outline: 'none',
            fontFamily: 'inherit',
            minHeight: 36, maxHeight: 100,
          }}
        />
        <button
          onClick={onSend}
          disabled={disabled || !value.trim()}
          style={{
            padding: '8px 16px', borderRadius: 8, fontSize: 14, fontWeight: 500,
            background: value.trim() && !disabled ? '#6366f1' : '#e2e8f0',
            color: value.trim() && !disabled ? '#fff' : '#94a3b8',
            border: 'none', cursor: value.trim() && !disabled ? 'pointer' : 'not-allowed',
            flexShrink: 0,
          }}
        >发送</button>
      </div>
    </div>
  )
}
