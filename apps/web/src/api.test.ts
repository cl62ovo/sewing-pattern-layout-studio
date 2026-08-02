import { afterEach, expect, test, vi } from 'vitest'

import { api } from './api'

afterEach(() => {
  vi.unstubAllGlobals()
})

test('creates a model job when crypto.randomUUID is unavailable', async () => {
  vi.stubGlobal('crypto', {
    getRandomValues: (bytes: Uint8Array) => {
      bytes.fill(0)
      return bytes
    },
  })
  const fetchMock = vi.fn(() => Promise.resolve({
    ok: true,
    json: () => Promise.resolve({}),
  }))
  vi.stubGlobal('fetch', fetchMock)

  await api.createModelJob('version-1')

  expect(fetchMock).toHaveBeenCalledWith('/api/versions/version-1/model-jobs', expect.objectContaining({
    method: 'POST',
    body: JSON.stringify({ idempotencyKey: '00000000-0000-4000-8000-000000000000' }),
  }))
})