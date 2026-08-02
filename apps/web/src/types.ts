export type Capabilities = {
  mode: 'local'
  openRouter: boolean
  meshy: boolean
  meshyBalance: number | null
  authentication: boolean
  queue: string
  objectStorage: string
}

export type ProjectSummary = {
  id: string
  name: string
  locale: 'en' | 'zh-CN'
  updatedAt: string
  versionId: string
  status: string
  heightMm: number
}

export type ProjectAsset = {
  id: string
  kind: string
  contentType: string
  byteSize: number
  sha256: string
  url: string
  metadata: Record<string, unknown>
}

export type ModelJob = {
  id: string
  versionId: string
  state: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'
  stage: string
  progress: number
  thumbnailUrl: string | null
  consumedCredits: number | null
  errorCode: string | null
  errorMessage: string | null
  providerStatus: string | null
}

export type PlushSpecification = {
  supported: boolean
  reasonCodes: string[]
  summary: string
  mainVolume: {
    shape: string
    proportions: string
    pose: string
  }
  protrusions: Array<{
    kind: string
    count: number
    placement: string
    shape: string
    mustRemainGeometry: boolean
  }>
  symmetry: string
  surfaceDetails: string[]
  assumptions: string[]
  meshyConstraints: string[]
}

export type ProjectDetail = {
  id: string
  name: string
  locale: 'en' | 'zh-CN'
  createdAt: string
  version: {
    id: string
    status: string
    description: string
    heightMm: number
    seamAllowanceMm: number
    specification: PlushSpecification
    meshyPrompt: {
      positivePrompt: string
      generationNotes: string[]
    } | null
    assets: ProjectAsset[]
    latestJob: ModelJob | null
  }
}

export type CreateProjectInput = {
  name: string
  description: string
  heightMm: number
  seamAllowanceMm: number
  locale: 'en' | 'zh-CN'
}