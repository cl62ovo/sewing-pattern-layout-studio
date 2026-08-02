import { lazy, Suspense, useEffect, useState } from 'react'
import {
  AlertTriangle,
  Box,
  Check,
  ChevronLeft,
  ChevronRight,
  Download,
  LoaderCircle,
  Plus,
  Sparkles,
} from 'lucide-react'

import { api } from './api'
import type { Capabilities, CreateProjectInput, ProjectDetail, ProjectSummary } from './types'

const ModelViewer = lazy(() => import('./ModelViewer').then((module) => ({ default: module.ModelViewer })))

const emptyProject: CreateProjectInput = {
  name: '',
  description: '',
  heightMm: 240,
  seamAllowanceMm: 7,
  locale: 'en',
}

const statusLabels: Record<string, string> = {
  draft: 'Specification ready',
  generating_model: 'Generating model',
  model_review: 'Model ready',
  failed: 'Needs attention',
}

export function PatternStudio() {
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null)
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [selected, setSelected] = useState<ProjectDetail | null>(null)
  const [showCreate, setShowCreate] = useState(true)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function refreshProjects() {
    const items = await api.projects()
    setProjects(items)
    return items
  }

  async function openProject(id: string) {
    setError('')
    setLoading(true)
    try {
      setSelected(await api.project(id))
      setShowCreate(false)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Project could not be opened.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let active = true
    Promise.all([api.capabilities(), api.projects()])
      .then(([serviceCapabilities, items]) => {
        if (!active) return
        setCapabilities(serviceCapabilities)
        setProjects(items)
        if (items.length > 0) return api.project(items[0].id)
        return null
      })
      .then((project) => {
        if (!active || !project) return
        setSelected(project)
        setShowCreate(false)
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : 'Studio services are unavailable.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [])

  useEffect(() => {
    const job = selected?.version.latestJob
    if (!job || !['queued', 'running'].includes(job.state)) return
    const timer = window.setInterval(async () => {
      try {
        const next = await api.job(job.id)
        setSelected((current) => current ? {
          ...current,
          version: { ...current.version, latestJob: next },
        } : current)
        if (!['queued', 'running'].includes(next.state) && selected) {
          await openProject(selected.id)
          await refreshProjects()
        }
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : 'Task status could not be updated.')
      }
    }, 2500)
    return () => window.clearInterval(timer)
  }, [selected?.id, selected?.version.latestJob?.id, selected?.version.latestJob?.state])

  async function createProject(input: CreateProjectInput) {
    setLoading(true)
    setError('')
    try {
      const project = await api.createProject(input)
      setSelected(project)
      setShowCreate(false)
      await refreshProjects()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Project could not be created.')
    } finally {
      setLoading(false)
    }
  }

  async function generateModel() {
    if (!selected) return
    setLoading(true)
    setError('')
    try {
      const job = await api.createModelJob(selected.version.id)
      setSelected({
        ...selected,
        version: { ...selected.version, status: 'generating_model', latestJob: job },
      })
      await refreshProjects()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Model task could not be created.')
    } finally {
      setLoading(false)
    }
  }

  async function resumeModel() {
    const job = selected?.version.latestJob
    if (!selected || !job) return
    setLoading(true)
    setError('')
    try {
      const resumed = await api.resumeModelJob(job.id)
      setSelected({
        ...selected,
        version: { ...selected.version, status: 'generating_model', latestJob: resumed },
      })
      await refreshProjects()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Existing model task could not be resumed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="pattern-workspace">
      <aside className="project-rail">
        <div className="rail-heading">
          <div><span>Local workspace</span><strong>Projects</strong></div>
          <button type="button" title="New project" onClick={() => setShowCreate(true)}><Plus size={18} /></button>
        </div>
        <div className="project-list">
          {projects.map((project) => (
            <button
              type="button"
              className={selected?.id === project.id && !showCreate ? 'active' : ''}
              onClick={() => void openProject(project.id)}
              key={project.id}
            >
              <span><strong>{project.name}</strong><small>{project.heightMm} mm · {statusLabels[project.status] || project.status}</small></span>
              <ChevronRight size={15} />
            </button>
          ))}
          {!projects.length && !loading && <p>No projects yet</p>}
        </div>
        <div className="capability-strip">
          <span className={capabilities?.openRouter ? 'ready' : ''}><i />OpenRouter</span>
          <span className={capabilities?.meshy ? 'ready' : ''}><i />Meshy</span>
          {capabilities?.meshyBalance != null && <small>{capabilities.meshyBalance} credits</small>}
        </div>
      </aside>

      <main className="project-main">
        {error && <div className="workspace-alert" role="alert"><AlertTriangle size={17} />{error}</div>}
        {showCreate ? (
          <CreateProjectForm busy={loading} onSubmit={createProject} />
        ) : selected ? (
          <ProjectWorkspace
            project={selected}
            capabilities={capabilities}
            busy={loading}
            onGenerate={generateModel}
            onResume={resumeModel}
          />
        ) : loading ? (
          <div className="workspace-loading"><LoaderCircle size={24} />Loading workspace</div>
        ) : (
          <CreateProjectForm busy={false} onSubmit={createProject} />
        )}
      </main>
    </div>
  )
}

function CreateProjectForm({ busy, onSubmit }: {
  busy: boolean
  onSubmit: (input: CreateProjectInput) => Promise<void>
}) {
  const [form, setForm] = useState(emptyProject)
  return (
    <section className="create-project" aria-labelledby="create-project-heading">
      <div className="create-intro">
        <p className="eyebrow">New experimental pattern</p>
        <h1 id="create-project-heading">Describe one simple plush.</h1>
        <p>Start with a rounded single body. Connected ears or one simple tail are supported.</p>
      </div>
      <form onSubmit={(event) => { event.preventDefault(); void onSubmit(form) }}>
        <label>
          <span>Project name</span>
          <input required maxLength={120} value={form.name} placeholder="Cloud rabbit" onChange={(event) => setForm({ ...form, name: event.target.value })} />
        </label>
        <label className="description-field">
          <span>Plush description</span>
          <textarea required minLength={3} maxLength={1200} rows={7} value={form.description} placeholder="A sleepy rounded cloud plush with two long rabbit ears and embroidered eyes" onChange={(event) => setForm({ ...form, description: event.target.value })} />
        </label>
        <div className="form-row">
          <label>
            <span>Finished height</span>
            <div className="unit-input"><input type="number" min="50" max="2000" value={form.heightMm} onChange={(event) => setForm({ ...form, heightMm: Number(event.target.value) })} /><b>mm</b></div>
          </label>
          <label>
            <span>Seam allowance</span>
            <div className="unit-input"><input type="number" min="0" max="50" step="0.5" value={form.seamAllowanceMm} onChange={(event) => setForm({ ...form, seamAllowanceMm: Number(event.target.value) })} /><b>mm</b></div>
          </label>
          <label>
            <span>Response language</span>
            <select value={form.locale} onChange={(event) => setForm({ ...form, locale: event.target.value as 'en' | 'zh-CN' })}>
              <option value="en">English</option>
              <option value="zh-CN">简体中文</option>
            </select>
          </label>
        </div>
        <button className="primary-command" disabled={busy} type="submit">
          {busy ? <LoaderCircle className="spin" size={18} /> : <Sparkles size={18} />}
          {busy ? 'Structuring request' : 'Create specification'}
        </button>
      </form>
      <p className="experimental-note">Geometry checks are deterministic. Results remain experimental and are not a guarantee of physical sewability.</p>
    </section>
  )
}

const pipelineStages = ['Specification', '3D model', 'Normalize', 'Segment', 'Flatten', 'Score', 'PDF']

function defaultStepFor(status: string, supported: boolean) {
  if (!supported) return 0
  if (status === 'model_review') return 2
  if (status === 'failed' || status === 'generating_model') return 1
  return 0
}

function ProjectWorkspace({ project, capabilities, busy, onGenerate, onResume }: {
  project: ProjectDetail
  capabilities: Capabilities | null
  busy: boolean
  onGenerate: () => Promise<void>
  onResume: () => Promise<void>
}) {
  const { version } = project
  const specification = version.specification
  const job = version.latestJob
  const normalizedModel = version.assets.find((asset) => asset.kind === 'normalized_glb')
  const report = version.assets.find((asset) => asset.kind === 'normalization_report')
  const isGenerating = job && ['queued', 'running'].includes(job.state)
  const completeThrough = version.status === 'model_review' ? 2 : version.status === 'generating_model' ? 0 : 0
  const lastStepIndex = pipelineStages.length - 1

  const [step, setStep] = useState(() => defaultStepFor(version.status, specification.supported))
  useEffect(() => {
    setStep(defaultStepFor(version.status, specification.supported))
  }, [project.id, version.status, specification.supported])

  return (
    <div className="project-workspace">
      <header className="project-heading">
        <div><p className="eyebrow">Version 1 · {version.heightMm} mm</p><h1>{project.name}</h1></div>
        <span className={`project-status ${version.status}`}>{statusLabels[version.status] || version.status}</span>
      </header>

      {step === 0 && (
        <section className="specification-review" aria-labelledby="specification-heading">
          <div className="spec-summary">
            <p className="section-index">01 / VALIDATED SPECIFICATION</p>
            <h2 id="specification-heading">{specification.summary}</h2>
            <p>{version.description}</p>
          </div>
          <dl className="spec-facts">
            <div><dt>Main volume</dt><dd>{specification.mainVolume.shape}</dd></div>
            <div><dt>Proportions</dt><dd>{specification.mainVolume.proportions}</dd></div>
            <div><dt>Symmetry</dt><dd>{specification.symmetry.replace('_', ' ')}</dd></div>
            <div><dt>Connected features</dt><dd>{specification.protrusions.length ? specification.protrusions.map((item) => `${item.count} × ${item.kind}`).join(', ') : 'None'}</dd></div>
          </dl>
          {specification.assumptions.length > 0 && <div className="assumptions"><strong>Assumptions</strong>{specification.assumptions.map((item) => <span key={item}>{item}</span>)}</div>}
        </section>
      )}

      {step === 0 && !specification.supported && (
        <div className="scope-block"><AlertTriangle size={20} /><div><strong>Outside the supported MVP scope</strong><p>{specification.reasonCodes.join(', ')}</p></div></div>
      )}

      {step === 1 && !specification.supported && (
        <div className="step-locked"><AlertTriangle size={20} /><div><strong>Specification isn't supported yet</strong><p>Update the description on the specification step before generating a model.</p></div></div>
      )}
      {step === 1 && specification.supported && isGenerating && (
        <section className="generation-progress" aria-live="polite">
          <div><LoaderCircle className="spin" size={20} /><span><strong>{job.stage === 'queued' ? 'Waiting for worker' : 'Meshy is generating the model'}</strong><small>{job.progress}% complete</small></span></div>
          <progress max="100" value={job.progress} />
        </section>
      )}
      {step === 1 && specification.supported && !isGenerating && version.status === 'draft' && (
        <section className="generation-command">
          <div><p className="section-index">02 / 3D GENERATION</p><h2>Generate one geometry candidate</h2><p>Meshy preview creates an untextured GLB for deterministic mesh checks.</p></div>
          <button className="primary-command" type="button" disabled={busy || !capabilities?.meshy || (capabilities.meshyBalance ?? 0) < 20} onClick={() => void onGenerate()}>
            {busy ? <LoaderCircle className="spin" size={18} /> : <Box size={18} />}
            Generate model · about 20 credits
          </button>
        </section>
      )}
      {step === 1 && version.status === 'failed' && (
        <div className="scope-block">
          <AlertTriangle size={20} />
          <div className="failure-copy">
            <strong>Generation or mesh validation failed</strong>
            <p>{job?.errorMessage || job?.errorCode || specification.reasonCodes.join(', ')}</p>
            {job?.providerStatus && <small>Meshy status: {job.providerStatus}</small>}
            {job && ['PROVIDER_GENERATION_FAILED', 'PROVIDER_ASSET_INVALID'].includes(job.errorCode || '') && (
              <button className="primary-command" type="button" disabled={busy} onClick={() => void onResume()}>
                {busy ? <LoaderCircle className="spin" size={18} /> : <Box size={18} />}
                Continue existing Meshy task
              </button>
            )}
          </div>
        </div>
      )}
      {step === 1 && version.status === 'model_review' && (
        <div className="step-locked"><Check size={20} /><div><strong>3D model generated</strong><p>The raw geometry passed generation. Go to the next step to review the normalized mesh.</p></div></div>
      )}

      {step === 2 && version.status === 'model_review' && normalizedModel ? (
        <section className="model-review" aria-labelledby="model-review-heading">
          <div className="model-review-copy">
            <p className="section-index">03 / MODEL REVIEW</p>
            <h2 id="model-review-heading">Normalized geometry</h2>
            <p>Drag to inspect the generated shape. This model has passed the current closed-mesh and winding checks.</p>
            <div className="asset-actions">
              <a href={normalizedModel.url} download><Download size={16} />Normalized GLB</a>
              {report && <a href={report.url} download><Download size={16} />Diagnostic JSON</a>}
            </div>
          </div>
          <Suspense fallback={<div className="model-loading">Loading 3D model</div>}>
            <ModelViewer url={normalizedModel.url} />
          </Suspense>
        </section>
      ) : step === 2 ? (
        <div className="step-locked"><AlertTriangle size={20} /><div><strong>Not reached yet</strong><p>Complete the 3D model generation step first.</p></div></div>
      ) : null}

      {step >= 3 && (
        <div className="step-locked"><AlertTriangle size={20} /><div><strong>{pipelineStages[step]} isn't implemented yet</strong><p>This step is planned but not available in the current MVP.</p></div></div>
      )}

      <section className="pipeline-state" aria-label="Pattern pipeline state">
        {pipelineStages.map((stage, index) => {
          const state = index <= completeThrough ? 'complete' : index === completeThrough + 1 ? 'current' : 'future'
          return (
            <button
              type="button"
              className={`${state}${index === step ? ' viewing' : ''}`}
              key={stage}
              onClick={() => setStep(index)}
              aria-current={index === step ? 'step' : undefined}
            >
              {state === 'complete' ? <Check size={14} /> : <i />}{stage}
            </button>
          )
        })}
      </section>

      <div className="step-nav">
        <button type="button" onClick={() => setStep((current) => Math.max(0, current - 1))} disabled={step === 0}>
          <ChevronLeft size={16} />Previous step
        </button>
        <span>{step + 1} / {pipelineStages.length} · {pipelineStages[step]}</span>
        <button type="button" onClick={() => setStep((current) => Math.min(lastStepIndex, current + 1))} disabled={step === lastStepIndex}>
          Next step<ChevronRight size={16} />
        </button>
      </div>
    </div>
  )
}