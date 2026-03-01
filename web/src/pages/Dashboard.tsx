import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getStatus, getBusinesses, getApprovals, getRecentRuns } from '../api/client'
import type { SystemStatus, Business, TaskRun } from '../api/client'

function statusBadge(ok: boolean) {
  return ok
    ? <span className="badge badge-green">Online</span>
    : <span className="badge badge-red">Offline</span>
}

function runStatusBadge(status: string) {
  switch (status) {
    case 'success': return <span className="badge badge-green">{status}</span>
    case 'failed': case 'error': return <span className="badge badge-red">{status}</span>
    case 'running': return <span className="badge badge-blue">{status}</span>
    default: return <span className="badge badge-dim">{status}</span>
  }
}

export default function Dashboard() {
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [businesses, setBusinesses] = useState<Business[]>([])
  const [pendingCount, setPendingCount] = useState(0)
  const [runs, setRuns] = useState<TaskRun[]>([])

  useEffect(() => {
    getStatus().then(setStatus).catch(() => {})
    getBusinesses().then(d => setBusinesses(d.businesses)).catch(() => {})
    getApprovals('pending').then(d => setPendingCount(d.approvals.length)).catch(() => {})
    getRecentRuns(10).then(d => setRuns(d.runs)).catch(() => {})
  }, [])

  return (
    <>
      <h1>Mission Control</h1>

      <div className="card-grid">
        <div className="card">
          <h3>Ollama</h3>
          <div>{status ? statusBadge(status.ollama) : '...'}</div>
        </div>
        <div className="card">
          <h3>Businesses</h3>
          <div className="value">{businesses.length}</div>
        </div>
        <div className="card">
          <h3>Pending Approvals</h3>
          <div className="value">
            <Link to="/approvals">{pendingCount}</Link>
          </div>
        </div>
        <div className="card">
          <h3>Memory</h3>
          <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>
            {status?.counts.memory
              ? Object.entries(status.counts.memory).map(([k, v]) => (
                  <div key={k}>{k}: {v}</div>
                ))
              : '...'}
          </div>
        </div>
      </div>

      {businesses.length > 0 && (
        <>
          <h2 style={{ fontSize: 18, marginBottom: 12 }}>Businesses</h2>
          <div className="card-grid" style={{ marginBottom: 24 }}>
            {businesses.map(b => (
              <div className="card" key={b.id}>
                <h3>{b.type}</h3>
                <div style={{ fontSize: 16, fontWeight: 600 }}>{b.name}</div>
                <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 4 }}>
                  Autonomy: Level {b.autonomy_level}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      <h2 style={{ fontSize: 18, marginBottom: 12 }}>Recent Task Runs</h2>
      {runs.length === 0 ? (
        <div className="empty">No task runs yet</div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <table>
            <thead>
              <tr>
                <th>Task</th>
                <th>Type</th>
                <th>Status</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {runs.map(r => (
                <tr key={r.id}>
                  <td>{r.task_name ?? `Task #${r.task_id}`}</td>
                  <td>{r.task_type ?? '-'}</td>
                  <td>{runStatusBadge(r.status)}</td>
                  <td style={{ color: 'var(--text-dim)', fontSize: 12 }}>{r.started_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
