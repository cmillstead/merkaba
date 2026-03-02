import { Routes, Route, NavLink } from 'react-router-dom'
import { Radar, MessageSquare, ListTodo, ShieldCheck, Brain, BarChart3 } from 'lucide-react'
import { BusinessProvider } from './context/BusinessContext'
import ErrorBoundary from './components/ErrorBoundary'
import BusinessSwitcher from './components/BusinessSwitcher'
import MissionControl from './pages/MissionControl'
import Chat from './pages/Chat'
import Tasks from './pages/Tasks'
import Approvals from './pages/Approvals'
import Memory from './pages/Memory'
import Analytics from './pages/Analytics'
import BusinessConfig from './pages/BusinessConfig'

function App() {
  return (
    <BusinessProvider>
      <div className="layout">
        <aside className="sidebar">
          <div className="sidebar-brand">Merkaba</div>
          <BusinessSwitcher />
          <nav>
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
            </Routes>
          </ErrorBoundary>
        </main>
      </div>
    </BusinessProvider>
  )
}

export default App
