import { useMemo } from 'react'
import { Routes, Route, NavLink, useNavigate } from 'react-router-dom'
import { Radar, MessageSquare, ListTodo, ShieldCheck, Brain, BarChart3 } from 'lucide-react'
import { BusinessProvider } from './context/BusinessContext'
import { ToastProvider } from './context/ToastContext'
import ErrorBoundary from './components/ErrorBoundary'
import ToastContainer from './components/Toast'
import BusinessSwitcher from './components/BusinessSwitcher'
import CommandPalette from './components/CommandPalette'
import MissionControl from './pages/MissionControl'
import Chat from './pages/Chat'
import Tasks from './pages/Tasks'
import Approvals from './pages/Approvals'
import Memory from './pages/Memory'
import Analytics from './pages/Analytics'
import BusinessConfig from './pages/BusinessConfig'
import NotFound from './pages/NotFound'

function AppShell() {
  const navigate = useNavigate()

  const commands = useMemo(() => [
    { id: 'nav-home', label: 'Mission Control', action: () => navigate('/') },
    { id: 'nav-chat', label: 'Chat', action: () => navigate('/chat') },
    { id: 'nav-tasks', label: 'Tasks', action: () => navigate('/tasks') },
    { id: 'nav-approvals', label: 'Approvals', action: () => navigate('/approvals') },
    { id: 'nav-memory', label: 'Memory', action: () => navigate('/memory') },
    { id: 'nav-analytics', label: 'Analytics', action: () => navigate('/analytics') },
  ], [navigate])

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-brand">Merkaba</div>
        <BusinessSwitcher />
        <nav role="navigation" aria-label="Main navigation">
          <NavLink to="/" end><Radar size={16} /> Mission Control</NavLink>
          <NavLink to="/chat"><MessageSquare size={16} /> Chat</NavLink>
          <NavLink to="/tasks"><ListTodo size={16} /> Tasks</NavLink>
          <NavLink to="/approvals"><ShieldCheck size={16} /> Approvals</NavLink>
          <NavLink to="/memory"><Brain size={16} /> Memory</NavLink>
          <NavLink to="/analytics"><BarChart3 size={16} /> Analytics</NavLink>
        </nav>
      </aside>
      <main className="main">
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<MissionControl />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/tasks" element={<Tasks />} />
            <Route path="/approvals" element={<Approvals />} />
            <Route path="/memory" element={<Memory />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/businesses/:id/config" element={<BusinessConfig />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </ErrorBoundary>
      </main>
      <CommandPalette commands={commands} />
    </div>
  )
}

function App() {
  return (
    <ToastProvider>
      <BusinessProvider>
        <AppShell />
        <ToastContainer />
      </BusinessProvider>
    </ToastProvider>
  )
}

export default App
