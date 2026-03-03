import { useMemo } from 'react'
import { Routes, Route, NavLink, useNavigate } from 'react-router-dom'
import {
  Radar, MessageSquare, ListTodo, ShieldCheck, Brain, BarChart3,
  CalendarDays, Columns3, BookOpen, Users, FolderKanban,
  Settings as SettingsIcon,
} from 'lucide-react'
import MerkabaGlyph from './components/MerkabaGlyph'
import SidebarGroup from './components/SidebarGroup'
import NotificationBell from './components/NotificationBell'
import { BusinessProvider } from './context/BusinessContext'
import { ToastProvider } from './context/ToastContext'
import { NotificationProvider } from './context/NotificationContext'
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
import Calendar from './pages/Calendar'
import KanbanPage from './pages/KanbanPage'
import Settings from './pages/Settings'
import Placeholder from './pages/Placeholder'
import BusinessConfig from './pages/BusinessConfig'
import NotFound from './pages/NotFound'

function AppShell() {
  const navigate = useNavigate()

  const commands = useMemo(() => [
    { id: 'nav-home', label: 'Dashboard', action: () => navigate('/') },
    { id: 'nav-calendar', label: 'Calendar', action: () => navigate('/calendar') },
    { id: 'nav-kanban', label: 'Kanban', action: () => navigate('/kanban') },
    { id: 'nav-tasks', label: 'Tasks', action: () => navigate('/tasks') },
    { id: 'nav-memory', label: 'Memory Vault', action: () => navigate('/memory') },
    { id: 'nav-docs', label: 'Docs', action: () => navigate('/docs') },
    { id: 'nav-team', label: 'Org Chart', action: () => navigate('/team') },
    { id: 'nav-chat', label: 'Chat', action: () => navigate('/chat') },
    { id: 'nav-approvals', label: 'Approvals', action: () => navigate('/approvals') },
    { id: 'nav-analytics', label: 'Analytics', action: () => navigate('/analytics') },
    { id: 'nav-projects', label: 'Projects', action: () => navigate('/projects') },
    { id: 'nav-settings', label: 'Settings', action: () => navigate('/settings') },
  ], [navigate])

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <MerkabaGlyph size={34} status="active" speed={0.5} />
          Merkaba
          <NotificationBell />
        </div>
        <BusinessSwitcher />
        <nav role="navigation" aria-label="Main navigation">
          <SidebarGroup label="Operations" storageKey="operations">
            <NavLink to="/" end><Radar size={16} /> Dashboard</NavLink>
            <NavLink to="/calendar"><CalendarDays size={16} /> Calendar</NavLink>
            <NavLink to="/kanban"><Columns3 size={16} /> Kanban</NavLink>
            <NavLink to="/tasks"><ListTodo size={16} /> Tasks</NavLink>
          </SidebarGroup>
          <SidebarGroup label="Knowledge" storageKey="knowledge">
            <NavLink to="/memory"><Brain size={16} /> Memory Vault</NavLink>
            <NavLink to="/docs"><BookOpen size={16} /> Docs</NavLink>
          </SidebarGroup>
          <SidebarGroup label="Team" storageKey="team">
            <NavLink to="/team"><Users size={16} /> Org Chart</NavLink>
            <NavLink to="/chat"><MessageSquare size={16} /> Chat</NavLink>
          </SidebarGroup>
          <SidebarGroup label="System" storageKey="system">
            <NavLink to="/approvals"><ShieldCheck size={16} /> Approvals</NavLink>
            <NavLink to="/analytics"><BarChart3 size={16} /> Analytics</NavLink>
            <NavLink to="/projects"><FolderKanban size={16} /> Projects</NavLink>
            <NavLink to="/settings"><SettingsIcon size={16} /> Settings</NavLink>
          </SidebarGroup>
        </nav>
      </aside>
      <main className="main">
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<MissionControl />} />
            <Route path="/calendar" element={<Calendar />} />
            <Route path="/kanban" element={<KanbanPage />} />
            <Route path="/tasks" element={<Tasks />} />
            <Route path="/memory" element={<Memory />} />
            <Route path="/docs" element={<Placeholder title="Docs" phase={2} />} />
            <Route path="/team" element={<Placeholder title="Org Chart" phase={3} />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/approvals" element={<Approvals />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/projects" element={<Placeholder title="Projects" phase={4} />} />
            <Route path="/settings" element={<Settings />} />
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
        <NotificationProvider>
          <AppShell />
          <ToastContainer />
        </NotificationProvider>
      </BusinessProvider>
    </ToastProvider>
  )
}

export default App
