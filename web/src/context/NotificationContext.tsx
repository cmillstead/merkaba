import { createContext, useContext, type ReactNode } from 'react'

const NotificationContext = createContext<null>(null)

export function NotificationProvider({ children }: { children: ReactNode }) {
  return <NotificationContext.Provider value={null}>{children}</NotificationContext.Provider>
}

export function useNotificationContext() {
  return useContext(NotificationContext)
}
