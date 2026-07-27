'use client'

import { useCallback, useDeferredValue, useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  AlertTriangle, ArrowRight, Check, ChevronRight, CircleDotDashed,
  Clock3, FileCheck2, Files, GitBranch, GitCommitHorizontal,
  GitCompareArrows, Loader2, Search, ShieldCheck, Sparkles, UsersRound,
  type LucideIcon,
} from 'lucide-react'
import AppLayout from '../../components/AppLayout'
import SourceLogo from '../../components/SourceLogo'
import StudioTopbar from '../../components/StudioTopbar'
import PaginationBar from '../../components/PaginationBar'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { API_URL, apiFetch, getActiveOrgId } from '../../lib/api'

type Claim = {
  id: string
  entity_type: string
  statement: string
  status?: string
  confidence?: string
}

type ChangeCounts = {
  added: number
  removed: number
  changed: number
  unchanged: number
  conflicts: number
}

type Version = {
  id: string
  title: string
  source: string
  reference: string
  url?: string | null
  author?: string | null
  source_date?: string | null
  content_hash?: string | null
  claims: Claim[]
  sequence: number
  is_latest: boolean
  parent_id?: string | null
  changes_from_previous: ChangeCounts
}

type ChangedClaim = {
  entity_type: string
  before: string
  after: string
  reason: string
  similarity: number
}

type Family = {
  id: string
  title: string
  is_demo: boolean
  version_count: number
  contributors: string[]
  sources: string[]
  latest_version_id: string
  latest_confidence: number
  match_confidence: number
  truth_status: 'contested' | 'reviewed' | 'needs review'
  versions: Version[]
  canonical_claims: Claim[]
  diff: {
    added: Claim[]
    removed: Claim[]
    changed: ChangedClaim[]
    unchanged: Claim[]
    conflicts: Array<{
      entity_type: string
      previous: string
      current: string
      reason: string
      status: string
    }>
    counts: ChangeCounts
  }
}

type VersionsResponse = {
  families: Family[]
  total: number
  limit: number
  offset: number
  has_more: boolean
  stats: {
    workspace_families: number
    workspace_versions: number
    contributors: number
    unresolved_conflicts: number
  }
  methodology: Record<string, string>
}

const SOURCE_NAMES: Record<string, string> = {
  notion: 'Notion', google: 'Google Drive', slack: 'Slack', upload: 'Upload',
  manual: 'Local file', local: 'Local file', github: 'GitHub',
}

const TYPE_TONES: Record<string, string> = {
  Decision: 'border-info/30 bg-info-soft text-info',
  Goal: 'border-teal/30 bg-success-soft text-teal',
  Constraint: 'border-orange/30 bg-warning-soft text-orange-dark',
  Project: 'border-ink bg-ink text-white',
}

function formatDate(value?: string | null, includeTime = false) {
  if (!value) return 'Date unknown'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Date unknown'
  return new Intl.DateTimeFormat('en', {
    day: '2-digit', month: 'short', year: 'numeric',
    ...(includeTime ? { hour: '2-digit', minute: '2-digit' } : {}),
  }).format(date)
}

function percent(value: number) {
  return `${Math.round(value * 100)}%`
}

function TypeBadge({ type }: { type: string }) {
  return (
    <span className={`inline-flex shrink-0 rounded-full border px-2 py-0.5 font-mono text-[8px] font-bold uppercase tracking-wider ${TYPE_TONES[type] || 'border-line bg-paper-2 text-muted'}`}>
      {type}
    </span>
  )
}

function VersionSource({ version, compact = false }: { version: Version; compact?: boolean }) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      <SourceLogo type={version.source} className={compact ? '!size-9 !rounded-lg !border' : undefined} />
      <div className="min-w-0">
        <div className="flex min-w-0 items-center gap-2">
          <p className="truncate text-sm font-bold">{SOURCE_NAMES[version.source] || version.source}</p>
          {version.is_latest && <Badge variant="teal" className="px-2 py-0.5 text-[8px]">Latest candidate</Badge>}
        </div>
        <p className="mt-0.5 truncate text-[10px] text-muted">
          {version.author || 'Unknown editor'} · {formatDate(version.source_date)}
        </p>
      </div>
    </div>
  )
}

export default function VersionsPage() {
  const [data, setData] = useState<VersionsResponse | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [filter, setFilter] = useState<'all' | 'workspace' | 'example'>('all')
  const [query, setQuery] = useState('')
  const deferredQuery = useDeferredValue(query)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const orgId = getActiveOrgId()
      const params = new URLSearchParams({
        org_id: orgId,
        include_demo: 'true',
        scope: filter,
        query: deferredQuery.trim(),
        limit: '20',
        offset: String(offset),
      })
      const response = await apiFetch(`${API_URL}/versions?${params.toString()}`)
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not build document lineage')
      setData(payload)
      setSelectedId((current) => (
        payload.families.some((family: Family) => family.id === current)
          ? current
          : payload.families[0]?.id ?? null
      ))
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not build document lineage')
    } finally {
      setLoading(false)
    }
  }, [deferredQuery, filter, offset])

  useEffect(() => { void load() }, [load])

  useEffect(() => { setOffset(0) }, [deferredQuery, filter])

  const families = useMemo(() => data?.families ?? [], [data?.families])

  const selected = useMemo(
    () => families.find((family) => family.id === selectedId) ?? families[0] ?? null,
    [families, selectedId],
  )
  const latest = selected?.versions.find((version) => version.id === selected.latest_version_id)

  return (
    <AppLayout>
      <StudioTopbar
        section="Company brain"
        title="Versions"
        description="Git for files across every connected source"
        icon={GitBranch}
        actions={
          <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
            {loading ? <Loader2 className="animate-spin" /> : <GitCompareArrows />} Re-analyze
          </Button>
        }
      />

      <main className="min-h-[calc(100vh-78px)] bg-paper">
        <section className="overflow-hidden border-b-2 border-ink bg-ink text-white">
          <div className="mx-auto grid max-w-[1380px] gap-8 px-5 py-9 sm:px-8 lg:grid-cols-[minmax(0,1fr)_420px] lg:px-10 lg:py-12">
            <div>
              <div className="flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-orange-light">
                <GitBranch className="size-4" /> Git for files
              </div>
              <h1 className="mt-4 max-w-3xl text-[clamp(2.5rem,5vw,4.7rem)] leading-[0.9] text-white">
                Know what changed.<br /><span className="text-orange-light">Know what to trust.</span>
              </h1>
              <p className="mt-5 max-w-2xl text-sm leading-6 text-paper-3 sm:text-base">
                Komponist groups copies of the same document across platforms, traces who changed what, and compares the underlying graph claims—not just filenames.
              </p>
            </div>
            <div className="grid grid-cols-2 overflow-hidden rounded-xl border-2 border-white/30 bg-white/10">
              {([
                ['Families', data?.stats.workspace_families ?? 0, Files],
                ['Versions', data?.stats.workspace_versions ?? 0, GitCommitHorizontal],
                ['Contributors', data?.stats.contributors ?? 0, UsersRound],
                ['Conflicts', data?.stats.unresolved_conflicts ?? 0, AlertTriangle],
              ] as Array<[string, number, LucideIcon]>).map(([label, value, Icon], index) => (
                <div key={String(label)} className={`p-4 ${index % 2 === 0 ? 'border-r border-white/20' : ''} ${index < 2 ? 'border-b border-white/20' : ''}`}>
                  <div className="flex items-center justify-between text-paper-3"><span className="font-mono text-[8px] font-bold uppercase tracking-wider">{label}</span><Icon className="size-3.5" /></div>
                  <div className="mt-3 font-display text-3xl font-black">{loading ? '—' : value}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <div className="mx-auto max-w-[1380px] px-5 py-7 sm:px-8 lg:px-10 lg:py-10">
          {error && (
            <div className="mb-6 flex items-center justify-between rounded-xl border-2 border-danger bg-danger-soft p-4 text-sm font-bold text-danger" role="alert">
              <span className="flex items-center gap-2"><AlertTriangle className="size-4" />{error}</span>
              <Button variant="ghost" size="sm" onClick={() => void load()}>Try again</Button>
            </div>
          )}

          <div className="grid gap-6 xl:grid-cols-[340px_minmax(0,1fr)]">
            <aside>
              <div className="sticky top-4 overflow-hidden rounded-xl border-2 border-ink bg-white shadow-[4px_4px_0_var(--color-shadow-soft)]">
                <div className="border-b-2 border-ink p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-mono text-[9px] font-bold uppercase tracking-wider text-orange-dark">Repositories</p>
                      <h2 className="mt-1 text-xl">Document families</h2>
                    </div>
                    <Badge variant="dark" className="px-2.5 py-1 text-[9px]">{data?.total ?? 0}</Badge>
                  </div>
                  <label className="mt-4 flex h-10 items-center gap-2 rounded-lg border-2 border-line bg-paper-2 px-3 focus-within:border-ink">
                    <Search className="size-4 text-muted" />
                    <input value={query} onChange={(event) => setQuery(event.target.value)} className="min-w-0 flex-1 bg-transparent text-xs outline-none" placeholder="Find a document family" />
                  </label>
                  <div className="mt-3 grid grid-cols-3 rounded-lg border border-line bg-paper-2 p-1">
                    {(['all', 'workspace', 'example'] as const).map((option) => (
                      <button key={option} type="button" onClick={() => setFilter(option)} className={`rounded-md px-2 py-1.5 text-[10px] font-bold capitalize transition ${filter === option ? 'bg-white text-ink shadow-sm' : 'text-muted hover:text-ink'}`}>{option}</button>
                    ))}
                  </div>
                </div>

                <div className="max-h-[670px] divide-y divide-line overflow-y-auto">
                  {loading ? [0, 1, 2].map((item) => <div key={item} className="h-28 animate-pulse bg-paper-2" />) : families.length === 0 ? (
                    <div className="p-8 text-center"><Files className="mx-auto size-7 text-faint" /><p className="mt-3 text-sm font-bold">No matching families</p><p className="mt-1 text-xs text-muted">Upload related documents or open the example.</p></div>
                  ) : families.map((family) => (
                    <button key={family.id} type="button" onClick={() => setSelectedId(family.id)} className={`w-full p-4 text-left transition ${selected?.id === family.id ? 'bg-warning-soft' : 'hover:bg-paper-2'}`}>
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <p className="truncate text-sm font-bold">{family.title}</p>
                            {family.is_demo && <Badge variant="orange" className="px-2 py-0.5 text-[7px]">Example</Badge>}
                          </div>
                          <p className="mt-1 text-[10px] text-muted">{family.version_count} versions · {family.contributors.length || 'Unknown'} contributors</p>
                        </div>
                        <ChevronRight className="mt-0.5 size-4 shrink-0 text-faint" />
                      </div>
                      <div className="mt-3 flex items-center justify-between">
                        <div className="flex -space-x-1.5">
                          {family.sources.slice(0, 4).map((source) => <SourceLogo key={source} type={source} className="!size-7 !rounded-md !border !shadow-[1px_1px_0_var(--color-shadow-strong)]" />)}
                        </div>
                        <span className={`rounded-full px-2 py-1 font-mono text-[8px] font-bold uppercase ${family.truth_status === 'contested' ? 'bg-danger-soft text-danger' : family.truth_status === 'reviewed' ? 'bg-success-soft text-teal' : 'bg-paper-3 text-muted'}`}>
                          {family.truth_status}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
                {data && (
                  <PaginationBar
                    itemLabel="document families"
                    total={data.total}
                    limit={data.limit}
                    offset={data.offset}
                    onOffsetChange={setOffset}
                  />
                )}
              </div>
            </aside>

            <AnimatePresence mode="wait">
              {selected && latest ? (
                <motion.div key={selected.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -5 }} className="min-w-0 space-y-6">
                  <section className="overflow-hidden rounded-xl border-2 border-ink bg-white shadow-[5px_5px_0_var(--color-shadow-soft)]">
                    <div className="flex flex-col gap-5 border-b-2 border-ink p-5 sm:flex-row sm:items-start sm:justify-between lg:p-6">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant={selected.is_demo ? 'orange' : 'dark'}>{selected.is_demo ? 'Interactive example' : 'Workspace family'}</Badge>
                          <Badge variant="default">{percent(selected.match_confidence)} family match</Badge>
                        </div>
                        <h2 className="mt-4 text-3xl leading-tight sm:text-4xl">{selected.title}</h2>
                        <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">Grouped from {selected.sources.map((source) => SOURCE_NAMES[source] || source).join(', ')} using filenames and ontology-aligned claims.</p>
                      </div>
                      <div className={`shrink-0 rounded-xl border-2 p-4 sm:w-52 ${selected.truth_status === 'contested' ? 'border-danger bg-danger-soft' : 'border-teal bg-success-soft'}`}>
                        <div className="flex items-center gap-2 font-mono text-[9px] font-bold uppercase tracking-wider">
                          {selected.truth_status === 'contested' ? <AlertTriangle className="size-4 text-danger" /> : <ShieldCheck className="size-4 text-teal" />} Knowledge state
                        </div>
                        <p className="mt-2 text-lg font-black capitalize">{selected.truth_status}</p>
                        <p className="mt-1 text-[10px] leading-4 text-muted">Latest is a candidate backed by provenance—not an automatic truth claim.</p>
                      </div>
                    </div>

                    <div className="bg-paper-2 p-5 lg:p-6">
                      <div className="mb-4 flex items-center justify-between">
                        <div><p className="font-mono text-[9px] font-bold uppercase tracking-wider text-muted">Revision graph</p><h3 className="mt-1 text-xl">Who changed what</h3></div>
                        <div className="hidden items-center gap-2 text-[10px] text-muted sm:flex"><CircleDotDashed className="size-3.5 text-orange" /> Newest by source metadata</div>
                      </div>
                      <div className="grid gap-3 lg:grid-cols-3">
                        {selected.versions.map((version, index) => (
                          <motion.div key={version.id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: index * 0.05 }} className={`relative rounded-xl border-2 p-4 ${version.is_latest ? 'border-teal bg-success-soft shadow-[3px_3px_0_var(--color-teal)]' : 'border-line bg-white'}`}>
                            {index > 0 && <ArrowRight className="absolute -left-[18px] top-1/2 z-10 hidden size-5 -translate-y-1/2 rounded-full bg-paper-2 text-orange lg:block" />}
                            <div className="mb-4 flex items-center justify-between"><span className="font-mono text-[9px] font-bold text-muted">V{version.sequence}</span><GitCommitHorizontal className={`size-4 ${version.is_latest ? 'text-teal' : 'text-faint'}`} /></div>
                            <VersionSource version={version} compact />
                            <p className="mt-4 truncate text-xs font-bold" title={version.title}>{version.title}</p>
                            <div className="mt-3 flex flex-wrap gap-1.5 font-mono text-[8px] font-bold uppercase">
                              {version.changes_from_previous.changed > 0 && <span className="rounded bg-warning-soft px-2 py-1 text-orange-dark">{version.changes_from_previous.changed} changed</span>}
                              {version.changes_from_previous.added > 0 && <span className="rounded bg-success-soft px-2 py-1 text-teal">+{version.changes_from_previous.added} added</span>}
                              {version.changes_from_previous.removed > 0 && <span className="rounded bg-danger-soft px-2 py-1 text-danger">−{version.changes_from_previous.removed} removed</span>}
                              {index === 0 && <span className="rounded bg-paper-3 px-2 py-1 text-muted">Base</span>}
                            </div>
                          </motion.div>
                        ))}
                      </div>
                    </div>
                  </section>

                  <div className="grid gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(300px,.8fr)]">
                    <section className="overflow-hidden rounded-xl border-2 border-ink bg-white shadow-[4px_4px_0_var(--color-shadow-soft)]">
                      <div className="flex items-center justify-between border-b-2 border-ink p-5">
                        <div><p className="font-mono text-[9px] font-bold uppercase tracking-wider text-orange-dark">Semantic diff</p><h3 className="mt-1 text-2xl">Base → latest candidate</h3></div>
                        <GitCompareArrows className="size-6 text-orange" />
                      </div>
                      {selected.diff.changed.length === 0 && selected.diff.added.length === 0 && selected.diff.removed.length === 0 ? (
                        <div className="p-8 text-center"><Check className="mx-auto size-7 text-teal" /><p className="mt-3 text-sm font-bold">No semantic changes detected</p></div>
                      ) : (
                        <div className="divide-y divide-line">
                          {selected.diff.changed.map((change, index) => (
                            <div key={`${change.before}-${index}`} className="p-5">
                              <div className="flex items-center justify-between"><TypeBadge type={change.entity_type} /><span className="font-mono text-[8px] font-bold uppercase text-orange-dark">{change.reason}</span></div>
                              <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto_1fr] sm:items-center">
                                <div className="rounded-lg border border-danger/30 bg-danger-soft p-3"><p className="mb-1 font-mono text-[8px] font-bold uppercase text-danger">Before</p><p className="text-xs leading-5 line-through decoration-danger/50">{change.before}</p></div>
                                <ArrowRight className="mx-auto size-4 rotate-90 text-muted sm:rotate-0" />
                                <div className="rounded-lg border border-teal/30 bg-success-soft p-3"><p className="mb-1 font-mono text-[8px] font-bold uppercase text-teal">Current candidate</p><p className="text-xs font-semibold leading-5">{change.after}</p></div>
                              </div>
                            </div>
                          ))}
                          {selected.diff.added.map((claim) => (
                            <div key={`added-${claim.id}`} className="flex gap-3 p-5"><span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-success-soft font-mono text-xs font-black text-teal">+</span><div><TypeBadge type={claim.entity_type} /><p className="mt-2 text-sm leading-6">{claim.statement}</p></div></div>
                          ))}
                          {selected.diff.removed.map((claim) => (
                            <div key={`removed-${claim.id}`} className="flex gap-3 p-5 opacity-70"><span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-danger-soft font-mono text-xs font-black text-danger">−</span><div><TypeBadge type={claim.entity_type} /><p className="mt-2 text-sm leading-6 line-through">{claim.statement}</p></div></div>
                          ))}
                        </div>
                      )}
                    </section>

                    <div className="space-y-6">
                      <section className="overflow-hidden rounded-xl border-2 border-ink bg-white shadow-[4px_4px_0_var(--color-shadow-soft)]">
                        <div className="border-b-2 border-ink bg-ink p-5 text-white">
                          <div className="flex items-center justify-between"><div><p className="font-mono text-[9px] font-bold uppercase tracking-wider text-orange-light">Latest candidate</p><h3 className="mt-1 text-xl text-white">{formatDate(latest.source_date, true)}</h3></div><FileCheck2 className="size-6 text-orange-light" /></div>
                        </div>
                        <div className="p-5">
                          <VersionSource version={latest} />
                          <div className="mt-5 grid grid-cols-2 gap-2">
                            <div className="rounded-lg border border-line bg-paper-2 p-3"><p className="font-mono text-[8px] font-bold uppercase text-muted">Recency confidence</p><p className="mt-1 text-xl font-black">{percent(selected.latest_confidence)}</p></div>
                            <div className="rounded-lg border border-line bg-paper-2 p-3"><p className="font-mono text-[8px] font-bold uppercase text-muted">Claims</p><p className="mt-1 text-xl font-black">{latest.claims.length}</p></div>
                          </div>
                          {latest.content_hash && <p className="mt-4 truncate font-mono text-[8px] text-faint" title={latest.content_hash}>sha256:{latest.content_hash}</p>}
                        </div>
                      </section>

                      <section className={`rounded-xl border-2 p-5 shadow-[4px_4px_0_var(--color-shadow-soft)] ${selected.diff.conflicts.length ? 'border-danger bg-danger-soft' : 'border-teal bg-success-soft'}`}>
                        <div className="flex items-start gap-3">
                          {selected.diff.conflicts.length ? <AlertTriangle className="mt-0.5 size-5 shrink-0 text-danger" /> : <ShieldCheck className="mt-0.5 size-5 shrink-0 text-teal" />}
                          <div><p className="font-mono text-[9px] font-bold uppercase tracking-wider">Conflict check</p><h3 className="mt-1 text-lg">{selected.diff.conflicts.length ? `${selected.diff.conflicts.length} unresolved changes` : 'Versions agree'}</h3><p className="mt-2 text-xs leading-5 text-muted">{selected.diff.conflicts.length ? 'Komponist preserves both claims and asks for review instead of silently overwriting history.' : 'No competing meaning was detected between the base and latest candidate.'}</p></div>
                        </div>
                      </section>
                    </div>
                  </div>

                  <section className="overflow-hidden rounded-xl border-2 border-ink bg-white shadow-[4px_4px_0_var(--color-shadow-soft)]">
                    <div className="flex flex-col gap-3 border-b-2 border-ink p-5 sm:flex-row sm:items-center sm:justify-between">
                      <div><p className="font-mono text-[9px] font-bold uppercase tracking-wider text-teal">Graph-backed state</p><h3 className="mt-1 text-2xl">What Komponist currently knows</h3></div>
                      <p className="max-w-md text-xs leading-5 text-muted">Claims from the newest candidate, aligned to the company ontology and retaining their review state.</p>
                    </div>
                    <div className="grid divide-y divide-line md:grid-cols-2 md:divide-x md:divide-y-0">
                      {selected.canonical_claims.map((claim) => (
                        <div key={claim.id} className="flex items-start gap-3 p-5 odd:border-b odd:border-line md:[&:nth-last-child(-n+2)]:border-b-0">
                          <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full border border-teal bg-success-soft"><Check className="size-3.5 text-teal" /></span>
                          <div><div className="flex flex-wrap items-center gap-2"><TypeBadge type={claim.entity_type} /><span className="font-mono text-[8px] uppercase text-muted">{claim.status || 'unreviewed'}</span></div><p className="mt-2 text-sm leading-6">{claim.statement}</p></div>
                        </div>
                      ))}
                    </div>
                  </section>

                  <section className="grid overflow-hidden rounded-xl border-2 border-ink bg-ink sm:grid-cols-2 lg:grid-cols-4">
                    {Object.entries(data?.methodology ?? {}).map(([label, value], index) => {
                      const icons = [GitCommitHorizontal, GitBranch, Sparkles, ShieldCheck]
                      const Icon = icons[index] || Sparkles
                      return <div key={label} className="border-b border-white/20 bg-ink p-4 text-white last:border-b-0 sm:border-r sm:[&:nth-child(2)]:border-r-0 lg:border-b-0 lg:[&:nth-child(2)]:border-r lg:last:border-r-0"><Icon className="size-4 text-orange-light" /><p className="mt-3 font-mono text-[8px] font-bold uppercase tracking-wider text-paper-3">{label}</p><p className="mt-1 text-xs leading-5 text-white">{value}</p></div>
                    })}
                  </section>
                </motion.div>
              ) : !loading && (
                <div className="grid min-h-[520px] place-items-center rounded-xl border-2 border-dashed border-line bg-white p-8 text-center"><div><Files className="mx-auto size-9 text-faint" /><h2 className="mt-4 text-2xl">No document family selected</h2></div></div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </main>
    </AppLayout>
  )
}
