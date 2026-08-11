/** 卡片列表（用户可点选的选项）。*/
import type { CardItem } from '../../types/chat'

export function CardList({ cards, onSelect }: { cards: CardItem[]; onSelect: (c: CardItem) => void }) {
  return (
    <div style={{ marginTop: 8, display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 8 }}>
      {cards.map(c => (
        <button
          key={c.id}
          onClick={() => onSelect(c)}
          style={{
            padding: '10px 12px', borderRadius: 10,
            background: '#fff', border: '1px solid #e2e8f0',
            cursor: 'pointer', textAlign: 'left',
            transition: 'all 0.15s',
            display: 'flex', flexDirection: 'column', gap: 4,
          }}
          onMouseEnter={e => e.currentTarget.style.borderColor = '#6366f1'}
          onMouseLeave={e => e.currentTarget.style.borderColor = '#e2e8f0'}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: '#1e293b' }}>{c.title}</span>
            {c.badge && <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, background: '#f1f5f9', color: '#64748b' }}>{c.badge}</span>}
          </div>
          {c.subtitle && <span style={{ fontSize: 12, color: '#64748b', lineHeight: 1.5 }}>{c.subtitle}</span>}
        </button>
      ))}
    </div>
  )
}
