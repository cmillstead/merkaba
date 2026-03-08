import { useCallback, useEffect, useState } from 'react'
import { Check, X } from 'lucide-react'
import { getApprovals, approveAction, denyAction } from '../api/client'
import type { Approval } from '../api/client'
import { useToast } from '../context/ToastContext'
import ApprovalConfirmDialog from '../components/ApprovalConfirmDialog'
import type { ApprovalAction } from '../components/ApprovalConfirmDialog'

interface ConfirmAction {
  id: number
  type: ApprovalAction
  description: string
}

export default function Approvals() {
  const [tab, setTab] = useState<'pending' | 'all'>('pending')
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [loading, setLoading] = useState(true)
  const [confirmAction, setConfirmAction] = useState<ConfirmAction | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const { showToast } = useToast()

  const load = useCallback(() => {
    setLoading(true)
    const status = tab === 'pending' ? 'pending' : undefined
    getApprovals(status)
      .then(d => setApprovals(d.approvals))
      .catch(err => showToast(err.message || 'An error occurred', 'error'))
      .finally(() => setLoading(false))
  }, [tab, showToast])

  useEffect(() => { load() }, [load])

  function openConfirm(id: number, type: ApprovalAction, description: string) {
    setConfirmAction({ id, type, description })
  }

  const cancelConfirm = useCallback(() => {
    if (!submitting) setConfirmAction(null)
  }, [submitting])

  const handleConfirm = useCallback(async (totp?: string) => {
    if (!confirmAction) return
    setSubmitting(true)
    try {
      if (confirmAction.type === 'approve') {
        await approveAction(confirmAction.id, totp)
        showToast('Action approved', 'success')
      } else if (confirmAction.type === 'reject') {
        await denyAction(confirmAction.id)
        showToast('Action rejected', 'success')
      }
      setConfirmAction(null)
      load()
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'An error occurred'
      showToast(message, 'error')
    } finally {
      setSubmitting(false)
    }
  }, [confirmAction, showToast, load])

  function decisionBadge(status: string) {
    switch (status) {
      case 'pending': return <span className="badge badge-yellow">{status}</span>
      case 'approved': return <span className="badge badge-green">{status}</span>
      case 'denied': return <span className="badge badge-red">{status}</span>
      case 'executed': return <span className="badge badge-blue">{status}</span>
      default: return <span className="badge badge-dim">{status}</span>
    }
  }

  return (
    <>
      <h1>Approvals</h1>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <button
          className={`btn ${tab === 'pending' ? 'btn-primary' : 'btn-dim'}`}
          onClick={() => setTab('pending')}
        >
          Pending
        </button>
        <button
          className={`btn ${tab === 'all' ? 'btn-primary' : 'btn-dim'}`}
          onClick={() => setTab('all')}
        >
          All
        </button>
      </div>

      <ApprovalConfirmDialog
        open={confirmAction !== null}
        submitting={submitting}
        action={confirmAction?.type ?? 'approve'}
        itemDescription={confirmAction?.description ?? ''}
        requireTotp={confirmAction?.type === 'approve'}
        onConfirm={handleConfirm}
        onCancel={cancelConfirm}
      />

      {loading ? (
        <div className="empty">Loading...</div>
      ) : approvals.length === 0 ? (
        <div className="empty">
          {tab === 'pending' ? 'No pending approvals' : 'No approvals yet'}
        </div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <table>
            <thead>
              <tr>
                <th>Action</th>
                <th>Description</th>
                <th>Level</th>
                <th>Status</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {approvals.map(a => (
                <tr key={a.id}>
                  <td style={{ fontWeight: 500 }}>{a.action_type}</td>
                  <td>{a.description}</td>
                  <td>{a.autonomy_level}</td>
                  <td>{decisionBadge(a.status)}</td>
                  <td style={{ fontSize: 12, color: 'var(--text-dim)' }}>{a.created_at}</td>
                  <td>
                    {a.status === 'pending' && (
                      <div style={{ display: 'flex', gap: 4 }}>
                        <button
                          className="btn btn-green"
                          onClick={() => openConfirm(a.id, 'approve', a.description)}
                          disabled={submitting}
                          title="Approve"
                        >
                          <Check size={14} />
                        </button>
                        <button
                          className="btn btn-red"
                          onClick={() => openConfirm(a.id, 'reject', a.description)}
                          disabled={submitting}
                          title="Deny"
                        >
                          <X size={14} />
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
