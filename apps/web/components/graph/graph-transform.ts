/**
 * The adapter between the graph API and the Reagraph canvas.
 *
 * Everything here is pure: given the same API payload it returns the same view
 * model, which is what makes progressive expansion safe. Merging a freshly
 * loaded neighborhood into the visible graph is a set union keyed by id, so a
 * node can be reached from three different directions and still appear once.
 */

import type { Theme } from '../ThemeProvider'
import type {
  EntityStatus,
  GraphEdge,
  GraphNode,
  GraphView,
  GraphViewEdge,
  GraphViewNode,
} from './types'

/**
 * Entity colors, taken from the Komponist tokens rather than a generic graph
 * palette. Each theme gets its own values because the dark tokens are not
 * simple lightenings of the light ones.
 */
const TYPE_COLORS: Record<Theme, Record<string, string>> = {
  light: {
    Decision: '#e8641b',
    Goal: '#0e8a7d',
    Constraint: '#f5a46b',
    Project: '#4a443a',
  },
  dark: {
    Decision: '#f47b35',
    Goal: '#43b9ac',
    Constraint: '#f6aa78',
    Project: '#d6cbbb',
  },
}

/** Anything the ontology does not name renders in a neutral grey. */
const UNKNOWN_TYPE_COLOR: Record<Theme, string> = {
  light: '#9a9184',
  dark: '#7d7468',
}

/** The order type chips appear in, matching the ontology's own ordering. */
export const ENTITY_TYPES = ['Decision', 'Goal', 'Constraint', 'Project'] as const

const MIN_NODE_SIZE = 7
const MAX_NODE_SIZE = 16

/**
 * Entity statements are sentences, not names. Drawn in full they overlap into
 * an unreadable mat of text, so the canvas gets a short form and the full text
 * stays in the hover readout and the details panel.
 */
const MAX_LABEL_LENGTH = 24

/**
 * Edge thickness. Reagraph raycasts a tube of half this radius, so this is as
 * much a hit-target size as a visual weight: thin enough to stay quiet behind
 * the nodes, thick enough that a relationship can actually be clicked.
 */
const EDGE_SIZE = 3

export function typeColor(type: string | undefined, theme: Theme): string {
  if (!type) return UNKNOWN_TYPE_COLOR[theme]
  return TYPE_COLORS[theme][type] ?? UNKNOWN_TYPE_COLOR[theme]
}

export function entityPalette(theme: Theme): Record<string, string> {
  return TYPE_COLORS[theme]
}

/**
 * Size grows with how connected a node is, but only within a narrow band. A
 * hub with 200 links should read as important, not swallow the viewport.
 */
export function nodeSize(degree: number | null | undefined): number {
  const links = Math.max(0, degree ?? 0)
  return Math.min(MAX_NODE_SIZE, MIN_NODE_SIZE + Math.sqrt(links) * 1.6)
}

/** `AFFECTS_DELIVERY` reads as `Affects delivery` in the UI. */
export function relationshipLabel(type: string): string {
  const words = type.replace(/_/g, ' ').trim().toLowerCase()
  if (!words) return 'Related'
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/** Only the two statuses the API can return survive; anything else is unknown. */
export function normalizeStatus(value: unknown): EntityStatus | undefined {
  return value === 'confirmed' || value === 'proposed' ? value : undefined
}

function normalizeNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function normalizeText(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

/** Confidence arrives either as a 0-1 score or as a label. Keep whichever. */
function normalizeConfidence(value: unknown): number | string | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  return normalizeText(value)
}

/**
 * Render confidence without pretending to a precision the record does not
 * have: a score becomes a percentage, a label is shown as written, and a
 * missing value stays missing.
 */
export function formatConfidence(value: number | string | null | undefined): string {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return `${Math.round(value * 100)}%`
  }
  if (typeof value === 'string' && value.trim()) {
    return value.charAt(0).toUpperCase() + value.slice(1)
  }
  return '—'
}

/**
 * Accept a raw API record without trusting its shape. A node with no usable id
 * is dropped rather than rendered as an anonymous dot.
 */
export function normalizeNode(raw: unknown): GraphNode | null {
  if (!raw || typeof raw !== 'object') return null
  const record = raw as Record<string, unknown>
  const id = typeof record.id === 'string' ? record.id : null
  if (!id) return null
  const name = normalizeText(record.name) ?? normalizeText(record.statement) ?? id
  return {
    id,
    name,
    type: typeof record.type === 'string' ? record.type : 'Unknown',
    description: normalizeText(record.description),
    status: normalizeStatus(record.status),
    confidence: normalizeConfidence(record.confidence),
    degree: normalizeNumber(record.degree),
    evidence_count: normalizeNumber(record.evidence_count),
  }
}

export function normalizeEdge(raw: unknown): GraphEdge | null {
  if (!raw || typeof raw !== 'object') return null
  const record = raw as Record<string, unknown>
  const source = typeof record.source === 'string' ? record.source : null
  const target = typeof record.target === 'string' ? record.target : null
  if (!source || !target) return null
  return {
    source,
    target,
    type: typeof record.type === 'string' ? record.type : 'RELATED_TO',
    description: normalizeText(record.description),
  }
}

/**
 * The API has no relationship id, so the client derives one. Source, type and
 * target identify a relationship uniquely in almost every case; where a company
 * really does record the same relationship twice, an occurrence counter keeps
 * the ids distinct without making them depend on array position.
 */
export function edgeId(edge: GraphEdge, occurrence = 0): string {
  const base = `${edge.source}|${edge.type}|${edge.target}`
  return occurrence === 0 ? base : `${base}#${occurrence}`
}

export function truncateLabel(name: string): string {
  const collapsed = name.trim().replace(/\s+/g, ' ')
  if (collapsed.length <= MAX_LABEL_LENGTH) return collapsed
  return `${collapsed.slice(0, MAX_LABEL_LENGTH - 1).trimEnd()}…`
}

/**
 * Build a renderable node. Deliberately theme-free: `fill` is the canonical
 * colour for the entity type, and the renderer picks the per-theme variant when
 * it draws. Baking the theme in here would give every node a new identity on a
 * light/dark switch, which Reagraph reads as a new graph — rebuilding it and
 * throwing away a layout the reader was in the middle of using.
 */
export function toViewNode(node: GraphNode): GraphViewNode {
  return {
    id: node.id,
    label: truncateLabel(node.name),
    data: node,
    fill: typeColor(node.type, 'light'),
    size: nodeSize(node.degree),
  }
}

export function toViewNodes(nodes: GraphNode[]): GraphViewNode[] {
  return nodes.map(toViewNode)
}

/**
 * Build renderable edges. Two rules keep the canvas from throwing:
 * duplicates get distinct ids, and an edge pointing at a node that is not on
 * screen is dropped — graphology rejects dangling endpoints, and a half-drawn
 * relationship would be a lie anyway.
 */
export function toViewEdges(edges: GraphEdge[], nodeIds: Set<string>): GraphViewEdge[] {
  const occurrences = new Map<string, number>()
  const seen = new Set<string>()
  const result: GraphViewEdge[] = []

  for (const edge of edges) {
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) continue
    const base = `${edge.source}|${edge.type}|${edge.target}`
    const occurrence = occurrences.get(base) ?? 0
    occurrences.set(base, occurrence + 1)
    const id = edgeId(edge, occurrence)
    if (seen.has(id)) continue
    seen.add(id)
    result.push({
      id,
      source: edge.source,
      target: edge.target,
      label: relationshipLabel(edge.type),
      data: edge,
      size: EDGE_SIZE,
    })
  }

  return result
}

export function toGraphView(nodes: GraphNode[], edges: GraphEdge[]): GraphView {
  const ids = new Set(nodes.map(node => node.id))
  return { nodes: toViewNodes(nodes), edges: toViewEdges(edges, ids) }
}

/**
 * Union two node sets by id. Records from `/graph` carry degree, confidence and
 * evidence counts that `/graph/neighbors` omits, so a merge never lets a
 * thinner record overwrite fields the richer one already established.
 */
export function mergeNodes(current: GraphNode[], incoming: GraphNode[]): GraphNode[] {
  const byId = new Map(current.map(node => [node.id, node]))
  for (const node of incoming) {
    const existing = byId.get(node.id)
    if (!existing) {
      byId.set(node.id, node)
      continue
    }
    byId.set(node.id, {
      ...existing,
      ...node,
      description: node.description ?? existing.description,
      status: node.status ?? existing.status,
      confidence: node.confidence ?? existing.confidence,
      degree: node.degree ?? existing.degree,
      evidence_count: node.evidence_count ?? existing.evidence_count,
    })
  }
  return Array.from(byId.values())
}

/** Union two relationship sets, keyed the same way the renderer keys them. */
export function mergeEdges(current: GraphEdge[], incoming: GraphEdge[]): GraphEdge[] {
  const byKey = new Map<string, GraphEdge>()
  for (const edge of [...current, ...incoming]) {
    const key = `${edge.source}|${edge.type}|${edge.target}`
    const existing = byKey.get(key)
    if (!existing) {
      byKey.set(key, edge)
      continue
    }
    // Keep whichever copy actually explains the relationship.
    if (!existing.description && edge.description) byKey.set(key, edge)
  }
  return Array.from(byKey.values())
}

/** Ids of everything one hop from `nodeId`, including the node itself. */
export function neighborhoodIds(nodeId: string, edges: GraphEdge[]): Set<string> {
  const ids = new Set<string>([nodeId])
  for (const edge of edges) {
    if (edge.source === nodeId) ids.add(edge.target)
    if (edge.target === nodeId) ids.add(edge.source)
  }
  return ids
}

/** The nodes one hop from `nodeId`, in the order the graph returned them. */
export function directNeighbors(
  nodeId: string,
  nodes: GraphNode[],
  edges: GraphEdge[],
): GraphNode[] {
  const ids = neighborhoodIds(nodeId, edges)
  ids.delete(nodeId)
  return nodes.filter(node => ids.has(node.id))
}

/** How many relationships in the visible graph touch this node. */
export function visibleDegree(nodeId: string, edges: GraphEdge[]): number {
  return edges.filter(edge => edge.source === nodeId || edge.target === nodeId).length
}
