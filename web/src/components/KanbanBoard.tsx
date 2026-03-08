import { useEffect, useState, useCallback } from 'react'
import type { KanbanState, KanbanCard } from '../hooks/useControlSocket'
import { approveAction, denyAction } from '../api/client'
import { useToast } from '../context/ToastContext'
import ApprovalConfirmDialog from './ApprovalConfirmDialog'
import type { ApprovalAction } from './ApprovalConfirmDialog'

interface Props {
  kanban: KanbanState | null
  onSubscribe: () => void
  onUnsubscribe: () => void
}

interface PendingConfirm {
  cardId: number
  action: ApprovalAction
  description: string
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
  decidedIds,
  onRequestApproval,
}: {
  card: KanbanCard
  columnKey: keyof KanbanState
  decidedIds: Set<number>
  onRequestApproval: (cardId: number, action: ApprovalAction, description: string) => void
}) {
  const [expanded, setExpanded] = useState(false)

  const handleApprove = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    onRequestApproval(card.id, 'approve', card.description || card.name || `Action #${card.id}`)
  }, [card.id, card.description, card.name, onRequestApproval])

  const handleReject = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    onRequestApproval(card.id, 'reject', card.description || card.name || `Action #${card.id}`)
  }, [card.id, card.description, card.name, onRequestApproval])

  const isApproval = columnKey === 'awaiting_approval'
  const isRun = columnKey === 'completed' || columnKey === 'failed'
  const isDone = decidedIds.has(card.id)

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
      {isApproval && !isDone && (
        <div className="kanban-card-actions">
          <button
            className="kanban-approve-btn"
            onClick={handleApprove}
          >
            Approve
          </button>
          <button
            className="kanban-reject-btn"
            onClick={handleReject}
          >
            Reject
          </button>
        </div>
      )}
      {isApproval && isDone && (
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
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirm | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [decidedIds, setDecidedIds] = useState<Set<number>>(new Set())
  const { showToast } = useToast()

  useEffect(() => {
    onSubscribe()
    return () => { onUnsubscribe() }
  }, [onSubscribe, onUnsubscribe])

  const handleRequestApproval = useCallback((cardId: number, action: ApprovalAction, description: string) => {
    setPendingConfirm({ cardId, action, description })
  }, [])

  const handleConfirm = useCallback(async (totp?: string) => {
    if (!pendingConfirm) return
    setSubmitting(true)
    try {
      if (pendingConfirm.action === 'approve') {
        await approveAction(pendingConfirm.cardId, totp)
        showToast('Action approved', 'success')
      } else {
        await denyAction(pendingConfirm.cardId)
        showToast('Action rejected', 'success')
      }
      setDecidedIds(prev => new Set(prev).add(pendingConfirm.cardId))
      setPendingConfirm(null)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'An error occurred'
      showToast(message, 'error')
    } finally {
      setSubmitting(false)
    }
  }, [pendingConfirm, showToast])

  const handleCancel = useCallback(() => {
    if (!submitting) setPendingConfirm(null)
  }, [submitting])

  if (!kanban) {
    return (
      <div className="kanban-board kanban-board--loading">
        <div className="kanban-loading">Loading kanban data...</div>
      </div>
    )
  }

  return (
    <>
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
                    <CardComponent
                      key={`${key}-${card.id}`}
                      card={card}
                      columnKey={key}
                      decidedIds={decidedIds}
                      onRequestApproval={handleRequestApproval}
                    />
                  ))
                )}
              </div>
            </div>
          )
        })}
      </div>
      <ApprovalConfirmDialog
        open={pendingConfirm !== null}
        submitting={submitting}
        action={pendingConfirm?.action ?? 'approve'}
        itemDescription={pendingConfirm?.description ?? ''}
        requireTotp={pendingConfirm?.action === 'approve'}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
    </>
  )
}
