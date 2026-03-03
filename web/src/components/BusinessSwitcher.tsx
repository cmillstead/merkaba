import { useBusinessContext } from '../context/BusinessContext'

export default function BusinessSwitcher() {
  const { businesses, selected, setSelected, loading } = useBusinessContext()

  if (loading) return null
  if (businesses.length === 0) return null

  return (
    <div style={{
      padding: '8px 20px 16px',
      borderBottom: '1px solid var(--border)',
      marginBottom: 8,
    }}>
      <label style={{
        display: 'block',
        fontSize: 11,
        color: 'var(--text-dim)',
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        marginBottom: 4,
      }}>
        Business
      </label>
      <select
        value={selected ?? ''}
        onChange={e => setSelected(e.target.value ? Number(e.target.value) : null)}
        aria-label="Select business"
        style={{
          width: '100%',
          background: 'var(--bg)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius)',
          color: 'var(--text)',
          padding: '6px 8px',
          fontSize: 13,
          cursor: 'pointer',
        }}
      >
        <option value="">All Businesses</option>
        {businesses.map(b => (
          <option key={b.id} value={b.id}>{b.name}</option>
        ))}
      </select>
    </div>
  )
}
