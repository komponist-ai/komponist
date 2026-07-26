/**
 * Contracts for the knowledge graph explorer.
 *
 * Two families of shapes live here on purpose:
 *
 *   - `Graph*` mirrors exactly what `/graph`, `/graph/stats` and
 *     `/graph/neighbors/{id}` return. Nothing in the UI may add fields the
 *     backend did not send; a missing value stays missing so the panel can say
 *     so rather than invent one.
 *   - `GraphView*` is what the renderer consumes. Deriving it means the layout
 *     engine mutates its own objects (positions, velocities) instead of the API
 *     payload that the toolbar, panel and accessible list all read from.
 */

export type EntityStatus = 'confirmed' | 'proposed'

/** A node exactly as the API returns it. */
export interface GraphNode {
  id: string
  name: string
  type: string
  description?: string | null
  status?: EntityStatus
  /**
   * Extraction confidence. The pipeline writes a label (`high`/`medium`/`low`)
   * but older records and fixtures carry a 0-1 score, so both survive here and
   * the formatter decides how to read them.
   */
  confidence?: number | string | null
  degree?: number | null
  evidence_count?: number | null
}

/** A relationship exactly as the API returns it. */
export interface GraphEdge {
  source: string
  target: string
  type: string
  description?: string | null
}

export interface GraphPayload {
  nodes: GraphNode[]
  edges: GraphEdge[]
  total: number
  limit?: number
  truncated: boolean
}

export interface GraphStats {
  total_nodes: number
  total_edges: number
  nodes_by_type: Record<string, number>
  edges_by_type: Record<string, number>
}

/** `/graph/neighbors/{id}` returns a thinner node than `/graph` does. */
export interface NeighborPayload {
  center: string
  nodes: Array<GraphNode & { isCenter?: boolean }>
  edges: GraphEdge[]
}

/** A node handed to Reagraph. `data` keeps the untouched API record. */
export interface GraphViewNode {
  id: string
  label: string
  data: GraphNode
  fill: string
  size: number
}

/** An edge handed to Reagraph, carrying a stable synthetic id. */
export interface GraphViewEdge {
  id: string
  source: string
  target: string
  label: string
  data: GraphEdge
  /**
   * Line thickness, which Reagraph also uses as the radius of the invisible
   * tube it raycasts against. At the default of 1 the pickable tube is half a
   * world unit wide and a relationship is essentially impossible to click.
   */
  size: number
}

export interface GraphView {
  nodes: GraphViewNode[]
  edges: GraphViewEdge[]
}

export type GraphStatusFilter = 'all' | 'confirmed' | 'proposed'

/**
 * How the visible graph came to be. `overview` is the server's own selection,
 * `search` is a server-side query, `focus` is one node plus its neighborhood.
 */
export type GraphMode = 'overview' | 'search' | 'focus'

/** What the details panel is currently describing. */
export type GraphSelection =
  | { kind: 'node'; id: string }
  | { kind: 'edge'; id: string }
  | null

/**
 * The camera actions the page drives from its own toolbar. Exposed as a plain
 * object rather than a ref because the renderer is behind a dynamic import and
 * `next/dynamic` does not forward refs.
 */
export interface GraphCanvasHandle {
  fitView: () => void
  zoomIn: () => void
  zoomOut: () => void
  centerOn: (nodeIds: string[]) => void
}
