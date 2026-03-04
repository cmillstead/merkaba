import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

export interface Notification {
  id: string
  type: 'run_completed' | 'run_failed' | 'new_approval' | 'worker_stuck' | 'status_change'
  title: string
  detail?: string
  timestamp: string
  read: boolean
}

interface NotificationContextValue {
  notifications: Notification[]
  unreadCount: number
  addNotification: (n: Omit<Notification, 'id' | 'timestamp' | 'read'>) => void
  markAllRead: () => void
  clearAll: () => void
}

const STORAGE_KEY = 'merkaba_notifications'
const MAX_NOTIFICATIONS = 50
const DEDUP_WINDOW_MS = 60_000 // merge duplicates within 60s

function loadFromStorage(): Notification[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw) as Notification[]
  } catch { /* ignore corrupt data */ }
  return []
}

function saveToStorage(notifications: Notification[]) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(notifications))
}

const NotificationContext = createContext<NotificationContextValue | null>(null)

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<Notification[]>(loadFromStorage)

  const addNotification = useCallback((n: Omit<Notification, 'id' | 'timestamp' | 'read'>) => {
    setNotifications(prev => {
      const now = Date.now()
      const dupeIdx = prev.findIndex(
        p => p.type === n.type && p.title === n.title &&
          now - new Date(p.timestamp).getTime() < DEDUP_WINDOW_MS,
      )
      if (dupeIdx !== -1) {
        const updated = { ...prev[dupeIdx], timestamp: new Date().toISOString(), read: false }
        const next = [updated, ...prev.filter((_, i) => i !== dupeIdx)]
        saveToStorage(next)
        return next
      }
      const next = [
        {
          ...n,
          id: crypto.randomUUID(),
          timestamp: new Date().toISOString(),
          read: false,
        },
        ...prev,
      ].slice(0, MAX_NOTIFICATIONS)
      saveToStorage(next)
      return next
    })
  }, [])

  const markAllRead = useCallback(() => {
    setNotifications(prev => {
      const next = prev.map(n => ({ ...n, read: true }))
      saveToStorage(next)
      return next
    })
  }, [])

  const clearAll = useCallback(() => {
    saveToStorage([])
    setNotifications([])
  }, [])

  const unreadCount = useMemo(
    () => notifications.filter(n => !n.read).length,
    [notifications],
  )

  const value = useMemo<NotificationContextValue>(
    () => ({ notifications, unreadCount, addNotification, markAllRead, clearAll }),
    [notifications, unreadCount, addNotification, markAllRead, clearAll],
  )

  return (
    <NotificationContext.Provider value={value}>
      {children}
    </NotificationContext.Provider>
  )
}

export function useNotificationContext() {
  const ctx = useContext(NotificationContext)
  if (!ctx) throw new Error('useNotificationContext must be used within NotificationProvider')
  return ctx
}
