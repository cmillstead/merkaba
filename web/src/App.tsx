import { Routes, Route, NavLink } from 'react-router-dom'
import { LayoutDashboard, MessageSquare, ListTodo, ShieldCheck, Brain, BarChart3 } from 'lucide-react'
import { BusinessProvider } from './context/BusinessContext'
import BusinessSwitcher from './components/BusinessSwitcher'
import Dashboard from './pages/Dashboard'
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
          <div className="sidebar-brand">Friday</div>
          <BusinessSwitcher />
          <nav>
            <NavLink to="/" end><LayoutDashboard size={16} /> Dashboard</NavLink>
            <NavLink to="/chat"><MessageSquare size={16} /> Chat</NavLink>
            <NavLink to="/tasks"><ListTodo size={16} /> Tasks</NavLink>
            <NavLink to="/approvals"><ShieldCheck size={16} /> Approvals</NavLink>
            <NavLink to="/memory"><Brain size={16} /> Memory</NavLink>
            <NavLink to="/analytics"><BarChart3 size={16} /> Analytics</NavLink>
          </nav>
        </aside>
        <main className="main">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/tasks" element={<Tasks />} />
            <Route path="/approvals" element={<Approvals />} />
            <Route path="/memory" element={<Memory />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/businesses/:id/config" element={<BusinessConfig />} />
          </Routes>
        </main>
      </div>
    </BusinessProvider>
  )
}

export default App
