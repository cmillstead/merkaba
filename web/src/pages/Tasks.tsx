import { useEffect, useState } from 'react'
import { Pause, Play } from 'lucide-react'
import { getTasks, updateTask, getTask as fetchTask } from '../api/client'
import type { Task, TaskRun } from '../api/client'

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
  const [expanded, setExpanded] = useState<number | null>(null)
  const [runs, setRuns] = useState<TaskRun[]>([])

  const load = () => getTasks().then(d => setTasks(d.tasks)).catch(() => {})

  useEffect(() => { load() }, [])

  async function toggle(task: Task) {
    const newStatus = task.status === 'paused' ? 'pending' : 'paused'
    await updateTask(task.id, { status: newStatus })
    load()
  }

  async function expand(id: number) {
    if (expanded === id) { setExpanded(null); return }
    setExpanded(id)
    const data = await fetchTask(id)
    setRuns(data.runs)
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
                  <tr key={t.id} onClick={() => expand(t.id)} style={{ cursor: 'pointer' }}>
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
