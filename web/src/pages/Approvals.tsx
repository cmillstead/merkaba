import { useEffect, useState } from 'react'
import { Check, X } from 'lucide-react'
import { getApprovals, approveAction, denyAction } from '../api/client'
import type { Approval } from '../api/client'
import { useToast } from '../context/ToastContext'

interface ConfirmAction {
  id: number
  type: 'approve' | 'deny'
  description: string
}

export default function Approvals() {
  const [tab, setTab] = useState<'pending' | 'all'>('pending')
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [loading, setLoading] = useState(true)
  const [confirmAction, setConfirmAction] = useState<ConfirmAction | null>(null)
  const [totpCode, setTotpCode] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const { showToast } = useToast()

  const load = () => {
    setLoading(true)
    const status = tab === 'pending' ? 'pending' : undefined
    getApprovals(status)
      .then(d => setApprovals(d.approvals))
      .catch(err => showToast(err.message || 'An error occurred', 'error'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [tab])

  function openConfirm(id: number, type: 'approve' | 'deny', description: string) {
    setConfirmAction({ id, type, description })
    setTotpCode('')
  }

  function cancelConfirm() {
    setConfirmAction(null)
    setTotpCode('')
  }

  async function handleConfirm() {
    if (!confirmAction) return
    setSubmitting(true)
    try {
      if (confirmAction.type === 'approve') {
        await approveAction(confirmAction.id, totpCode || undefined)
        showToast('Action approved', 'success')
      } else {
        await denyAction(confirmAction.id)
        showToast('Action denied', 'success')
      }
      setConfirmAction(null)
      setTotpCode('')
      load()
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'An error occurred'
      showToast(message, 'error')
    } finally {
      setSubmitting(false)
    }
  }

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

      {confirmAction && (
        <div className="card" style={{ marginBottom: 16, padding: 16, border: '1px solid var(--border)', background: 'var(--surface)' }}>
          <p style={{ marginBottom: 8, fontWeight: 500 }}>
            {confirmAction.type === 'approve' ? 'Approve' : 'Deny'} this action?
          </p>
          <p style={{ marginBottom: 12, color: 'var(--text-dim)', fontSize: 13 }}>
            {confirmAction.description}
          </p>
          {confirmAction.type === 'approve' && (
            <div style={{ marginBottom: 12 }}>
              <label style={{ display: 'block', fontSize: 12, color: 'var(--text-dim)', marginBottom: 4 }}>
                TOTP Code (optional — required if 2FA is enabled)
              </label>
              <input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="6-digit code"
                value={totpCode}
                onChange={e => setTotpCode(e.target.value)}
                style={{ width: 140, padding: '4px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg)', color: 'var(--text)', fontSize: 14 }}
              />
            </div>
          )}
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              className={`btn ${confirmAction.type === 'approve' ? 'btn-green' : 'btn-red'}`}
              onClick={handleConfirm}
              disabled={submitting}
            >
              {submitting ? 'Submitting...' : confirmAction.type === 'approve' ? 'Confirm Approve' : 'Confirm Deny'}
            </button>
            <button className="btn btn-dim" onClick={cancelConfirm} disabled={submitting}>
              Cancel
            </button>
          </div>
        </div>
      )}

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
                          onClick={() => openConfirm(a.id, 'deny', a.description)}
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
