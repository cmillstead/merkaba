import { useState } from 'react'
import { Search } from 'lucide-react'
import { searchMemory, getFacts, getLearnings } from '../api/client'
import type { MemoryResult, Fact, Learning } from '../api/client'

// MemoryResult is a union with [key: string]: unknown, so we access fields via bracket notation
const field = (r: MemoryResult, key: string) => r[key] as string
const numField = (r: MemoryResult, key: string) => r[key] as number

function typeColor(type: string) {
  switch (type) {
    case 'fact': return 'var(--blue)'
    case 'decision': return 'var(--yellow)'
    case 'learning': return 'var(--green)'
    default: return 'var(--text-dim)'
  }
}

export default function Memory() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<MemoryResult[]>([])
  const [facts, setFacts] = useState<Fact[]>([])
  const [learnings, setLearnings] = useState<Learning[]>([])
  const [mode, setMode] = useState<'search' | 'browse'>('search')
  const [searched, setSearched] = useState(false)

  async function doSearch() {
    if (!query.trim()) return
    setSearched(true)
    const data = await searchMemory(query.trim())
    setResults(data.results)
  }

  async function loadBrowse() {
    setMode('browse')
    const [f, l] = await Promise.all([getFacts(), getLearnings()])
    setFacts(f.facts)
    setLearnings(l.learnings)
  }

  return (
    <>
      <h1>Memory</h1>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <button
          className={`btn ${mode === 'search' ? 'btn-primary' : 'btn-dim'}`}
          onClick={() => setMode('search')}
        >
          Search
        </button>
        <button
          className={`btn ${mode === 'browse' ? 'btn-primary' : 'btn-dim'}`}
          onClick={loadBrowse}
        >
          Browse
        </button>
      </div>

      {mode === 'search' && (
        <>
          <div className="search-bar">
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && doSearch()}
              placeholder="Search memory (semantic)..."
            />
            <button className="btn btn-primary" onClick={doSearch}>
              <Search size={16} />
            </button>
          </div>

          {!searched && results.length === 0 && (
            <div className="empty">Enter a query to search Merkaba's memory</div>
          )}
          {searched && results.length === 0 && (
            <div className="empty">No results found</div>
          )}
          {results.map((r, i) => (
            <div className="memory-card" key={i}>
              <div className="type-label" style={{ color: typeColor(r.type) }}>
                {r.type}
              </div>
              {r.type === 'fact' && (
                <div>
                  <span style={{ fontWeight: 600 }}>{field(r, 'key')}</span>: {field(r, 'value')}
                  <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 4 }}>
                    Category: {field(r, 'category')} | Confidence: {numField(r, 'confidence')}%
                  </div>
                </div>
              )}
              {r.type === 'decision' && (
                <div>
                  <div style={{ fontWeight: 600 }}>{field(r, 'decision')}</div>
                  <div style={{ fontSize: 13, marginTop: 4 }}>{field(r, 'reasoning')}</div>
                </div>
              )}
              {r.type === 'learning' && (
                <div>
                  <div>{field(r, 'insight')}</div>
                  {field(r, 'evidence') && (
                    <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 4 }}>
                      Evidence: {field(r, 'evidence')}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </>
      )}

      {mode === 'browse' && (
        <>
          {facts.length > 0 && (
            <>
              <h2 style={{ fontSize: 16, margin: '16px 0 8px' }}>Facts ({facts.length})</h2>
              {facts.slice(0, 50).map(f => (
                <div className="memory-card" key={f.id}>
                  <div className="type-label" style={{ color: 'var(--blue)' }}>
                    {f.category}
                  </div>
                  <span style={{ fontWeight: 600 }}>{f.key}</span>: {f.value}
                </div>
              ))}
            </>
          )}
          {learnings.length > 0 && (
            <>
              <h2 style={{ fontSize: 16, margin: '16px 0 8px' }}>Learnings ({learnings.length})</h2>
              {learnings.map(l => (
                <div className="memory-card" key={l.id}>
                  <div className="type-label" style={{ color: 'var(--green)' }}>
                    {l.category}
                  </div>
                  <div>{l.insight}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 4 }}>
                    Confidence: {l.confidence}%
                  </div>
                </div>
              ))}
            </>
          )}
          {facts.length === 0 && learnings.length === 0 && (
            <div className="empty">No memory entries yet</div>
          )}
        </>
      )}
    </>
  )
}
