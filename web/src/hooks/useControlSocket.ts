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
}

function controlReducer(state: ControlState, action: Action): ControlState {
  switch (action.type) {
    case 'STATE_SNAPSHOT':
      return action.payload
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
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout>>(undefined)
  const retryDelay = useRef(1000)

  const connect = useCallback(() => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws/control`)

    ws.onopen = () => {
      setConnected(true)
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

  return { state, connected, sendCommand }
}
