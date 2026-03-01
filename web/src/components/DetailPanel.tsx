import type { ToolInfo } from '../hooks/useControlSocket'

interface Props {
  tool: ToolInfo | null
}

export default function DetailPanel({ tool }: Props) {
  if (!tool) {
    return (
      <aside className="detail-panel detail-panel--empty">
        <p className="detail-hint">Select a tool to view details</p>
      </aside>
    )
  }

  return (
    <aside className="detail-panel">
      <h3 className="detail-name">{tool.name}</h3>
      <dl className="detail-fields">
        <dt>Tier</dt>
        <dd>
          <span className={`badge badge-${tool.tier === 'SAFE' ? 'green' : tool.tier === 'MODERATE' ? 'blue' : tool.tier === 'SENSITIVE' ? 'yellow' : 'red'}`}>
            {tool.tier}
          </span>
        </dd>
        <dt>Status</dt>
        <dd>{tool.active ? 'Active' : 'Disabled'}</dd>
      </dl>
    </aside>
  )
}
