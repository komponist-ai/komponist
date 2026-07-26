'use client'

import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import dynamic from 'next/dynamic'
import Link from 'next/link'
import {
  ArrowUpRight,
  Check,
  CircleDot,
  Download,
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
  Sparkles,
  X,
} from 'lucide-react'
import AppLayout from '../../components/AppLayout'
import StudioTopbar from '../../components/StudioTopbar'
import { Button } from '../../components/ui/button'
import { API_URL, apiFetch, getActiveOrgId } from '../../lib/api'
import { useTheme } from '../../components/ThemeProvider'

const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), {
  ssr: false,
  loading: () => (
    <div className="grid h-full min-h-[420px] place-items-center">
      <div className="flex items-center gap-2 font-mono text-xs text-muted">
        <RefreshCw className="size-4 animate-spin" /> Building graph view…
      </div>
    </div>
  ),
})
const ForceGraph = ForceGraph2D as any

interface GraphNode {
  id: string
  name: string
  type: string
  description?: string
  status?: 'confirmed' | 'proposed'
  confidence?: number
  degree?: number
  evidence_count?: number
  x?: number
  y?: number
  vx?: number
  vy?: number
}

interface GraphEdge {
  source: string | GraphNode
  target: string | GraphNode
  type: string
  description?: string
}

interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  total: number
  truncated: boolean
}

interface GraphStats {
  total_nodes: number
  total_edges: number
  nodes_by_type: Record<string, number>
  edges_by_type: Record<string, number>
}

type GraphStatus = 'all' | 'confirmed' | 'proposed'

const lightTypeColors: Record<string, string> = {
  Decision: '#e8641b',
  Goal: '#0e8a7d',
  Constraint: '#c2500d',
  Project: '#4a443a',
}

const darkTypeColors: Record<string, string> = {
  Decision: '#f58a49',
  Goal: '#73c9bd',
  Constraint: '#ffb174',
  Project: '#e7ddd0',
}

function endpointId(value: string | GraphNode) {
  return typeof value === 'string' ? value : value.id
}

export default function GraphPage() {
  const { theme } = useTheme()
  const palette = theme === 'dark' ? darkTypeColors : lightTypeColors
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], edges: [], total: 0, truncated: false })
  const [stats, setStats] = useState<GraphStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const deferredSearch = useDeferredValue(searchQuery)
  const [selectedTypes, setSelectedTypes] = useState<string[]>([])
  const [status, setStatus] = useState<GraphStatus>('all')
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null)
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null)
  const [showLabels, setShowLabels] = useState(true)
  const [detailsOpen, setDetailsOpen] = useState(true)
  const graphContainerRef = useRef<HTMLDivElement>(null)
  const graphRef = useRef<any>(null)
  const [graphSize, setGraphSize] = useState({ width: 0, height: 0 })

  const fetchGraph = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const orgId = getActiveOrgId()
      const params = new URLSearchParams({
        org_id: orgId,
        limit: '400',
        status,
      })
      if (selectedTypes.length) params.set('entity_types', selectedTypes.join(','))
      if (deferredSearch.trim()) params.set('query', deferredSearch.trim())

      const [graphRes, statsRes] = await Promise.all([
        apiFetch(`${API_URL}/graph?${params.toString()}`),
        apiFetch(`${API_URL}/graph/stats?org_id=${encodeURIComponent(orgId)}`),
      ])
      if (!graphRes.ok) {
        const body = await graphRes.json().catch(() => null)
        throw new Error(body?.detail || 'Failed to fetch graph')
      }

      const graph = await graphRes.json()
      const statsData = statsRes.ok ? await statsRes.json() : null
      setGraphData({
        nodes: graph.nodes || [],
        edges: (graph.edges || []).map((edge: GraphEdge) => ({ ...edge })),
        total: graph.total ?? graph.nodes?.length ?? 0,
        truncated: Boolean(graph.truncated),
      })
      if (statsData) setStats(statsData)
    } catch (fetchError) {
      console.error('Graph fetch error:', fetchError)
      setError(fetchError instanceof Error ? fetchError.message : 'Failed to load graph')
    } finally {
      setLoading(false)
    }
  }, [deferredSearch, selectedTypes, status])

  useEffect(() => {
    void fetchGraph()
  }, [fetchGraph])

  useEffect(() => {
    const container = graphContainerRef.current
    if (!container) return
    const updateGraphSize = () => {
      const { width, height } = container.getBoundingClientRect()
      setGraphSize({
        width: Math.max(0, Math.floor(width)),
        height: Math.max(0, Math.floor(height)),
      })
    }
    updateGraphSize()
    const observer = new ResizeObserver(updateGraphSize)
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!loading && graphData.nodes.length) {
      const timeout = window.setTimeout(() => graphRef.current?.zoomToFit?.(650, 80), 180)
      return () => window.clearTimeout(timeout)
    }
  }, [loading, graphData.nodes.length, selectedTypes, status, deferredSearch])

  const neighborIds = useMemo(() => {
    if (!focusNodeId) return null
    const ids = new Set<string>([focusNodeId])
    graphData.edges.forEach(edge => {
      const source = endpointId(edge.source)
      const target = endpointId(edge.target)
      if (source === focusNodeId) ids.add(target)
      if (target === focusNodeId) ids.add(source)
    })
    return ids
  }, [focusNodeId, graphData.edges])

  const selectedNeighbors = useMemo(() => {
    if (!selectedNode) return []
    const ids = new Set<string>()
    graphData.edges.forEach(edge => {
      const source = endpointId(edge.source)
      const target = endpointId(edge.target)
      if (source === selectedNode.id) ids.add(target)
      if (target === selectedNode.id) ids.add(source)
    })
    return graphData.nodes.filter(node => ids.has(node.id)).slice(0, 8)
  }, [graphData.edges, graphData.nodes, selectedNode])

  const visibleTypes = useMemo(
    () => Object.entries(stats?.nodes_by_type || {}).filter(([type]) => type in lightTypeColors),
    [stats],
  )

  const getNodeColor = useCallback((node: GraphNode) => (
    palette[node.type] || (theme === 'dark' ? '#aba092' : '#6b6257')
  ), [palette, theme])

  const getNodeRadius = useCallback((node: GraphNode) => (
    Math.min(12, 5.5 + Math.sqrt(Math.max(0, node.degree || 0)) * 1.45)
  ), [])

  const paintNode = useCallback((node: GraphNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const radius = getNodeRadius(node)
    const isSelected = selectedNode?.id === node.id
    const isFocused = focusNodeId === node.id
    const isDimmed = Boolean(neighborIds && !neighborIds.has(node.id))
    ctx.save()
    ctx.globalAlpha = isDimmed ? 0.12 : 1

    if (isSelected || isFocused) {
      ctx.beginPath()
      ctx.arc(node.x || 0, node.y || 0, radius + 5, 0, Math.PI * 2)
      ctx.fillStyle = isFocused ? 'rgba(14,138,125,0.2)' : 'rgba(232,100,27,0.22)'
      ctx.fill()
    }

    ctx.beginPath()
    ctx.arc(node.x || 0, node.y || 0, radius, 0, Math.PI * 2)
    ctx.fillStyle = getNodeColor(node)
    ctx.fill()
    ctx.strokeStyle = node.status === 'proposed'
      ? (theme === 'dark' ? '#f7efe2' : '#201c15')
      : (theme === 'dark' ? '#100e0b' : '#fffdf8')
    ctx.lineWidth = node.status === 'proposed' ? 2.2 : 1.6
    if (node.status === 'proposed') ctx.setLineDash([3, 2])
    ctx.stroke()
    ctx.setLineDash([])

    if (showLabels && (globalScale > 0.78 || isSelected || isFocused)) {
      const label = node.name.length > 32 ? `${node.name.slice(0, 31)}…` : node.name
      const fontSize = Math.max(3.6, 11 / globalScale)
      ctx.font = `600 ${fontSize}px Instrument Sans, sans-serif`
      const textWidth = ctx.measureText(label).width
      const x = node.x || 0
      const y = (node.y || 0) + radius + (9 / globalScale)
      ctx.fillStyle = theme === 'dark' ? 'rgba(16,14,11,0.9)' : 'rgba(255,253,248,0.94)'
      ctx.fillRect(x - textWidth / 2 - 4 / globalScale, y - fontSize + 1 / globalScale, textWidth + 8 / globalScale, fontSize + 5 / globalScale)
      ctx.fillStyle = theme === 'dark' ? '#f7efe2' : '#201c15'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'alphabetic'
      ctx.fillText(label, x, y)
    }
    ctx.restore()
  }, [focusNodeId, getNodeColor, getNodeRadius, neighborIds, selectedNode?.id, showLabels, theme])

  const paintPointerArea = useCallback((node: GraphNode, color: string, ctx: CanvasRenderingContext2D) => {
    ctx.fillStyle = color
    ctx.beginPath()
    ctx.arc(node.x || 0, node.y || 0, getNodeRadius(node) + 4, 0, Math.PI * 2)
    ctx.fill()
  }, [getNodeRadius])

  const selectNode = useCallback((node: GraphNode) => {
    setSelectedNode(node)
    setSelectedEdge(null)
    setDetailsOpen(true)
    if (node.x !== undefined && node.y !== undefined) {
      graphRef.current?.centerAt?.(node.x, node.y, 500)
      graphRef.current?.zoom?.(2.2, 500)
    }
  }, [])

  const toggleType = (type: string) => {
    setSelectedTypes(current => (
      current.includes(type) ? current.filter(value => value !== type) : [...current, type]
    ))
    setSelectedNode(null)
    setSelectedEdge(null)
    setFocusNodeId(null)
  }

  const resetFilters = () => {
    setSearchQuery('')
    setSelectedTypes([])
    setStatus('all')
    setSelectedNode(null)
    setSelectedEdge(null)
    setFocusNodeId(null)
  }

  const exportGraph = () => {
    const payload = {
      exported_at: new Date().toISOString(),
      filters: { query: deferredSearch, entity_types: selectedTypes, status },
      ...graphData,
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
    const container = graphContainerRef.current
    if (!container) return
    if (document.fullscreenElement) await document.exitFullscreen()
    else await container.requestFullscreen()
  }

  const activeFilterCount = selectedTypes.length + (status === 'all' ? 0 : 1) + (deferredSearch ? 1 : 0)

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
                    className={`flex h-10 shrink-0 items-center gap-2 rounded-lg border-2 px-3 text-xs font-bold transition ${
                      active ? 'border-ink bg-ink text-white shadow-[2px_2px_0_#e8641b]' : 'border-line bg-white hover:border-ink'
                    }`}
                  >
                    <span className="size-2.5 rounded-full" style={{ background: palette[type] || '#6b6257' }} />
                    {type}
                    <span className={active ? 'text-white/55' : 'text-muted'}>{count.toLocaleString()}</span>
                  </button>
                )
              })}
            </div>

            <div className="flex shrink-0 items-center gap-2">
              <div className="flex rounded-lg border-2 border-ink bg-white p-1">
                {(['all', 'confirmed', 'proposed'] as GraphStatus[]).map(value => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setStatus(value)}
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
          <div className="mx-4 mt-4 rounded-lg border-2 border-danger bg-danger-soft p-4 text-sm font-semibold text-danger sm:mx-6">
            {error}
          </div>
        )}

        {!loading && !error && graphData.nodes.length === 0 ? (
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
              <div ref={graphContainerRef} className="graph-canvas-container relative h-full min-h-[520px] overflow-hidden bg-paper-2">
                {loading && (
                  <div className="absolute inset-0 z-20 grid place-items-center bg-paper/70 backdrop-blur-sm">
                    <div className="rounded-lg border-2 border-ink bg-white px-4 py-3 font-mono text-xs font-semibold shadow-[3px_3px_0_#201c15]">
                      <RefreshCw className="mr-2 inline size-4 animate-spin" /> Resolving visible graph…
                    </div>
                  </div>
                )}
                {graphSize.width > 0 && graphSize.height > 0 && (
                  <ForceGraph
                    ref={graphRef}
                    width={graphSize.width}
                    height={graphSize.height}
                    graphData={{ nodes: graphData.nodes, links: graphData.edges }}
                    nodeId="id"
                    nodeLabel={(node: GraphNode) => `${node.name} · ${node.type}`}
                    nodeCanvasObject={paintNode}
                    nodeCanvasObjectMode={() => 'replace'}
                    nodePointerAreaPaint={paintPointerArea}
                    nodeRelSize={1}
                    nodeVal={(node: GraphNode) => getNodeRadius(node)}
                    linkSource="source"
                    linkTarget="target"
                    linkLabel={(edge: GraphEdge) => edge.type}
                    linkColor={(edge: GraphEdge) => {
                      const source = endpointId(edge.source)
                      const target = endpointId(edge.target)
                      if (selectedEdge === edge) return '#e8641b'
                      if (focusNodeId && (source === focusNodeId || target === focusNodeId)) return theme === 'dark' ? '#73c9bd' : '#0e8a7d'
                      if (neighborIds && (!neighborIds.has(source) || !neighborIds.has(target))) return theme === 'dark' ? '#29241e22' : '#d9cfbf33'
                      return theme === 'dark' ? '#655b4e' : '#c8bcaa'
                    }}
                    linkWidth={(edge: GraphEdge) => selectedEdge === edge ? 2.5 : 1.2}
                    linkDirectionalArrowLength={4}
                    linkDirectionalArrowRelPos={0.92}
                    linkDirectionalParticles={(edge: GraphEdge) => selectedEdge === edge ? 2 : 0}
                    linkDirectionalParticleWidth={2}
                    onNodeClick={(node: GraphNode) => selectNode(node)}
                    onNodeRightClick={(node: GraphNode) => {
                      setFocusNodeId(node.id)
                      selectNode(node)
                    }}
                    onLinkClick={(edge: GraphEdge) => {
                      setSelectedEdge(edge)
                      setSelectedNode(null)
                      setDetailsOpen(true)
                    }}
                    onBackgroundClick={() => {
                      setSelectedNode(null)
                      setSelectedEdge(null)
                    }}
                    backgroundColor={theme === 'dark' ? '#181510' : '#f6eedf'}
                    enableNodeDrag
                    enableZoomInteraction
                    enablePanInteraction
                    cooldownTime={1800}
                    cooldownTicks={60}
                    d3AlphaMin={0.035}
                  />
                )}

                <div className="absolute left-3 top-3 z-10 flex flex-col gap-2">
                  <div className="flex overflow-hidden rounded-lg border-2 border-ink bg-white shadow-[2px_2px_0_#201c15]">
                    <button type="button" className="grid size-9 place-items-center hover:bg-paper-2" onClick={() => graphRef.current?.zoom?.((graphRef.current?.zoom?.() || 1) * 1.35, 300)} aria-label="Zoom in"><Plus className="size-4" /></button>
                    <button type="button" className="grid size-9 place-items-center border-l border-line hover:bg-paper-2" onClick={() => graphRef.current?.zoom?.((graphRef.current?.zoom?.() || 1) / 1.35, 300)} aria-label="Zoom out"><Minus className="size-4" /></button>
                    <button type="button" className="grid size-9 place-items-center border-l border-line hover:bg-paper-2" onClick={() => graphRef.current?.zoomToFit?.(500, 70)} aria-label="Fit graph"><Focus className="size-4" /></button>
                    <button type="button" className="grid size-9 place-items-center border-l border-line hover:bg-paper-2" onClick={() => void toggleFullscreen()} aria-label="Open fullscreen"><Maximize2 className="size-4" /></button>
                  </div>
                  <button
                    type="button"
                    className="flex h-9 items-center gap-2 rounded-lg border-2 border-ink bg-white px-3 text-[10px] font-bold shadow-[2px_2px_0_#201c15]"
                    onClick={() => setShowLabels(value => !value)}
                  >
                    {showLabels ? <Eye className="size-3.5" /> : <EyeOff className="size-3.5" />}
                    Labels
                  </button>
                </div>

                <div className="absolute bottom-3 left-3 z-10 flex max-w-[calc(100%-1.5rem)] flex-wrap items-center gap-2 rounded-lg border-2 border-ink bg-white/95 px-3 py-2 shadow-[2px_2px_0_#201c15] backdrop-blur">
                  <span className="font-mono text-[9px] font-bold uppercase tracking-wider text-muted">
                    {graphData.nodes.length.toLocaleString()} / {graphData.total.toLocaleString()} entities
                  </span>
                  <span className="h-4 w-px bg-line" />
                  {Object.entries(palette).map(([type, color]) => (
                    <span key={type} className="flex items-center gap-1.5 text-[9px] font-semibold">
                      <span className="size-2 rounded-full" style={{ background: color }} /> {type}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {detailsOpen && (
              <aside className="graph-side-panel min-h-0 overflow-y-auto bg-white">
                <div className="border-b-2 border-ink p-5">
                  <div className="flex items-center justify-between">
                    <p className="font-mono text-[9px] font-bold uppercase tracking-[0.12em] text-muted">Graph overview</p>
                    <button type="button" onClick={() => setDetailsOpen(false)} className="grid size-8 place-items-center rounded-md hover:bg-paper-2" aria-label="Close graph details"><X className="size-4" /></button>
                  </div>
                  <div className="mt-4 grid grid-cols-2 gap-3">
                    <div className="rounded-lg border-2 border-ink bg-paper p-3">
                      <strong className="block font-mono text-2xl">{(stats?.total_nodes || 0).toLocaleString()}</strong>
                      <span className="text-[10px] font-semibold text-muted">Visible entities</span>
                    </div>
                    <div className="rounded-lg border-2 border-ink bg-paper p-3">
                      <strong className="block font-mono text-2xl">{(stats?.total_edges || 0).toLocaleString()}</strong>
                      <span className="text-[10px] font-semibold text-muted">Relationships</span>
                    </div>
                  </div>
                  {graphData.truncated && (
                    <p className="mt-3 rounded-md bg-warning-soft p-2.5 text-[10px] leading-4 text-orange-dark">
                      The canvas shows the {graphData.nodes.length.toLocaleString()} most connected/recent matches. Search narrows the full visible graph.
                    </p>
                  )}
                </div>

                {selectedNode ? (
                  <div className="p-5">
                    <div className="flex items-center justify-between gap-3">
                      <span
                        className="rounded-full border border-ink px-2.5 py-1 font-mono text-[9px] font-bold uppercase tracking-wider text-white"
                        style={{ background: palette[selectedNode.type] || '#6b6257' }}
                      >
                        {selectedNode.type}
                      </span>
                      <span className={`flex items-center gap-1.5 text-[10px] font-bold ${selectedNode.status === 'confirmed' ? 'text-teal' : 'text-orange-dark'}`}>
                        {selectedNode.status === 'confirmed' ? <Check className="size-3.5" /> : <CircleDot className="size-3.5" />}
                        {selectedNode.status || 'unknown'}
                      </span>
                    </div>
                    <h2 className="mt-4 text-2xl font-bold leading-tight">{selectedNode.name}</h2>
                    {selectedNode.description && <p className="mt-3 text-sm leading-6 text-ink-2">{selectedNode.description}</p>}

                    <div className="mt-5 grid grid-cols-3 gap-2">
                      {[
                        [selectedNode.degree || 0, 'Links'],
                        [selectedNode.evidence_count || 0, 'Sources'],
                        [selectedNode.confidence === undefined ? '—' : `${Math.round(selectedNode.confidence * 100)}%`, 'Confidence'],
                      ].map(([value, label]) => (
                        <div key={label as string} className="rounded-md border border-line bg-paper p-2 text-center">
                          <strong className="block font-mono text-sm">{value}</strong>
                          <span className="text-[9px] text-muted">{label}</span>
                        </div>
                      ))}
                    </div>

                    <div className="mt-5 flex gap-2">
                      <Button
                        size="sm"
                        variant={focusNodeId === selectedNode.id ? 'default' : 'outline'}
                        className="flex-1"
                        onClick={() => setFocusNodeId(current => current === selectedNode.id ? null : selectedNode.id)}
                      >
                        <Focus /> {focusNodeId === selectedNode.id ? 'Focused' : 'Focus'}
                      </Button>
                      <Button asChild size="sm" variant="subtle" className="flex-1">
                        <Link href="/entities">Browse library <ArrowUpRight /></Link>
                      </Button>
                    </div>

                    {selectedNeighbors.length > 0 && (
                      <div className="mt-7 border-t border-line pt-5">
                        <p className="font-mono text-[9px] font-bold uppercase tracking-wider text-muted">Connected knowledge</p>
                        <div className="mt-3 space-y-2">
                          {selectedNeighbors.map(node => (
                            <button
                              key={node.id}
                              type="button"
                              onClick={() => selectNode(node)}
                              className="flex w-full items-center gap-3 rounded-lg border border-line bg-paper p-2.5 text-left transition hover:border-ink"
                            >
                              <span className="size-2.5 shrink-0 rounded-full" style={{ background: palette[node.type] || '#6b6257' }} />
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
                    <p className="font-mono text-[9px] font-bold uppercase tracking-wider text-orange-dark">Relationship</p>
                    <h2 className="mt-3 text-2xl font-bold">{selectedEdge.type.replaceAll('_', ' ')}</h2>
                    <p className="mt-3 text-sm leading-6 text-muted">{selectedEdge.description || 'This relationship connects two facts in the company graph.'}</p>
                    <div className="mt-5 space-y-2">
                      {[endpointId(selectedEdge.source), endpointId(selectedEdge.target)].map((id, index) => {
                        const node = graphData.nodes.find(item => item.id === id)
                        if (!node) return null
                        return (
                          <button key={id} type="button" onClick={() => selectNode(node)} className="w-full rounded-lg border-2 border-ink bg-paper p-3 text-left">
                            <span className="font-mono text-[8px] uppercase text-muted">{index === 0 ? 'From' : 'To'} · {node.type}</span>
                            <strong className="mt-1 block text-sm">{node.name}</strong>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                ) : (
                  <div className="p-5">
                    <span className="grid size-12 place-items-center rounded-lg border-2 border-ink bg-info-soft">
                      <Sparkles className="size-5" />
                    </span>
                    <h2 className="mt-5 text-2xl font-bold">Explore the context</h2>
                    <p className="mt-3 text-sm leading-6 text-muted">
                      Select a node to inspect its evidence, confidence, and direct neighbors. Select a line to inspect the relationship.
                    </p>
                    <div className="mt-5 space-y-2 rounded-lg border border-line bg-paper p-3 text-[11px] leading-5 text-muted">
                      <p><strong className="text-ink">Click</strong> a node or relationship for details.</p>
                      <p><strong className="text-ink">Right-click</strong> a node to isolate its neighborhood.</p>
                      <p><strong className="text-ink">Drag and scroll</strong> to navigate the canvas.</p>
                    </div>
                  </div>
                )}

                <div className="border-t-2 border-ink p-5">
                  <div className="flex items-center justify-between">
                    <p className="font-mono text-[9px] font-bold uppercase tracking-wider text-muted">Relationship types</p>
                    <button type="button" onClick={exportGraph} className="flex items-center gap-1.5 text-[10px] font-bold text-orange-dark hover:underline">
                      <Download className="size-3.5" /> Export JSON
                    </button>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {Object.entries(stats?.edges_by_type || {}).slice(0, 8).map(([type, count]) => (
                      <span key={type} className="rounded-full border border-line bg-paper px-2.5 py-1 font-mono text-[8px] font-semibold">
                        {type.replaceAll('_', ' ')} · {count}
                      </span>
                    ))}
                  </div>
                </div>
              </aside>
            )}
          </div>
        )}
      </div>
    </AppLayout>
  )
}
