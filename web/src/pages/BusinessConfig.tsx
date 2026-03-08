import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getBusinessConfig, updateBusinessConfig } from '../api/client'
import type { BusinessConfig as BusinessConfigType } from '../api/client'
import { ArrowLeft, Save, FileText, Plug } from 'lucide-react'
import { useToast } from '../context/ToastContext'

type Tab = 'prompt' | 'adapters'

export default function BusinessConfig() {
  const { id } = useParams<{ id: string }>()
  const businessId = Number(id)
  const [config, setConfig] = useState<BusinessConfigType | null>(null)
  const [soul, setSoul] = useState('')
  const [user, setUser] = useState('')
  const [activeTab, setActiveTab] = useState<Tab>('prompt')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const { showToast } = useToast()

  useEffect(() => {
    getBusinessConfig(businessId).then(c => {
      setConfig(c)
      setSoul(c.soul)
      setUser(c.user)
    }).catch(err => showToast(err.message || 'Failed to load config', 'error'))
  }, [businessId])

  const handleSave = async () => {
    setSaving(true)
    setMessage(null)
    try {
      const updated = await updateBusinessConfig(businessId, { soul, user })
      setConfig(updated)
      setMessage({ type: 'success', text: 'Config saved' })
    } catch {
      setMessage({ type: 'error', text: 'Failed to save' })
    } finally {
      setSaving(false)
    }
  }

  const sourceBadge = (source: string) => {
    switch (source) {
      case 'business': return <span className="badge badge-green">business</span>
      case 'global': return <span className="badge badge-blue">global</span>
      default: return <span className="badge badge-dim">builtin</span>
    }
  }

  if (!config) return <div className="empty">Loading...</div>

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <Link to="/" style={{ color: 'var(--text-dim)' }}><ArrowLeft size={18} /></Link>
        <h1 style={{ margin: 0 }}>Business {businessId} Config</h1>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        <button
          className={activeTab === 'prompt' ? 'btn btn-primary' : 'btn btn-dim'}
          onClick={() => setActiveTab('prompt')}
        >
          <FileText size={14} /> Prompt Files
        </button>
        <button
          className={activeTab === 'adapters' ? 'btn btn-primary' : 'btn btn-dim'}
          onClick={() => setActiveTab('adapters')}
        >
          <Plug size={14} /> Adapters
        </button>
      </div>

      {activeTab === 'prompt' && (
        <div>
          <div className="card" style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <h3>SOUL.md</h3>
              {sourceBadge(config.soul_source)}
            </div>
            <textarea
              value={soul}
              onChange={e => setSoul(e.target.value)}
              rows={10}
              style={{ minHeight: 200, resize: 'vertical' }}
            />
          </div>

          <div className="card" style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <h3>USER.md</h3>
              {sourceBadge(config.user_source)}
            </div>
            <textarea
              value={user}
              onChange={e => setUser(e.target.value)}
              rows={6}
              style={{ minHeight: 120, resize: 'vertical' }}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
              <Save size={14} /> {saving ? 'Saving...' : 'Save'}
            </button>
            {message && (
              <span style={{ fontSize: 13, color: message.type === 'success' ? 'var(--green)' : 'var(--red)' }}>
                {message.text}
              </span>
            )}
          </div>
        </div>
      )}

      {activeTab === 'adapters' && (
        <div className="card">
          <h3>Connected Adapters</h3>
          <div style={{ color: 'var(--text-dim)', fontSize: 13, marginTop: 8 }}>
            Adapter health monitoring coming soon. Configure adapters via CLI:
            <code style={{ display: 'block', marginTop: 8, padding: 8, background: 'var(--bg)', borderRadius: 'var(--radius)', fontSize: 12 }}>
              merkaba integrations connect slack
            </code>
          </div>
        </div>
      )}
    </>
  )
}
