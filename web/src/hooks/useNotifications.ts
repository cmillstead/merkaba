import { useEffect, useRef } from 'react'
import type { ControlState, WorkerState } from './useControlSocket'
import { useNotificationContext } from '../context/NotificationContext'

function detectNewRuns(
  prevWorkers: WorkerState[],
  currWorkers: WorkerState[],
  emit: ReturnType<typeof useNotificationContext>['addNotification'],
) {
  const prevById = new Map(prevWorkers.map(w => [w.id, w]))

  for (const worker of currWorkers) {
    const prev = prevById.get(worker.id)
    if (!prev) continue

    const prevRunIds = new Set(prev.run_history.map(r => r.id))
    const newRuns = worker.run_history.filter(r => !prevRunIds.has(r.id) && r.finished_at)

    for (const run of newRuns) {
      const failed = run.status === 'failed' || run.status === 'error'
      emit({
        type: failed ? 'run_failed' : 'run_completed',
        title: `${worker.name} ${failed ? 'failed' : 'completed'}`,
        detail: run.finished_at ? `Finished at ${run.finished_at}` : undefined,
      })
    }
  }
}

export function useNotificationDetection(state: ControlState) {
  const prevRef = useRef<ControlState | null>(null)
  const { addNotification } = useNotificationContext()

  useEffect(() => {
    const prev = prevRef.current
    prevRef.current = state

    if (!prev) return

    detectNewRuns(prev.workers, state.workers, addNotification)

    if (state.system.pending_approvals > prev.system.pending_approvals) {
      const delta = state.system.pending_approvals - prev.system.pending_approvals
      addNotification({
        type: 'new_approval',
        title: `${delta} new approval${delta > 1 ? 's' : ''} pending`,
      })
    }

    if (state.system.status !== prev.system.status) {
      addNotification({
        type: 'status_change',
        title: `System status: ${state.system.status}`,
        detail: `Changed from ${prev.system.status}`,
      })
    }
  }, [state, addNotification])
}
