import { useState, useMemo } from 'react'
import { useControlSocket } from '../hooks/useControlSocket'
import type { KanbanState } from '../hooks/useControlSocket'
import KanbanBoard from '../components/KanbanBoard'

const COLUMNS: (keyof KanbanState)[] = [
  'queued',
  'awaiting_approval',
  'running',
  'completed',
  'failed',
]

export default function KanbanPage() {
  const { state, subscribeKanban, unsubscribeKanban } = useControlSocket()
  const [workerFilter, setWorkerFilter] = useState('')

  const workerTypes = useMemo(() => {
    if (!state.kanban) return []
    const types = new Set<string>()
    for (const col of COLUMNS) {
      for (const card of state.kanban[col]) {
        if (card.task_type) types.add(card.task_type)
      }
    }
    return Array.from(types).sort()
  }, [state.kanban])

  const filteredKanban = useMemo((): KanbanState | null => {
    if (!state.kanban) return null
    if (!workerFilter) return state.kanban
    const result = {} as KanbanState
    for (const col of COLUMNS) {
      result[col] = state.kanban[col].filter(
        (card) => card.task_type === workerFilter,
      )
    }
    return result
  }, [state.kanban, workerFilter])

  return (
    <div>
      <div className="kanban-page-header">
        <h1>Kanban</h1>
        <select
          className="kanban-filter"
          aria-label="Filter by worker type"
          value={workerFilter}
          onChange={(e) => setWorkerFilter(e.target.value)}
        >
          <option value="">All workers</option>
          {workerTypes.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </div>
      <KanbanBoard
        kanban={filteredKanban}
        onSubscribe={subscribeKanban}
        onUnsubscribe={unsubscribeKanban}
      />
    </div>
  )
}
