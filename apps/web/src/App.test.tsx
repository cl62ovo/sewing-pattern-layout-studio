import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { App } from './App'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function mockEmptyWorkspace() {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: string | URL | Request) => {
      const url = String(input)
      const payload = url.endsWith('/api/capabilities')
        ? {
            mode: 'local',
            openRouter: true,
            meshy: true,
            meshyBalance: 3586,
            authentication: false,
            queue: 'sqlite-worker',
            objectStorage: 'local',
          }
        : []
      return Promise.resolve({ ok: true, json: () => Promise.resolve(payload) })
    }),
  )
}

test('loads the usable local project workspace', async () => {
  mockEmptyWorkspace()

  render(<App />)

  expect(await screen.findByRole('heading', { name: 'Describe one simple plush.' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Create specification/ })).toBeEnabled()
  expect(screen.getByText('3586 credits')).toBeInTheDocument()
})

test('keeps pattern and fabric layout as peer tabs', () => {
  mockEmptyWorkspace()

  render(<App />)

  const patternTab = screen.getByRole('tab', { name: /Pattern Studio/ })
  const layoutTab = screen.getByRole('tab', { name: /Nest & Cut/ })
  const legacyFrame = screen.getByTitle('Nest & Cut fabric layout')

  expect(patternTab).toHaveAttribute('aria-selected', 'true')
  expect(legacyFrame).toHaveAttribute('src', '/legacy/index.html')

  fireEvent.click(layoutTab)

  expect(layoutTab).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByRole('tabpanel', { name: /Nest & Cut/ })).toBeVisible()
})