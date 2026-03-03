import { useEffect, useReducer, useRef, useState, useCallback } from 'react'

// Types
export interface ToolInfo {
  name: string
  tier: string
  active: boolean
}

export interface AgentState {
  id: string
  name: string
  role: string
  model: string
  status: string
  tools: ToolInfo[]
  workers: string[]
  active_skill: string | null
  current_task: string | null
}

export interface WorkerState {
  id: string
  name: string
  status: string
  scheduled: boolean
  last_run: string | null
  parent: string
}

export interface Connection {
  from: string
  to: string
  type: string
}

export interface WebSocketConnection {
  path: string
  connected_at: string
  frames_sent: number
  frames_received: number
}

export interface RequestTrace {
  timestamp: string
  scope_type: string
  method: string
  path: string
  status: number
  duration_ms: number
  route?: string
  request_size?: number
  response_size?: number
  error?: string
  query_string?: string
  headers?: [string, string][]
  event_type?: string
  frames_sent?: number
  frames_received?: number
}

export interface DiagnosticsState {
  trace_depth: string
  active_websockets: WebSocketConnection[]
  recent_requests: RequestTrace[]
  recent_errors: RequestTrace[]
  total_requests: number
  total_errors: number
  avg_duration_ms: number
  buffer_size: number
  buffer_used: number
}

export interface SystemState {
  status: string
  memory_facts: number
  pending_approvals: number
  active_tasks: number
}

export interface ControlState {
  system: SystemState
  agents: AgentState[]
  workers: WorkerState[]
  connections: Connection[]
  diagnostics: DiagnosticsState | null
}

type Action =
  | { type: 'STATE_SNAPSHOT'; payload: ControlState }
  | { type: 'TOOL_INVOKED'; agent: string; tool: string }
  | { type: 'WORKER_STARTED'; worker: string }
  | { type: 'WORKER_COMPLETED'; worker: string }
  | { type: 'MODEL_CHANGED'; agent: string; model: string }

const initialState: ControlState = {
  system: { status: 'offline', memory_facts: 0, pending_approvals: 0, active_tasks: 0 },
  agents: [],
  workers: [],
  connections: [],
  diagnostics: null,
}

// Shallow equality check for SystemState — avoids re-render when heartbeat
// delivers identical system stats (the most frequent update path).
function systemEqual(a: SystemState, b: SystemState): boolean {
  return (
    a.status === b.status &&
    a.memory_facts === b.memory_facts &&
    a.pending_approvals === b.pending_approvals &&
    a.active_tasks === b.active_tasks
  )
}

// JSON.stringify comparison for arrays/objects where deep equality matters.
// Used on agents/workers/connections which change infrequently.
function jsonEqual<T>(a: T, b: T): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

// Returns the incoming snapshot if it differs meaningfully from current state,
// otherwise returns the current state reference — preventing unnecessary re-renders
// when the backend sends the same data on every heartbeat.
//
// NOTE: Components that consume useControlSocket output should be wrapped in
// React.memo to further prevent re-renders from parent updates. Example:
//   export default React.memo(ConstellationMap)
//   export default React.memo(HarnessView)
function deduplicateSnapshot(current: ControlState, next: ControlState): ControlState {
  const sameSystem = systemEqual(current.system, next.system)
  const sameAgents = jsonEqual(current.agents, next.agents)
  const sameWorkers = jsonEqual(current.workers, next.workers)
  const sameConnections = jsonEqual(current.connections, next.connections)
  const sameDiagnostics = jsonEqual(current.diagnostics, next.diagnostics)

  if (sameSystem && sameAgents && sameWorkers && sameConnections && sameDiagnostics) {
    return current // Same reference → React skips re-render
  }

  // Return partial new object reusing unchanged slice references
  return {
    system: sameSystem ? current.system : next.system,
    agents: sameAgents ? current.agents : next.agents,
    workers: sameWorkers ? current.workers : next.workers,
    connections: sameConnections ? current.connections : next.connections,
    diagnostics: sameDiagnostics ? current.diagnostics : next.diagnostics,
  }
}

function controlReducer(state: ControlState, action: Action): ControlState {
  switch (action.type) {
    case 'STATE_SNAPSHOT':
      return deduplicateSnapshot(state, action.payload)
    case 'TOOL_INVOKED':
      return state // Visual flash handled by component, not state
    case 'WORKER_STARTED':
      return {
        ...state,
        workers: state.workers.map(w =>
          w.id === action.worker ? { ...w, status: 'active' } : w
        ),
      }
    case 'WORKER_COMPLETED':
      return {
        ...state,
        workers: state.workers.map(w =>
          w.id === action.worker ? { ...w, status: 'idle' } : w
        ),
      }
    case 'MODEL_CHANGED':
      return {
        ...state,
        agents: state.agents.map(a =>
          a.id === action.agent ? { ...a, model: action.model } : a
        ),
      }
    default:
      return state
  }
}

export function useControlSocket() {
  const [state, dispatch] = useReducer(controlReducer, initialState)
  const [connected, setConnected] = useState(false)
  const [reconnecting, setReconnecting] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout>>(undefined)
  const retryDelay = useRef(1000)

  const connect = useCallback(() => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws/control`)

    ws.onopen = () => {
      setConnected(true)
      setReconnecting(false)
      retryDelay.current = 1000
    }

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.type === 'state_update') {
          dispatch({
            type: 'STATE_SNAPSHOT',
            payload: {
              system: msg.system,
              agents: msg.agents,
              workers: msg.workers,
              connections: msg.connections,
              diagnostics: msg.diagnostics ?? null,
            },
          })
        } else if (msg.type === 'tool_invoked') {
          dispatch({ type: 'TOOL_INVOKED', agent: msg.agent, tool: msg.tool })
        } else if (msg.type === 'worker_started') {
          dispatch({ type: 'WORKER_STARTED', worker: msg.worker })
        } else if (msg.type === 'worker_completed') {
          dispatch({ type: 'WORKER_COMPLETED', worker: msg.worker })
        } else if (msg.type === 'model_changed') {
          dispatch({ type: 'MODEL_CHANGED', agent: msg.agent, model: msg.model })
        }
      } catch {
        // Ignore malformed messages
      }
    }

    ws.onclose = () => {
      setConnected(false)
      setReconnecting(true)
      wsRef.current = null
      // Exponential backoff reconnect
      reconnectTimeout.current = setTimeout(() => {
        retryDelay.current = Math.min(retryDelay.current * 2, 30000)
        connect()
      }, retryDelay.current)
    }

    ws.onerror = () => {
      ws.close()
    }

    wsRef.current = ws
  }, [])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current)
      if (wsRef.current) wsRef.current.close()
    }
  }, [connect])

  const sendCommand = useCallback((cmd: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(cmd))
    }
  }, [])

  const subscribeDiagnostics = useCallback(() => {
    sendCommand({ type: 'subscribe', channel: 'diagnostics' })
  }, [sendCommand])

  const unsubscribeDiagnostics = useCallback(() => {
    sendCommand({ type: 'unsubscribe', channel: 'diagnostics' })
  }, [sendCommand])

  const setTraceDepth = useCallback((level: 'lightweight' | 'moderate' | 'full') => {
    sendCommand({ type: 'set_trace_depth', level })
  }, [sendCommand])

  return { state, connected, reconnecting, sendCommand, subscribeDiagnostics, unsubscribeDiagnostics, setTraceDepth }
}
