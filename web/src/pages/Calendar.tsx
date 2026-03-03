import { useState, useMemo, useCallback, useEffect, useRef } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useControlSocket } from '../hooks/useControlSocket.ts'
import type { WorkerState } from '../hooks/useControlSocket.ts'
import { cronOccurrences } from '../utils/cron.ts'

type ViewMode = 'week' | 'month'

interface ScheduledWorker {
  worker: WorkerState
  occurrences: Date[]
  colorType: 'health' | 'memory' | 'default'
}

function getWorkerColorType(id: string): 'health' | 'memory' | 'default' {
  if (id.includes('health')) return 'health'
  if (id.includes('memory')) return 'memory'
  return 'default'
}

function getMondayOfWeek(date: Date): Date {
  const d = new Date(date)
  const day = d.getDay()
  const diff = day === 0 ? -6 : 1 - day
  d.setDate(d.getDate() + diff)
  d.setHours(0, 0, 0, 0)
  return d
}

function getFirstOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1)
}

function formatDateRange(start: Date, end: Date): string {
  const opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' }
  const startStr = start.toLocaleDateString('en-US', opts)
  const endStr = end.toLocaleDateString('en-US', opts)
  const year = end.getFullYear()
  return `${startStr} \u2013 ${endStr}, ${year}`
}

function formatMonthYear(date: Date): string {
  return date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
}

function describeCronFrequency(schedule: string): string | null {
  const parts = schedule.trim().split(/\s+/)
  if (parts.length !== 5) return null

  const [min, hour] = parts

  if (hour.startsWith('*/')) {
    const h = parseInt(hour.slice(2), 10)
    return `every ${h}h`
  }
  if (min === '0' && hour === '*') {
    return 'every hour'
  }
  if (min.startsWith('*/')) {
    const m = parseInt(min.slice(2), 10)
    return `every ${m}m`
  }
  return null
}

const HOUR_LABELS = [
  '12a','1a','2a','3a','4a','5a','6a','7a','8a','9a','10a','11a',
  '12p','1p','2p','3p','4p','5p','6p','7p','8p','9p','10p','11p',
]

const DAY_NAMES = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']

function isSameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
}

interface PopoverData {
  worker: WorkerState
  schedule: string
  colorType: 'health' | 'memory' | 'default'
  x: number
  y: number
}

export default function Calendar() {
  const { state, connected } = useControlSocket()
  const [viewMode, setViewMode] = useState<ViewMode>('week')
  const [anchor, setAnchor] = useState<Date>(() => new Date())
  const [popover, setPopover] = useState<PopoverData | null>(null)
  const [triggerState, setTriggerState] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')
  const popoverRef = useRef<HTMLDivElement>(null)

  const scheduledWorkers = useMemo(() => state.workers.filter(
    (w): w is WorkerState & { schedule: string } => w.scheduled && w.schedule !== null
  ), [state.workers])

  const weekStart = useMemo(() => getMondayOfWeek(anchor), [anchor])
  const weekEnd = useMemo(() => {
    const d = new Date(weekStart)
    d.setDate(d.getDate() + 6)
    d.setHours(23, 59, 59, 999)
    return d
  }, [weekStart])

  const monthStart = useMemo(() => getFirstOfMonth(anchor), [anchor])
  const monthEnd = useMemo(() => {
    const d = new Date(monthStart.getFullYear(), monthStart.getMonth() + 1, 0)
    d.setHours(23, 59, 59, 999)
    return d
  }, [monthStart])

  const rangeStart = viewMode === 'week' ? weekStart : monthStart
  const rangeEnd = viewMode === 'week' ? weekEnd : monthEnd

  const workerSchedules: ScheduledWorker[] = useMemo(() => {
    return scheduledWorkers.map(w => ({
      worker: w,
      occurrences: cronOccurrences(w.schedule, rangeStart, rangeEnd),
      colorType: getWorkerColorType(w.id),
    }))
  }, [scheduledWorkers, rangeStart, rangeEnd])

  const alwaysOnWorkers = useMemo(() => {
    if (viewMode !== 'week') return []
    return workerSchedules.filter(ws => ws.occurrences.length > 7)
  }, [workerSchedules, viewMode])

  const navigatePrev = useCallback(() => {
    setAnchor(prev => {
      const d = new Date(prev)
      if (viewMode === 'week') {
        d.setDate(d.getDate() - 7)
      } else {
        d.setMonth(d.getMonth() - 1)
      }
      return d
    })
    setPopover(null)
  }, [viewMode])

  const navigateNext = useCallback(() => {
    setAnchor(prev => {
      const d = new Date(prev)
      if (viewMode === 'week') {
        d.setDate(d.getDate() + 7)
      } else {
        d.setMonth(d.getMonth() + 1)
      }
      return d
    })
    setPopover(null)
  }, [viewMode])

  const handleBlockClick = useCallback((
    e: React.MouseEvent,
    worker: WorkerState,
    schedule: string,
    colorType: 'health' | 'memory' | 'default',
  ) => {
    e.stopPropagation()
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    setPopover({ worker, schedule, colorType, x: rect.left, y: rect.bottom + 4 })
    setTriggerState('idle')
  }, [])

  const handleTrigger = useCallback(async (workerId: string) => {
    setTriggerState('loading')
    try {
      const res = await fetch(`/api/control/worker/${workerId}/trigger`, { method: 'POST' })
      setTriggerState(res.ok ? 'success' : 'error')
    } catch {
      setTriggerState('error')
    }
    setTimeout(() => setTriggerState('idle'), 3000)
  }, [])

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setPopover(null)
      }
    }
    if (popover) {
      document.addEventListener('mousedown', handleClick)
      return () => document.removeEventListener('mousedown', handleClick)
    }
  }, [popover])

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setPopover(null)
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [])

  const weekDays = useMemo(() => {
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(weekStart)
      d.setDate(d.getDate() + i)
      return d
    })
  }, [weekStart])

  const monthWeeks = useMemo(() => {
    const first = getFirstOfMonth(anchor)
    const mondayBefore = getMondayOfWeek(first)
    const weeks: Date[][] = []
    const cursor = new Date(mondayBefore)
    for (let w = 0; w < 6; w++) {
      const week: Date[] = []
      for (let d = 0; d < 7; d++) {
        week.push(new Date(cursor))
        cursor.setDate(cursor.getDate() + 1)
      }
      weeks.push(week)
      if (cursor.getMonth() !== anchor.getMonth() && w >= 3) break
    }
    return weeks
  }, [anchor])

  function renderPopover() {
    if (!popover) return null
    const { worker, schedule, colorType } = popover
    const lastRun = worker.run_history.length > 0 ? worker.run_history[worker.run_history.length - 1] : null
    return (
      <div
        ref={popoverRef}
        className="calendar-popover"
        style={{ left: popover.x, top: popover.y, position: 'fixed' }}
        role="dialog"
        aria-label={`${worker.name} details`}
      >
        <h4 className={`calendar-block type-${colorType}`} style={{ background: 'none', padding: 0 }}>
          {worker.name}
        </h4>
        {worker.description && (
          <p style={{ fontSize: 12, color: 'var(--text-dim)', margin: '4px 0 8px' }}>{worker.description}</p>
        )}
        <dl style={{ fontSize: 12, display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '4px 8px' }}>
          <dt style={{ color: 'var(--text-dim)' }}>Schedule</dt>
          <dd>{schedule}</dd>
          <dt style={{ color: 'var(--text-dim)' }}>Last Run</dt>
          <dd>{lastRun ? `${lastRun.status} at ${new Date(lastRun.started_at).toLocaleString()}` : 'Never'}</dd>
        </dl>
        <button
          className="btn btn-primary"
          style={{ marginTop: 12, width: '100%', justifyContent: 'center' }}
          onClick={() => handleTrigger(worker.id)}
          disabled={triggerState === 'loading'}
          aria-label={`Trigger ${worker.name}`}
        >
          {triggerState === 'loading' ? 'Triggering...' : triggerState === 'success' ? 'Triggered!' : triggerState === 'error' ? 'Failed' : 'Run Now'}
        </button>
      </div>
    )
  }

  function renderWeekView() {
    const nonAlwaysOn = workerSchedules.filter(ws => ws.occurrences.length <= 7)

    return (
      <div className="calendar-grid" role="grid" aria-label="Weekly calendar">
        <div className="calendar-day-header" />
        {weekDays.map((d, i) => (
          <div key={i} className="calendar-day-header" role="columnheader">
            {DAY_NAMES[i]} {d.getDate()}
          </div>
        ))}

        {HOUR_LABELS.map((label, hour) => (
          <div key={hour} style={{ display: 'contents' }} role="row">
            <div className="calendar-hour-label" role="rowheader">{label}</div>
            {weekDays.map((day, dayIdx) => {
              const cellBlocks = nonAlwaysOn.flatMap(ws =>
                ws.occurrences
                  .filter(occ => occ.getHours() === hour && isSameDay(occ, day))
                  .map(() => ({ name: ws.worker.name, worker: ws.worker, schedule: ws.worker.schedule!, colorType: ws.colorType }))
              )
              return (
                <div key={dayIdx} className="calendar-cell" role="gridcell">
                  {cellBlocks.map((block, bIdx) => (
                    <button
                      key={bIdx}
                      className={`calendar-block type-${block.colorType}`}
                      style={{ top: 2, left: bIdx * 4 }}
                      onClick={(e) => handleBlockClick(e, block.worker, block.schedule, block.colorType)}
                      aria-label={`${block.name} at ${label} on ${DAY_NAMES[dayIdx]}`}
                    >
                      {block.name}
                    </button>
                  ))}
                </div>
              )
            })}
          </div>
        ))}
      </div>
    )
  }

  function renderMonthView() {
    const currentMonth = anchor.getMonth()

    return (
      <div className="calendar-month-grid" role="grid" aria-label="Monthly calendar">
        {DAY_NAMES.map(d => (
          <div key={d} className="calendar-day-header" role="columnheader">{d}</div>
        ))}
        {monthWeeks.flatMap(week =>
          week.map((day, dayIdx) => {
            const isCurrentMonth = day.getMonth() === currentMonth
            const dots = workerSchedules.flatMap(ws =>
              ws.occurrences
                .filter(occ => isSameDay(occ, day))
                .slice(0, 1)
                .map(() => ws.colorType)
            )
            return (
              <div
                key={`${day.getTime()}-${dayIdx}`}
                className="calendar-month-day"
                style={{ opacity: isCurrentMonth ? 1 : 0.3 }}
                role="gridcell"
                aria-label={day.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
              >
                <div className="calendar-month-day-number">{day.getDate()}</div>
                <div className="calendar-month-dots">
                  {dots.map((ct, i) => (
                    <span key={i} className={`calendar-month-dot type-${ct}`} />
                  ))}
                </div>
              </div>
            )
          })
        )}
      </div>
    )
  }

  return (
    <div className="calendar-page">
      <div className="calendar-header">
        <h1>Calendar</h1>
        <div className="calendar-nav">
          <button onClick={navigatePrev} aria-label="Previous">
            <ChevronLeft size={16} />
          </button>
          <span style={{ minWidth: 180, textAlign: 'center' }}>
            {viewMode === 'week' ? formatDateRange(weekStart, weekEnd) : formatMonthYear(anchor)}
          </span>
          <button onClick={navigateNext} aria-label="Next">
            <ChevronRight size={16} />
          </button>
        </div>
        <div className="calendar-toggle" role="group" aria-label="View mode">
          <button
            className={viewMode === 'week' ? 'active' : ''}
            onClick={() => { setViewMode('week'); setPopover(null) }}
            aria-pressed={viewMode === 'week'}
          >
            Week
          </button>
          <button
            className={viewMode === 'month' ? 'active' : ''}
            onClick={() => { setViewMode('month'); setPopover(null) }}
            aria-pressed={viewMode === 'month'}
          >
            Month
          </button>
        </div>
      </div>

      {!connected && (
        <div className="calendar-always-on" style={{ color: 'var(--yellow)' }}>
          Connecting to server...
        </div>
      )}

      {alwaysOnWorkers.length > 0 && (
        <div className="calendar-always-on" role="status">
          <strong>ALWAYS ON:</strong>{' '}
          {alwaysOnWorkers.map((ws, i) => (
            <span key={ws.worker.id}>
              {i > 0 && ' \u2022 '}
              {ws.worker.name}
              {ws.worker.schedule && describeCronFrequency(ws.worker.schedule)
                ? ` (${describeCronFrequency(ws.worker.schedule)})`
                : ''}
            </span>
          ))}
        </div>
      )}

      {scheduledWorkers.length === 0 && connected && (
        <div className="empty">No scheduled workers found.</div>
      )}

      {viewMode === 'week' ? renderWeekView() : renderMonthView()}
      {renderPopover()}
    </div>
  )
}
