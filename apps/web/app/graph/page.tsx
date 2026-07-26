'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import {
  ArrowLeft,
  ArrowUpRight,
  Eye,
  EyeOff,
  Focus,
  Maximize2,
  Minus,
  Network,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  RefreshCw,
  Search,
  X,
} from 'lucide-react'
import AppLayout from '../../components/AppLayout'
import StudioTopbar from '../../components/StudioTopbar'
import { Button } from '../../components/ui/button'
import { API_URL, apiFetch, getActiveOrgId } from '../../lib/api'
import { useTheme } from '../../components/ThemeProvider'
import KnowledgeGraphCanvas from '../../components/graph/KnowledgeGraphCanvas'
import GraphDetailsPanel from '../../components/graph/GraphDetailsPanel'
import {
  ENTITY_TYPES,
  directNeighbors,
  entityPalette,
  mergeEdges,
  mergeNodes,
  neighborhoodIds,
  normalizeEdge,
  normalizeNode,
  relationshipLabel,
  toGraphView,
  typeColor,
} from '../../components/graph/graph-transform'
import type {
  GraphCanvasHandle,
  GraphEdge,
  GraphNode,
  GraphSelection,
  GraphStats,
  GraphStatusFilter,
} from '../../components/graph/types'

/** Node labels stay readable up to this many nodes; past it, only the hubs. */
const ALL_LABELS_BELOW = 30

/**
 * The force layout keeps moving for a while after mount, so a single fit lands
 * on a graph that is still collapsing into place. A short burst of fits covers
 * it. The burst stays short on purpose: each fit re-centres the graph, which
 * re-triggers the edge springs, so late fits make the canvas flare rather than
 * settle. Fitting also stops the moment the reader touches the camera, so the
 * view never yanks itself out from under someone who has started exploring.
 */
const FIT_DELAYS_MS = [400, 1200, 2400]

/**
 * How much of the company graph the overview draws at once.
 *
 * A real company brain runs to thousands of entities, and drawing them all
 * produces a hairball that answers no question. The server already returns the
 * best-connected matches first, so a hundred of them is a readable starting
 * point; everything else is reached deliberately, by searching, filtering, or
 * expanding a neighbourhood.
 */
const OVERVIEW_LIMIT = 100

/** Typing pauses this long before the server is asked anything. */
const SEARCH_DEBOUNCE_MS = 275

/**
 * Ceilings on progressive expansion. Without them a few enthusiastic
 * double-taps rebuild the hairball the overview limit exists to prevent.
 */
const MAX_EXPANSIONS = 25
const MAX_VISIBLE_NODES = 600

/**
 * Above this many nodes the graph is drawn without animation.
 *
 * Reagraph animates each edge from the graph's centre to its endpoints. While
 * the force layout is still moving, those springs keep restarting, and the
 * canvas fills with long rays reaching out of the cluster to nothing — geometry
 * caught mid-flight, not relationships. Small graphs settle before it shows;
 * larger ones do not, so they skip the entrance entirely. It is also the
 * cheaper way to draw a hundred nodes.
 */
const ANIMATE_BELOW = 40

export default function GraphPage() {
  const { theme } = useTheme()
  const palette = entityPalette(theme)

  // What the server returned for the current filters, kept separate from
  // anything the reader expanded so "Back to overview" is a state reset rather
  // than another round trip.
  const [serverNodes, setServerNodes] = useState<GraphNode[]>([])
  const [serverEdges, setServerEdges] = useState<GraphEdge[]>([])
  const [total, setTotal] = useState(0)
  const [truncated, setTruncated] = useState(false)

  const [expandedNodes, setExpandedNodes] = useState<GraphNode[]>([])
  const [expandedEdges, setExpandedEdges] = useState<GraphEdge[]>([])

  const [stats, setStats] = useState<GraphStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [expanding, setExpanding] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [searchQuery, setSearchQuery] = useState('')
  // What the server has actually been asked for, which lags the input box by
  // one debounce interval.
  const [activeSearch, setActiveSearch] = useState('')
  const [selectedTypes, setSelectedTypes] = useState<string[]>([])
  const [status, setStatus] = useState<GraphStatusFilter>('all')

  const [selection, setSelection] = useState<GraphSelection>(null)
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null)
  const [hovered, setHovered] = useState<string | null>(null)
  const [showLabels, setShowLabels] = useState(true)
  const [detailsOpen, setDetailsOpen] = useState(true)
  const [reducedMotion, setReducedMotion] = useState(false)

  const containerRef = useRef<HTMLDivElement>(null)
  const canvasHandle = useRef<GraphCanvasHandle | null>(null)

  // Neighbourhoods are immutable for a given reader, so re-expanding a node —
  // or coming back to one after leaving focus — costs nothing the second time.
  const neighborCache = useRef(new Map<string, { nodes: GraphNode[]; edges: GraphEdge[] }>())
  // Guards against a double-tap firing the same request twice.
  const inFlight = useRef(new Set<string>())
  const [expandedIds, setExpandedIds] = useState<string[]>([])
  // Only the newest graph request may write to state; an earlier one that
  // happens to land later must not overwrite it.
  const requestSeq = useRef(0)
  const graphRequest = useRef<AbortController | null>(null)

  // Once the reader pans or zooms, the graph is theirs; scheduled fits stop.
  const viewAdjusted = useRef(false)

  const handleCanvasReady = useCallback((handle: GraphCanvasHandle) => {
    canvasHandle.current = handle
  }, [])

  const handleViewAdjusted = useCallback(() => {
    viewAdjusted.current = true
  }, [])

  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReducedMotion(query.matches)
    update()
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])

  // Search runs on the server, so it waits for a pause in typing rather than
  // firing a query per keystroke.
  useEffect(() => {
    const timeout = window.setTimeout(
      () => setActiveSearch(searchQuery.trim()),
      SEARCH_DEBOUNCE_MS,
    )
    return () => window.clearTimeout(timeout)
  }, [searchQuery])

  const fetchGraph = useCallback(async () => {
    graphRequest.current?.abort()
    const controller = new AbortController()
    graphRequest.current = controller
    const sequence = requestSeq.current + 1
    requestSeq.current = sequence

    setLoading(true)
    setError(null)
    try {
      const orgId = getActiveOrgId()
      const params = new URLSearchParams({
        org_id: orgId,
        limit: String(OVERVIEW_LIMIT),
        status,
      })
      if (selectedTypes.length) params.set('entity_types', selectedTypes.join(','))
      if (activeSearch) params.set('query', activeSearch)

      const [graphRes, statsRes] = await Promise.all([
        apiFetch(`${API_URL}/graph?${params.toString()}`, { signal: controller.signal }),
        apiFetch(`${API_URL}/graph/stats?org_id=${encodeURIComponent(orgId)}`, {
          signal: controller.signal,
        }),
      ])
      if (!graphRes.ok) {
        const body = await graphRes.json().catch(() => null)
        throw new Error(body?.detail || 'Failed to fetch graph')
      }

      const payload = await graphRes.json()
      const statsPayload = statsRes.ok ? await statsRes.json() : null

      // A slower earlier request must never replace a newer answer.
      if (sequence !== requestSeq.current) return

      const nodes = (payload.nodes ?? [])
        .map(normalizeNode)
        .filter((node: GraphNode | null): node is GraphNode => node !== null)
      const edges = (payload.edges ?? [])
        .map(normalizeEdge)
        .filter((edge: GraphEdge | null): edge is GraphEdge => edge !== null)

      setServerNodes(nodes)
      setServerEdges(edges)
      setTotal(payload.total ?? nodes.length)
      setTruncated(Boolean(payload.truncated))
      // Filters changed, so anything expanded under the old filters no longer
      // belongs on screen. The cache survives — the neighbourhoods themselves
      // did not change.
      setExpandedNodes([])
      setExpandedEdges([])
      setExpandedIds([])
      setFocusNodeId(null)
      setSelection(null)

      if (statsPayload) setStats(statsPayload)
    } catch (fetchError) {
      // An abort means a newer request replaced this one, which is not a
      // failure the reader should hear about.
      if (fetchError instanceof DOMException && fetchError.name === 'AbortError') return
      console.error('Graph fetch error:', fetchError)
      setError(fetchError instanceof Error ? fetchError.message : 'Failed to load graph')
    } finally {
      if (sequence === requestSeq.current) setLoading(false)
    }
  }, [activeSearch, selectedTypes, status])

  useEffect(() => {
    void fetchGraph()
  }, [fetchGraph])

  useEffect(() => () => graphRequest.current?.abort(), [])

  // --- The graph as it currently stands ------------------------------------

  const allNodes = useMemo(
    () => mergeNodes(serverNodes, expandedNodes),
    [serverNodes, expandedNodes],
  )
  const allEdges = useMemo(
    () => mergeEdges(serverEdges, expandedEdges),
    [serverEdges, expandedEdges],
  )

  // Focus narrows the canvas to one node and its immediate neighbours. The
  // wider graph is not discarded, only hidden, so leaving focus is instant.
  const { visibleNodes, visibleEdges } = useMemo(() => {
    if (!focusNodeId) return { visibleNodes: allNodes, visibleEdges: allEdges }
    const ids = neighborhoodIds(focusNodeId, allEdges)
    return {
      visibleNodes: allNodes.filter(node => ids.has(node.id)),
      visibleEdges: allEdges.filter(edge => ids.has(edge.source) && ids.has(edge.target)),
    }
  }, [allEdges, allNodes, focusNodeId])

  const view = useMemo(
    () => toGraphView(visibleNodes, visibleEdges, theme),
    [visibleNodes, visibleEdges, theme],
  )

  const nodesById = useMemo(
    () => new Map(visibleNodes.map(node => [node.id, node])),
    [visibleNodes],
  )
  const edgesById = useMemo(
    () => new Map(view.edges.map(edge => [edge.id, edge])),
    [view.edges],
  )

  const selectedNode = selection?.kind === 'node' ? nodesById.get(selection.id) ?? null : null
  const selectedEdge = selection?.kind === 'edge' ? edgesById.get(selection.id) ?? null : null

  const selections = useMemo(() => (selection ? [selection.id] : []), [selection])

  /**
   * While a node is selected the rest of the graph dims; its direct
   * neighbourhood stays lit so the reader can see what it touches without
   * losing the shape of everything else.
   */
  const actives = useMemo(() => {
    if (!selectedNode) return []
    const ids = neighborhoodIds(selectedNode.id, visibleEdges)
    const edgeIds = view.edges
      .filter(edge => edge.source === selectedNode.id || edge.target === selectedNode.id)
      .map(edge => edge.id)
    return [...Array.from(ids), ...edgeIds]
  }, [selectedNode, view.edges, visibleEdges])

  const selectedNeighbors = useMemo(
    () => (selectedNode ? directNeighbors(selectedNode.id, visibleNodes, visibleEdges) : []),
    [selectedNode, visibleNodes, visibleEdges],
  )

  /**
   * The relationships touching the selected node, so the panel can offer them
   * as rows. Clicking a two-pixel line on a canvas is a poor way to reach a
   * relationship; this is the same selection by a reliable route.
   */
  const incidentEdges = useMemo(() => {
    if (!selectedNode) return []
    return view.edges.filter(
      edge => edge.source === selectedNode.id || edge.target === selectedNode.id,
    )
  }, [selectedNode, view.edges])

  const labelType = useMemo(() => {
    if (!showLabels) return 'none' as const
    return view.nodes.length <= ALL_LABELS_BELOW ? ('nodes' as const) : ('auto' as const)
  }, [showLabels, view.nodes.length])

  // Refit whenever the visible set changes shape, as the layout settles.
  useEffect(() => {
    if (!view.nodes.length) return
    viewAdjusted.current = false
    const timeouts = FIT_DELAYS_MS.map(delay => window.setTimeout(() => {
      if (!viewAdjusted.current) canvasHandle.current?.fitView()
    }, delay))
    return () => timeouts.forEach(window.clearTimeout)
  }, [view.nodes.length, focusNodeId])

  // --- Interactions ---------------------------------------------------------

  const selectNode = useCallback((id: string) => {
    setSelection({ kind: 'node', id })
    setDetailsOpen(true)
  }, [])

  const selectEdge = useCallback((id: string) => {
    setSelection({ kind: 'edge', id })
    setDetailsOpen(true)
  }, [])

  const clearSelection = useCallback(() => setSelection(null), [])

  /** Selecting from the panel also brings the node into view on the canvas. */
  const selectAndCenter = useCallback((id: string) => {
    selectNode(id)
    canvasHandle.current?.centerOn([id])
  }, [selectNode])

  /**
   * Pull in one hop around a node. The merge is keyed by id, so expanding the
   * same region twice, or reaching a node from two directions, never duplicates
   * it on the canvas.
   */
  const expandNode = useCallback(async (id: string) => {
    if (inFlight.current.has(id)) return
    selectNode(id)

    const cached = neighborCache.current.get(id)
    if (cached) {
      setExpandedNodes(current => mergeNodes(current, cached.nodes))
      setExpandedEdges(current => mergeEdges(current, cached.edges))
      setExpandedIds(current => (current.includes(id) ? current : [...current, id]))
      return
    }

    if (expandedIds.length >= MAX_EXPANSIONS) {
      setError(
        `That is ${MAX_EXPANSIONS} expansions in one view. Back to overview, `
        + 'or narrow the graph with search and filters, to keep exploring.',
      )
      return
    }
    if (allNodes.length >= MAX_VISIBLE_NODES) {
      setError(
        `The canvas is holding ${allNodes.length.toLocaleString()} entities, which is `
        + 'as many as stays readable. Focus a node or return to the overview to continue.',
      )
      return
    }

    inFlight.current.add(id)
    setExpanding(id)
    setError(null)
    try {
      const orgId = getActiveOrgId()
      const response = await apiFetch(
        `${API_URL}/graph/neighbors/${encodeURIComponent(id)}`
        + `?org_id=${encodeURIComponent(orgId)}&depth=1`,
      )
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(body?.detail || 'Failed to load neighbours')
      }
      const payload = await response.json()
      const nodes = (payload.nodes ?? [])
        .map(normalizeNode)
        .filter((node: GraphNode | null): node is GraphNode => node !== null)
      const edges = (payload.edges ?? [])
        .map(normalizeEdge)
        .filter((edge: GraphEdge | null): edge is GraphEdge => edge !== null)

      neighborCache.current.set(id, { nodes, edges })
      setExpandedNodes(current => mergeNodes(current, nodes))
      setExpandedEdges(current => mergeEdges(current, edges))
      setExpandedIds(current => (current.includes(id) ? current : [...current, id]))
    } catch (expandError) {
      console.error('Neighbour fetch error:', expandError)
      setError(expandError instanceof Error ? expandError.message : 'Failed to load neighbours')
    } finally {
      inFlight.current.delete(id)
      setExpanding(null)
    }
  }, [allNodes.length, expandedIds.length, selectNode])

  const handleExpandNode = useCallback((id: string) => {
    void expandNode(id)
  }, [expandNode])

  const focusOn = useCallback((id: string) => {
    setFocusNodeId(id)
    setSelection({ kind: 'node', id })
    setDetailsOpen(true)
  }, [])

  /** Focus is a toggle: pressing it on the focused node returns to the overview. */
  const toggleFocus = useCallback((id: string) => {
    setFocusNodeId(current => (current === id ? null : id))
    setSelection({ kind: 'node', id })
    setDetailsOpen(true)
  }, [])

  const backToOverview = useCallback(() => {
    setFocusNodeId(null)
    setExpandedNodes([])
    setExpandedEdges([])
    setExpandedIds([])
    setSelection(null)
    setError(null)
  }, [])

  const toggleType = (type: string) => {
    setSelectedTypes(current => (
      current.includes(type) ? current.filter(value => value !== type) : [...current, type]
    ))
  }

  const resetFilters = () => {
    setSearchQuery('')
    setSelectedTypes([])
    setStatus('all')
  }

  const exportGraph = () => {
    const payload = {
      exported_at: new Date().toISOString(),
      filters: { query: activeSearch, entity_types: selectedTypes, status },
      focus: focusNodeId,
      nodes: visibleNodes,
      edges: visibleEdges,
      total,
      truncated,
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `komponist-graph-${new Date().toISOString().slice(0, 10)}.json`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const toggleFullscreen = async () => {
    const container = containerRef.current
    if (!container) return
    if (document.fullscreenElement) await document.exitFullscreen()
    else await container.requestFullscreen()
  }

  // Escape clears the selection, matching the background click.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setSelection(null)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  const visibleTypes = useMemo(
    () => ENTITY_TYPES
      .map(type => [type, stats?.nodes_by_type?.[type] ?? 0] as const)
      .filter(([, count]) => count > 0),
    [stats],
  )

  const activeFilterCount =
    selectedTypes.length + (status === 'all' ? 0 : 1) + (activeSearch ? 1 : 0)

  /**
   * What the canvas is showing against what exists. `total` is the count the
   * current filters match; `stats.total_nodes` is everything the reader can
   * see. Naming both when they differ is the difference between "your graph is
   * small" and "you are looking at a slice of it".
   */
  const coverage = useMemo(() => {
    const shown = view.nodes.length.toLocaleString()
    const matching = total.toLocaleString()
    if (activeFilterCount && stats) {
      return `Showing ${shown} of ${matching} matching · ${stats.total_nodes.toLocaleString()} total`
    }
    return `Showing ${shown} of ${matching} entities`
  }, [activeFilterCount, stats, total, view.nodes.length])
  const hoveredLabel = hovered
    ? nodesById.get(hovered)?.name
      ?? (edgesById.get(hovered) ? relationshipLabel(edgesById.get(hovered)!.data.type) : null)
    : null

  return (
    <AppLayout>
      <StudioTopbar
        section="Company brain"
        title="Knowledge Graph"
        description="Explore how confirmed company knowledge connects"
        icon={Network}
        actions={
          <>
            <Button
              onClick={() => setDetailsOpen(open => !open)}
              variant="subtle"
              size="icon"
              aria-label={detailsOpen ? 'Hide graph details' : 'Show graph details'}
            >
              {detailsOpen ? <PanelRightClose /> : <PanelRightOpen />}
            </Button>
            <Button onClick={() => void fetchGraph()} variant="subtle" size="sm" disabled={loading}>
              <RefreshCw className={loading ? 'animate-spin' : ''} />
              <span className="hidden sm:inline">Refresh</span>
            </Button>
          </>
        }
      />

      <div className="graph-page-body">
        <section className="border-b-2 border-ink bg-paper px-4 py-3 sm:px-6">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
            <div className="relative min-w-0 flex-1 xl:max-w-md">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
              <input
                value={searchQuery}
                onChange={event => setSearchQuery(event.target.value)}
                placeholder="Search decisions, goals, constraints, projects…"
                className="h-11 w-full rounded-lg border-2 border-ink bg-white pl-10 pr-10 text-sm font-semibold outline-none transition focus:shadow-[3px_3px_0_#e8641b]"
                aria-label="Search graph"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery('')}
                  className="absolute right-2 top-1/2 grid size-7 -translate-y-1/2 place-items-center rounded hover:bg-paper-2"
                  aria-label="Clear graph search"
                >
                  <X className="size-3.5" />
                </button>
              )}
            </div>

            <div className="flex min-w-0 flex-1 gap-2 overflow-x-auto pb-1 xl:pb-0">
              {visibleTypes.map(([type, count]) => {
                const active = selectedTypes.includes(type)
                return (
                  <button
                    key={type}
                    type="button"
                    onClick={() => toggleType(type)}
                    aria-pressed={active}
                    className={`flex h-10 shrink-0 items-center gap-2 rounded-lg border-2 px-3 text-xs font-bold transition ${
                      active ? 'border-ink bg-ink text-white shadow-[2px_2px_0_#e8641b]' : 'border-line bg-white hover:border-ink'
                    }`}
                  >
                    <span className="size-2.5 rounded-full" style={{ background: typeColor(type, theme) }} />
                    {type}
                    <span className={active ? 'text-white/55' : 'text-muted'}>{count.toLocaleString()}</span>
                  </button>
                )
              })}
            </div>

            <div className="flex shrink-0 items-center gap-2">
              <div className="flex rounded-lg border-2 border-ink bg-white p-1" role="group" aria-label="Filter by status">
                {(['all', 'confirmed', 'proposed'] as GraphStatusFilter[]).map(value => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setStatus(value)}
                    aria-pressed={status === value}
                    className={`h-8 rounded-md px-3 text-[10px] font-bold capitalize transition ${
                      status === value ? 'bg-ink text-white' : 'text-muted hover:bg-paper-2 hover:text-ink'
                    }`}
                  >
                    {value}
                  </button>
                ))}
              </div>
              {activeFilterCount > 0 && (
                <Button variant="ghost" size="sm" onClick={resetFilters}>Clear {activeFilterCount}</Button>
              )}
            </div>
          </div>
        </section>

        {error && (
          <div className="mx-4 mt-4 rounded-lg border-2 border-danger bg-danger-soft p-4 text-sm font-semibold text-danger sm:mx-6" role="alert">
            {error}
          </div>
        )}

        {!loading && !error && allNodes.length === 0 ? (
          <div className="grid min-h-[520px] place-items-center p-6">
            <div className="max-w-md rounded-xl border-2 border-ink bg-white p-8 text-center shadow-[6px_6px_0_#201c15]">
              <span className="mx-auto grid size-14 place-items-center rounded-xl border-2 border-ink bg-warning-soft">
                <Network className="size-6" />
              </span>
              <h2 className="mt-5 text-2xl font-bold">{activeFilterCount ? 'No matching knowledge' : 'Your graph starts with a source'}</h2>
              <p className="mt-3 leading-7 text-muted">
                {activeFilterCount
                  ? 'Try a broader search or clear the active type and status filters.'
                  : 'Upload documents or connect Notion and Slack, then confirm the extracted knowledge in Review.'}
              </p>
              {activeFilterCount ? (
                <Button className="mt-6" onClick={resetFilters}>Clear filters</Button>
              ) : (
                <Button asChild className="mt-6"><Link href="/onboard">Add a source <ArrowUpRight /></Link></Button>
              )}
            </div>
          </div>
        ) : (
          <div className={`graph-workspace grid min-h-0 flex-1 ${detailsOpen ? 'lg:grid-cols-[minmax(0,1fr)_320px]' : 'grid-cols-1'}`}>
            <div className="graph-visualization relative min-h-0 min-w-0 border-ink lg:border-r-2">
              <div ref={containerRef} className="graph-canvas-container relative h-full min-h-[520px] overflow-hidden bg-paper-2">
                <KnowledgeGraphCanvas
                  nodes={view.nodes}
                  edges={view.edges}
                  theme={theme}
                  selections={selections}
                  actives={actives}
                  focusNodeId={focusNodeId}
                  labelType={labelType}
                  animated={!reducedMotion && view.nodes.length < ANIMATE_BELOW}
                  onSelectNode={selectNode}
                  onSelectEdge={selectEdge}
                  onClearSelection={clearSelection}
                  onExpandNode={handleExpandNode}
                  onHoverNode={setHovered}
                  onHoverEdge={setHovered}
                  onReady={handleCanvasReady}
                  onViewAdjusted={handleViewAdjusted}
                />

                {loading && (
                  <div className="absolute inset-0 z-20 grid place-items-center bg-paper/70 backdrop-blur-sm">
                    <div className="rounded-lg border-2 border-ink bg-white px-4 py-3 font-mono text-xs font-semibold shadow-[3px_3px_0_#201c15]">
                      <RefreshCw className="mr-2 inline size-4 animate-spin" /> Resolving visible graph…
                    </div>
                  </div>
                )}

                <div className="pointer-events-none absolute left-3 top-3 z-10 flex flex-col gap-2">
                  <div className="pointer-events-auto flex overflow-hidden rounded-lg border-2 border-ink bg-white shadow-[2px_2px_0_#201c15]">
                    <button type="button" className="grid size-9 place-items-center hover:bg-paper-2" onClick={() => canvasHandle.current?.zoomIn()} aria-label="Zoom in"><Plus className="size-4" /></button>
                    <button type="button" className="grid size-9 place-items-center border-l border-line hover:bg-paper-2" onClick={() => canvasHandle.current?.zoomOut()} aria-label="Zoom out"><Minus className="size-4" /></button>
                    <button type="button" className="grid size-9 place-items-center border-l border-line hover:bg-paper-2" onClick={() => canvasHandle.current?.fitView()} aria-label="Fit graph to view"><Focus className="size-4" /></button>
                    <button type="button" className="grid size-9 place-items-center border-l border-line hover:bg-paper-2" onClick={() => void toggleFullscreen()} aria-label="Toggle fullscreen"><Maximize2 className="size-4" /></button>
                  </div>
                  <button
                    type="button"
                    className="pointer-events-auto flex h-9 items-center gap-2 rounded-lg border-2 border-ink bg-white px-3 text-[10px] font-bold shadow-[2px_2px_0_#201c15]"
                    onClick={() => setShowLabels(value => !value)}
                    aria-pressed={showLabels}
                  >
                    {showLabels ? <Eye className="size-3.5" /> : <EyeOff className="size-3.5" />}
                    Labels
                  </button>
                  {focusNodeId && (
                    <button
                      type="button"
                      onClick={backToOverview}
                      className="pointer-events-auto flex h-9 items-center gap-2 rounded-lg border-2 border-ink bg-ink px-3 text-[10px] font-bold text-white shadow-[2px_2px_0_#e8641b]"
                    >
                      <ArrowLeft className="size-3.5" /> Back to overview
                    </button>
                  )}
                </div>

                {hoveredLabel && (
                  <div className="pointer-events-none absolute right-3 top-3 z-10 max-w-[60%] truncate rounded-lg border-2 border-ink bg-white px-3 py-1.5 text-[11px] font-semibold shadow-[2px_2px_0_#201c15]">
                    {hoveredLabel}
                  </div>
                )}

                <div className="pointer-events-none absolute bottom-3 left-3 z-10 flex max-w-[calc(100%-1.5rem)] flex-wrap items-center gap-2 rounded-lg border-2 border-ink bg-white/95 px-3 py-2 shadow-[2px_2px_0_#201c15] backdrop-blur">
                  <span className="font-mono text-[9px] font-bold uppercase tracking-wider text-muted">
                    {coverage}
                  </span>
                  <span className="h-4 w-px bg-line" />
                  {Object.entries(palette).map(([type, color]) => (
                    <span key={type} className="flex items-center gap-1.5 text-[9px] font-semibold">
                      <span className="size-2 rounded-full" style={{ background: color }} /> {type}
                    </span>
                  ))}
                  <span className="h-4 w-px bg-line" />
                  <span className="flex items-center gap-1.5 text-[9px] font-semibold text-muted">
                    <span className="size-2 rounded-full border-2 border-current" /> Proposed
                  </span>
                </div>
              </div>
            </div>

            {detailsOpen && (
              <GraphDetailsPanel
                theme={theme}
                stats={stats}
                coverage={coverage}
                truncated={truncated}
                overviewCount={serverNodes.length}
                total={total}
                expandedIds={expandedIds}
                selectedNode={selectedNode}
                selectedEdge={selectedEdge}
                neighbors={selectedNeighbors}
                incidentEdges={incidentEdges}
                nodesById={nodesById}
                focusNodeId={focusNodeId}
                expandingId={expanding}
                onClose={() => setDetailsOpen(false)}
                onSelectNode={selectAndCenter}
                onSelectEdge={selectEdge}
                onFocus={toggleFocus}
                onExpand={handleExpandNode}
                onExport={exportGraph}
              />
            )}
          </div>
        )}
      </div>
    </AppLayout>
  )
}
