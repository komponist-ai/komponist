'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import dynamic from 'next/dynamic'
import Link from 'next/link'
import { Network, RefreshCw } from 'lucide-react'
import AppLayout from '../../components/AppLayout'
import StudioTopbar from '../../components/StudioTopbar'
import { Button } from '../../components/ui/button'
import { API_URL, apiFetch, getActiveOrgId } from '../../lib/api'
import { useTheme } from '../../components/ThemeProvider'

const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), {
  ssr: false,
  loading: () => <div className="flex items-center justify-center h-96">Loading graph...</div>
})

interface GraphNode {
  id: string
  name: string
  type: string
  description?: string
  status?: string
  // Force graph props
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
}

interface GraphStats {
  total_nodes: number
  total_edges: number
  nodes_by_type: Record<string, number>
  edges_by_type: Record<string, number>
}

// Color palette for entity types
const lightTypeColors: Record<string, string> = {
  Person: '#e8641b',      // orange
  Concept: '#0e8a7d',     // teal
  Fact: '#6b6257',        // muted
  Decision: '#c2500d',    // orange-dark
  Goal: '#7bc4b9',        // teal-light
  Project: '#4a443a',     // ink-2
  Tool: '#f5a46b',        // peach
  Location: '#9a9184',    // faint
  Organization: '#201c15', // ink
  Event: '#d9cfbf',       // line
  Instruction: '#efe5d2', // paper-3
  Note: '#f6eedf',        // paper-2
}

const darkTypeColors: Record<string, string> = {
  ...lightTypeColors,
  Fact: '#aba092',
  Project: '#d6cbbb',
  Location: '#b9aea0',
  Organization: '#f7efe2',
  Event: '#7d7468',
  Instruction: '#b69b7b',
  Note: '#685b4b',
}

export default function GraphPage() {
  const { theme } = useTheme()
  const typeColors = theme === 'dark' ? darkTypeColors : lightTypeColors
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], edges: [] })
  const [stats, setStats] = useState<GraphStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const graphContainerRef = useRef<HTMLDivElement>(null)
  const [graphSize, setGraphSize] = useState({ width: 0, height: 0 })

  const fetchGraph = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      const orgId = getActiveOrgId()

      // Fetch graph data and stats in parallel
      const [graphRes, statsRes] = await Promise.all([
        apiFetch(`${API_URL}/graph?org_id=${orgId}&limit=300`),
        apiFetch(`${API_URL}/graph/stats?org_id=${orgId}`)
      ])

      if (!graphRes.ok) throw new Error('Failed to fetch graph')

      const graph = await graphRes.json()
      const statsData = await statsRes.json()

      // Transform for force graph (edges need to reference node objects or IDs)
      setGraphData({
        nodes: graph.nodes || [],
        edges: (graph.edges || []).map((e: any) => ({
          ...e,
          source: e.source,
          target: e.target
        }))
      })

      setStats(statsData)
    } catch (err: any) {
      console.error('Graph fetch error:', err)
      setError(err.message || 'Failed to load graph')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchGraph()
  }, [fetchGraph])

  useEffect(() => {
    const container = graphContainerRef.current
    if (!container) return

    const updateGraphSize = () => {
      const { width, height } = container.getBoundingClientRect()
      setGraphSize({
        width: Math.max(0, Math.floor(width)),
        height: Math.max(0, Math.floor(height))
      })
    }

    updateGraphSize()
    const observer = new ResizeObserver(updateGraphSize)
    observer.observe(container)

    return () => observer.disconnect()
  }, [loading, graphData.nodes.length])

  const handleNodeClick = useCallback((node: any) => {
    setSelectedNode(node as GraphNode)
  }, [])

  const getNodeColor = useCallback((node: GraphNode) => {
    const palette = theme === 'dark' ? darkTypeColors : lightTypeColors
    return palette[node.type] || (theme === 'dark' ? '#aba092' : '#6b6257')
  }, [theme])

  const getNodeSize = (node: GraphNode) => {
    // Larger nodes for important types
    if (['Decision', 'Goal', 'Project'].includes(node.type)) return 8
    if (['Person', 'Organization'].includes(node.type)) return 7
    return 5
  }

  const paintNode = useCallback((node: any, ctx: CanvasRenderingContext2D) => {
    const size = getNodeSize(node)
    const color = getNodeColor(node)

    // Draw circle
    ctx.beginPath()
    ctx.arc(node.x, node.y, size, 0, 2 * Math.PI, false)
    ctx.fillStyle = color
    ctx.fill()
    ctx.strokeStyle = theme === 'dark' ? '#100e0b' : '#fffdf8'
    ctx.lineWidth = 1.5
    ctx.stroke()
  }, [getNodeColor, theme])

  return (
    <AppLayout>
      <StudioTopbar
        section="Company brain"
        title="Knowledge Graph"
        description="Explore the entities and relationships behind every answer"
        icon={Network}
        actions={
          <Button
            onClick={fetchGraph}
            variant="subtle"
            size="sm"
            disabled={loading}
          >
            <RefreshCw className={loading ? 'animate-spin' : ''} />
            {loading ? 'Loading…' : 'Refresh'}
          </Button>
        }
      />

      <div className="graph-page-body page-body">
        {error && (
          <div className="card mb-6" style={{ background: 'var(--color-danger-soft)', borderColor: 'var(--color-danger)' }}>
            <p className="text-small" style={{ color: 'var(--color-danger)' }}>
              ⚠ {error}
            </p>
          </div>
        )}

        {!loading && graphData.nodes.length === 0 ? (
          <div className="card">
            <div className="empty-state">
              <div className="empty-state-icon">◉</div>
              <h3 className="empty-state-title">No graph data yet</h3>
              <p className="empty-state-description">
                Connect a source and sync to build your knowledge graph.
                The graph will show entities and their relationships.
              </p>
              <Link href="/onboard" className="btn btn-primary">
                Add Source →
              </Link>
            </div>
          </div>
        ) : (
          <div className="graph-workspace flex h-full gap-4 overflow-hidden px-4 sm:px-6">
            {/* Graph visualization */}
            <div className="graph-visualization flex min-w-0 flex-1 flex-col overflow-hidden">
              <div ref={graphContainerRef} className="graph-canvas-container card min-h-0 flex-1 overflow-hidden p-0">
                {graphSize.width > 0 && graphSize.height > 0 && <ForceGraph2D
                  width={graphSize.width}
                  height={graphSize.height}
                  graphData={{
                    nodes: graphData.nodes,
                    links: graphData.edges
                  }}
                  nodeId="id"
                  nodeLabel={(node: any) => `${node.name} (${node.type})`}
                  nodeCanvasObject={paintNode}
                  nodeRelSize={1}
                  nodeVal={(node: any) => getNodeSize(node)}
                  linkSource="source"
                  linkTarget="target"
                  linkLabel={(link: any) => link.type}
                  linkColor={() => theme === 'dark' ? '#51483c' : '#d9cfbf'}
                  linkWidth={1}
                  linkDirectionalArrowLength={3}
                  linkDirectionalArrowRelPos={1}
                  onNodeClick={handleNodeClick}
                  backgroundColor={theme === 'dark' ? '#100e0b' : '#fdf9f1'}
                  enableNodeDrag={true}
                  enableZoomInteraction={true}
                  enablePanInteraction={true}
                  cooldownTime={2000}
                  cooldownTicks={50}
                  d3AlphaMin={0.05}
                />}
              </div>

              {/* Legend */}
              <div className="mt-4 flex flex-wrap gap-3">
                {Object.entries(typeColors).slice(0, 8).map(([type, color]) => (
                  <div key={type} className="flex items-center gap-2">
                    <span
                      className="w-3 h-3 rounded-full"
                      style={{ background: color }}
                    />
                    <span className="text-caption text-muted">{type}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Side panel */}
            <div className="graph-side-panel h-full w-64 flex-shrink-0 space-y-4 overflow-y-auto">
              {/* Stats card */}
              {stats && (
                <div className="card">
                  <h3 className="text-h3 mb-3">Graph Stats</h3>
                  <div className="space-y-2">
                    <div className="flex justify-between text-small">
                      <span className="text-muted">Total Entities</span>
                      <span className="font-mono">{stats.total_nodes}</span>
                    </div>
                    <div className="flex justify-between text-small">
                      <span className="text-muted">Relationships</span>
                      <span className="font-mono">{stats.total_edges}</span>
                    </div>
                  </div>

                  {Object.keys(stats.nodes_by_type).length > 0 && (
                    <div className="mt-4 pt-4 border-t border-line">
                      <p className="text-caption text-muted mb-2 uppercase tracking-wide">By Type</p>
                      <div className="space-y-1">
                        {Object.entries(stats.nodes_by_type).slice(0, 6).map(([type, count]) => (
                          <div key={type} className="flex justify-between text-small">
                            <span className="flex items-center gap-2">
                              <span
                                className="w-2 h-2 rounded-full"
                                style={{ background: typeColors[type] || '#6b6257' }}
                              />
                              {type}
                            </span>
                            <span className="font-mono text-muted">{count}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Selected node card */}
              {selectedNode && (
                <div className="card">
                  <div className="flex items-start justify-between mb-2">
                    <span
                      className="badge"
                      style={{ background: typeColors[selectedNode.type], color: '#fff' }}
                    >
                      {selectedNode.type}
                    </span>
                    <button
                      onClick={() => setSelectedNode(null)}
                      className="text-muted hover:text-ink"
                    >
                      ✕
                    </button>
                  </div>
                  <h3 className="text-h3 mb-2">{selectedNode.name}</h3>
                  {selectedNode.description && (
                    <p className="text-small text-muted mb-3">
                      {selectedNode.description}
                    </p>
                  )}
                  {selectedNode.status && (
                    <span className={`badge ${selectedNode.status === 'confirmed' ? 'badge-teal' : 'badge-orange'}`}>
                      {selectedNode.status}
                    </span>
                  )}
                </div>
              )}

              {/* Instructions */}
              {!selectedNode && (
                <div className="card bg-paper-2">
                  <p className="text-small text-muted">
                    <strong>Hover</strong> over a node to see its name<br/>
                    <strong>Click</strong> a node to see details<br/>
                    <strong>Drag nodes</strong> to reposition<br/>
                    <strong>Drag background</strong> to pan<br/>
                    <strong>Scroll</strong> to zoom
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  )
}
