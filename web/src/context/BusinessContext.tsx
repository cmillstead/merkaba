import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'
import { getBusinesses } from '../api/client'
import type { Business } from '../api/client'

interface BusinessContextType {
  businesses: Business[]
  selected: number | null  // null = "All businesses"
  setSelected: (id: number | null) => void
  loading: boolean
}

const BusinessContext = createContext<BusinessContextType>({
  businesses: [],
  selected: null,
  setSelected: () => {},
  loading: true,
})

export const useBusinessContext = () => useContext(BusinessContext)

export function BusinessProvider({ children }: { children: ReactNode }) {
  const [businesses, setBusinesses] = useState<Business[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelectedState] = useState<number | null>(() => {
    const stored = localStorage.getItem('friday_business')
    return stored ? Number(stored) : null
  })

  useEffect(() => {
    getBusinesses()
      .then(d => setBusinesses(d.businesses))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const setSelected = (id: number | null) => {
    setSelectedState(id)
    if (id !== null) {
      localStorage.setItem('friday_business', String(id))
    } else {
      localStorage.removeItem('friday_business')
    }
  }

  return (
    <BusinessContext.Provider value={{ businesses, selected, setSelected, loading }}>
      {children}
    </BusinessContext.Provider>
  )
}
