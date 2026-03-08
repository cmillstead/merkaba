import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { getStatus, getBusinesses } from '../client'

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
