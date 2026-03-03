interface PlaceholderProps {
  title: string
  phase: number
}

export default function Placeholder({ title, phase }: PlaceholderProps) {
  return (
    <div style={{ padding: '60px 0', textAlign: 'center' }}>
      <h1>{title}</h1>
      <p style={{ color: 'var(--text-dim)', marginTop: 12 }}>Coming in Phase {phase}</p>
    </div>
  )
}
