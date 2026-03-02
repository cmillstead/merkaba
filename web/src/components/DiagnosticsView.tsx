import { useEffect } from 'react'
import type { DiagnosticsState } from '../hooks/useControlSocket'

interface Props {
  diagnostics: DiagnosticsState | null
  onSubscribe: () => void
  onUnsubscribe: () => void
  onSetTraceDepth: (level: 'lightweight' | 'moderate' | 'full') => void
}

const STATUS_COLORS: Record<string, string> = {
  '2': '#00ff88',  // green
  '3': '#fbbf24',  // yellow
  '4': '#f87171',  // red
  '5': '#f87171',  // red
}

function statusColor(status: number): string {
  if (status === 0) return '#00f0ff'  // WebSocket events in cyan
  return STATUS_COLORS[String(status)[0]] ?? '#8888a0'
}

function formatDuration(ms: number): string {
  if (ms < 1) return '<1ms'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return iso
  }
}

export default function DiagnosticsView({ diagnostics, onSubscribe, onUnsubscribe, onSetTraceDepth }: Props) {
  useEffect(() => {
    onSubscribe()
    return () => { onUnsubscribe() }
  }, [onSubscribe, onUnsubscribe])

  if (!diagnostics) {
    return (
      <div className="diagnostics-view">
        <div className="diagnostics-waiting">Waiting for diagnostic data...</div>
      </div>
    )
  }

  const traceDepth = diagnostics.trace_depth

  return (
    <div className="diagnostics-view">
      {/* Left Panel — Connections + Summary */}
      <div className="diagnostics-sidebar">
        <div className="diagnostics-section">
          <h3 className="diagnostics-heading">Connections</h3>
          {diagnostics.active_websockets.length === 0 ? (
            <div className="diagnostics-empty">No active WebSockets</div>
          ) : (
            diagnostics.active_websockets.map((ws, i) => (
              <div key={i} className="diagnostics-connection">
                <div className="diagnostics-conn-path">
                  <span className="diagnostics-dot diagnostics-dot--active" />
                  {ws.path}
                </div>
                <div className="diagnostics-conn-stats">
                  {ws.frames_sent}&uarr; {ws.frames_received}&darr;
                </div>
              </div>
            ))
          )}
        </div>

        <div className="diagnostics-section">
          <h3 className="diagnostics-heading">Summary</h3>
          <dl className="diagnostics-summary">
            <dt>Requests</dt>
            <dd>{diagnostics.total_requests.toLocaleString()}</dd>
            <dt>Errors</dt>
            <dd className={diagnostics.total_errors > 0 ? 'diagnostics-error-count' : ''}>
              {diagnostics.total_errors}
            </dd>
            <dt>Avg Duration</dt>
            <dd>{formatDuration(diagnostics.avg_duration_ms)}</dd>
            <dt>Buffer</dt>
            <dd>{diagnostics.buffer_used}/{diagnostics.buffer_size}</dd>
          </dl>
        </div>

        <div className="diagnostics-section">
          <h3 className="diagnostics-heading">Trace Depth</h3>
          <div className="diagnostics-depth-toggle">
            {(['lightweight', 'moderate', 'full'] as const).map(level => (
              <button
                key={level}
                className={`diagnostics-depth-btn ${traceDepth === level ? 'diagnostics-depth-btn--active' : ''}`}
                onClick={() => onSetTraceDepth(level)}
              >
                {level === 'lightweight' ? 'lite' : level === 'moderate' ? 'mod' : 'full'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Right Panel — Request Timeline */}
      <div className="diagnostics-timeline">
        <h3 className="diagnostics-heading">Request Timeline</h3>
        <div className="diagnostics-timeline-list">
          {diagnostics.recent_requests.length === 0 ? (
            <div className="diagnostics-empty">No requests recorded yet</div>
          ) : (
            diagnostics.recent_requests.map((req, i) => (
              <details key={i} className="diagnostics-request">
                <summary
                  className="diagnostics-request-row"
                  style={{ borderLeftColor: statusColor(req.status) }}
                >
                  <span className="diagnostics-req-time">{formatTimestamp(req.timestamp)}</span>
                  <span className="diagnostics-req-method">{req.method}</span>
                  <span className="diagnostics-req-path">{req.path}</span>
                  {req.status > 0 && (
                    <span
                      className="diagnostics-req-status"
                      style={{ color: statusColor(req.status) }}
                    >
                      {req.status}
                    </span>
                  )}
                  <span className="diagnostics-req-duration">{formatDuration(req.duration_ms)}</span>
                  {req.route && <span className="diagnostics-req-route">{req.route}</span>}
                </summary>
                <div className="diagnostics-request-detail">
                  {req.error && <div className="diagnostics-error-detail">{req.error}</div>}
                  {req.query_string && <div><span className="diagnostics-label">Query:</span> {req.query_string}</div>}
                  {req.response_size != null && <div><span className="diagnostics-label">Response:</span> {req.response_size} bytes</div>}
                  {req.frames_sent != null && (
                    <div><span className="diagnostics-label">Frames:</span> {req.frames_sent}&uarr; {req.frames_received}&darr;</div>
                  )}
                  {req.headers && (
                    <div className="diagnostics-headers">
                      <span className="diagnostics-label">Headers:</span>
                      {req.headers.map(([k, v], j) => (
                        <div key={j} className="diagnostics-header-row">
                          <span className="diagnostics-header-key">{k}:</span> {v}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </details>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
