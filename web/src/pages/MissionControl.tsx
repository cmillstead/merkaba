import { useCallback, useEffect, useMemo, useState } from 'react'
import { useControlSocket } from '../hooks/useControlSocket'
import HudStatusBar from '../components/HudStatusBar'
import ConstellationMap from '../components/ConstellationMap'
import AgentDetailView from '../components/AgentDetailView'
import DiagnosticsView from '../components/DiagnosticsView'
import DashboardView from '../components/DashboardView'
import KanbanBoard from '../components/KanbanBoard'
import WorkerDetailView from '../components/WorkerDetailView'
import CommandPalette from '../components/CommandPalette'
import { useNotificationDetection } from '../hooks/useNotifications'
import { getConfig, triggerWorker, updateConfig } from '../api/client'
import { useToast } from '../context/ToastContext'

type View =
  | { mode: 'dashboard' }
  | { mode: 'constellation' }
  | { mode: 'agent'; nodeId: string }
  | { mode: 'worker'; workerId: string }
  | { mode: 'kanban' }
  | { mode: 'diagnostics' }

export default function MissionControl() {
  const { state, connected, subscribeDiagnostics, unsubscribeDiagnostics, subscribeKanban, unsubscribeKanban, setTraceDepth } = useControlSocket()
  useNotificationDetection(state)
  const { showToast } = useToast()
  const [view, setView] = useState<View>({ mode: 'constellation' })
  const [viewReady, setViewReady] = useState(false)

  useEffect(() => {
    setViewReady(false)
    requestAnimationFrame(() => {
      requestAnimationFrame(() => setViewReady(true))
    })
  }, [view.mode])

  const handleSelectNode = useCallback((nodeId: string, nodeType: 'agent' | 'worker') => {
    if (nodeType === 'worker') {
      setView({ mode: 'worker', workerId: nodeId })
    } else {
      setView({ mode: 'agent', nodeId })
    }
  }, [])

  const handleBack = useCallback(() => {
    setView({ mode: 'constellation' })
  }, [])

  const handleModelChange = useCallback((model: string) => {
    getConfig()
      .then(cfg => {
        const currentModels = typeof cfg.models === 'object' && cfg.models !== null
          ? cfg.models as Record<string, unknown>
          : {}
        return updateConfig({
          models: {
            ...currentModels,
            complex: model,
          },
        })
      })
      .catch(err => {
        showToast(err instanceof Error ? err.message : 'Failed to change model', 'error')
      })
  }, [showToast])

  const commands = useMemo(() => [
    { id: 'nav-dashboard', label: 'Go to Dashboard', action: () => setView({ mode: 'dashboard' }) },
    { id: 'nav-constellation', label: 'Go to Constellation', action: () => setView({ mode: 'constellation' }) },
    { id: 'nav-kanban', label: 'Go to Kanban', action: () => setView({ mode: 'kanban' }) },
    { id: 'nav-diagnostics', label: 'Go to Diagnostics', action: () => setView({ mode: 'diagnostics' }) },
    ...state.workers.map(w => ({
      id: `nav-worker-${w.id}`,
      label: `Go to Worker: ${w.name}`,
      action: () => setView({ mode: 'worker', workerId: w.id }),
    })),
    ...state.workers.map(w => ({
      id: `trigger-${w.id}`,
      label: `Trigger Worker: ${w.name}`,
      action: () => { triggerWorker(w.id).catch(err => {
        showToast(err instanceof Error ? err.message : 'Failed to trigger worker', 'error')
      }) },
    })),
  ], [state.workers, showToast])

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === 'h' || e.key === 'H') {
        if (view.mode !== 'dashboard') {
          setView({ mode: 'dashboard' })
        }
      } else if (e.key === 'd' || e.key === 'D') {
        if (view.mode !== 'diagnostics') {
          setView({ mode: 'diagnostics' })
        }
      } else if (e.key === 'k' || e.key === 'K') {
        if (view.mode !== 'kanban') {
          setView({ mode: 'kanban' })
        }
      } else if (e.key === 'c' || e.key === 'C') {
        if (view.mode !== 'constellation') {
          setView({ mode: 'constellation' })
        }
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [view.mode])

  return (
    <div className="mission-control">
      <HudStatusBar system={state.system} connected={connected} />

      <div className={`mc-view-wrapper ${viewReady ? 'mc-view-active' : 'mc-view-enter'}`}>
        {view.mode === 'dashboard' && (
          <DashboardView state={state} connected={connected} />
        )}

        {view.mode === 'constellation' && (
          <ConstellationMap
            agents={state.agents}
            workers={state.workers}
            connections={state.connections}
            system={state.system}
            onSelectNode={handleSelectNode}
          />
        )}

        {view.mode === 'agent' && (() => {
          const agent = state.agents.find(a => a.id === view.nodeId)
          if (!agent) return null
          const approvals = state.kanban?.awaiting_approval ?? []
          return (
            <AgentDetailView
              agent={agent}
              system={state.system}
              pendingApprovals={approvals}
              onBack={handleBack}
              onModelChange={handleModelChange}
            />
          )
        })()}

        {view.mode === 'worker' && (() => {
          const worker = state.workers.find(w => w.id === view.workerId)
          if (!worker) return null
          return <WorkerDetailView worker={worker} onBack={handleBack} />
        })()}

        {view.mode === 'kanban' && (
          <KanbanBoard
            kanban={state.kanban}
            onSubscribe={subscribeKanban}
            onUnsubscribe={unsubscribeKanban}
          />
        )}

        {view.mode === 'diagnostics' && (
          <DiagnosticsView
            diagnostics={state.diagnostics}
            onSubscribe={subscribeDiagnostics}
            onUnsubscribe={unsubscribeDiagnostics}
            onSetTraceDepth={setTraceDepth}
          />
        )}
      </div>

      <CommandPalette commands={commands} />

      <div className="command-bar">
        <span className="command-hint">Ctrl+/ Command Palette</span>
        <span className="command-hint">H Dashboard</span>
        <span className="command-hint">D Diagnostics</span>
        <span className="command-hint">K Kanban</span>
        <span className="command-hint">C Constellation</span>
        <span className="command-hint">Esc Back</span>
      </div>
    </div>
  )
}
