'use client'

import Link from 'next/link'
import { useDeferredValue, useEffect, useMemo, useState } from 'react'
import useSWR from 'swr'
import { motion } from 'framer-motion'
import {
  ArrowUpRight,
  CalendarDays,
  CheckCircle2,
  CircleDashed,
  FileCheck2,
  FolderKanban,
  Layers3,
  Search,
  ShieldCheck,
  Target,
  X,
  type LucideIcon,
} from 'lucide-react'
import AppLayout from '../../components/AppLayout'
import EvidenceChip from '../../components/EvidenceChip'
import PaginationBar from '../../components/PaginationBar'
import StudioTopbar from '../../components/StudioTopbar'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { fetchEntities } from '../../lib/api'

type EntityStatus = 'confirmed' | 'proposed' | 'rejected' | 'all'

interface EntityEvidence {
  id: string
  source: string
  reference: string
  url?: string
}

interface Entity {
  id: string
  entity_type: string
  statement: string
  detail?: string
  status: Exclude<EntityStatus, 'all'>
  confidence?: string | number
  confirmed_at?: string
  created_at?: string
  evidence?: EntityEvidence[]
}

interface EntitiesResponse {
  entities: Entity[]
  total: number
  limit: number
  offset: number
  has_more: boolean
  counts_by_type: Record<string, number>
  counts_by_status: Record<string, number>
}

const TYPE_META: Record<string, {
  label: string
  plural: string
  description: string
  icon: LucideIcon
  tone: string
  badge: 'default' | 'orange' | 'teal' | 'dark'
}> = {
  Decision: {
    label: 'Decision',
    plural: 'Decisions',
    description: 'Chosen directions and policies',
    icon: FileCheck2,
    tone: 'bg-info-soft text-info border-info/30',
    badge: 'default',
  },
  Goal: {
    label: 'Goal',
    plural: 'Goals',
    description: 'Targets and desired outcomes',
    icon: Target,
    tone: 'bg-success-soft text-teal border-teal/30',
    badge: 'teal',
  },
  Constraint: {
    label: 'Constraint',
    plural: 'Constraints',
    description: 'Rules, limits, and requirements',
    icon: ShieldCheck,
    tone: 'bg-warning-soft text-orange-dark border-orange/30',
    badge: 'orange',
  },
  Project: {
    label: 'Project',
    plural: 'Projects',
    description: 'Initiatives, pilots, and workstreams',
    icon: FolderKanban,
    tone: 'bg-paper-2 text-ink border-line',
    badge: 'dark',
  },
}

const PRIMARY_TYPES = ['Decision', 'Goal', 'Constraint', 'Project']
const PAGE_SIZE = 24

const STATUS_OPTIONS: Array<{ value: EntityStatus; label: string }> = [
  { value: 'confirmed', label: 'Confirmed' },
  { value: 'proposed', label: 'Proposed' },
  { value: 'all', label: 'All' },
]

function formatDate(value?: string) {
  if (!value) return 'Not confirmed'
  return new Intl.DateTimeFormat('en', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(new Date(value))
}

function confidenceLabel(value?: string | number) {
  if (value === undefined || value === null || value === '') return null
  if (typeof value === 'number') return `${Math.round(value * 100)}% confidence`
  return `${value} confidence`
}

export default function EntitiesPage() {
  const [typeFilter, setTypeFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState<EntityStatus>('confirmed')
  const [query, setQuery] = useState('')
  const [offset, setOffset] = useState(0)
  const deferredQuery = useDeferredValue(query.trim())

  const { data, error, isLoading } = useSWR<EntitiesResponse>(
    ['entities', statusFilter, typeFilter, deferredQuery, offset],
    () => fetchEntities({
      status: statusFilter,
      entityType: typeFilter === 'all' ? undefined : typeFilter,
      query: deferredQuery,
      limit: PAGE_SIZE,
      offset,
    }),
    { keepPreviousData: true },
  )

  const entities = useMemo(() => data?.entities ?? [], [data?.entities])
  const countsByType = useMemo(() => data?.counts_by_type ?? {}, [data?.counts_by_type])
  const countsByStatus = data?.counts_by_status ?? {}
  const totalAcrossStatuses = Object.values(countsByStatus).reduce((sum, count) => sum + count, 0)

  const availableTypes = useMemo(() => {
    const extraTypes = Object.keys(countsByType).filter((type) => !PRIMARY_TYPES.includes(type))
    return [...PRIMARY_TYPES, ...extraTypes]
  }, [countsByType])

  useEffect(() => {
    setOffset(0)
  }, [deferredQuery, statusFilter, typeFilter])

  const selectedStatusLabel = STATUS_OPTIONS.find((option) => option.value === statusFilter)?.label ?? 'All'

  return (
    <AppLayout>
      <div className="min-h-screen bg-paper">
        <StudioTopbar
          section="Company brain"
          title="Entities"
          description="Reviewed facts your team and agents can rely on"
          icon={Layers3}
          actions={
            <>
              <div className="hidden rounded-lg border-2 border-ink bg-paper-2 px-3 py-1.5 shadow-[2px_2px_0_var(--color-shadow-strong)] sm:block">
                <span className="font-display text-lg font-bold">{isLoading ? '—' : data?.total ?? 0}</span>
                <span className="ml-2 font-mono text-[9px] uppercase tracking-wider text-muted">{selectedStatusLabel}</span>
              </div>
              <Button asChild size="sm"><Link href="/onboard">Add source <ArrowUpRight /></Link></Button>
            </>
          }
        />
        <section className="border-b-2 border-ink bg-white px-5 py-7 sm:px-8 lg:px-10">
          <div className="mx-auto max-w-[1320px]">
            <div>
              <div className="mb-3 flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-orange-dark">
                <Layers3 className="size-3.5" /> Company brain / entity library
              </div>
              <h1 className="text-[clamp(2.6rem,5vw,4.6rem)] leading-[0.9]">Every fact,<br />in its place.</h1>
              <p className="mt-4 max-w-2xl text-sm leading-6 text-muted sm:text-base">
                Browse the reviewed building blocks your team and agents can rely on. Every entity keeps its status and evidence attached.
              </p>
            </div>
          </div>
        </section>

        <div className="mx-auto max-w-[1320px] px-5 py-7 sm:px-8 lg:px-10 lg:py-10">
          {error && (
            <div className="mb-7 flex items-center gap-3 rounded-xl border-2 border-danger bg-danger-soft px-4 py-3 text-sm font-semibold text-danger" role="alert">
              <CircleDashed className="size-4" /> The entity library could not reach the API.
            </div>
          )}

          <section aria-label="Entity type totals" className="grid overflow-hidden rounded-xl border-2 border-ink bg-ink sm:grid-cols-2 xl:grid-cols-4">
            {PRIMARY_TYPES.map((type, index) => {
              const meta = TYPE_META[type]
              const Icon = meta.icon
              const count = countsByType[type] ?? 0
              const active = typeFilter === type
              return (
                <button
                  key={type}
                  type="button"
                  onClick={() => setTypeFilter(active ? 'all' : type)}
                  className={`group min-h-[164px] border-b-2 border-ink p-5 text-left transition-colors sm:[&:nth-child(odd)]:border-r-2 xl:border-b-0 xl:border-r-2 xl:last:border-r-0 ${active ? 'bg-warning-soft' : 'bg-white hover:bg-paper-2'}`}
                  aria-pressed={active}
                >
                  <div className="flex items-start justify-between gap-4">
                    <span className={`grid size-11 place-items-center rounded-lg border-2 shadow-[2px_2px_0_var(--color-shadow-strong)] ${meta.tone}`}><Icon className="size-5" /></span>
                    <span className="font-mono text-[10px] text-muted">0{index + 1}</span>
                  </div>
                  <div className="mt-5 flex items-end justify-between gap-3">
                    <div>
                      <div className="font-display text-xl font-bold">{meta.plural}</div>
                      <div className="mt-1 text-xs text-muted">{meta.description}</div>
                    </div>
                    <div className="font-display text-4xl font-black tracking-[-0.06em]">{isLoading ? '—' : count}</div>
                  </div>
                </button>
              )
            })}
          </section>

          <section className="mt-7 overflow-hidden rounded-xl border-2 border-ink bg-white shadow-[5px_5px_0_var(--color-shadow-soft)]">
            <div className="grid gap-4 border-b-2 border-ink bg-paper-2 p-4 lg:grid-cols-[minmax(260px,1fr)_auto] lg:items-center">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted" />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search statements or details…"
                  aria-label="Search entities"
                  className="h-11 w-full rounded-lg border-2 border-ink bg-white pl-10 pr-10 text-sm outline-none shadow-[2px_2px_0_var(--color-shadow-strong)] transition focus:-translate-y-0.5 focus:shadow-[4px_4px_0_var(--color-orange)]"
                />
                {query && (
                  <button type="button" aria-label="Clear search" onClick={() => setQuery('')} className="absolute right-2.5 top-1/2 grid size-7 -translate-y-1/2 place-items-center rounded-md hover:bg-paper-2">
                    <X className="size-3.5" />
                  </button>
                )}
              </div>
              <div className="flex flex-wrap gap-2" aria-label="Status filter">
                {STATUS_OPTIONS.map((option) => {
                  const count = option.value === 'all'
                    ? totalAcrossStatuses
                    : countsByStatus[option.value] ?? 0
                  return (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setStatusFilter(option.value)}
                      className={`inline-flex h-10 items-center gap-2 rounded-lg border-2 px-3 font-mono text-[10px] font-bold uppercase tracking-wider transition ${statusFilter === option.value ? 'border-ink bg-ink text-white' : 'border-line bg-white text-ink hover:border-ink'}`}
                    >
                      {option.value === 'confirmed' ? <CheckCircle2 className="size-3.5" /> : <CircleDashed className="size-3.5" />}
                      {option.label}
                      <span className={`rounded px-1.5 py-0.5 ${statusFilter === option.value ? 'bg-white/15' : 'bg-paper-2 text-muted'}`}>{count}</span>
                    </button>
                  )
                })}
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
              <button type="button" onClick={() => setTypeFilter('all')} className={`rounded-full border px-3 py-1.5 font-mono text-[10px] font-bold uppercase tracking-wider ${typeFilter === 'all' ? 'border-ink bg-ink text-white' : 'border-line bg-white text-muted hover:border-ink'}`}>
                All types <span className="ml-1 opacity-70">{data?.total ?? 0}</span>
              </button>
              {availableTypes.map((type) => {
                const meta = TYPE_META[type]
                return (
                  <button key={type} type="button" onClick={() => setTypeFilter(type)} className={`rounded-full border px-3 py-1.5 font-mono text-[10px] font-bold uppercase tracking-wider ${typeFilter === type ? 'border-orange bg-warning-soft text-orange-dark' : 'border-line bg-white text-muted hover:border-ink'}`}>
                    {meta?.plural ?? type} <span className="ml-1 opacity-70">{countsByType[type] ?? 0}</span>
                  </button>
                )
              })}
            </div>

            <div className="flex items-center justify-between gap-4 border-b border-line px-5 py-3 font-mono text-[10px] uppercase tracking-wider text-muted">
              <span>{entities.length} shown · {data?.total ?? 0} matching</span>
              <span>Newest first</span>
            </div>

            {isLoading ? (
              <div className="grid gap-px bg-line sm:grid-cols-2">
                {[0, 1, 2, 3].map((index) => <div key={index} className="h-56 animate-pulse bg-white p-5"><div className="h-4 w-24 rounded bg-paper-3" /><div className="mt-8 h-5 w-4/5 rounded bg-paper-2" /><div className="mt-3 h-4 w-2/3 rounded bg-paper-2" /></div>)}
              </div>
            ) : entities.length === 0 ? (
              <div className="grid min-h-[360px] place-items-center p-8 text-center">
                <div>
                  <span className="mx-auto grid size-14 place-items-center rounded-xl border-2 border-ink bg-paper-2 shadow-[3px_3px_0_var(--color-shadow-strong)]"><Search className="size-5" /></span>
                  <h3 className="mt-5">No entities found</h3>
                  <p className="mt-2 max-w-md text-sm text-muted">
                    {query || typeFilter !== 'all'
                      ? 'Try another search term or clear one of the filters.'
                      : 'Connect a source and confirm extracted knowledge to start building the library.'}
                  </p>
                  {(query || typeFilter !== 'all') && <Button variant="outline" size="sm" className="mt-5" onClick={() => { setQuery(''); setTypeFilter('all') }}>Clear filters</Button>}
                </div>
              </div>
            ) : (
              <div className="grid gap-px bg-line sm:grid-cols-2">
                {entities.map((entity, index) => {
                  const meta = TYPE_META[entity.entity_type]
                  const Icon = meta?.icon ?? Layers3
                  const date = entity.confirmed_at ?? entity.created_at
                  const confidence = confidenceLabel(entity.confidence)
                  return (
                    <motion.article
                      key={entity.id}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.24, delay: Math.min(index * 0.025, 0.2) }}
                      className="group flex min-h-[250px] flex-col bg-white p-5 transition-colors hover:bg-[#fffaf0] sm:p-6"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex items-center gap-3">
                          <span className={`grid size-9 place-items-center rounded-lg border ${meta?.tone ?? 'border-line bg-paper-2 text-ink'}`}><Icon className="size-4" /></span>
                          <Badge variant={meta?.badge ?? 'default'}>{entity.entity_type}</Badge>
                        </div>
                        <Badge variant={entity.status === 'confirmed' ? 'teal' : entity.status === 'proposed' ? 'orange' : 'default'} className="px-2 py-0.5 text-[9px]">
                          {entity.status}
                        </Badge>
                      </div>

                      <p className="mt-5 text-base font-semibold leading-6 text-ink sm:text-[17px]">{entity.statement}</p>
                      {entity.detail && <p className="mt-2 line-clamp-3 text-sm leading-6 text-muted">{entity.detail}</p>}

                      <div className="mt-auto pt-6">
                        {entity.evidence && entity.evidence.length > 0 ? (
                          <div className="flex flex-wrap gap-2">
                            {entity.evidence.slice(0, 2).map((evidence) => <EvidenceChip key={evidence.id} source={evidence.source} reference={evidence.reference} url={evidence.url} />)}
                            {entity.evidence.length > 2 && <span className="inline-flex items-center rounded-md border border-line bg-paper px-2 py-1 font-mono text-[10px] text-muted">+{entity.evidence.length - 2} more</span>}
                          </div>
                        ) : <span className="font-mono text-[10px] uppercase tracking-wider text-faint">No evidence attached</span>}

                        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3 font-mono text-[9px] uppercase tracking-wider text-muted">
                          <span className="inline-flex items-center gap-1.5"><CalendarDays className="size-3" /> {formatDate(date)}</span>
                          {confidence && <span>{confidence}</span>}
                        </div>
                      </div>
                    </motion.article>
                  )
                })}
              </div>
            )}
            <PaginationBar
              offset={offset}
              limit={PAGE_SIZE}
              total={data?.total ?? 0}
              disabled={isLoading}
              itemLabel="entities"
              onOffsetChange={setOffset}
            />
          </section>
        </div>
      </div>
    </AppLayout>
  )
}
