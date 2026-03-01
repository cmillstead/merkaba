import { useEffect, useRef, useState } from 'react'
import { Send, Paperclip, History, Plus } from 'lucide-react'
import { connectChat } from '../api/client'
import type { ChatMessage } from '../api/client'

interface DisplayMsg {
  role: 'user' | 'assistant' | 'thinking'
  content: string
  attachment?: string
}

interface Session {
  id: string
  saved_at: string | null
  message_count: number
  preview: string
}

export default function Chat() {
  const [messages, setMessages] = useState<DisplayMsg[]>([])
  const [input, setInput] = useState('')
  const [connected, setConnected] = useState(false)
  const [attachedFile, setAttachedFile] = useState<{ path: string; name: string } | null>(null)
  const [uploading, setUploading] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [sessions, setSessions] = useState<Session[]>([])
  const wsRef = useRef<{ send: (t: string) => void; close: () => void } | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const ws = connectChat((msg: ChatMessage) => {
      if (msg.type === 'thinking') {
        const label = msg.tool ? `Using ${msg.tool}...` : 'Thinking...'
        setMessages(prev => {
          if (prev.length && prev[prev.length - 1].role === 'thinking') {
            return [...prev.slice(0, -1), { role: 'thinking', content: label }]
          }
          return [...prev, { role: 'thinking', content: label }]
        })
      } else if (msg.type === 'response' && msg.content) {
        setMessages(prev => {
          const cleaned = prev.filter((m, i) => !(m.role === 'thinking' && i === prev.length - 1))
          return [...cleaned, { role: 'assistant', content: msg.content! }]
        })
      }
    })
    wsRef.current = ws
    setConnected(true)
    return () => { ws.close(); setConnected(false) }
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function loadSessions() {
    try {
      const resp = await fetch('/api/chat/sessions')
      const data = await resp.json()
      setSessions(data.sessions)
    } catch { /* ignore */ }
  }

  async function loadSession(id: string) {
    try {
      const resp = await fetch(`/api/chat/sessions/${id}`)
      const data = await resp.json()
      const loaded: DisplayMsg[] = data.messages
        .filter((m: { role: string }) => m.role === 'user' || m.role === 'assistant')
        .map((m: { role: string; content: string }) => ({
          role: m.role as 'user' | 'assistant',
          content: m.content || '',
        }))
      setMessages(loaded)
      setShowHistory(false)
    } catch { /* ignore */ }
  }

  function toggleHistory() {
    if (!showHistory) loadSessions()
    setShowHistory(!showHistory)
  }

  function newChat() {
    setMessages([])
    setShowHistory(false)
    setTimeout(() => inputRef.current?.focus(), 100)
    // Reconnect to get fresh agent
    if (wsRef.current) wsRef.current.close()
    const ws = connectChat((msg: ChatMessage) => {
      if (msg.type === 'thinking') {
        const label = msg.tool ? `Using ${msg.tool}...` : 'Thinking...'
        setMessages(prev => {
          if (prev.length && prev[prev.length - 1].role === 'thinking') {
            return [...prev.slice(0, -1), { role: 'thinking', content: label }]
          }
          return [...prev, { role: 'thinking', content: label }]
        })
      } else if (msg.type === 'response' && msg.content) {
        setMessages(prev => {
          const cleaned = prev.filter((m, i) => !(m.role === 'thinking' && i === prev.length - 1))
          return [...cleaned, { role: 'assistant', content: msg.content! }]
        })
      }
    })
    wsRef.current = ws
  }

  async function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      const resp = await fetch('/api/upload', { method: 'POST', body: form })
      if (!resp.ok) throw new Error('Upload failed')
      const data = await resp.json()
      setAttachedFile({ path: data.path, name: file.name })
    } catch { /* ignore */ }
    finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  function send() {
    let text = input.trim()
    if (!text && !attachedFile) return
    if (!wsRef.current) return

    let displayText = text
    let agentText = text
    if (attachedFile) {
      const prefix = `[Attached file: ${attachedFile.path}]`
      agentText = agentText ? `${prefix}\n${agentText}` : prefix
      displayText = displayText || attachedFile.name
    }

    setMessages(prev => [...prev, {
      role: 'user',
      content: displayText,
      attachment: attachedFile?.name,
    }])
    wsRef.current.send(agentText)
    setInput('')
    setAttachedFile(null)
  }

  return (
    <div className="chat-container">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h1>Chat with Friday</h1>
        <div style={{ display: 'flex', gap: 6 }}>
          <button className="btn btn-dim" onClick={newChat} title="New chat">
            <Plus size={14} /> New
          </button>
          <button className="btn btn-dim" onClick={toggleHistory} title="Chat history">
            <History size={14} /> History
          </button>
        </div>
      </div>

      {showHistory && (
        <div className="card" style={{ marginBottom: 12, maxHeight: 200, overflowY: 'auto' }}>
          {sessions.length === 0 ? (
            <div style={{ color: 'var(--text-dim)', fontSize: 13, padding: 8 }}>No past sessions</div>
          ) : (
            sessions.map(s => (
              <div
                key={s.id}
                onClick={() => loadSession(s.id)}
                style={{
                  padding: '8px 12px',
                  cursor: 'pointer',
                  borderBottom: '1px solid var(--border)',
                  fontSize: 13,
                }}
                onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                <div style={{ fontWeight: 500 }}>{s.preview || 'Empty session'}</div>
                <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 2 }}>
                  {s.message_count} messages &middot; {s.id}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="empty">Send a message to start a conversation</div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`chat-msg ${m.role}`}>
            {m.attachment && (
              <div style={{ fontSize: 11, opacity: 0.7, marginBottom: 4 }}>
                Attached: {m.attachment}
              </div>
            )}
            {m.content}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      {attachedFile && (
        <div style={{ fontSize: 12, color: 'var(--accent)', padding: '4px 0', display: 'flex', alignItems: 'center', gap: 6 }}>
          <Paperclip size={12} /> {attachedFile.name}
          <button
            className="btn btn-dim"
            style={{ padding: '2px 6px', fontSize: 11 }}
            onClick={() => setAttachedFile(null)}
          >
            Remove
          </button>
        </div>
      )}
      <div className="chat-input-bar">
        <input type="file" ref={fileRef} onChange={handleFileSelect} style={{ display: 'none' }} />
        <button
          className="btn btn-dim"
          onClick={() => fileRef.current?.click()}
          disabled={!connected || uploading}
          title="Attach file"
        >
          <Paperclip size={16} />
        </button>
        <input
          ref={inputRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send()}
          placeholder={connected ? 'Message Friday...' : 'Connecting...'}
          disabled={!connected}
        />
        <button className="btn btn-primary" onClick={send} disabled={!connected}>
          <Send size={16} />
        </button>
      </div>
    </div>
  )
}
