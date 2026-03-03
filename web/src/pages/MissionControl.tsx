import { useCallback, useEffect, useState } from 'react'
import { useControlSocket } from '../hooks/useControlSocket'
import HudStatusBar from '../components/HudStatusBar'
import ConstellationMap from '../components/ConstellationMap'
import AgentDetailView from '../components/AgentDetailView'
import DiagnosticsView from '../components/DiagnosticsView'
import KanbanBoard from '../components/KanbanBoard'
import WorkerDetailView from '../components/WorkerDetailView'

type View =
  | { mode: 'constellation' }
  | { mode: 'agent'; nodeId: string }
  | { mode: 'worker'; workerId: string }
  | { mode: 'kanban' }
  | { mode: 'diagnostics' }

export default function MissionControl() {
  const { state, connected, subscribeDiagnostics, unsubscribeDiagnostics, subscribeKanban, unsubscribeKanban, setTraceDepth } = useControlSocket()
  const [view, setView] = useState<View>({ mode: 'constellation' })

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
    fetch('/api/control/model', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent: 'merkaba-prime', model }),
    })
  }, [])

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === 'd' || e.key === 'D') {
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

      {view.mode === 'constellation' && (
        <ConstellationMap
          agents={state.agents}
          workers={state.workers}
          connections={state.connections}
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

      <div className="command-bar">
        <span className="command-hint">Ctrl+/ Command Palette</span>
        <span className="command-hint">D Diagnostics</span>
        <span className="command-hint">K Kanban</span>
        <span className="command-hint">C Constellation</span>
        <span className="command-hint">Esc Back</span>
      </div>
    </div>
  )
}
