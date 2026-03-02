import { useCallback, useEffect, useMemo, useState } from 'react'
import { useControlSocket } from '../hooks/useControlSocket'
import HudStatusBar from '../components/HudStatusBar'
import ConstellationMap from '../components/ConstellationMap'
import HarnessView from '../components/HarnessView'
import CommandPalette from '../components/CommandPalette'
import DiagnosticsView from '../components/DiagnosticsView'

type View =
  | { mode: 'constellation' }
  | { mode: 'harness'; nodeId: string; nodeType: 'agent' | 'worker' }
  | { mode: 'diagnostics' }

export default function MissionControl() {
  const { state, connected, subscribeDiagnostics, unsubscribeDiagnostics, setTraceDepth } = useControlSocket()
  const [view, setView] = useState<View>({ mode: 'constellation' })

  const handleSelectNode = useCallback((nodeId: string, nodeType: 'agent' | 'worker') => {
    setView({ mode: 'harness', nodeId, nodeType })
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

  const agent = view.mode === 'harness'
    ? state.agents.find(a => a.id === view.nodeId) ?? null
    : null

  const commands = useMemo(() => [
    ...state.agents.map(a => ({
      id: `go-${a.id}`,
      label: `Go to ${a.name}`,
      action: () => setView({ mode: 'harness', nodeId: a.id, nodeType: 'agent' }),
    })),
    ...state.workers.map(w => ({
      id: `go-${w.id}`,
      label: `Go to ${w.name}`,
      action: () => setView({ mode: 'harness', nodeId: w.id, nodeType: 'worker' }),
    })),
    {
      id: 'diagnostics',
      label: 'Diagnostics',
      action: () => setView({ mode: 'diagnostics' }),
    },
    {
      id: 'overview',
      label: 'Back to overview',
      action: () => setView({ mode: 'constellation' }),
    },
  ], [state.agents, state.workers])

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === 'd' || e.key === 'D') {
        if (view.mode !== 'diagnostics') {
          setView({ mode: 'diagnostics' })
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

      {view.mode === 'harness' && agent && (
        <HarnessView
          agent={agent}
          onBack={handleBack}
          onModelChange={handleModelChange}
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
        <span className="command-hint">C Constellation</span>
        <span className="command-hint">Esc Back</span>
      </div>

      <CommandPalette commands={commands} />
    </div>
  )
}
