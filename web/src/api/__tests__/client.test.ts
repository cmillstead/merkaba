import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { getStatus, getBusinesses, connectChat, MAX_PENDING_MESSAGES } from '../client'

// Provide a minimal localStorage stub for jsdom
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { store = {} },
  }
})()

beforeEach(() => {
  Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })
  localStorageMock.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('API client error handling', () => {
  it('throws an error with status code when the server returns a non-OK response', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      statusText: 'Service Unavailable',
    })
    vi.stubGlobal('fetch', mockFetch)

    await expect(getStatus()).rejects.toThrow('503 Service Unavailable')
    expect(mockFetch).toHaveBeenCalledOnce()
  })

  it('throws an error when fetch itself rejects (network failure)', async () => {
    const mockFetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    vi.stubGlobal('fetch', mockFetch)

    await expect(getBusinesses()).rejects.toThrow('Failed to fetch')
  })
})

describe('API client auth header', () => {
  it('includes X-API-Key header when merkaba_api_key is set in localStorage', async () => {
    localStorageMock.setItem('merkaba_api_key', 'test-secret-key')

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ ollama: true, databases: {}, counts: {} }),
    })
    vi.stubGlobal('fetch', mockFetch)

    await getStatus()

    expect(mockFetch).toHaveBeenCalledOnce()
    const [, init] = mockFetch.mock.calls[0]
    expect(init.headers).toHaveProperty('X-API-Key', 'test-secret-key')
    expect(init.headers).toHaveProperty('Content-Type', 'application/json')
  })

  it('does not include X-API-Key header when no key is stored', async () => {
    // localStorage is already cleared in beforeEach

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ ollama: true, databases: {}, counts: {} }),
    })
    vi.stubGlobal('fetch', mockFetch)

    await getStatus()

    const [, init] = mockFetch.mock.calls[0]
    expect(init.headers).not.toHaveProperty('X-API-Key')
    expect(init.headers).toHaveProperty('Content-Type', 'application/json')
  })
})

describe('WebSocket pending messages cap', () => {
  let mockWsInstances: Array<{ readyState: number; send: ReturnType<typeof vi.fn>; close: ReturnType<typeof vi.fn>; onopen?: (() => void) | null; onclose?: (() => void) | null; onmessage?: ((e: { data: string }) => void) | null; onerror?: (() => void) | null }>

  beforeEach(() => {
    mockWsInstances = []
    // Must use a real class so `new WebSocket(...)` works
    class MockWebSocket {
      static CONNECTING = 0
      static OPEN = 1
      static CLOSING = 2
      static CLOSED = 3
      readyState = 0
      send = vi.fn()
      close = vi.fn()
      onopen: (() => void) | null = null
      onclose: (() => void) | null = null
      onmessage: ((e: { data: string }) => void) | null = null
      onerror: (() => void) | null = null
      constructor() {
        mockWsInstances.push(this as any)
      }
    }
    vi.stubGlobal('WebSocket', MockWebSocket)
  })

  it('caps pending messages at MAX_PENDING_MESSAGES, keeping the most recent', () => {
    const onMessage = vi.fn()
    const conn = connectChat({ onMessage })
    const ws = mockWsInstances[0]

    // WebSocket stays in CONNECTING state — messages will be queued
    expect(ws.readyState).toBe(0)

    // Send 100 messages while disconnected
    const totalMessages = 100
    for (let i = 0; i < totalMessages; i++) {
      conn.send(`message-${i}`)
    }

    // Now simulate the socket opening and draining
    ws.readyState = 1 // WebSocket.OPEN
    ws.onopen?.()

    // Should have sent exactly MAX_PENDING_MESSAGES messages
    expect(ws.send).toHaveBeenCalledTimes(MAX_PENDING_MESSAGES)

    // The messages sent should be the most recent 50 (message-50 through message-99)
    const sentPayloads = ws.send.mock.calls.map((call: [string]) => JSON.parse(call[0]).message)
    for (let i = 0; i < MAX_PENDING_MESSAGES; i++) {
      expect(sentPayloads[i]).toBe(`message-${totalMessages - MAX_PENDING_MESSAGES + i}`)
    }

    conn.close()
  })
})
