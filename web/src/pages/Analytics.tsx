import { useEffect, useState } from 'react'
import { getAnalytics } from '../api/client'
import type { AnalyticsOverview } from '../api/client'
import { BarChart3, PieChart, Database } from 'lucide-react'

export default function Analytics() {
  const [data, setData] = useState<AnalyticsOverview | null>(null)
  const [days, setDays] = useState(30)

  useEffect(() => {
    getAnalytics(days).then(setData).catch(() => {})
  }, [days])

  if (!data) return <div className="empty">Loading analytics...</div>

  const taskEntries = Object.entries(data.tasks_by_business)
  const memoryEntries = Object.entries(data.memory_by_business)
  const maxTasks = Math.max(...taskEntries.map(([, v]) => v.total), 1)
  const maxMemory = Math.max(...memoryEntries.map(([, v]) => v.facts + v.decisions), 1)

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h1>Analytics</h1>
        <div style={{ display: 'flex', gap: 4 }}>
          {[7, 30, 90].map(d => (
            <button
              key={d}
              className={days === d ? 'btn btn-primary' : 'btn btn-dim'}
              onClick={() => setDays(d)}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {/* Summary cards */}
      <div className="card-grid">
        <div className="card">
          <h3>Businesses</h3>
          <div className="value">{data.businesses}</div>
        </div>
        <div className="card">
          <h3>Total Approvals</h3>
          <div className="value">{data.approvals_summary.total ?? 0}</div>
        </div>
        <div className="card">
          <h3>Approved</h3>
          <div className="value" style={{ color: 'var(--green)' }}>
            {data.approvals_summary.approved ?? 0}
          </div>
        </div>
        <div className="card">
          <h3>Denied</h3>
          <div className="value" style={{ color: 'var(--red)' }}>
            {data.approvals_summary.denied ?? 0}
          </div>
        </div>
      </div>

      {/* Tasks by Business */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <BarChart3 size={16} style={{ color: 'var(--accent)' }} />
          <h3 style={{ margin: 0 }}>Tasks by Business</h3>
        </div>
        {taskEntries.length === 0 ? (
          <div style={{ color: 'var(--text-dim)', fontSize: 13 }}>No task data yet</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {taskEntries.map(([bizId, info]) => (
              <div key={bizId}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 4 }}>
                  <span>{info.name}</span>
                  <span style={{ color: 'var(--text-dim)' }}>{info.total} total</span>
                </div>
                <div style={{
                  display: 'flex',
                  height: 20,
                  borderRadius: 4,
                  overflow: 'hidden',
                  background: 'var(--bg)',
                  width: `${Math.max((info.total / maxTasks) * 100, 5)}%`,
                }}>
                  {info.completed > 0 && (
                    <div style={{ width: `${(info.completed / info.total) * 100}%`, background: 'var(--green)' }}
                      title={`${info.completed} completed`} />
                  )}
                  {info.running > 0 && (
                    <div style={{ width: `${(info.running / info.total) * 100}%`, background: 'var(--blue)' }}
                      title={`${info.running} running`} />
                  )}
                  {info.pending > 0 && (
                    <div style={{ width: `${(info.pending / info.total) * 100}%`, background: 'var(--yellow)' }}
                      title={`${info.pending} pending`} />
                  )}
                </div>
              </div>
            ))}
            <div style={{ display: 'flex', gap: 16, fontSize: 11, color: 'var(--text-dim)', marginTop: 4 }}>
              <span><span className="dot dot-green" />Completed</span>
              <span><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: 'var(--blue)', marginRight: 6 }} />Running</span>
              <span><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: 'var(--yellow)', marginRight: 6 }} />Pending</span>
            </div>
          </div>
        )}
      </div>

      {/* Approvals breakdown */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <PieChart size={16} style={{ color: 'var(--accent)' }} />
          <h3 style={{ margin: 0 }}>Approval Status</h3>
        </div>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          {Object.entries(data.approvals_summary)
            .filter(([k]) => k !== 'total')
            .map(([status, count]) => (
              <div key={status} style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 24, fontWeight: 700, color: status === 'approved' ? 'var(--green)' : status === 'denied' ? 'var(--red)' : 'var(--text-dim)' }}>
                  {count}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-dim)', textTransform: 'capitalize' }}>
                  {status}
                </div>
              </div>
            ))
          }
        </div>
      </div>

      {/* Memory by Business */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Database size={16} style={{ color: 'var(--accent)' }} />
          <h3 style={{ margin: 0 }}>Memory by Business</h3>
        </div>
        {memoryEntries.length === 0 ? (
          <div style={{ color: 'var(--text-dim)', fontSize: 13 }}>No memory data yet</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {memoryEntries.map(([bizId, info]) => {
              const total = info.facts + info.decisions
              return (
                <div key={bizId}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 4 }}>
                    <span>{info.name}</span>
                    <span style={{ color: 'var(--text-dim)' }}>{total} items</span>
                  </div>
                  <div style={{
                    display: 'flex',
                    height: 20,
                    borderRadius: 4,
                    overflow: 'hidden',
                    background: 'var(--bg)',
                    width: `${Math.max((total / maxMemory) * 100, 5)}%`,
                  }}>
                    {info.facts > 0 && (
                      <div style={{ width: `${(info.facts / total) * 100}%`, background: 'var(--accent)' }}
                        title={`${info.facts} facts`} />
                    )}
                    {info.decisions > 0 && (
                      <div style={{ width: `${(info.decisions / total) * 100}%`, background: 'var(--yellow)' }}
                        title={`${info.decisions} decisions`} />
                    )}
                  </div>
                </div>
              )
            })}
            <div style={{ display: 'flex', gap: 16, fontSize: 11, color: 'var(--text-dim)', marginTop: 4 }}>
              <span><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)', marginRight: 6 }} />Facts</span>
              <span><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: 'var(--yellow)', marginRight: 6 }} />Decisions</span>
            </div>
          </div>
        )}
      </div>
    </>
  )
}
