'use client'

import Link from 'next/link'
import { useMemo, useState } from 'react'
import useSWR from 'swr'
import { AnimatePresence, motion } from 'framer-motion'
import {
  ArrowUpRight,
  CheckCircle2,
  CircleAlert,
  CircleDashed,
  FileCheck2,
  FolderKanban,
  ListChecks,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
  X,
  type LucideIcon,
} from 'lucide-react'
import AppLayout from '../../components/AppLayout'
import FactCard from '../../components/FactCard'
import StudioTopbar from '../../components/StudioTopbar'
import { Button } from '../../components/ui/button'
import { confirmEntity, fetchQueue, mergeEntity, rejectEntity } from '../../lib/api'

type QueueFilter = 'all' | 'Decision' | 'Goal' | 'Constraint' | 'Project'

interface QueueEvidence {
  id: string
  source: string
  reference: string
  url?: string
  source_date?: string
}

interface RelatedEntity {
  id: string
  statement: string
  score: number
}

interface QueueItem {
  id: string
  entity_type: string
  statement: string
  detail?: string
  confidence?: string | number
  created_at?: string
  evidence?: QueueEvidence[]
  related_to?: RelatedEntity[]
}

interface QueueResponse {
  items: QueueItem[]
  total: number
}

const TYPE_ORDER: QueueFilter[] = ['Decision', 'Goal', 'Constraint', 'Project']

const TYPE_META: Record<Exclude<QueueFilter, 'all'>, {
  icon: LucideIcon
  label: string
  description: string
  tone: string
  active: string
}> = {
  Decision: {
    icon: FileCheck2,
    label: 'Decisions',
    description: 'Chosen directions',
    tone: 'border-info/30 bg-info-soft text-info',
    active: 'border-info bg-info-soft text-info',
  },
  Goal: {
    icon: Target,
    label: 'Goals',
    description: 'Desired outcomes',
    tone: 'border-teal/30 bg-success-soft text-teal',
    active: 'border-teal bg-success-soft text-teal',
  },
  Constraint: {
    icon: ShieldCheck,
    label: 'Constraints',
    description: 'Rules and limits',
    tone: 'border-orange/30 bg-warning-soft text-orange-dark',
    active: 'border-orange bg-warning-soft text-orange-dark',
  },
  Project: {
    icon: FolderKanban,
    label: 'Projects',
    description: 'Active workstreams',
    tone: 'border-line bg-paper-2 text-ink',
    active: 'border-ink bg-ink text-white',
  },
}

function QueueSkeleton() {
  return (
    <div className="space-y-4" aria-label="Loading review queue">
      {[0, 1, 2].map((index) => (
        <div key={index} className="min-h-[300px] animate-pulse rounded-xl border-2 border-line bg-white p-5 sm:p-6">
          <div className="flex items-center justify-between">
            <div className="h-9 w-36 rounded-lg bg-paper-3" />
            <div className="h-6 w-24 rounded-full bg-paper-2" />
          </div>
          <div className="mt-8 h-6 w-5/6 rounded bg-paper-2" />
          <div className="mt-3 h-4 w-2/3 rounded bg-paper-2" />
          <div className="mt-8 h-16 rounded-lg bg-paper-2" />
          <div className="mt-6 h-11 rounded-lg bg-paper-3" />
        </div>
      ))}
    </div>
  )
}

export default function QueuePage() {
  const [filter, setFilter] = useState<QueueFilter>('all')
  const [query, setQuery] = useState('')
  const [actionError, setActionError] = useState<string | null>(null)

  const { data, error, isLoading, mutate } = useSWR<QueueResponse>('/queue', fetchQueue, {
    refreshInterval: 5000,
    keepPreviousData: true,
  })

  const items = useMemo(() => data?.items ?? [], [data?.items])

  const countsByType = useMemo(() => items.reduce<Record<string, number>>((counts, item) => {
    counts[item.entity_type] = (counts[item.entity_type] ?? 0) + 1
    return counts
  }, {}), [items])

  const filteredItems = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase()
    return items.filter((item) => {
      const matchesType = filter === 'all' || item.entity_type === filter
      const searchable = [
        item.statement,
        item.detail,
        item.entity_type,
        ...(item.evidence ?? []).map((evidence) => evidence.reference),
      ]
      const matchesQuery = !normalizedQuery || searchable.some((value) => value?.toLocaleLowerCase().includes(normalizedQuery))
      return matchesType && matchesQuery
    })
  }, [filter, items, query])

  const withEvidence = items.filter((item) => (item.evidence?.length ?? 0) > 0).length
  const possibleDuplicates = items.filter((item) => (item.related_to?.length ?? 0) > 0).length
  const highConfidence = items.filter((item) => {
    const confidence = item.confidence
    return confidence === 'high' || (typeof confidence === 'number' && confidence >= 0.8)
  }).length

  const runAction = async (action: () => Promise<unknown>, message: string) => {
    setActionError(null)
    try {
      await action()
      await mutate()
    } catch (actionFailure) {
      console.error(message, actionFailure)
      setActionError(message)
    }
  }

  const handleConfirm = (id: string, statement: string) => runAction(
    () => confirmEntity(id, statement),
    'This fact could not be confirmed. Please try again.',
  )

  const handleReject = (id: string) => runAction(
    () => rejectEntity(id),
    'This fact could not be rejected. Please try again.',
  )

  const handleMerge = (id: string, targetId: string) => runAction(
    () => mergeEntity(id, targetId),
    'These facts could not be merged. Please try again.',
  )

  const clearFilters = () => {
    setFilter('all')
    setQuery('')
  }

  return (
    <AppLayout>
      <div className="min-h-screen bg-paper">
        <StudioTopbar
          section="Company brain"
          title="Review Queue"
          description="Approve what becomes trusted company context"
          icon={ListChecks}
          actions={
            <>
              <div className="hidden rounded-lg border-2 border-ink bg-paper-2 px-3 py-1.5 shadow-[2px_2px_0_#201c15] sm:block">
                <span className="font-display text-lg font-bold">{isLoading ? '—' : data?.total ?? items.length}</span>
                <span className="ml-2 font-mono text-[9px] uppercase tracking-wider text-muted">Pending</span>
              </div>
              <Button asChild size="sm"><Link href="/onboard">Add source <ArrowUpRight /></Link></Button>
            </>
          }
        />
        <section className="overflow-hidden border-b-2 border-ink bg-white">
          <div className="mx-auto grid max-w-[1320px] lg:grid-cols-[minmax(0,1fr)_340px]">
            <div className="px-5 py-8 sm:px-8 lg:px-10 lg:py-10">
              <div className="mb-3 flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-orange-dark">
                <ListChecks className="size-3.5" /> Company brain / human review
              </div>
              <h1 className="max-w-3xl text-[clamp(2.7rem,5vw,4.8rem)] leading-[0.9]">
                Tune what<br />becomes truth.
              </h1>
              <p className="mt-5 max-w-2xl text-sm leading-6 text-muted sm:text-base">
                Every extracted fact waits here before it joins the company brain. Confirm what is right, edit what needs nuance, and reject the noise.
              </p>
            </div>

            <div className="relative flex min-h-[250px] flex-col justify-between border-t-2 border-ink bg-ink p-6 text-white lg:border-l-2 lg:border-t-0 lg:p-8">
              <div className="pointer-events-none absolute inset-0 overflow-hidden opacity-[0.13]" aria-hidden="true">
                {[18, 36, 54, 72].map((top) => <div key={top} className="absolute left-0 right-0 border-t border-white" style={{ top: `${top}%` }} />)}
                <div className="absolute left-[24%] top-[54%] size-4 rounded-full bg-white" />
                <div className="absolute left-[54%] top-[30%] size-4 rounded-full bg-white" />
                <div className="absolute left-[78%] top-[45%] size-4 rounded-full bg-white" />
                <div className="absolute left-[26%] top-[48%] h-px w-[34%] -rotate-[23deg] bg-white" />
                <div className="absolute left-[56%] top-[37%] h-px w-[24%] rotate-[19deg] bg-white" />
              </div>
              <div className="relative flex items-center justify-between font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-white/60">
                <span>Awaiting review</span>
                <CircleDashed className="size-4 text-orange" />
              </div>
              <div className="relative">
                <div className="font-display text-[76px] font-black leading-none tracking-[-0.08em] text-orange">
                  {isLoading ? '—' : data?.total ?? items.length}
                </div>
                <p className="mt-3 max-w-[230px] text-sm leading-5 text-white/65">
                  {items.length === 0 && !isLoading ? 'The queue is clear. Your reviewed brain is up to date.' : 'Review one fact at a time. Each decision improves the context your agents receive.'}
                </p>
              </div>
            </div>
          </div>
        </section>

        <main className="mx-auto max-w-[1320px] px-5 py-7 sm:px-8 lg:px-10 lg:py-10">
          {error && (
            <div className="mb-6 flex items-center gap-3 rounded-xl border-2 border-danger bg-danger-soft px-4 py-3 text-sm font-semibold text-danger" role="alert">
              <CircleAlert className="size-4 shrink-0" /> The review queue could not reach the API.
            </div>
          )}
          {actionError && (
            <div className="mb-6 flex items-center justify-between gap-3 rounded-xl border-2 border-danger bg-danger-soft px-4 py-3 text-sm font-semibold text-danger" role="alert">
              <span className="flex items-center gap-3"><CircleAlert className="size-4 shrink-0" /> {actionError}</span>
              <button type="button" onClick={() => setActionError(null)} aria-label="Dismiss error" className="grid size-7 place-items-center rounded-md hover:bg-white/50"><X className="size-4" /></button>
            </div>
          )}

          {items.length > 0 && (
            <section aria-label="Pending facts by type" className="mb-7 grid overflow-hidden rounded-xl border-2 border-ink bg-ink sm:grid-cols-2 xl:grid-cols-4">
              {TYPE_ORDER.map((type, index) => {
                const meta = TYPE_META[type as Exclude<QueueFilter, 'all'>]
                const Icon = meta.icon
                const count = countsByType[type] ?? 0
                const active = filter === type
                return (
                  <button
                    key={type}
                    type="button"
                    onClick={() => setFilter(active ? 'all' : type)}
                    aria-pressed={active}
                    className={`min-h-[132px] border-b-2 border-ink p-4 text-left transition sm:[&:nth-child(odd)]:border-r-2 xl:border-b-0 xl:border-r-2 xl:last:border-r-0 ${active ? 'bg-warning-soft' : 'bg-white hover:bg-paper-2'}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <span className={`grid size-9 place-items-center rounded-lg border ${meta.tone}`}><Icon className="size-4" /></span>
                      <span className="font-mono text-[9px] text-muted">0{index + 1}</span>
                    </div>
                    <div className="mt-4 flex items-end justify-between gap-3">
                      <div>
                        <div className="font-display text-base font-bold">{meta.label}</div>
                        <div className="mt-0.5 text-[11px] text-muted">{meta.description}</div>
                      </div>
                      <span className="font-display text-3xl font-black tracking-[-0.06em]">{count}</span>
                    </div>
                  </button>
                )
              })}
            </section>
          )}

          {items.length > 0 && (
            <section className="mb-7 grid gap-3 rounded-xl border-2 border-ink bg-paper-2 p-3 shadow-[4px_4px_0_#d9cfc0] lg:grid-cols-[minmax(260px,1fr)_auto] lg:items-center">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted" />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search facts, details, or sources…"
                  aria-label="Search review queue"
                  className="h-11 w-full rounded-lg border-2 border-ink bg-white pl-10 pr-10 text-sm outline-none shadow-[2px_2px_0_#201c15] transition focus:-translate-y-0.5 focus:shadow-[4px_4px_0_#e8641b]"
                />
                {query && (
                  <button type="button" onClick={() => setQuery('')} aria-label="Clear search" className="absolute right-2.5 top-1/2 grid size-7 -translate-y-1/2 place-items-center rounded-md hover:bg-paper-2"><X className="size-3.5" /></button>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => setFilter('all')} className={`rounded-full border-2 px-3 py-2 font-mono text-[9px] font-bold uppercase tracking-wider transition ${filter === 'all' ? 'border-ink bg-ink text-white' : 'border-line bg-white text-muted hover:border-ink'}`}>
                  All <span className="ml-1 opacity-65">{items.length}</span>
                </button>
                {TYPE_ORDER.map((type) => {
                  const count = countsByType[type] ?? 0
                  if (count === 0) return null
                  const meta = TYPE_META[type as Exclude<QueueFilter, 'all'>]
                  return (
                    <button key={type} type="button" onClick={() => setFilter(type)} className={`rounded-full border-2 px-3 py-2 font-mono text-[9px] font-bold uppercase tracking-wider transition ${filter === type ? meta.active : 'border-line bg-white text-muted hover:border-ink'}`}>
                      {type} <span className="ml-1 opacity-65">{count}</span>
                    </button>
                  )
                })}
              </div>
            </section>
          )}

          <div className="grid items-start gap-7 xl:grid-cols-[minmax(0,1fr)_290px]">
            <section aria-label="Facts awaiting review" className="min-w-0">
              {items.length > 0 && (
                <div className="mb-4 flex items-center justify-between gap-4 font-mono text-[10px] font-bold uppercase tracking-[0.1em] text-muted" aria-live="polite">
                  <span>{filteredItems.length} of {items.length} pending</span>
                  <span>Newest first</span>
                </div>
              )}

              {isLoading && items.length === 0 ? (
                <QueueSkeleton />
              ) : items.length === 0 ? (
                <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="grid min-h-[460px] place-items-center rounded-xl border-2 border-ink bg-white p-8 text-center shadow-[5px_5px_0_#d9cfc0]">
                  <div>
                    <span className="mx-auto grid size-16 place-items-center rounded-xl border-2 border-ink bg-success-soft text-teal shadow-[4px_4px_0_#201c15]"><CheckCircle2 className="size-7" /></span>
                    <p className="mt-6 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-teal">Review complete</p>
                    <h2 className="mt-2 text-3xl">You are all caught up.</h2>
                    <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-muted">New extracted facts will appear here after a source is uploaded or synced.</p>
                    <Button asChild className="mt-6"><Link href="/onboard">Add a source <ArrowUpRight /></Link></Button>
                  </div>
                </motion.div>
              ) : filteredItems.length === 0 ? (
                <div className="grid min-h-[360px] place-items-center rounded-xl border-2 border-ink bg-white p-8 text-center shadow-[4px_4px_0_#d9cfc0]">
                  <div>
                    <span className="mx-auto grid size-14 place-items-center rounded-xl border-2 border-ink bg-paper-2"><Search className="size-5" /></span>
                    <h2 className="mt-5 text-2xl">No matching facts</h2>
                    <p className="mt-2 text-sm text-muted">Try a different search or review all entity types.</p>
                    <Button variant="outline" size="sm" className="mt-5" onClick={clearFilters}>Clear filters</Button>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <AnimatePresence initial={false} mode="popLayout">
                    {filteredItems.map((item, index) => (
                      <FactCard
                        key={item.id}
                        id={item.id}
                        position={index + 1}
                        total={filteredItems.length}
                        type={item.entity_type}
                        statement={item.statement}
                        detail={item.detail}
                        confidence={item.confidence}
                        createdAt={item.created_at}
                        evidence={item.evidence ?? []}
                        relatedTo={item.related_to}
                        onConfirm={handleConfirm}
                        onReject={handleReject}
                        onMerge={handleMerge}
                      />
                    ))}
                  </AnimatePresence>
                </div>
              )}
            </section>

            {items.length > 0 && (
              <aside className="space-y-4 xl:sticky xl:top-6">
                <div className="overflow-hidden rounded-xl border-2 border-ink bg-white shadow-[4px_4px_0_#d9cfc0]">
                  <div className="border-b-2 border-ink bg-ink px-4 py-3 text-white">
                    <div className="flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[0.12em]"><Sparkles className="size-3.5 text-orange" /> Queue health</div>
                  </div>
                  <div className="divide-y divide-line">
                    <div className="flex items-center justify-between px-4 py-4"><span className="text-xs text-muted">With evidence</span><strong className="font-display text-xl">{withEvidence}/{items.length}</strong></div>
                    <div className="flex items-center justify-between px-4 py-4"><span className="text-xs text-muted">High confidence</span><strong className="font-display text-xl">{highConfidence}</strong></div>
                    <div className="flex items-center justify-between px-4 py-4"><span className="text-xs text-muted">Possible duplicates</span><strong className={`font-display text-xl ${possibleDuplicates > 0 ? 'text-orange-dark' : 'text-teal'}`}>{possibleDuplicates}</strong></div>
                  </div>
                </div>

                <div className="rounded-xl border-2 border-ink bg-warning-soft p-5">
                  <div className="font-mono text-[10px] font-bold uppercase tracking-[0.12em] text-orange-dark">A good review</div>
                  <ol className="mt-4 space-y-4">
                    {[
                      ['01', 'Check the source', 'Make sure the evidence supports the claim.'],
                      ['02', 'Sharpen the wording', 'Keep one clear, reusable fact per entity.'],
                      ['03', 'Choose its fate', 'Confirm, reject, or merge a duplicate.'],
                    ].map(([number, title, copy]) => (
                      <li key={number} className="grid grid-cols-[28px_1fr] gap-3">
                        <span className="font-mono text-[9px] font-bold text-orange-dark">{number}</span>
                        <div><div className="text-xs font-bold text-ink">{title}</div><p className="mt-1 text-[11px] leading-4 text-muted">{copy}</p></div>
                      </li>
                    ))}
                  </ol>
                </div>
              </aside>
            )}
          </div>
        </main>
      </div>
    </AppLayout>
  )
}
