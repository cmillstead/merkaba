import { useCallback, useMemo, useState } from 'react'
import { useControlSocket } from '../hooks/useControlSocket'
import HudStatusBar from '../components/HudStatusBar'
import ConstellationMap from '../components/ConstellationMap'
import HarnessView from '../components/HarnessView'
import CommandPalette from '../components/CommandPalette'

type View =
  | { mode: 'constellation' }
  | { mode: 'harness'; nodeId: string; nodeType: 'agent' | 'worker' }

export default function MissionControl() {
  const { state, connected, sendCommand } = useControlSocket()
  const [view, setView] = useState<View>({ mode: 'constellation' })

  const handleSelectNode = useCallback((nodeId: string, nodeType: 'agent' | 'worker') => {
    setView({ mode: 'harness', nodeId, nodeType })
  }, [])

  const handleBack = useCallback(() => {
    setView({ mode: 'constellation' })
  }, [])

  const handleModelChange = useCallback((model: string) => {
    sendCommand({ type: 'change_model', agent: 'merkaba-prime', model })
    // Also update via REST for persistence
    fetch('/api/control/model', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent: 'merkaba-prime', model }),
    })
  }, [sendCommand])

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
      id: 'overview',
      label: 'Back to overview',
      action: () => setView({ mode: 'constellation' }),
    },
  ], [state.agents, state.workers])

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

      <div className="command-bar">
        <span className="command-hint">Ctrl+/ Command Palette</span>
        <span className="command-hint">←→ Navigate</span>
        <span className="command-hint">Enter Expand</span>
        <span className="command-hint">Esc Back</span>
      </div>

      <CommandPalette commands={commands} />
    </div>
  )
}
