import type { SystemState } from '../hooks/useControlSocket'

interface Props {
  system: SystemState
  connected: boolean
}

export default function HudStatusBar({ system, connected }: Props) {
  return (
    <div className="hud-status-bar" role="status" aria-live="polite">
      <div className="hud-item">
        <span className="hud-label">SYS</span>
        <span className={`hud-value ${connected ? 'hud-online' : 'hud-offline'}`}>
          {connected ? 'ONLINE' : 'OFFLINE'}
        </span>
      </div>
      <div className="hud-item">
        <span className="hud-label">MEM</span>
        <span className="hud-value">{system.memory_facts}</span>
      </div>
      <div className="hud-item">
        <span className="hud-label">TASKS</span>
        <span className="hud-value">{system.active_tasks}</span>
      </div>
      <div className="hud-item">
        <span className="hud-label">APPROVALS</span>
        <span className={`hud-value ${system.pending_approvals > 0 ? 'hud-warning' : ''}`}>
          {system.pending_approvals}
        </span>
      </div>
    </div>
  )
}
