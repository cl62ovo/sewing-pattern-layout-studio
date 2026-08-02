import type {
  Capabilities,
  CreateProjectInput,
  ModelJob,
  ProjectDetail,
  ProjectSummary,
} from './types'

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
    body: JSON.stringify({ idempotencyKey: crypto.randomUUID() }),
  }),
  job: (id: string) => request<ModelJob>(`/api/jobs/${id}`),
  resumeModelJob: (id: string) => request<ModelJob>(`/api/jobs/${id}/resume`, {
    method: 'POST',
  }),
}