import { Bell } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNotificationContext, type Notification } from '../context/NotificationContext'

const TYPE_COLORS: Record<Notification['type'], string> = {
  run_completed: 'notification-type-run_completed',
  run_failed: 'notification-type-run_failed',
  new_approval: 'notification-type-new_approval',
  worker_stuck: 'notification-type-worker_stuck',
  status_change: 'notification-type-status_change',
}

function timeAgo(timestamp: string): string {
  const diff = Date.now() - new Date(timestamp).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export default function NotificationBell() {
  const { notifications, unreadCount, markAllRead, clearAll } = useNotificationContext()
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const toggle = useCallback(() => {
    setOpen(prev => {
      const next = !prev
      if (next && unreadCount > 0) markAllRead()
      return next
    })
  }, [unreadCount, markAllRead])

  useEffect(() => {
    if (!open) return
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  const label = unreadCount > 0
    ? `Notifications (${unreadCount} unread)`
    : 'Notifications'

  return (
    <div className="notification-bell" ref={containerRef}>
      <button
        className="notification-bell-btn"
        onClick={toggle}
        aria-label={label}
        aria-expanded={open}
      >
        <Bell size={16} />
        {unreadCount > 0 && (
          <span className="notification-badge" aria-hidden="true">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>
      {open && (
        <div className="notification-dropdown" role="region" aria-live="polite" aria-label="Notifications">
          <div className="notification-dropdown-header">
            <span>Notifications</span>
            <button className="notification-clear" onClick={clearAll}>Clear</button>
          </div>
          {notifications.length === 0 ? (
            <div className="notification-empty">No notifications</div>
          ) : (
            <div className="notification-list">
              {notifications.map(n => (
                <div key={n.id} className={`notification-item${n.read ? '' : ' notification-unread'}`}>
                  <span className={`notification-type-dot ${TYPE_COLORS[n.type]}`} />
                  <div className="notification-content">
                    <div className="notification-title">{n.title}</div>
                    {n.detail && <div className="notification-detail">{n.detail}</div>}
                    <div className="notification-time">{timeAgo(n.timestamp)}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
