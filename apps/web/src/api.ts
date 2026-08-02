import type {
  Capabilities,
  CreateProjectInput,
  ModelJob,
  PatternQuality,
  PatternReport,
  ProjectDetail,
  ProjectSummary,
} from './types'

function createIdempotencyKey(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID()
  }

  const bytes = new Uint8Array(16)
  if (typeof globalThis.crypto?.getRandomValues === 'function') {
    globalThis.crypto.getRandomValues(bytes)
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256)
    }
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const value = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
  return `${value.slice(0, 8)}-${value.slice(8, 12)}-${value.slice(12, 16)}-${value.slice(16, 20)}-${value.slice(20)}`
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as {
      detail?: { code?: string; message?: string }
    } | null
    throw new Error(payload?.detail?.message || payload?.detail?.code || `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export const api = {
  capabilities: () => request<Capabilities>('/api/capabilities'),
  projects: () => request<ProjectSummary[]>('/api/projects'),
  project: (id: string) => request<ProjectDetail>(`/api/projects/${id}`),
  createProject: (input: CreateProjectInput) => request<ProjectDetail>('/api/projects', {
    method: 'POST',
    body: JSON.stringify(input),
  }),
  createModelJob: (versionId: string) => request<ModelJob>(`/api/versions/${versionId}/model-jobs`, {
    method: 'POST',
    body: JSON.stringify({ idempotencyKey: createIdempotencyKey() }),
  }),
  job: (id: string) => request<ModelJob>(`/api/jobs/${id}`),
  resumeModelJob: (id: string) => request<ModelJob>(`/api/jobs/${id}/resume`, {
    method: 'POST',
  }),
  acceptModel: (versionId: string) => request<ModelJob>(`/api/versions/${versionId}/accept-model`, {
    method: 'POST',
    body: JSON.stringify({ idempotencyKey: createIdempotencyKey() }),
  }),
  pattern: (versionId: string) => request<PatternReport>(`/api/versions/${versionId}/pattern`),
  qualityReport: (versionId: string) => request<PatternQuality>(`/api/versions/${versionId}/quality-report`),
}