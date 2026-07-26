'use client'

/**
 * The inspector beside the canvas.
 *
 * Its one rule: never fill a gap with something plausible. A relationship with
 * no recorded description says so, an entity with no readable source says so,
 * and a confidence the pipeline stored as a word is shown as that word rather
 * than converted into a percentage it never had.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  CircleDot,
  Focus,
  Sparkles,
  Waypoints,
  X,
} from 'lucide-react'
import EvidenceChip from '../EvidenceChip'
import { Button } from '../ui/button'
import type { Theme } from '../ThemeProvider'
import { API_URL, apiFetch, getActiveOrgId } from '../../lib/api'
import { formatConfidence, relationshipLabel, typeColor } from './graph-transform'
import type {
  EvidenceRef,
  GraphEdge,
  GraphNode,
  GraphStats,
  GraphViewEdge,
} from './types'

const NO_SOURCES = 'No source information available'

export interface GraphDetailsPanelProps {
  theme: Theme
  stats: GraphStats | null
  coverage: string
  truncated: boolean
  overviewCount: number
  total: number
  expandedIds: string[]
  selectedNode: GraphNode | null
  selectedEdge: GraphViewEdge | null
  neighbors: GraphNode[]
  /** Every visible relationship that touches the selected node. */
  incidentEdges: GraphViewEdge[]
  nodesById: Map<string, GraphNode>
  focusNodeId: string | null
  expandingId: string | null
  onClose: () => void
  onSelectNode: (id: string) => void
  onSelectEdge: (id: string) => void
  onFocus: (id: string) => void
  onExpand: (id: string) => void
  onExport: () => void
  children?: React.ReactNode
}

/** Loads the sources behind one entity, dropping answers for a stale selection. */
function useEntityEvidence(entityId: string | null) {
  const [evidence, setEvidence] = useState<EvidenceRef[] | null>(null)
  const [loading, setLoading] = useState(false)
  const cache = useRef(new Map<string, EvidenceRef[]>())

  useEffect(() => {
    if (!entityId) {
      setEvidence(null)
      return
    }
    const cached = cache.current.get(entityId)
    if (cached) {
      setEvidence(cached)
      return
    }

    const controller = new AbortController()
    setLoading(true)
    setEvidence(null)
    void (async () => {
      try {
        const orgId = getActiveOrgId()
        const response = await apiFetch(
          `${API_URL}/entities/${encodeURIComponent(entityId)}`
          + `?org_id=${encodeURIComponent(orgId)}`,
          { signal: controller.signal },
        )
        if (!response.ok) throw new Error('unavailable')
        const payload = await response.json()
        const rows: EvidenceRef[] = Array.isArray(payload.evidence)
          ? payload.evidence.filter((row: EvidenceRef) => row && row.id)
          : []
        cache.current.set(entityId, rows)
        setEvidence(rows)
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return
        // A failure here is indistinguishable to the reader from "no sources
        // recorded", so say the honest thing rather than showing an error.
        setEvidence([])
      } finally {
        setLoading(false)
      }
    })()

    return () => controller.abort()
  }, [entityId])

  return { evidence, loading }
}

/**
 * Show a source date only when the API sent something a reader can read. Dates
 * arrive from a graph driver rather than a hand-written serialiser, so a value
 * that is not a plain ISO-ish string is dropped rather than rendered as
 * `[object Object]`.
 */
function sourceDateLabel(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  const match = value.match(/^\d{4}-\d{2}-\d{2}/)
  return match ? match[0] : undefined
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <p className="font-mono text-[9px] font-bold uppercase tracking-wider text-muted">
      {children}
    </p>
  )
}

function SourceList({
  evidence,
  loading,
}: {
  evidence: EvidenceRef[] | null
  loading: boolean
}) {
  if (loading) {
    return <p className="mt-3 text-[11px] text-muted">Loading sources…</p>
  }
  if (!evidence?.length) {
    return <p className="mt-3 text-[11px] text-muted">{NO_SOURCES}</p>
  }
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {evidence.map(row => (
        <EvidenceChip
          key={row.id}
          source={row.source}
          reference={row.reference}
          url={typeof row.url === 'string' ? row.url : undefined}
          date={sourceDateLabel(row.source_date)}
        />
      ))}
    </div>
  )
}

/** `Fixture 28 advances Fixture 29` — the relationship read back as a sentence. */
function connectionSentence(
  edge: GraphEdge,
  nodesById: Map<string, GraphNode>,
): string {
  const from = nodesById.get(edge.source)?.name ?? 'an entity outside this view'
  const to = nodesById.get(edge.target)?.name ?? 'an entity outside this view'
  return `${from} — ${relationshipLabel(edge.type).toLowerCase()} → ${to}`
}

export default function GraphDetailsPanel({
  theme,
  stats,
  coverage,
  truncated,
  overviewCount,
  total,
  expandedIds,
  selectedNode,
  selectedEdge,
  neighbors,
  incidentEdges,
  nodesById,
  focusNodeId,
  expandingId,
  onClose,
  onSelectNode,
  onSelectEdge,
  onFocus,
  onExpand,
  onExport,
}: GraphDetailsPanelProps) {
  const { evidence, loading: evidenceLoading } = useEntityEvidence(selectedNode?.id ?? null)

  const endpoints = useMemo(() => {
    if (!selectedEdge) return []
    return ([['From', selectedEdge.source], ['To', selectedEdge.target]] as const)
      .map(([role, id]) => ({ role, node: nodesById.get(id) ?? null }))
      .filter((entry): entry is { role: 'From' | 'To'; node: GraphNode } => entry.node !== null)
  }, [nodesById, selectedEdge])

  return (
    <aside
      id="graph-details"
      className="graph-side-panel min-h-0 overflow-y-auto bg-white"
      aria-label="Graph details"
    >
      <div className="border-b-2 border-ink p-5">
        <div className="flex items-center justify-between">
          <SectionHeading>Graph overview</SectionHeading>
          <button
            type="button"
            onClick={onClose}
            className="grid size-8 place-items-center rounded-md hover:bg-paper-2"
            aria-label="Close graph details"
          >
            <X className="size-4" />
          </button>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3">
          <div className="rounded-lg border-2 border-ink bg-paper p-3">
            <strong className="block font-mono text-2xl">
              {(stats?.total_nodes ?? 0).toLocaleString()}
            </strong>
            <span className="text-[10px] font-semibold text-muted">Entities you can see</span>
          </div>
          <div className="rounded-lg border-2 border-ink bg-paper p-3">
            <strong className="block font-mono text-2xl">
              {(stats?.total_edges ?? 0).toLocaleString()}
            </strong>
            <span className="text-[10px] font-semibold text-muted">Relationships</span>
          </div>
        </div>
        <p className="mt-3 font-mono text-[10px] text-muted">{coverage}</p>
        {truncated && (
          <p className="mt-3 rounded-md bg-warning-soft p-2.5 text-[10px] leading-4 text-orange-dark">
            This is the {overviewCount.toLocaleString()} best-connected
            of {total.toLocaleString()} matching entities — enough to stay readable.
            Search or filter to change what is drawn, or open a node and use
            Neighbors to pull in what it connects to.
          </p>
        )}
        {expandedIds.length > 0 && (
          <p className="mt-3 rounded-md border border-line bg-paper p-2.5 text-[10px] leading-4 text-muted">
            {expandedIds.length === 1
              ? '1 neighbourhood added to the overview.'
              : `${expandedIds.length} neighbourhoods added to the overview.`}
            {' '}Back to overview clears them.
          </p>
        )}
      </div>

      {selectedNode ? (
        <div className="p-5">
          <div className="flex items-center justify-between gap-3">
            <span
              className="rounded-full border border-ink px-2.5 py-1 font-mono text-[9px] font-bold uppercase tracking-wider text-white"
              style={{ background: typeColor(selectedNode.type, theme) }}
            >
              {selectedNode.type}
            </span>
            <span
              className={`flex items-center gap-1.5 text-[10px] font-bold ${
                selectedNode.status === 'confirmed' ? 'text-teal' : 'text-orange-dark'
              }`}
            >
              {selectedNode.status === 'confirmed'
                ? <Check className="size-3.5" aria-hidden />
                : <CircleDot className="size-3.5" aria-hidden />}
              {selectedNode.status ?? 'status unknown'}
            </span>
          </div>
          <h2 className="mt-4 text-2xl font-bold leading-tight">{selectedNode.name}</h2>
          <p className="mt-3 text-sm leading-6 text-ink-2">
            {selectedNode.description ?? 'No further detail was recorded for this entity.'}
          </p>

          <div className="mt-5 grid grid-cols-3 gap-2">
            {[
              [selectedNode.degree ?? '—', 'Links'],
              [selectedNode.evidence_count ?? '—', 'Sources'],
              [formatConfidence(selectedNode.confidence), 'Confidence'],
            ].map(([value, label]) => (
              <div key={label as string} className="rounded-md border border-line bg-paper p-2 text-center">
                <strong className="block font-mono text-sm">{value}</strong>
                <span className="text-[9px] text-muted">{label}</span>
              </div>
            ))}
          </div>

          <div className="mt-5 grid grid-cols-2 gap-2">
            <Button
              size="sm"
              variant={focusNodeId === selectedNode.id ? 'default' : 'outline'}
              onClick={() => onFocus(selectedNode.id)}
            >
              <Focus /> {focusNodeId === selectedNode.id ? 'Focused' : 'Focus'}
            </Button>
            <Button
              size="sm"
              variant="subtle"
              onClick={() => onExpand(selectedNode.id)}
              disabled={expandingId === selectedNode.id}
            >
              <Waypoints className={expandingId === selectedNode.id ? 'animate-pulse' : ''} />
              {expandedIds.includes(selectedNode.id) ? 'Expanded' : 'Explore neighbors'}
            </Button>
          </div>
          <Button asChild size="sm" variant="ghost" className="mt-2 w-full">
            <Link href="/entities">Open in entity library <ArrowUpRight /></Link>
          </Button>

          <div className="mt-7 border-t border-line pt-5">
            <SectionHeading>Sources</SectionHeading>
            <SourceList evidence={evidence} loading={evidenceLoading} />
          </div>

          {incidentEdges.length > 0 && (
            <div className="mt-7 border-t border-line pt-5">
              <SectionHeading>Relationships</SectionHeading>
              <div className="mt-3 space-y-2">
                {incidentEdges.map(edge => {
                  const outgoing = edge.source === selectedNode.id
                  const otherId = outgoing ? edge.target : edge.source
                  const other = nodesById.get(otherId)
                  return (
                    <button
                      key={edge.id}
                      type="button"
                      onClick={() => onSelectEdge(edge.id)}
                      className="flex w-full items-start gap-2 rounded-lg border border-line bg-paper p-2.5 text-left transition hover:border-ink"
                    >
                      <ArrowRight
                        className={`mt-0.5 size-3 shrink-0 text-muted ${outgoing ? '' : 'rotate-180'}`}
                        aria-hidden
                      />
                      <span className="min-w-0">
                        <span className="block font-mono text-[9px] uppercase tracking-wider text-orange-dark">
                          {edge.label}
                        </span>
                        <strong className="block truncate text-xs">
                          {other?.name ?? 'Entity outside this view'}
                        </strong>
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {neighbors.length > 0 && (
            <div className="mt-7 border-t border-line pt-5">
              <SectionHeading>Connected knowledge</SectionHeading>
              <div className="mt-3 space-y-2">
                {neighbors.slice(0, 8).map(node => (
                  <button
                    key={node.id}
                    type="button"
                    onClick={() => onSelectNode(node.id)}
                    className="flex w-full items-center gap-3 rounded-lg border border-line bg-paper p-2.5 text-left transition hover:border-ink"
                  >
                    <span
                      className="size-2.5 shrink-0 rounded-full"
                      style={{ background: typeColor(node.type, theme) }}
                    />
                    <span className="min-w-0">
                      <strong className="block truncate text-xs">{node.name}</strong>
                      <span className="font-mono text-[8px] uppercase text-muted">{node.type}</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : selectedEdge ? (
        <div className="p-5">
          <SectionHeading>Relationship</SectionHeading>
          <h2 className="mt-3 text-2xl font-bold">{selectedEdge.label}</h2>

          <div className="mt-5 space-y-2">
            {endpoints.map(({ role, node }) => (
              <div key={role} className="rounded-lg border-2 border-ink bg-paper p-3">
                <span className="font-mono text-[8px] uppercase text-muted">
                  {role} · {node.type}
                </span>
                <strong className="mt-1 block text-sm">{node.name}</strong>
                <div className="mt-2 flex gap-2">
                  <Button size="sm" variant="ghost" onClick={() => onSelectNode(node.id)}>
                    Inspect
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => onFocus(node.id)}>
                    <Focus /> Focus
                  </Button>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-7 border-t border-line pt-5">
            <SectionHeading>Why connected?</SectionHeading>
            <p className="mt-3 text-sm leading-6 text-ink-2">
              {connectionSentence(selectedEdge.data, nodesById)}
            </p>
            <p className="mt-3 text-[11px] leading-5 text-muted">
              {selectedEdge.data.description
                ?? 'No explanation was recorded for this relationship. '
                  + 'Open either entity to see the sources it was extracted from.'}
            </p>
          </div>
        </div>
      ) : (
        <div className="p-5">
          <span className="grid size-12 place-items-center rounded-lg border-2 border-ink bg-info-soft">
            <Sparkles className="size-5" aria-hidden />
          </span>
          <h2 className="mt-5 text-2xl font-bold">Explore the context</h2>
          <p className="mt-3 text-sm leading-6 text-muted">
            Select a node to inspect its sources, confidence, and direct neighbors.
            Select a line to inspect the relationship.
          </p>
          <div className="mt-5 space-y-2 rounded-lg border border-line bg-paper p-3 text-[11px] leading-5 text-muted">
            <p><strong className="text-ink">Tap</strong> a node or relationship for details.</p>
            <p><strong className="text-ink">Double-tap</strong> a node, or use Explore neighbors, to pull in what it connects to.</p>
            <p><strong className="text-ink">Drag and pinch</strong> to move around the canvas.</p>
          </div>
        </div>
      )}

      <div className="border-t-2 border-ink p-5">
        <div className="flex items-center justify-between">
          <SectionHeading>Relationship types</SectionHeading>
          <button
            type="button"
            onClick={onExport}
            className="flex items-center gap-1.5 text-[10px] font-bold text-orange-dark hover:underline"
          >
            Export JSON
          </button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {Object.entries(stats?.edges_by_type ?? {}).slice(0, 8).map(([type, count]) => (
            <span
              key={type}
              className="rounded-full border border-line bg-paper px-2.5 py-1 font-mono text-[8px] font-semibold"
            >
              {relationshipLabel(type)} · {count}
            </span>
          ))}
        </div>
      </div>
    </aside>
  )
}
