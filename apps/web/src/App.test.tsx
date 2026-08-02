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

  expect(patternTab).toHaveAttribute('aria-selected', 'true')
  expect(screen.queryByTitle('Nest & Cut fabric layout')).not.toBeInTheDocument()

  fireEvent.click(layoutTab)

  expect(layoutTab).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByTitle('Nest & Cut fabric layout')).toHaveAttribute('src', '/legacy/index.html')
  expect(screen.getByRole('tabpanel', { name: /Nest & Cut/ })).toBeVisible()
})

test('shows deterministic quality metrics and exports for a ready pattern', async () => {
  const project = {
    id: 'project-1',
    name: 'Box plush',
    locale: 'en',
    createdAt: '2026-08-02T00:00:00Z',
    version: {
      id: 'version-1',
      status: 'ready',
      description: 'A simple box plush',
      heightMm: 240,
      seamAllowanceMm: 7,
      specification: {
        supported: true,
        reasonCodes: ['SUPPORTED'],
        summary: 'A simple box plush.',
        mainVolume: { shape: 'box', proportions: 'compact', pose: 'upright' },
        protrusions: [],
        symmetry: 'bilateral',
        surfaceDetails: [],
        assumptions: [],
        meshyConstraints: ['closed', 'watertight', 'manifold', 'single volume'],
      },
      meshyPrompt: null,
      assets: [
        { id: 'svg-1', kind: 'pattern_svg', contentType: 'image/svg+xml', byteSize: 100, sha256: 'a', url: '/api/assets/svg-1', metadata: {} },
        { id: 'pdf-1', kind: 'pattern_pdf', contentType: 'application/pdf', byteSize: 100, sha256: 'b', url: '/api/assets/pdf-1', metadata: {} },
        { id: 'report-1', kind: 'pattern_report', contentType: 'application/json', byteSize: 100, sha256: 'c', url: '/api/assets/report-1', metadata: {} },
      ],
      latestJob: { id: 'job-1', versionId: 'version-1', kind: 'build_pattern', state: 'succeeded', stage: 'ready', progress: 100, thumbnailUrl: null, consumedCredits: null, errorCode: null, errorMessage: null, providerStatus: null, patternPassed: true },
    },
  }
  const pattern = {
    schemaVersion: 1,
    algorithmVersion: 'pattern-v3',
    units: 'mm',
    sourceSha256: 'a',
    targetHeightMm: 240,
    seamAllowanceMm: 7,
    pieces: [],
    quality: { pieceCount: 6, meanDistortion: 0.012, maxDistortion: 0.025, maxSeamMismatch: 0.003, flippedTriangleCount: 0, boundarySelfIntersectionCount: 0, unpairedSeamCount: 0, passed: true, failureReasons: [] },
    svgFileName: 'pattern.svg',
    pdfFileName: 'pattern.pdf',
  }
  vi.stubGlobal('fetch', vi.fn((input: string | URL | Request) => {
    const url = String(input)
    let payload: unknown = []
    if (url.endsWith('/api/capabilities')) payload = { mode: 'local', openRouter: true, meshy: true, meshyBalance: 100, authentication: false, queue: 'sqlite-worker', objectStorage: 'local' }
    else if (url.endsWith('/api/projects')) payload = [{ id: project.id, name: project.name, locale: project.locale, updatedAt: project.createdAt, versionId: project.version.id, status: 'ready', heightMm: 240 }]
    else if (url.endsWith('/api/projects/project-1')) payload = project
    else if (url.endsWith('/api/versions/version-1/pattern')) payload = pattern
    return Promise.resolve({ ok: true, json: () => Promise.resolve(payload) })
  }))

  render(<App />)

  expect(await screen.findByRole('heading', { name: 'Pattern passed digital checks' })).toBeInTheDocument()
  expect(screen.getByText('1.20%')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /1:1 A4 PDF/ })).toHaveAttribute('href', '/api/assets/pdf-1')
  expect(screen.getByAltText('Generated two-dimensional sewing pattern pieces')).toHaveAttribute('src', '/api/assets/svg-1')
})