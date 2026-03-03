import { useEffect, useState, useCallback } from 'react'
import type { KanbanState, KanbanCard } from '../hooks/useControlSocket'

interface Props {
  kanban: KanbanState | null
  onSubscribe: () => void
  onUnsubscribe: () => void
}

const COLUMNS: { key: keyof KanbanState; label: string }[] = [
  { key: 'queued', label: 'Queued' },
  { key: 'awaiting_approval', label: 'Awaiting Approval' },
  { key: 'running', label: 'Running' },
  { key: 'completed', label: 'Completed' },
  { key: 'failed', label: 'Failed' },
]

function formatTimestamp(iso?: string): string {
  if (!iso) return '--'
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return iso
  }
}

function formatDate(iso?: string): string {
  if (!iso) return '--'
  try {
    const d = new Date(iso)
    return d.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    }) + ' ' + d.toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function computeDuration(startedAt?: string, finishedAt?: string): string {
  if (!startedAt || !finishedAt) return '--'
  try {
    const ms = new Date(finishedAt).getTime() - new Date(startedAt).getTime()
    if (ms < 1000) return `${ms}ms`
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
    return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`
  } catch {
    return '--'
  }
}

function CardComponent({
  card,
  columnKey,
}: {
  card: KanbanCard
  columnKey: keyof KanbanState
}) {
  const [expanded, setExpanded] = useState(false)
  const [actionState, setActionState] = useState<'idle' | 'approving' | 'rejecting' | 'done'>('idle')

  const handleApprove = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation()
    setActionState('approving')
    try {
      await fetch(`/api/approvals/${card.id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decided_by: 'mission-control' }),
      })
      setActionState('done')
    } catch {
      setActionState('idle')
    }
  }, [card.id])

  const handleReject = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation()
    setActionState('rejecting')
    try {
      await fetch(`/api/approvals/${card.id}/deny`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decided_by: 'mission-control' }),
      })
      setActionState('done')
    } catch {
      setActionState('idle')
    }
  }, [card.id])

  const isApproval = columnKey === 'awaiting_approval'
  const isRun = columnKey === 'completed' || columnKey === 'failed'

  return (
    <div
      className={`kanban-card${expanded ? ' kanban-card--expanded' : ''}`}
      onClick={() => setExpanded(prev => !prev)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          setExpanded(prev => !prev)
        }
      }}
    >
      {/* Card summary */}
      <div className="kanban-card-summary">
        <span className="kanban-card-name">
          {card.name || card.description || `#${card.id}`}
        </span>
        {card.task_type && (
          <span className="kanban-card-type">{card.task_type}</span>
        )}
        {card.action_type && (
          <span className="kanban-card-type">{card.action_type}</span>
        )}
      </div>

      {/* Timestamps */}
      {!isRun && card.created_at && (
        <div className="kanban-card-time">{formatTimestamp(card.created_at)}</div>
      )}
      {isRun && (
        <div className="kanban-card-time">
          {formatTimestamp(card.started_at)}
          {card.started_at && card.finished_at && (
            <span className="kanban-card-duration">
              {' '}{computeDuration(card.started_at, card.finished_at)}
            </span>
          )}
        </div>
      )}

      {/* Approval buttons */}
      {isApproval && actionState !== 'done' && (
        <div className="kanban-card-actions">
          <button
            className="kanban-approve-btn"
            onClick={handleApprove}
            disabled={actionState !== 'idle'}
          >
            {actionState === 'approving' ? '...' : 'Approve'}
          </button>
          <button
            className="kanban-reject-btn"
            onClick={handleReject}
            disabled={actionState !== 'idle'}
          >
            {actionState === 'rejecting' ? '...' : 'Reject'}
          </button>
        </div>
      )}
      {isApproval && actionState === 'done' && (
        <div className="kanban-card-decided">Decided</div>
      )}

      {/* Expanded details */}
      {expanded && (
        <div className="kanban-card-details">
          <div className="kanban-card-detail-row">
            <span className="kanban-card-detail-label">ID</span>
            <span>{card.id}</span>
          </div>
          {card.task_id != null && (
            <div className="kanban-card-detail-row">
              <span className="kanban-card-detail-label">Task ID</span>
              <span>{card.task_id}</span>
            </div>
          )}
          {card.name && (
            <div className="kanban-card-detail-row">
              <span className="kanban-card-detail-label">Name</span>
              <span>{card.name}</span>
            </div>
          )}
          {card.description && (
            <div className="kanban-card-detail-row">
              <span className="kanban-card-detail-label">Description</span>
              <span>{card.description}</span>
            </div>
          )}
          {card.status && (
            <div className="kanban-card-detail-row">
              <span className="kanban-card-detail-label">Status</span>
              <span>{card.status}</span>
            </div>
          )}
          {card.created_at && (
            <div className="kanban-card-detail-row">
              <span className="kanban-card-detail-label">Created</span>
              <span>{formatDate(card.created_at)}</span>
            </div>
          )}
          {card.started_at && (
            <div className="kanban-card-detail-row">
              <span className="kanban-card-detail-label">Started</span>
              <span>{formatDate(card.started_at)}</span>
            </div>
          )}
          {card.finished_at && (
            <div className="kanban-card-detail-row">
              <span className="kanban-card-detail-label">Finished</span>
              <span>{formatDate(card.finished_at)}</span>
            </div>
          )}
          {card.started_at && card.finished_at && (
            <div className="kanban-card-detail-row">
              <span className="kanban-card-detail-label">Duration</span>
              <span>{computeDuration(card.started_at, card.finished_at)}</span>
            </div>
          )}
          {card.error && (
            <div className="kanban-card-detail-row kanban-card-error">
              <span className="kanban-card-detail-label">Error</span>
              <span>{card.error}</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function KanbanBoard({ kanban, onSubscribe, onUnsubscribe }: Props) {
  useEffect(() => {
    onSubscribe()
    return () => { onUnsubscribe() }
  }, [onSubscribe, onUnsubscribe])

  if (!kanban) {
    return (
      <div className="kanban-board kanban-board--loading">
        <div className="kanban-loading">Loading kanban data...</div>
      </div>
    )
  }

  return (
    <div className="kanban-board">
      {COLUMNS.map(({ key, label }) => {
        const cards = kanban[key]
        return (
          <div key={key} className="kanban-column">
            <div className="kanban-column-header">
              <span>{label}</span>
              <span className="kanban-count-badge">{cards.length}</span>
            </div>
            <div className="kanban-column-body">
              {cards.length === 0 ? (
                <div className="kanban-empty">No items</div>
              ) : (
                cards.map(card => (
                  <CardComponent key={`${key}-${card.id}`} card={card} columnKey={key} />
                ))
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
