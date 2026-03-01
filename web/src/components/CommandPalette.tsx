import { useCallback, useEffect, useRef, useState } from 'react'

interface Command {
  id: string
  label: string
  action: () => void
}

interface Props {
  commands: Command[]
}

export default function CommandPalette({ commands }: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  const filtered = commands.filter(c =>
    c.label.toLowerCase().includes(query.toLowerCase())
  )

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === '/') {
        e.preventDefault()
        setOpen(prev => !prev)
        setQuery('')
        setSelectedIndex(0)
      }
      if (e.key === 'Escape' && open) {
        setOpen(false)
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [open])

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIndex(i => Math.min(i + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIndex(i => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' && filtered[selectedIndex]) {
      filtered[selectedIndex].action()
      setOpen(false)
    }
  }, [filtered, selectedIndex])

  if (!open) return null

  return (
    <div className="command-palette-overlay" onClick={() => setOpen(false)}>
      <div className="command-palette" onClick={e => e.stopPropagation()} onKeyDown={handleKeyDown}>
        <input
          ref={inputRef}
          className="command-palette-input"
          placeholder="Type a command..."
          value={query}
          onChange={e => { setQuery(e.target.value); setSelectedIndex(0) }}
        />
        <ul className="command-palette-list" role="listbox">
          {filtered.map((cmd, i) => (
            <li
              key={cmd.id}
              className={`command-palette-item ${i === selectedIndex ? 'command-palette-item--selected' : ''}`}
              role="option"
              aria-selected={i === selectedIndex}
              onClick={() => { cmd.action(); setOpen(false) }}
            >
              {cmd.label}
            </li>
          ))}
          {filtered.length === 0 && (
            <li className="command-palette-item command-palette-item--empty">No matching commands</li>
          )}
        </ul>
      </div>
    </div>
  )
}
