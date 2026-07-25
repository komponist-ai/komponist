'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  AlertTriangle, Archive, ChevronDown, Clock3, FileText, LayoutDashboard,
  Loader2, Lock, Quote, RotateCcw, Send, ShieldCheck, Sparkles, X,
} from 'lucide-react'
import AppLayout from '../../components/AppLayout'
import StudioTopbar from '../../components/StudioTopbar'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { API_URL, apiFetch, getActiveOrgId } from '../../lib/api'

// ---------------------------------------------------------------- types ----

type Visibility = 'organization' | 'departments' | 'private'

type ComponentSpec = {
  id: string
  type: string
  title: string
  description: string
  narrative: string
  position: { row: number; column: number; width: number }
  binding: { query: string; limit: number; entity_ids: string[] }
  options: { show_sources: boolean; empty_text: string; accent: string }
}
type CanvasSpec = {
  schema_version: string
  title: string
  description: string
  components: ComponentSpec[]
}
type SourceRow = {
  id: string
  title?: string
  reference?: string
  excerpt?: string
  page?: number | null
  line_start?: number | null
  line_end?: number | null
  komponist_path: string
  supports?: string
}
type ComponentData = {
  kind: string
  rows: Array<Record<string, unknown>>
  sources: SourceRow[]
  value?: unknown
  truncated?: boolean
  error?: string
  note?: string
}
type CanvasData = {
  components: Record<string, ComponentData>
  sources: SourceRow[]
  permission_scope: {
    access_all_departments: boolean
    department_ids: string[]
    confirmed_only: boolean
  }
}
type CanvasSummary = {
  id: string
  title: string
  description: string
  visibility: Visibility
  department_ids?: string[]
  current_version: number
  status: string
  creator_name?: string | null
  is_owner?: boolean
  updated_at: string
}
type CanvasVersionSummary = {
  id: string
  version: number
  prompt: string
  origin: string
  provider?: string | null
  model?: string | null
  restored_from_version?: number | null
  created_at: string
}
type CanvasDetail = CanvasSummary & {
  spec: CanvasSpec
  data: CanvasData
  version: CanvasVersionSummary
}
type ExampleSummary = {
  key: string
  title: string
  description: string
  component_count: number
}

type MobileTab = 'view' | 'sources' | 'configure' | 'history'
type Department = { id: string; name: string }
type ActiveFilters = { types: string[]; confidences: string[]; search: string }

const emptyFilters: ActiveFilters = { types: [], confidences: [], search: '' }

// Filters narrow what is already on screen. They never re-query, so they can
// only ever hide rows the viewer was already permitted to see.
const FILTERABLE_KINDS = [
  'entity_list', 'timeline_events', 'relationship_list', 'evidence_list',
  'source_passages',
]

function rowText(row: Record<string, unknown>) {
  return [row.statement, row.from_statement, row.to_statement, row.excerpt, row.title]
    .filter(Boolean).join(' ').toLowerCase()
}

function rowMatches(row: Record<string, unknown>, filters: ActiveFilters) {
  const type = String(row.entity_type ?? row.from_type ?? '')
  const confidence = String(row.confidence ?? '')
  if (filters.types.length && type && !filters.types.includes(type)) return false
  if (filters.confidences.length && confidence && !filters.confidences.includes(confidence)) {
    return false
  }
  if (filters.search && !rowText(row).includes(filters.search.toLowerCase())) return false
  return true
}

function applyFilters(data: ComponentData | undefined, filters: ActiveFilters) {
  if (!data || !FILTERABLE_KINDS.includes(data.kind)) return data
  const active = filters.types.length || filters.confidences.length || filters.search
  if (!active) return data
  return { ...data, rows: data.rows.filter((row) => rowMatches(row, filters)) }
}

// ------------------------------------------------------------- renderer ----

// The renderer's allowlist. A specification is validated server-side too, but
// the client refuses anything it does not recognise as well: an unknown type
// renders a controlled message and never executes anything.
const RENDERABLE_TYPES = [
  'metric', 'entity_list', 'relationship_table', 'status_board', 'timeline',
  'evidence_list', 'markdown_narrative', 'filter_bar',
] as const

const accentTone: Record<string, string> = {
  neutral: 'border-line',
  positive: 'border-teal/40',
  warning: 'border-orange/40',
  danger: 'border-danger/40',
  info: 'border-info/40',
}

function sourceLocation(source: SourceRow) {
  if (source.page != null) return `Page ${source.page}`
  if (source.line_start != null) {
    return source.line_end && source.line_end !== source.line_start
      ? `Lines ${source.line_start}–${source.line_end}`
      : `Line ${source.line_start}`
  }
  return 'Source passage'
}

function formatDate(value?: string | null) {
  if (!value) return ''
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return ''
  return new Intl.DateTimeFormat('en', { day: 'numeric', month: 'short' }).format(parsed)
}

function EmptyBody({ text }: { text: string }) {
  return <p className="px-1 py-6 text-center text-xs text-muted">{text}</p>
}

function SourceChips({ sources }: { sources: SourceRow[] }) {
  if (!sources.length) return null
  return (
    <div className="mt-3 flex flex-wrap gap-1.5 border-t border-line pt-2">
      {sources.slice(0, 6).map((source) => (
        <Link
          key={source.id}
          href={source.komponist_path}
          className="inline-flex max-w-full items-center gap-1 rounded-full border border-line bg-paper-2 px-2 py-0.5 font-mono text-[9px] text-muted hover:border-ink"
        >
          <Quote className="size-2.5 shrink-0" />
          <span className="truncate">{source.title || source.reference || 'Source'}</span>
        </Link>
      ))}
    </div>
  )
}

/** Narrative text is rendered as plain paragraphs on purpose.
 *  The spec already refuses URLs and Markdown links; not parsing Markdown at
 *  all means there is no path by which one could be rendered anyway. */
function NarrativeBody({ text }: { text: string }) {
  return (
    <div className="space-y-2">
      {text.split(/\n{2,}/).map((paragraph, index) => (
        <p key={index} className="whitespace-pre-line break-words text-xs leading-5 text-ink-2">
          {paragraph}
        </p>
      ))}
    </div>
  )
}

function MetricBody({ data }: { data: ComponentData }) {
  if (data.kind === 'aggregate_by_type' || data.kind === 'aggregate_by_confidence') {
    if (!data.rows.length) return null
    return (
      <ul className="space-y-1.5">
        {data.rows.map((row, index) => (
          <li key={index} className="flex items-center justify-between gap-2">
            <span className="min-w-0 truncate text-xs capitalize">{String(row.label)}</span>
            <span className="font-mono text-sm font-black">{String(row.value)}</span>
          </li>
        ))}
      </ul>
    )
  }
  if (data.value == null || data.value === '') return null
  const isNumber = typeof data.value === 'number'
  return (
    <p className={isNumber ? 'text-3xl font-black' : 'text-sm font-bold leading-5'}>
      {String(data.value)}
    </p>
  )
}

function EntityListBody({ data }: { data: ComponentData }) {
  if (!data.rows.length) return null
  return (
    <ul className="space-y-2">
      {data.rows.map((row, index) => (
        <li key={String(row.id ?? index)} className="rounded-lg border border-line bg-paper-2 px-3 py-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge className="border-line bg-white text-[9px] uppercase text-muted">
              {String(row.entity_type ?? 'Fact')}
            </Badge>
            {!!row.confidence && (
              <span className="font-mono text-[9px] uppercase text-faint">
                {String(row.confidence)}
              </span>
            )}
          </div>
          <p className="mt-1 break-words text-xs leading-5">{String(row.statement ?? '')}</p>
        </li>
      ))}
    </ul>
  )
}

/** Groups facts into columns by confidence, which is the dimension that
 *  actually varies: Canvas only ever shows confirmed knowledge. */
function StatusBoardBody({ data }: { data: ComponentData }) {
  const buckets = new Map<string, Array<Record<string, unknown>>>()
  if (data.kind === 'aggregate_by_confidence') {
    for (const row of data.rows) buckets.set(String(row.label), [])
  } else {
    for (const row of data.rows) {
      const key = String(row.confidence || 'unspecified')
      if (!buckets.has(key)) buckets.set(key, [])
      buckets.get(key)!.push(row)
    }
  }
  if (!buckets.size) return null

  const counts = new Map<string, number>()
  if (data.kind === 'aggregate_by_confidence') {
    for (const row of data.rows) counts.set(String(row.label), Number(row.value))
  }

  return (
    <div className="-mx-1 flex gap-2 overflow-x-auto px-1">
      {[...buckets.entries()].map(([label, rows]) => (
        <div key={label} className="min-w-[150px] flex-1 rounded-lg border border-line bg-paper-2 p-2">
          <div className="flex items-baseline justify-between gap-2 border-b border-line pb-1.5">
            <span className="font-mono text-[9px] font-bold uppercase tracking-wide text-ink-2">
              {label}
            </span>
            <span className="font-mono text-xs font-black">
              {counts.get(label) ?? rows.length}
            </span>
          </div>
          <ul className="mt-1.5 space-y-1.5">
            {rows.slice(0, 8).map((row, index) => (
              <li key={String(row.id ?? index)} className="rounded border border-line bg-white px-2 py-1.5">
                <p className="break-words text-[11px] leading-4">{String(row.statement ?? '')}</p>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}

function TimelineBody({ data }: { data: ComponentData }) {
  if (!data.rows.length) return null
  return (
    <ol className="space-y-2">
      {data.rows.map((row, index) => (
        <li key={String(row.id ?? index)} className="flex gap-2.5">
          <div className="flex flex-col items-center pt-1">
            <span className="size-1.5 shrink-0 rounded-full bg-orange" />
            {index < data.rows.length - 1 && <span className="mt-0.5 w-px flex-1 bg-line" />}
          </div>
          <div className="min-w-0 pb-1">
            <p className="font-mono text-[9px] uppercase text-faint">
              {formatDate(row.occurred_at as string) || 'Undated'} · {String(row.entity_type ?? 'Fact')}
            </p>
            <p className="mt-0.5 break-words text-xs leading-5">{String(row.statement ?? '')}</p>
          </div>
        </li>
      ))}
    </ol>
  )
}

function RelationshipBody({ data }: { data: ComponentData }) {
  if (!data.rows.length) return null
  return (
    // Wide content scrolls inside its own container so the page never does.
    <div className="-mx-1 overflow-x-auto px-1">
      <table className="w-full min-w-[420px] border-collapse text-left text-xs">
        <thead>
          <tr className="border-b border-line font-mono text-[9px] uppercase tracking-wide text-faint">
            <th className="py-1.5 pr-2 font-bold">From</th>
            <th className="py-1.5 pr-2 font-bold">Relation</th>
            <th className="py-1.5 font-bold">To</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row, index) => (
            <tr key={index} className="border-b border-line last:border-0 align-top">
              <td className="py-1.5 pr-2">{String(row.from_statement ?? '')}</td>
              <td className="py-1.5 pr-2 font-mono text-[10px] text-muted">
                {String(row.relation ?? '')}
              </td>
              <td className="py-1.5">{String(row.to_statement ?? '')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function EvidenceBody({ data }: { data: ComponentData }) {
  if (!data.rows.length) return null
  return (
    <ul className="space-y-2">
      {data.rows.map((row, index) => {
        const passages = (row.passages as SourceRow[] | undefined) ?? [row as unknown as SourceRow]
        return (
          <li key={String(row.reference ?? row.id ?? index)}>
            <p className="font-mono text-[9px] uppercase tracking-wide text-faint">
              {String(row.title ?? row.reference ?? 'Source')}
            </p>
            <ul className="mt-1 space-y-1.5">
              {passages.map((passage) => (
                <li key={passage.id} className="rounded-lg border border-line bg-paper-2 px-3 py-2">
                  <p className="break-words text-xs leading-5 text-ink-2">“{passage.excerpt}”</p>
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    <span className="font-mono text-[9px] uppercase text-faint">
                      {sourceLocation(passage)}
                    </span>
                    <Link
                      href={passage.komponist_path}
                      className="font-mono text-[9px] uppercase text-orange-dark hover:underline"
                    >
                      Open passage
                    </Link>
                  </div>
                </li>
              ))}
            </ul>
          </li>
        )
      })}
    </ul>
  )
}

function CanvasComponent({
  spec, data, filters, facets, onFilterChange,
}: {
  spec: ComponentSpec
  data?: ComponentData
  filters: ActiveFilters
  facets: { types: string[]; confidences: string[] }
  onFilterChange: (next: ActiveFilters) => void
}) {
  const known = (RENDERABLE_TYPES as ReadonlyArray<string>).includes(spec.type)
  const tone = accentTone[spec.options?.accent] ?? 'border-line'

  // A component this build does not know about is reported, never executed.
  if (!known) {
    return (
      <section className="rounded-xl border-2 border-danger/40 bg-danger-soft p-4">
        <p className="flex items-center gap-2 text-xs font-bold text-danger">
          <AlertTriangle className="size-3.5" /> Unsupported component
        </p>
        <p className="mt-1 text-[11px] leading-4 text-danger">
          This view uses a component type this version of Komponist does not
          render. Nothing was executed.
        </p>
      </section>
    )
  }

  if (spec.type === 'filter_bar') {
    const toggle = (group: 'types' | 'confidences', value: string) => {
      const current = filters[group]
      onFilterChange({
        ...filters,
        [group]: current.includes(value)
          ? current.filter((item) => item !== value)
          : [...current, value],
      })
    }
    const active = filters.types.length || filters.confidences.length || filters.search
    return (
      <section className={`rounded-xl border-2 ${tone} bg-paper-2 px-4 py-3`}>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-ink-2">
            {spec.title}
          </p>
          {active ? (
            <button
              type="button"
              onClick={() => onFilterChange(emptyFilters)}
              className="font-mono text-[9px] uppercase text-orange-dark hover:underline"
            >
              Clear
            </button>
          ) : null}
        </div>
        {spec.description && (
          <p className="mt-1 text-[11px] leading-4 text-muted">{spec.description}</p>
        )}
        <div className="mt-2.5 flex flex-col gap-2">
          <input
            value={filters.search}
            onChange={(event) => onFilterChange({ ...filters, search: event.target.value })}
            placeholder="Search this view…"
            aria-label="Search this view"
            className="w-full rounded-lg border border-line bg-white px-3 py-1.5 text-xs outline-none focus:border-orange"
          />
          {facets.types.length > 1 && (
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by type">
              {facets.types.map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => toggle('types', value)}
                  aria-pressed={filters.types.includes(value)}
                  className={`rounded-full border px-2.5 py-0.5 text-[10px] ${
                    filters.types.includes(value)
                      ? 'border-ink bg-orange text-white'
                      : 'border-line bg-white text-muted hover:border-ink'
                  }`}
                >
                  {value}
                </button>
              ))}
            </div>
          )}
          {facets.confidences.length > 1 && (
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by confidence">
              {facets.confidences.map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => toggle('confidences', value)}
                  aria-pressed={filters.confidences.includes(value)}
                  className={`rounded-full border px-2.5 py-0.5 text-[10px] capitalize ${
                    filters.confidences.includes(value)
                      ? 'border-ink bg-ink text-white'
                      : 'border-line bg-white text-muted hover:border-ink'
                  }`}
                >
                  {value}
                </button>
              ))}
            </div>
          )}
        </div>
      </section>
    )
  }

  const body = (() => {
    if (!data) return null
    if (FILTERABLE_KINDS.includes(data.kind) && !data.rows.length && !data.error) {
      return null
    }
    if (data.error) {
      return (
        <p className="flex items-start gap-1.5 text-[11px] leading-4 text-danger">
          <AlertTriangle className="mt-0.5 size-3 shrink-0" /> {data.error}
        </p>
      )
    }
    switch (spec.type) {
      case 'metric':
        return <MetricBody data={data} />
      case 'entity_list':
        return <EntityListBody data={data} />
      case 'status_board':
        return <StatusBoardBody data={data} />
      case 'timeline':
        return <TimelineBody data={data} />
      case 'relationship_table':
        return <RelationshipBody data={data} />
      case 'evidence_list':
        return <EvidenceBody data={data} />
      case 'markdown_narrative':
        return <NarrativeBody text={spec.narrative} />
      default:
        return null
    }
  })()

  return (
    <section className={`flex h-full flex-col rounded-xl border-2 ${tone} bg-white p-4`}>
      <header>
        <h3 className="break-words text-sm font-black leading-5">{spec.title}</h3>
        {spec.description && (
          <p className="mt-0.5 break-words text-[11px] leading-4 text-muted">
            {spec.description}
          </p>
        )}
      </header>
      <div className="mt-3 flex-1">
        {body ?? (
          <EmptyBody
            text={
              spec.options?.empty_text
              || 'Nothing here is visible to you yet.'
            }
          />
        )}
      </div>
      {data?.truncated && (
        <p className="mt-2 font-mono text-[9px] uppercase text-faint">
          Showing the first {data.rows.length}
        </p>
      )}
      {spec.options?.show_sources && data?.sources?.length ? (
        <SourceChips sources={data.sources} />
      ) : null}
    </section>
  )
}

// ----------------------------------------------------------------- page ----

export default function CanvasPage() {
  const [canvases, setCanvases] = useState<CanvasSummary[]>([])
  const [examples, setExamples] = useState<ExampleSummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [canvas, setCanvas] = useState<CanvasDetail | null>(null)
  const [versions, setVersions] = useState<CanvasVersionSummary[]>([])
  const [viewingVersion, setViewingVersion] = useState<string | null>(null)

  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [prompt, setPrompt] = useState('')
  const [change, setChange] = useState('')
  const [showPicker, setShowPicker] = useState(false)
  const [filters, setFilters] = useState<ActiveFilters>(emptyFilters)
  const [departments, setDepartments] = useState<Department[]>([])
  const [showArchived, setShowArchived] = useState(false)
  const [mobileTab, setMobileTab] = useState<MobileTab>('view')

  const orgId = () => getActiveOrgId()

  const loadList = useCallback(async () => {
    const response = await apiFetch(
      `${API_URL}/canvases?org_id=${encodeURIComponent(orgId())}`
      + `&include_archived=${showArchived}`,
    )
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.detail || 'Could not load Canvas')
    setCanvases(payload.canvases)
    setExamples(payload.examples ?? [])
    setSelectedId((current) => current ?? payload.canvases[0]?.id ?? null)
  }, [showArchived])

  const loadCanvas = useCallback(async (id: string, version?: string | null) => {
    const org = encodeURIComponent(orgId())
    const suffix = version ? `&version=${encodeURIComponent(version)}` : ''
    const [detail, history] = await Promise.all([
      apiFetch(`${API_URL}/canvases/${id}?org_id=${org}${suffix}`),
      apiFetch(`${API_URL}/canvases/${id}/versions?org_id=${org}`),
    ])
    const payload = await detail.json()
    if (!detail.ok) throw new Error(payload.detail || 'Could not load this view')
    setCanvas(payload)
    if (history.ok) setVersions((await history.json()).versions)
  }, [])

  useEffect(() => {
    const bootstrap = async () => {
      setLoading(true)
      setError(null)
      try {
        const departmentsResponse = await apiFetch(
          `${API_URL}/departments?org_id=${encodeURIComponent(orgId())}`,
        ).catch(() => null)
        if (departmentsResponse?.ok) {
          setDepartments((await departmentsResponse.json()).departments ?? [])
        }
        await loadList()
      } catch (bootError) {
        setError(bootError instanceof Error ? bootError.message : 'Could not load Canvas')
      } finally {
        setLoading(false)
      }
    }
    void bootstrap()
  }, [loadList])

  useEffect(() => {
    setFilters(emptyFilters)
  }, [selectedId, viewingVersion])

  useEffect(() => {
    if (!selectedId) {
      setCanvas(null)
      return
    }
    setLoading(true)
    void loadCanvas(selectedId, viewingVersion)
      .catch((loadError) => {
        setError(loadError instanceof Error ? loadError.message : 'Could not load this view')
      })
      .finally(() => setLoading(false))
  }, [selectedId, viewingVersion, loadCanvas])

  const mutate = async (path: string, init: RequestInit = {}) => {
    setWorking(true)
    setError(null)
    try {
      const separator = path.includes('?') ? '&' : '?'
      const response = await apiFetch(
        `${API_URL}${path}${separator}org_id=${encodeURIComponent(orgId())}`,
        { headers: { 'Content-Type': 'application/json' }, ...init },
      )
      const payload = response.status === 204 ? null : await response.json().catch(() => null)
      if (!response.ok) throw new Error(payload?.detail || 'The action could not be completed')
      return payload
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : 'The action could not be completed')
      return null
    } finally {
      setWorking(false)
    }
  }

  const createFromPrompt = async () => {
    if (!prompt.trim()) return
    setGenerating(true)
    try {
      const created = await mutate('/canvases', {
        method: 'POST',
        body: JSON.stringify({ prompt, visibility: 'private' }),
      })
      if (created?.id) {
        setPrompt('')
        await loadList()
        setViewingVersion(null)
        setSelectedId(created.id)
      }
    } finally {
      setGenerating(false)
    }
  }

  const tryExample = async (key: string) => {
    setGenerating(true)
    try {
      const created = await mutate('/canvases/examples', {
        method: 'POST',
        body: JSON.stringify({ example: key, visibility: 'private' }),
      })
      if (created?.id) {
        await loadList()
        setViewingVersion(null)
        setSelectedId(created.id)
      }
    } finally {
      setGenerating(false)
    }
  }

  const refine = async () => {
    if (!selectedId || !change.trim()) return
    setGenerating(true)
    try {
      const result = await mutate(`/canvases/${selectedId}/refine`, {
        method: 'POST',
        body: JSON.stringify({ instruction: change }),
      })
      if (result) {
        setChange('')
        setViewingVersion(null)
        await loadCanvas(selectedId, null)
        await loadList()
      }
    } finally {
      setGenerating(false)
    }
  }

  const restore = async (versionId: string) => {
    if (!selectedId) return
    const result = await mutate(
      `/canvases/${selectedId}/versions/${versionId}/restore`, { method: 'POST' },
    )
    if (result) {
      setViewingVersion(null)
      await loadCanvas(selectedId, null)
    }
  }

  const changeVisibility = async (visibility: Visibility) => {
    if (!selectedId) return
    const body: Record<string, unknown> = { visibility }
    // A department-scoped view needs at least one department, so seed it with
    // the first available one rather than letting the API reject the change.
    if (visibility === 'departments' && !(canvas?.department_ids ?? []).length) {
      if (!departments.length) {
        setError('Create a department first to scope this view to one.')
        return
      }
      body.department_ids = [departments[0].id]
    }
    const updated = await mutate(`/canvases/${selectedId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    })
    if (updated) {
      await loadCanvas(selectedId, viewingVersion)
      await loadList()
    }
  }

  const toggleDepartment = async (departmentId: string) => {
    if (!selectedId || !canvas) return
    const current = canvas.department_ids ?? []
    const next = current.includes(departmentId)
      ? current.filter((id) => id !== departmentId)
      : [...current, departmentId]
    if (!next.length) {
      setError('A department-scoped view needs at least one department.')
      return
    }
    const updated = await mutate(`/canvases/${selectedId}`, {
      method: 'PATCH',
      body: JSON.stringify({ department_ids: next }),
    })
    if (updated) await loadCanvas(selectedId, viewingVersion)
  }

  const archive = async () => {
    if (!selectedId) return
    const updated = await mutate(`/canvases/${selectedId}/archive`, { method: 'POST' })
    if (updated) {
      setSelectedId(null)
      await loadList()
    }
  }

  const ordered = useMemo(() => {
    if (!canvas) return []
    return [...canvas.spec.components].sort(
      (a, b) => a.position.row - b.position.row || a.position.column - b.position.column,
    )
  }, [canvas])

  const facets = useMemo(() => {
    const types = new Set<string>()
    const confidences = new Set<string>()
    for (const payload of Object.values(canvas?.data.components ?? {})) {
      if (!FILTERABLE_KINDS.includes(payload.kind)) continue
      for (const row of payload.rows) {
        const type = String(row.entity_type ?? row.from_type ?? '')
        const confidence = String(row.confidence ?? '')
        if (type) types.add(type)
        if (confidence) confidences.add(confidence)
      }
    }
    return { types: [...types].sort(), confidences: [...confidences].sort() }
  }, [canvas?.data.components])

  const isHistoricView = !!viewingVersion
    && canvas?.version?.version !== canvas?.current_version

  const canvasList = (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
        <h2 className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-ink-2">
          Saved views
        </h2>
        <label className="flex cursor-pointer items-center gap-1.5 text-[10px] text-muted">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(event) => setShowArchived(event.target.checked)}
            className="size-3 accent-orange"
          />
          Archived
        </label>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {canvases.length === 0 ? (
          <p className="px-2 py-6 text-center text-[11px] leading-4 text-muted">
            No saved views yet. Describe one below, or start from an example.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {canvases.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedId(item.id)
                    setViewingVersion(null)
                    setShowPicker(false)
                    setMobileTab('view')
                  }}
                  aria-current={item.id === selectedId}
                  className={`w-full rounded-lg border px-3 py-2.5 text-left transition ${
                    item.id === selectedId
                      ? 'border-ink bg-paper-2 shadow-[2px_2px_0_var(--color-ink)]'
                      : 'border-line bg-white hover:border-ink'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="min-w-0 break-words text-sm font-bold leading-5">
                      {item.title}
                    </span>
                    {item.visibility === 'private' && (
                      <Lock className="mt-0.5 size-3 shrink-0 text-muted" />
                    )}
                  </div>
                  <p className="mt-1 font-mono text-[9px] uppercase text-faint">
                    v{item.current_version} · {formatDate(item.updated_at)}
                    {item.visibility === 'organization' ? ' · shared' : ''}
                    {item.visibility === 'departments' ? ' · departments' : ''}
                    {item.status === 'archived' ? ' · archived' : ''}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )

  const sourcesPanel = (
    <section className="rounded-xl border-2 border-ink bg-white">
      <header className="border-b border-line px-4 py-3">
        <h3 className="flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-ink-2">
          <Quote className="size-3.5 text-orange" /> Sources
        </h3>
      </header>
      <div className="p-4">
        {!canvas?.data.sources.length ? (
          <p className="text-xs text-muted">
            No source passages back this view yet.
          </p>
        ) : (
          <ul className="space-y-2">
            {canvas.data.sources.map((source) => (
              <li key={source.id} className="rounded-lg border border-line bg-paper-2 px-3 py-2">
                <p className="break-words text-[11px] font-bold">
                  {source.title || source.reference}
                </p>
                {source.excerpt && (
                  <p className="mt-0.5 line-clamp-2 text-[11px] leading-4 text-muted">
                    “{source.excerpt}”
                  </p>
                )}
                <Link
                  href={source.komponist_path}
                  className="mt-1 inline-block font-mono text-[9px] uppercase text-orange-dark hover:underline"
                >
                  {sourceLocation(source)} · open
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )

  const configurePanel = canvas && (
    <section className="rounded-xl border-2 border-ink bg-white">
      <header className="border-b border-line px-4 py-3">
        <h3 className="flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-ink-2">
          <ShieldCheck className="size-3.5 text-orange" /> This view
        </h3>
      </header>
      <div className="space-y-2 p-4">
        <p className="text-xs leading-5 text-ink-2">{canvas.spec.description}</p>
        <p className="text-[11px] leading-4 text-muted">
          Data is resolved against your own permissions every time this view
          loads, so a colleague may legitimately see different numbers.
        </p>
        <dl className="space-y-1 pt-1 font-mono text-[9px] uppercase text-faint">
          <div className="flex justify-between gap-2">
            <dt>Confirmed only</dt>
            <dd>{canvas.data.permission_scope.confirmed_only ? 'yes' : 'no'}</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt>All departments</dt>
            <dd>{canvas.data.permission_scope.access_all_departments ? 'yes' : 'no'}</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt>Components</dt>
            <dd>{canvas.spec.components.length}</dd>
          </div>
          {canvas.version.provider && (
            <div className="flex justify-between gap-2">
              <dt>Generated by</dt>
              <dd>{canvas.version.provider}</dd>
            </div>
          )}
        </dl>
      </div>
    </section>
  )

  const historyPanel = canvas && (
    <section className="rounded-xl border-2 border-ink bg-white">
      <header className="border-b border-line px-4 py-3">
        <h3 className="flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-ink-2">
          <Clock3 className="size-3.5 text-orange" /> History
        </h3>
      </header>
      <div className="p-4">
        <ul className="space-y-2">
          {versions.map((version) => {
            const active = version.version === canvas.version.version
            return (
              <li
                key={version.id}
                className={`rounded-lg border px-3 py-2 ${
                  active ? 'border-ink bg-paper-2' : 'border-line bg-white'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[10px] font-bold">v{version.version}</span>
                  <span className="font-mono text-[9px] uppercase text-faint">
                    {version.origin}
                  </span>
                </div>
                {version.prompt && (
                  <p className="mt-1 line-clamp-2 break-words text-[11px] leading-4 text-muted">
                    {version.prompt}
                  </p>
                )}
                <div className="mt-1.5 flex flex-wrap gap-2">
                  {!active && (
                    <button
                      type="button"
                      onClick={() => setViewingVersion(version.id)}
                      className="font-mono text-[9px] uppercase text-orange-dark hover:underline"
                    >
                      View
                    </button>
                  )}
                  {canvas.is_owner && version.version !== canvas.current_version && (
                    <button
                      type="button"
                      onClick={() => void restore(version.id)}
                      disabled={working}
                      className="font-mono text-[9px] uppercase text-orange-dark hover:underline disabled:opacity-40"
                    >
                      Restore
                    </button>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      </div>
    </section>
  )

  const rightRail = (
    <div className="space-y-4">
      {configurePanel}
      {sourcesPanel}
      {historyPanel}
    </div>
  )

  const canvasBody = canvas && (
    <>
      {isHistoricView && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border-2 border-info/40 bg-info-soft px-3 py-2">
          <p className="text-[11px] leading-4 text-info">
            Viewing version {canvas.version.version} of {canvas.current_version}.
          </p>
          <Button size="sm" variant="ghost" onClick={() => setViewingVersion(null)}>
            Back to latest
          </Button>
        </div>
      )}
      {/* A 12-column grid on desktop; a single column on small screens. */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-12">
        {ordered.map((component) => (
          <div
            key={component.id}
            className="md:[grid-column:span_var(--span)]"
            style={{ ['--span' as string]: String(Math.min(12, Math.max(1, component.position.width))) }}
          >
            <CanvasComponent
              spec={component}
              data={applyFilters(canvas.data.components[component.id], filters)}
              filters={filters}
              facets={facets}
              onFilterChange={setFilters}
            />
          </div>
        ))}
      </div>
    </>
  )

  return (
    <AppLayout>
      <StudioTopbar
        section="Dynamic interfaces"
        title="Canvas"
        description="Describe a view of your company knowledge and get a cited, working one"
        icon={LayoutDashboard}
      />

      <main className="min-h-[calc(100vh-78px)] bg-paper">
        {error && (
          <div className="flex items-start justify-between gap-3 border-b-2 border-ink bg-danger-soft px-4 py-2.5 sm:px-8">
            <p className="text-[11px] leading-4 text-danger">{error}</p>
            <button type="button" onClick={() => setError(null)} aria-label="Dismiss error">
              <X className="size-4 text-danger" />
            </button>
          </div>
        )}

        {/* Mobile: the saved-view list collapses into a selector. */}
        <div className="border-b-2 border-ink bg-white px-4 py-2 lg:hidden">
          <button
            type="button"
            onClick={() => setShowPicker((open) => !open)}
            aria-expanded={showPicker}
            className="flex w-full items-center justify-between gap-2 rounded-lg border border-line bg-paper-2 px-3 py-2 text-left"
          >
            <span className="min-w-0 truncate text-xs font-bold">
              {canvas?.title ?? 'Choose a view'}
            </span>
            <ChevronDown className={`size-4 shrink-0 transition ${showPicker ? 'rotate-180' : ''}`} />
          </button>
          <AnimatePresence>
            {showPicker && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden"
              >
                <div className="mt-2 max-h-[50vh] overflow-y-auto rounded-lg border border-line">
                  {canvasList}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <div className="mx-auto grid w-full max-w-[1600px] grid-cols-1 lg:grid-cols-[240px_minmax(0,1fr)] xl:grid-cols-[240px_minmax(0,1fr)_300px]">
          <aside className="hidden border-r-2 border-ink bg-white lg:block">
            {canvasList}
          </aside>

          <section className="min-w-0">
            {loading ? (
              <div className="grid min-h-[420px] place-items-center">
                <Loader2 className="size-7 animate-spin text-orange" />
              </div>
            ) : !canvas ? (
              <div className="grid min-h-[420px] place-items-center px-4 py-10">
                <div className="w-full max-w-lg text-center">
                  <LayoutDashboard className="mx-auto size-7 text-faint" />
                  <h2 className="mt-3 text-lg font-black">Describe a view</h2>
                  <p className="mx-auto mt-1 max-w-md text-xs leading-5 text-muted">
                    Ask for a dashboard of your confirmed company knowledge.
                    Komponist assembles it from approved building blocks and
                    cites every fact.
                  </p>
                  {examples.length > 0 && (
                    <div className="mt-5 space-y-2 text-left">
                      {examples.map((example) => (
                        <div
                          key={example.key}
                          className="rounded-lg border border-line bg-white px-3 py-2.5"
                        >
                          <p className="text-xs font-bold">{example.title}</p>
                          <p className="mt-0.5 text-[11px] leading-4 text-muted">
                            {example.description}
                          </p>
                          <Button
                            size="sm"
                            variant="outline"
                            className="mt-2"
                            onClick={() => void tryExample(example.key)}
                            disabled={generating}
                          >
                            {generating ? <Loader2 className="animate-spin" /> : <Sparkles />}
                            Try this example
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <>
                <header className="border-b-2 border-ink bg-white px-4 py-5 sm:px-6">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge className="border-line bg-paper-2 text-[9px] uppercase text-muted">
                      v{canvas.version.version}
                    </Badge>
                    {canvas.visibility === 'private' && (
                      <Badge className="border-line bg-paper-2 text-[9px] uppercase text-muted">
                        <Lock className="mr-1 inline size-2.5" /> Private
                      </Badge>
                    )}
                    {canvas.status === 'archived' && (
                      <Badge className="border-line bg-paper-2 text-[9px] uppercase text-muted">
                        Archived
                      </Badge>
                    )}
                  </div>
                  <h2 className="mt-2 break-words text-xl font-black tracking-tight sm:text-2xl">
                    {canvas.spec.title}
                  </h2>
                  <p className="mt-1.5 max-w-2xl break-words text-sm leading-6 text-muted">
                    {canvas.spec.description}
                  </p>

                  {canvas.is_owner && (
                    <div className="mt-4 flex flex-wrap items-center gap-2">
                      <label htmlFor="canvas-visibility" className="font-mono text-[9px] font-bold uppercase tracking-wide text-ink-2">
                        Who can see this
                      </label>
                      <select
                        id="canvas-visibility"
                        value={canvas.visibility}
                        onChange={(event) => void changeVisibility(event.target.value as Visibility)}
                        disabled={working}
                        className="rounded-lg border border-line bg-paper-2 px-2 py-1.5 text-xs outline-none focus:border-orange"
                      >
                        <option value="private">Only me</option>
                        <option value="organization">Everyone in the organization</option>
                        <option value="departments">Selected departments</option>
                      </select>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => void archive()}
                        disabled={working || canvas.status === 'archived'}
                      >
                        <Archive /> Archive
                      </Button>
                    </div>
                  )}
                  {canvas.is_owner && canvas.visibility === 'departments' && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {departments.length === 0 ? (
                        <p className="text-[11px] text-muted">
                          No departments exist yet, so this view stays visible to you only.
                        </p>
                      ) : departments.map((department) => {
                        const selected = (canvas.department_ids ?? []).includes(department.id)
                        return (
                          <button
                            key={department.id}
                            type="button"
                            onClick={() => void toggleDepartment(department.id)}
                            aria-pressed={selected}
                            disabled={working}
                            className={`rounded-full border px-2.5 py-1 text-[10px] ${
                              selected
                                ? 'border-ink bg-orange text-white'
                                : 'border-line bg-paper-2 text-muted hover:border-ink'
                            }`}
                          >
                            {department.name}
                          </button>
                        )
                      })}
                    </div>
                  )}
                </header>

                {/* Mobile tabs keep every panel reachable without three columns. */}
                <nav className="flex gap-1 overflow-x-auto border-b-2 border-ink bg-white px-2 xl:hidden" aria-label="Canvas sections">
                  {(['view', 'sources', 'configure', 'history'] as MobileTab[]).map((tab) => (
                    <button
                      key={tab}
                      type="button"
                      onClick={() => setMobileTab(tab)}
                      aria-current={mobileTab === tab ? 'page' : undefined}
                      className={`shrink-0 border-b-2 px-3 py-2.5 text-xs font-bold capitalize transition ${
                        mobileTab === tab
                          ? 'border-orange text-orange-dark'
                          : 'border-transparent text-muted hover:text-ink'
                      }`}
                    >
                      {tab}
                    </button>
                  ))}
                </nav>

                <div className="p-4 sm:p-6">
                  <div className="xl:hidden">
                    {mobileTab === 'view' && canvasBody}
                    {mobileTab === 'sources' && sourcesPanel}
                    {mobileTab === 'configure' && configurePanel}
                    {mobileTab === 'history' && historyPanel}
                  </div>
                  <div className="hidden xl:block">{canvasBody}</div>
                </div>
              </>
            )}
          </section>

          <aside className="hidden border-l-2 border-ink bg-paper p-4 xl:block">
            {canvas ? rightRail : null}
          </aside>
        </div>

        {/* Always-available request box: create when nothing is selected,
            refine when a view is open. */}
        <div className="sticky bottom-0 border-t-2 border-ink bg-white px-4 py-3 sm:px-6">
          <div className="mx-auto flex max-w-3xl flex-col gap-2 sm:flex-row">
            <input
              value={canvas ? change : prompt}
              onChange={(event) =>
                canvas ? setChange(event.target.value) : setPrompt(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') void (canvas ? refine() : createFromPrompt())
              }}
              placeholder={canvas
                ? 'Ask Komponist to change this view…'
                : 'Describe the view you need…'}
              aria-label={canvas ? 'Change this view' : 'Describe a new view'}
              className="min-w-0 flex-1 rounded-lg border border-line bg-paper-2 px-3 py-2.5 text-xs outline-none focus:border-orange"
            />
            <Button
              onClick={() => void (canvas ? refine() : createFromPrompt())}
              disabled={generating || working
                || (canvas ? !change.trim() : !prompt.trim())
                || (!!canvas && !canvas.is_owner)}
            >
              {generating
                ? <><Loader2 className="animate-spin" /> Building</>
                : canvas ? <><RotateCcw /> Update</> : <><Send /> Create</>}
            </Button>
          </div>
          {canvas && !canvas.is_owner && (
            <p className="mx-auto mt-1.5 max-w-3xl text-[11px] text-muted">
              Only the person who created this view can change it.
            </p>
          )}
        </div>
      </main>
    </AppLayout>
  )
}
