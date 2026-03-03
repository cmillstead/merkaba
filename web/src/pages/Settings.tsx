import { useEffect, useState } from 'react'
import {
  getConfig,
  updateConfig,
  getModels,
  getStatus,
  type OllamaModel,
  type SystemStatus,
} from '../api/client'
import { useToast } from '../context/ToastContext'

const DEFAULT_SCHEDULES: Record<string, { cron: string; description: string }> = {
  health_check: { cron: '0 */6 * * *', description: 'Every 6 hours' },
  memory_decay: { cron: '0 3 * * *', description: 'Daily at 3 AM' },
  memory_consolidate: { cron: '0 4 * * 0', description: 'Sundays at 4 AM' },
}

function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return 'N/A'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

export default function Settings() {
  const { showToast } = useToast()
  const [config, setConfig] = useState<Record<string, unknown>>({})
  const [models, setModels] = useState<OllamaModel[]>([])
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    Promise.all([getConfig(), getModels(), getStatus()])
      .then(([cfg, mdl, sts]) => {
        setConfig(cfg)
        setModels(mdl.models || [])
        setStatus(sts)
      })
      .catch(() => showToast('Failed to load settings', 'error'))
      .finally(() => setLoading(false))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const modelsConfig = (config.models ?? {}) as Record<string, string>
  const schedulesConfig = (config.schedules ?? {}) as Record<string, string>

  const modelNames = models.map((m) => m.name)

  function setModel(key: string, value: string) {
    setConfig((prev) => ({
      ...prev,
      models: { ...(prev.models as Record<string, string> | undefined), [key]: value },
    }))
  }

  function setSchedule(key: string, value: string) {
    setConfig((prev) => ({
      ...prev,
      schedules: { ...(prev.schedules as Record<string, string> | undefined), [key]: value },
    }))
  }

  async function handleSave() {
    setSaving(true)
    try {
      const updated = await updateConfig(config)
      setConfig(updated)
      showToast('Settings saved', 'success')
    } catch {
      showToast('Failed to save settings', 'error')
    } finally {
      setSaving(false)
    }
  }

  async function handleReset() {
    if (!window.confirm('Reset all settings to defaults? This cannot be undone.')) return
    setSaving(true)
    try {
      const defaults: Record<string, unknown> = {
        models: {
          complex: 'qwen3.5:122b',
          simple: 'qwen3:8b',
          classifier: 'qwen3:4b',
        },
        schedules: {
          health_check: '0 */6 * * *',
          memory_decay: '0 3 * * *',
          memory_consolidate: '0 4 * * 0',
        },
      }
      const updated = await updateConfig(defaults)
      setConfig(updated)
      showToast('Settings reset to defaults', 'success')
    } catch {
      showToast('Failed to reset settings', 'error')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="settings-page" role="status" aria-label="Loading settings">
        <h1>Settings</h1>
        <p style={{ color: 'var(--text-dim)', marginTop: 16 }}>Loading...</p>
      </div>
    )
  }

  return (
    <div className="settings-page">
      <h1>Settings</h1>

      <div className="settings-actions">
        <button
          className="btn-primary"
          onClick={handleSave}
          disabled={saving}
          aria-label="Save changes"
        >
          {saving ? 'Saving...' : 'Save Changes'}
        </button>
        <button
          className="btn-dim"
          onClick={handleReset}
          disabled={saving}
          aria-label="Reset to defaults"
        >
          Reset to Defaults
        </button>
      </div>

      {/* General */}
      <div className="card settings-section" role="group" aria-labelledby="section-general">
        <h2 id="section-general">General</h2>
        <ModelRow
          label="Default Model (complex)"
          value={modelsConfig.complex ?? ''}
          options={modelNames}
          onChange={(v) => setModel('complex', v)}
        />
        <ModelRow
          label="Simple Model"
          value={modelsConfig.simple ?? ''}
          options={modelNames}
          onChange={(v) => setModel('simple', v)}
        />
        <ModelRow
          label="Classifier Model"
          value={modelsConfig.classifier ?? ''}
          options={modelNames}
          onChange={(v) => setModel('classifier', v)}
        />
        <div className="settings-row">
          <span className="settings-label">Data Directory</span>
          <span className="settings-value">
            {(config.data_dir as string) ?? '~/.merkaba'}
          </span>
        </div>
      </div>

      {/* Security */}
      <div className="card settings-section" role="group" aria-labelledby="section-security">
        <h2 id="section-security">Security</h2>
        <div className="settings-row">
          <span className="settings-label">API Key</span>
          <span className="settings-value">
            {(config.api_key as string) ?? 'Not set'}
          </span>
        </div>
        <div className="settings-row">
          <label className="settings-label" htmlFor="auto-approve-level">
            Auto Approve Level
          </label>
          <input
            id="auto-approve-level"
            className="settings-input"
            type="number"
            min={0}
            max={5}
            value={String(config.auto_approve_level ?? '')}
            onChange={(e) =>
              setConfig((prev) => ({
                ...prev,
                auto_approve_level: e.target.value ? Number(e.target.value) : undefined,
              }))
            }
            aria-label="Auto approve level"
          />
        </div>
      </div>

      {/* Scheduler */}
      <div className="card settings-section" role="group" aria-labelledby="section-scheduler">
        <h2 id="section-scheduler">Scheduler</h2>
        {Object.entries(DEFAULT_SCHEDULES).map(([key, def]) => (
          <div className="settings-row" key={key}>
            <label className="settings-label" htmlFor={`schedule-${key}`}>
              {key.replace(/_/g, ' ')}
            </label>
            <div style={{ display: 'flex', alignItems: 'center' }}>
              <input
                id={`schedule-${key}`}
                className="settings-input"
                type="text"
                value={schedulesConfig[key] ?? def.cron}
                onChange={(e) => setSchedule(key, e.target.value)}
                aria-label={`${key.replace(/_/g, ' ')} cron schedule`}
              />
              <span className="cron-description">
                {describeCron(schedulesConfig[key] ?? def.cron, def.description)}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* System Info */}
      <div className="card settings-section" role="group" aria-labelledby="section-system">
        <h2 id="section-system">System Info</h2>
        <div className="settings-row">
          <span className="settings-label">Version</span>
          <span className="settings-value">0.1.0</span>
        </div>
        <div className="settings-row">
          <span className="settings-label">Ollama</span>
          <span className="settings-value" style={{ color: status?.ollama ? 'var(--green)' : 'var(--red)' }}>
            {status?.ollama ? 'Connected' : 'Disconnected'}
          </span>
        </div>
        {status?.databases &&
          Object.entries(status.databases).map(([name, size]) => (
            <div className="settings-row" key={name}>
              <span className="settings-label">{name}.db</span>
              <span className="settings-value">{formatBytes(size)}</span>
            </div>
          ))}
      </div>
    </div>
  )
}

function ModelRow({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: string[]
  onChange: (v: string) => void
}) {
  const id = label.toLowerCase().replace(/[^a-z0-9]+/g, '-')
  const hasValue = value && !options.includes(value)
  const allOptions = hasValue ? [value, ...options] : options.length > 0 ? options : value ? [value] : []

  return (
    <div className="settings-row">
      <label className="settings-label" htmlFor={id}>
        {label}
      </label>
      <select
        id={id}
        className="settings-select"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label={label}
      >
        {!value && <option value="">Select model...</option>}
        {allOptions.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
    </div>
  )
}

function describeCron(cron: string, fallback: string): string {
  const knownDescriptions: Record<string, string> = {
    '0 */6 * * *': 'Every 6 hours',
    '0 3 * * *': 'Daily at 3 AM',
    '0 4 * * 0': 'Sundays at 4 AM',
  }
  return knownDescriptions[cron] ?? fallback
}
