import { useEffect, useState } from 'react'
import { Check, X } from 'lucide-react'
import { getApprovals, approveAction, denyAction } from '../api/client'
import type { Approval } from '../api/client'
import { useToast } from '../context/ToastContext'

export default function Approvals() {
  const [tab, setTab] = useState<'pending' | 'all'>('pending')
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [loading, setLoading] = useState(true)
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

  async function approve(id: number) {
    await approveAction(id)
    load()
  }

  async function deny(id: number) {
    await denyAction(id)
    load()
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
                        <button className="btn btn-green" onClick={() => approve(a.id)}>
                          <Check size={14} />
                        </button>
                        <button className="btn btn-red" onClick={() => deny(a.id)}>
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
