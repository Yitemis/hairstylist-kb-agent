/** 打字动画 dots。*/
export function TypingDots() {
  return (
    <span style={{ display: 'inline-flex', gap: 3, marginLeft: 6, verticalAlign: 'middle' }}>
      <span style={{ width: 5, height: 5, borderRadius: '50%', background: '#94a3b8', display: 'inline-block', animation: 'dot-bounce 1.2s infinite ease-in-out' }} />
      <span style={{ width: 5, height: 5, borderRadius: '50%', background: '#94a3b8', display: 'inline-block', animation: 'dot-bounce 1.2s infinite ease-in-out 0.15s' }} />
      <span style={{ width: 5, height: 5, borderRadius: '50%', background: '#94a3b8', display: 'inline-block', animation: 'dot-bounce 1.2s infinite ease-in-out 0.3s' }} />
    </span>
  )
}
