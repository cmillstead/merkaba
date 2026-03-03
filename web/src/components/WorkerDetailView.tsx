import { useCallback, useState } from 'react'
import type { WorkerState, WorkerRun } from '../hooks/useControlSocket'

interface Props {
  worker: WorkerState
  onBack: () => void
}

function formatTimestamp(ts: string | null): string {
  if (!ts) return 'Never'
  try {
    const d = new Date(ts)
    return d.toLocaleString()
  } catch {
    return ts
  }
}

function runDotColor(status: string): string {
  if (status === 'completed' || status === 'success') return '#4ade80'
  if (status === 'failed' || status === 'error') return '#f87171'
  if (status === 'running') return '#00f0ff'
  return '#3a3a5c'
}

function isRunning(status: string): boolean {
  return status === 'running'
}

function runDotLabel(run: WorkerRun): string {
  const start = formatTimestamp(run.started_at)
  const end = run.finished_at ? formatTimestamp(run.finished_at) : 'running'
  return `${run.status} | ${start} - ${end}`
}

export default function WorkerDetailView({ worker, onBack }: Props) {
  const [triggerState, setTriggerState] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')
  const [triggerMessage, setTriggerMessage] = useState('')

  const handleRunNow = useCallback(async () => {
    setTriggerState('loading')
    setTriggerMessage('')
    try {
      const res = await fetch(`/api/control/worker/${worker.id}/trigger`, {
        method: 'POST',
      })
      if (res.ok) {
        setTriggerState('success')
        setTriggerMessage('Triggered successfully')
      } else {
        const text = await res.text()
        setTriggerState('error')
        setTriggerMessage(text || `Error ${res.status}`)
      }
    } catch (err) {
      setTriggerState('error')
      setTriggerMessage(err instanceof Error ? err.message : 'Network error')
    }
    // Reset after 3 seconds
    setTimeout(() => {
      setTriggerState('idle')
      setTriggerMessage('')
    }, 3000)
  }, [worker.id])

  const recentRuns = worker.run_history.slice(-5)

  return (
    <div className="worker-detail-view">
      <button className="btn btn-dim harness-back" onClick={onBack}>
        ← Back
      </button>

      <div className="worker-detail-content">
        <h2 className="worker-detail-name">{worker.name}</h2>
        <p className="worker-detail-description">
          {worker.description || 'No description available.'}
        </p>

        <div className="worker-detail-section">
          <h3 className="worker-detail-heading">Schedule</h3>
          <div className="worker-detail-fields">
            <dt>Cron</dt>
            <dd>{worker.schedule || 'Not scheduled'}</dd>
            <dt>Last Run</dt>
            <dd>{formatTimestamp(worker.last_run)}</dd>
            <dt>Next Run</dt>
            <dd>{worker.next_run ? formatTimestamp(worker.next_run) : 'Not scheduled'}</dd>
            <dt>Status</dt>
            <dd>
              <span
                className="worker-detail-status-dot"
                style={{
                  background:
                    worker.status === 'active' ? '#00f0ff' :
                    worker.status === 'idle' ? '#4ade80' :
                    '#3a3a5c',
                }}
              />
              {worker.status}
            </dd>
          </div>
        </div>

        <div className="worker-detail-section">
          <h3 className="worker-detail-heading">Run History</h3>
          {recentRuns.length === 0 ? (
            <p className="worker-detail-empty">No runs recorded.</p>
          ) : (
            <div className="worker-detail-timeline">
              {recentRuns.map((run) => (
                <span
                  key={run.id}
                  className={`worker-detail-run-dot${isRunning(run.status) ? ' run-dot-running' : ''}`}
                  title={runDotLabel(run)}
                  style={{ background: runDotColor(run.status) }}
                />
              ))}
            </div>
          )}
        </div>

        <div className="worker-detail-actions">
          <button
            className="btn worker-detail-trigger-btn"
            onClick={handleRunNow}
            disabled={triggerState === 'loading'}
          >
            {triggerState === 'loading' ? 'Triggering...' : 'Run Now'}
          </button>
          {triggerMessage && (
            <span
              className="worker-detail-trigger-feedback"
              style={{
                color: triggerState === 'success' ? '#4ade80' : '#f87171',
              }}
            >
              {triggerMessage}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
