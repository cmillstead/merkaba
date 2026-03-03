import React, { useMemo } from 'react'
import type { ControlState } from '../hooks/useControlSocket'

interface Props {
  state: ControlState
  connected: boolean
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
}

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'active': return 'badge badge-green'
    case 'idle': return 'badge badge-dim'
    case 'error': return 'badge badge-red'
    default: return 'badge badge-dim'
  }
}

function DashboardView({ state, connected }: Props) {
  const activeAgents = state.agents.filter(a => a.status === 'active')

  const recentActivity = useMemo(() => {
    const entries: { workerName: string; run: { started_at: string; status: string } }[] = []
    for (const w of state.workers) {
      for (const run of w.run_history) {
        entries.push({ workerName: w.name, run: { started_at: run.started_at, status: run.status } })
      }
    }
    entries.sort((a, b) => b.run.started_at.localeCompare(a.run.started_at))
    return entries.slice(0, 20)
  }, [state.workers])

  return (
    <div className="dashboard-view" role="region" aria-label="Dashboard overview">
      <div className="dashboard-kpis" role="list" aria-label="Key metrics">
        <div className="kpi-card" role="listitem">
          <div className="kpi-value" aria-label="Active tasks count">{state.system.active_tasks}</div>
          <div className="kpi-label">Active Tasks</div>
        </div>
        <div className="kpi-card" role="listitem">
          <div className="kpi-value" aria-label="Agents online count">{activeAgents.length}</div>
          <div className="kpi-label">Agents Online</div>
        </div>
        <div className="kpi-card" role="listitem">
          <div className={`kpi-value${state.system.pending_approvals > 0 ? ' kpi-attention' : ''}`} aria-label="Pending approvals count">
            {state.system.pending_approvals}
          </div>
          <div className="kpi-label">Pending Approvals</div>
        </div>
        <div className="kpi-card" role="listitem">
          <div className={`kpi-value ${connected ? 'dot-green' : 'dot-red'}`} style={{ fontSize: 28 }} aria-label={`Connection status: ${connected ? 'connected' : 'disconnected'}`}>
            {connected ? 'Online' : 'Offline'}
          </div>
          <div className="kpi-label">Connection</div>
        </div>
      </div>

      <div className="dashboard-panels">
        <div className="dashboard-panel" role="region" aria-label="Active agents">
          <h3>Active Agents</h3>
          {state.agents.length === 0 ? (
            <div className="empty-state">No agents registered</div>
          ) : (
            state.agents.map(agent => (
              <div className="agent-row" key={agent.id}>
                <div className="agent-row-name">{agent.name}</div>
                <div className="agent-row-meta">
                  <span className="badge badge-blue">{agent.role}</span>
                  <span className="badge badge-dim">{agent.model}</span>
                  <span className={statusBadgeClass(agent.status)}>{agent.status}</span>
                </div>
                {agent.current_task && (
                  <div className="agent-row-task">{agent.current_task}</div>
                )}
              </div>
            ))
          )}
        </div>

        <div className="dashboard-panel" role="region" aria-label="Recent activity">
          <h3>Recent Activity</h3>
          {recentActivity.length === 0 ? (
            <div className="empty-state">No recent worker activity</div>
          ) : (
            recentActivity.map((entry, i) => (
              <div className="activity-row" key={`${entry.workerName}-${entry.run.started_at}-${i}`}>
                <span
                  className={`activity-dot ${entry.run.status === 'success' ? 'dot-green' : entry.run.status === 'failed' ? 'dot-red' : 'dot-yellow'}`}
                  aria-label={entry.run.status}
                />
                <span className="activity-name">{entry.workerName}</span>
                <span className="activity-time">{formatTime(entry.run.started_at)}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

export default React.memo(DashboardView)
