const BASE = '';

function getHeaders(): HeadersInit {
  const headers: HeadersInit = { 'Content-Type': 'application/json' };
  const key = localStorage.getItem('merkaba_api_key');
  if (key) headers['X-API-Key'] = key;
  return headers;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...getHeaders(), ...init?.headers },
  });
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
  return resp.json();
}

// System
export const getStatus = () => request<SystemStatus>('/api/system/status');
export const getModels = () => request<{ models: OllamaModel[] }>('/api/system/models');

// Businesses
export const getBusinesses = () => request<{ businesses: Business[] }>('/api/businesses');
export const getBusiness = (id: number) => request<{ business: Business; facts: Fact[]; decisions: Decision[] }>(`/api/businesses/${id}`);

// Memory
export const searchMemory = (q: string) => request<{ query: string; results: MemoryResult[] }>(`/api/memory/search?q=${encodeURIComponent(q)}`);
export const getFacts = (businessId?: number, category?: string) => {
  const params = new URLSearchParams();
  if (businessId != null) params.set('business_id', String(businessId));
  if (category) params.set('category', category);
  return request<{ facts: Fact[] }>(`/api/memory/facts?${params}`);
};
export const getDecisions = (businessId?: number) => {
  const params = businessId != null ? `?business_id=${businessId}` : '';
  return request<{ decisions: Decision[] }>(`/api/memory/decisions${params}`);
};
export const getLearnings = () => request<{ learnings: Learning[] }>('/api/memory/learnings');

// Tasks
export const getTasks = async (status?: string) => {
  const params = status ? `?status=${status}` : '';
  const data = await request<{ items: Task[] }>(`/api/tasks${params}`);
  return { tasks: data.items };
};
export const getTask = (id: number) => request<{ task: Task; runs: TaskRun[] }>(`/api/tasks/${id}`);
export const createTask = (body: CreateTaskBody) => request<{ id: number; status: string }>('/api/tasks', { method: 'POST', body: JSON.stringify(body) });
export const updateTask = (id: number, body: UpdateTaskBody) => request<{ id: number; status: string }>(`/api/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
export const getRecentRuns = (limit = 10) => request<{ runs: TaskRun[] }>(`/api/tasks/runs/recent?limit=${limit}`);

// Approvals
export const getApprovals = (status = 'pending') => request<{ approvals: Approval[] }>(`/api/approvals?status=${status}`);
export function approveAction(id: number, totpCode?: string): Promise<{ id: number; status: string }> {
  const body: Record<string, unknown> = {}
  if (totpCode) body.totp_code = totpCode
  return request<{ id: number; status: string }>(`/api/approvals/${id}/approve`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
export const denyAction = (id: number, reason?: string) => request<{ id: number; status: string }>(`/api/approvals/${id}/deny`, { method: 'POST', body: JSON.stringify({ reason }) });
export const getApprovalStats = () => request<{ stats: Record<string, number> }>('/api/approvals/stats');

// WebSocket chat with message buffering, exponential backoff reconnect, and token auth
export const MAX_PENDING_MESSAGES = 50
export interface ChatConnection {
  send: (text: string) => void
  close: () => void
}

export interface ConnectChatOptions {
  onMessage: (msg: ChatMessage) => void
  onConnect?: () => void
  onDisconnect?: () => void
}

// Build a WebSocket URL with optional ?token= query param for auth.
// The token is read from localStorage (same key used by getHeaders()).
function buildWsUrl(path: string): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const base = `${proto}://${location.host}${path}`
  const token = localStorage.getItem('merkaba_api_key')
  return token ? `${base}?token=${encodeURIComponent(token)}` : base
}

export function connectChat(options: ConnectChatOptions): ChatConnection {
  const { onMessage, onConnect, onDisconnect } = options
  const pendingMessages: string[] = []
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined
  let intentionallyClosed = false
  let attempt = 0

  function drainPending() {
    while (pendingMessages.length > 0 && ws?.readyState === WebSocket.OPEN) {
      ws.send(pendingMessages.shift()!)
    }
  }

  function createSocket() {
    ws = new WebSocket(buildWsUrl('/ws/chat'))

    ws.onopen = () => {
      attempt = 0 // Reset backoff on successful connection
      onConnect?.()
      drainPending()
    }

    ws.onmessage = (e) => {
      try {
        onMessage(JSON.parse(e.data))
      } catch {
        // Ignore malformed messages
      }
    }

    ws.onclose = () => {
      ws = null
      onDisconnect?.()
      if (!intentionallyClosed) {
        // Exponential backoff: 1s → 2s → 4s → ... → 30s cap
        const delay = Math.min(1000 * Math.pow(2, attempt), 30000)
        attempt += 1
        reconnectTimer = setTimeout(createSocket, delay)
      }
    }

    ws.onerror = () => {
      ws?.close()
    }
  }

  createSocket()

  return {
    send(text: string) {
      const payload = JSON.stringify({ message: text })
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(payload)
      } else {
        if (pendingMessages.length >= MAX_PENDING_MESSAGES) {
          pendingMessages.shift()
        }
        pendingMessages.push(payload)
      }
    },
    close() {
      intentionallyClosed = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      ws?.close()
    },
  }
}

// Types
export interface SystemStatus {
  ollama: boolean;
  version?: string;
  databases: Record<string, number | null>;
  counts: {
    memory: Record<string, number>;
    tasks: Record<string, number>;
    actions: Record<string, number>;
  };
}

export interface OllamaModel {
  name: string;
  size: number;
  modified_at: string;
}

export interface Business {
  id: number;
  name: string;
  type: string;
  autonomy_level: number;
  created_at: string;
}

export interface Fact {
  id: number;
  business_id: number;
  category: string;
  key: string;
  value: string;
  confidence: number;
  source: string | null;
  created_at: string;
}

export interface Decision {
  id: number;
  business_id: number;
  action_type: string;
  decision: string;
  reasoning: string;
  outcome: string | null;
  created_at: string;
}

export interface Learning {
  id: number;
  category: string;
  insight: string;
  evidence: string | null;
  confidence: number;
  created_at: string;
}

export interface MemoryResult {
  type: 'fact' | 'decision' | 'learning';
  [key: string]: unknown;
}

export interface Task {
  id: number;
  business_id: number | null;
  name: string;
  task_type: string;
  schedule: string | null;
  next_run: string | null;
  last_run: string | null;
  status: string;
  payload: string | null;
  autonomy_level: number;
}

export interface TaskRun {
  id: number;
  task_id: number;
  started_at: string;
  finished_at: string | null;
  status: string;
  result: string | null;
  error: string | null;
  task_name?: string;
  task_type?: string;
}

export interface CreateTaskBody {
  name: string;
  task_type: string;
  schedule?: string;
  business_id?: number;
  payload?: Record<string, unknown>;
  autonomy_level?: number;
}

export interface UpdateTaskBody {
  name?: string;
  schedule?: string;
  status?: string;
  payload?: Record<string, unknown>;
}

export interface Approval {
  id: number;
  business_id: number;
  task_run_id: number | null;
  action_type: string;
  description: string;
  params: string | null;
  autonomy_level: number;
  status: string;
  created_at: string;
  decided_at: string | null;
  decided_by: string | null;
}

export interface ChatMessage {
  type: 'response' | 'thinking' | 'error';
  content?: string;
  tool?: string | null;
  status?: string;
}

// Config
export const getConfig = () => request<Record<string, unknown>>('/api/system/config')
export const updateConfig = (body: Record<string, unknown>) =>
  request<Record<string, unknown>>('/api/system/config', { method: 'PUT', body: JSON.stringify(body) })

// Business Config
export interface BusinessConfig {
  soul: string
  user: string
  soul_source: string
  user_source: string
}

export const getBusinessConfig = (id: number) =>
  request<BusinessConfig>(`/api/businesses/${id}/config`)

export const updateBusinessConfig = (id: number, body: { soul?: string; user?: string }) =>
  request<BusinessConfig>(`/api/businesses/${id}/config`, { method: 'PUT', body: JSON.stringify(body) })

// Analytics
export interface AnalyticsOverview {
  businesses: number
  tasks_by_business: Record<string, { name: string; total: number; completed: number; pending: number; running: number }>
  approvals_summary: Record<string, number>
  memory_by_business: Record<string, { name: string; facts: number; decisions: number }>
}

export const getAnalytics = (days?: number) => {
  const params = days ? `?days=${days}` : ''
  return request<AnalyticsOverview>(`/api/analytics/overview${params}`)
}

export const triggerWorker = (workerId: string) =>
  request<{ status: string }>(`/api/control/worker/${workerId}/trigger`, { method: 'POST' })

// Chat sessions
export interface ChatSession {
  id: string
  saved_at: string | null
  message_count: number
  preview: string
}

export interface ChatSessionDetail {
  messages: { role: string; content: string }[]
}

export const getChatSessions = () =>
  request<{ sessions: ChatSession[] }>('/api/chat/sessions')

export const getChatSession = (id: string) =>
  request<ChatSessionDetail>(`/api/chat/sessions/${id}`)

// File upload (uses FormData — must not set Content-Type so browser sets multipart boundary)
export async function uploadFile(form: FormData): Promise<{ path: string }> {
  const headers: HeadersInit = {}
  const key = localStorage.getItem('merkaba_api_key')
  if (key) headers['X-API-Key'] = key
  const resp = await fetch(`${BASE}/api/upload`, {
    method: 'POST',
    headers,
    body: form,
  })
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`)
  return resp.json()
}
