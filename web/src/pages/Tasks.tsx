import { useEffect, useState } from 'react'
import { Pause, Play } from 'lucide-react'
import { getTasks, updateTask, getTask as fetchTask } from '../api/client'
import type { Task, TaskRun } from '../api/client'
import { useToast } from '../context/ToastContext'

function statusBadge(s: string) {
  switch (s) {
    case 'pending': return <span className="badge badge-blue">{s}</span>
    case 'paused': return <span className="badge badge-yellow">{s}</span>
    case 'running': return <span className="badge badge-green">{s}</span>
    default: return <span className="badge badge-dim">{s}</span>
  }
}

export default function Tasks() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<number | null>(null)
  const [runs, setRuns] = useState<TaskRun[]>([])
  const { showToast } = useToast()

  const load = () => {
    setLoading(true)
    getTasks()
      .then(d => setTasks(d.tasks))
      .catch(err => showToast(err.message || 'An error occurred', 'error'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  async function toggle(task: Task) {
    const newStatus = task.status === 'paused' ? 'pending' : 'paused'
    try {
      await updateTask(task.id, { status: newStatus })
      load()
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to update task', 'error')
    }
  }

  async function expand(id: number) {
    if (expanded === id) { setExpanded(null); return }
    setExpanded(id)
    try {
      const data = await fetchTask(id)
      setRuns(data.runs)
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to load task runs', 'error')
    }
  }

  if (loading) {
    return (
      <>
        <h1>Tasks</h1>
        <div className="empty">Loading...</div>
      </>
    )
  }

  return (
    <>
      <h1>Tasks</h1>
      {tasks.length === 0 ? (
        <div className="empty">No tasks configured</div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Schedule</th>
                <th>Status</th>
                <th>Last Run</th>
                <th>Next Run</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {tasks.map(t => (
                <>
                  <tr
                    key={t.id}
                    onClick={() => expand(t.id)}
                    onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); expand(t.id) } }}
                    tabIndex={0}
                    role="button"
                    style={{ cursor: 'pointer' }}
                  >
                    <td style={{ fontWeight: 500 }}>{t.name}</td>
                    <td>{t.task_type}</td>
                    <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{t.schedule ?? '-'}</td>
                    <td>{statusBadge(t.status)}</td>
                    <td style={{ fontSize: 12, color: 'var(--text-dim)' }}>{t.last_run ?? '-'}</td>
                    <td style={{ fontSize: 12, color: 'var(--text-dim)' }}>{t.next_run ?? '-'}</td>
                    <td>
                      <button
                        className={`btn ${t.status === 'paused' ? 'btn-green' : 'btn-dim'}`}
                        onClick={e => { e.stopPropagation(); toggle(t) }}
                        title={t.status === 'paused' ? 'Resume' : 'Pause'}
                      >
                        {t.status === 'paused' ? <Play size={14} /> : <Pause size={14} />}
                      </button>
                    </td>
                  </tr>
                  {expanded === t.id && (
                    <tr key={`${t.id}-runs`}>
                      <td colSpan={7} style={{ background: 'var(--bg)', padding: 16 }}>
                        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
                          Recent Runs
                        </div>
                        {runs.length === 0 ? (
                          <div style={{ color: 'var(--text-dim)', fontSize: 13 }}>No runs yet</div>
                        ) : (
                          <table>
                            <thead>
                              <tr><th>Started</th><th>Finished</th><th>Status</th></tr>
                            </thead>
                            <tbody>
                              {runs.slice(0, 5).map(r => (
                                <tr key={r.id}>
                                  <td style={{ fontSize: 12 }}>{r.started_at}</td>
                                  <td style={{ fontSize: 12 }}>{r.finished_at ?? '-'}</td>
                                  <td>
                                    <span className={`badge ${r.status === 'success' ? 'badge-green' : r.status === 'failed' ? 'badge-red' : 'badge-dim'}`}>
                                      {r.status}
                                    </span>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
