import { useCallback, useEffect, useRef, useState } from 'react'
import MerkabaGlyph from './MerkabaGlyph'
import type { AgentState, SystemState, KanbanCard } from '../hooks/useControlSocket'
import { getModels } from '../api/client'

interface Props {
  agent: AgentState
  system: SystemState
  pendingApprovals: KanbanCard[]
  onBack: () => void
  onModelChange: (model: string) => void
}

// Fallback model list used when /api/system/models is unavailable
const FALLBACK_MODELS = ['qwen3.5:122b', 'qwen3:8b', 'qwen3:4b']

function formatTimestamp(ts: string): string {
  try {
    const d = new Date(ts)
    return d.toLocaleString()
  } catch {
    return ts
  }
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text
  return text.slice(0, max - 1) + '\u2026'
}

export default function AgentDetailView({ agent, system, pendingApprovals, onBack, onModelChange }: Props) {
  const [availableModels, setAvailableModels] = useState<string[]>(FALLBACK_MODELS)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [approvalStates, setApprovalStates] = useState<Record<number, 'loading' | 'approved' | 'denied' | 'error'>>({})
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Load available models from the API on mount
  useEffect(() => {
    getModels()
      .then(data => {
        const names = data.models.map(m => m.name)
        if (names.length > 0) setAvailableModels(names)
      })
      .catch(() => {
        // API unavailable -- keep hardcoded fallback list
      })
  }, [])

  // Close dropdown when clicking outside
  useEffect(() => {
    if (!dropdownOpen) return
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [dropdownOpen])

  const handleSelectModel = useCallback((model: string) => {
    onModelChange(model)
    setDropdownOpen(false)
  }, [onModelChange])

  const handleApprove = useCallback(async (id: number) => {
    setApprovalStates(prev => ({ ...prev, [id]: 'loading' }))
    try {
      const res = await fetch(`/api/approvals/${id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decided_by: 'mission-control' }),
      })
      if (res.ok) {
        setApprovalStates(prev => ({ ...prev, [id]: 'approved' }))
      } else {
        setApprovalStates(prev => ({ ...prev, [id]: 'error' }))
      }
    } catch {
      setApprovalStates(prev => ({ ...prev, [id]: 'error' }))
    }
  }, [])

  const handleDeny = useCallback(async (id: number) => {
    setApprovalStates(prev => ({ ...prev, [id]: 'loading' }))
    try {
      const res = await fetch(`/api/approvals/${id}/deny`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decided_by: 'mission-control' }),
      })
      if (res.ok) {
        setApprovalStates(prev => ({ ...prev, [id]: 'denied' }))
      } else {
        setApprovalStates(prev => ({ ...prev, [id]: 'error' }))
      }
    } catch {
      setApprovalStates(prev => ({ ...prev, [id]: 'error' }))
    }
  }, [])

  // Determine orb speed based on agent activity
  const orbSpeed = agent.current_task ? 2 : agent.active_skill ? 1.5 : 0.7

  // Ensure current model is in the list for display purposes
  const allModels = availableModels.includes(agent.model)
    ? availableModels
    : [agent.model, ...availableModels]

  const recentActivity = agent.recent_activity?.slice(-5) ?? []

  return (
    <div className="agent-detail-view">
      <button className="btn btn-dim harness-back" onClick={onBack}>
        &larr; Back
      </button>

      <div className="agent-detail-orb">
        <MerkabaGlyph size={120} status="active" speed={orbSpeed} />
      </div>

      <h2 className="agent-detail-name">{agent.name}</h2>

      <div className="agent-detail-grid">
        {/* Current Activity */}
        <div className="agent-detail-panel">
          <h3 className="agent-detail-panel-heading">Current Activity</h3>
          <p className="agent-detail-panel-text">
            {agent.current_task
              ? agent.current_task
              : agent.active_skill
                ? `Using skill: ${agent.active_skill}`
                : 'Idle'}
          </p>
        </div>

        {/* Model Selector */}
        <div className="agent-detail-panel">
          <h3 className="agent-detail-panel-heading">Model</h3>
          <div className="agent-detail-model-wrapper" ref={dropdownRef}>
            <button
              className="agent-detail-model-btn"
              onClick={() => setDropdownOpen(prev => !prev)}
              aria-haspopup="listbox"
              aria-expanded={dropdownOpen}
            >
              <span>{agent.model}</span>
              <span className="agent-detail-model-arrow">{dropdownOpen ? '\u25B2' : '\u25BC'}</span>
            </button>
            {dropdownOpen && (
              <ul className="agent-detail-model-dropdown" role="listbox">
                {allModels.map(name => (
                  <li
                    key={name}
                    role="option"
                    aria-selected={name === agent.model}
                    className={`agent-detail-model-option ${name === agent.model ? 'agent-detail-model-option--active' : ''}`}
                    onClick={() => handleSelectModel(name)}
                  >
                    {name}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* Recent Activity */}
        <div className="agent-detail-panel">
          <h3 className="agent-detail-panel-heading">Recent Activity</h3>
          {recentActivity.length === 0 ? (
            <p className="agent-detail-panel-empty">No recent activity</p>
          ) : (
            <ul className="agent-detail-activity-list">
              {recentActivity.map(activity => (
                <li key={activity.session_id} className="agent-detail-activity-item">
                  <span className="agent-detail-activity-preview">
                    {truncate(activity.preview, 60)}
                  </span>
                  <span className="agent-detail-activity-time">
                    {formatTimestamp(activity.timestamp)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Memory Stats */}
        <div className="agent-detail-panel">
          <h3 className="agent-detail-panel-heading">Memory</h3>
          <div className="agent-detail-stats">
            <div className="agent-detail-stat">
              <span className="agent-detail-stat-label">Facts</span>
              <span className="agent-detail-stat-value">{system.memory_facts}</span>
            </div>
            <div className="agent-detail-stat">
              <span className="agent-detail-stat-label">Archived</span>
              <span className="agent-detail-stat-value">{system.memory_archived}</span>
            </div>
          </div>
        </div>

        {/* Pending Approvals */}
        <div className="agent-detail-panel agent-detail-panel--wide">
          <h3 className="agent-detail-panel-heading">Pending Approvals</h3>
          {pendingApprovals.length === 0 ? (
            <p className="agent-detail-panel-empty">No pending approvals</p>
          ) : (
            <div className="agent-detail-approvals">
              {pendingApprovals.map(approval => {
                const state = approvalStates[approval.id]
                return (
                  <div key={approval.id} className="agent-detail-approval-card">
                    <div className="agent-detail-approval-info">
                      <span className="agent-detail-approval-desc">
                        {approval.description || `Action #${approval.id}`}
                      </span>
                      {approval.action_type && (
                        <span className="badge badge-blue">{approval.action_type}</span>
                      )}
                    </div>
                    <div className="agent-detail-approval-actions">
                      {state === 'approved' ? (
                        <span className="agent-detail-approval-status" style={{ color: '#4ade80' }}>Approved</span>
                      ) : state === 'denied' ? (
                        <span className="agent-detail-approval-status" style={{ color: '#f87171' }}>Denied</span>
                      ) : state === 'error' ? (
                        <span className="agent-detail-approval-status" style={{ color: '#f87171' }}>Error</span>
                      ) : (
                        <>
                          <button
                            className="agent-detail-approve-btn"
                            onClick={() => handleApprove(approval.id)}
                            disabled={state === 'loading'}
                          >
                            {state === 'loading' ? '...' : 'Approve'}
                          </button>
                          <button
                            className="agent-detail-reject-btn"
                            onClick={() => handleDeny(approval.id)}
                            disabled={state === 'loading'}
                          >
                            {state === 'loading' ? '...' : 'Reject'}
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
