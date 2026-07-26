/**
 * Contract tests for the adapter between the graph API and the canvas.
 *
 * These are the guarantees the explorer is built on: an id that survives a
 * reload, a merge that never doubles a node, and a refusal to draw a
 * relationship whose other end is not on screen. They are pure functions, so
 * they can be checked without a browser, a WebGL context or a database.
 *
 *   npm test
 */

import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  directNeighbors,
  edgeId,
  formatConfidence,
  mergeEdges,
  mergeNodes,
  neighborhoodIds,
  nodeSize,
  normalizeEdge,
  normalizeNode,
  relationshipLabel,
  toGraphView,
  truncateLabel,
  typeColor,
  visibleDegree,
} from '../components/graph/graph-transform'
import type { GraphEdge, GraphNode } from '../components/graph/types'

function node(id: string, extra: Partial<GraphNode> = {}): GraphNode {
  return {
    id,
    name: `Entity ${id}`,
    type: 'Decision',
    description: null,
    status: 'confirmed',
    confidence: 'high',
    degree: 2,
    evidence_count: 1,
    ...extra,
  }
}

function edge(source: string, target: string, type = 'AFFECTS'): GraphEdge {
  return { source, target, type, description: null }
}

describe('relationship identity', () => {
  it('derives the same id from the same relationship every time', () => {
    const first = edgeId(edge('a', 'b', 'ADVANCES'))
    const second = edgeId(edge('a', 'b', 'ADVANCES'))
    assert.equal(first, second)
  })

  it('separates a repeated relationship without depending on array order', () => {
    const repeated = edge('a', 'b')
    assert.notEqual(edgeId(repeated, 0), edgeId(repeated, 1))
    // The first occurrence keeps the plain id, so an id stays stable even when
    // a duplicate appears later.
    assert.equal(edgeId(repeated, 0), 'a|AFFECTS|b')
  })

  it('treats direction and type as part of the identity', () => {
    assert.notEqual(edgeId(edge('a', 'b')), edgeId(edge('b', 'a')))
    assert.notEqual(edgeId(edge('a', 'b', 'AFFECTS')), edgeId(edge('a', 'b', 'BLOCKS')))
  })
})

describe('building a renderable view', () => {
  it('drops a relationship whose endpoint is not on screen', () => {
    const view = toGraphView([node('a'), node('b')], [edge('a', 'b'), edge('a', 'ghost')])
    assert.equal(view.edges.length, 1)
    assert.equal(view.edges[0].source, 'a')
    assert.equal(view.edges[0].target, 'b')
  })

  it('gives every rendered relationship a distinct id', () => {
    const view = toGraphView(
      [node('a'), node('b')],
      [edge('a', 'b'), edge('a', 'b'), edge('a', 'b', 'BLOCKS')],
    )
    const ids = view.edges.map(item => item.id)
    assert.equal(new Set(ids).size, ids.length)
  })

  it('keeps the untouched API record on the node', () => {
    const source = node('a', { name: 'A decision about pricing' })
    const view = toGraphView([source], [])
    assert.deepEqual(view.nodes[0].data, source)
  })

  it('does not depend on the theme, so a switch cannot restart the layout', () => {
    const nodes = [node('a'), node('b')]
    const edges = [edge('a', 'b')]
    assert.deepEqual(toGraphView(nodes, edges), toGraphView(nodes, edges))
  })

  it('sizes nodes within a bounded band however connected they are', () => {
    assert.ok(nodeSize(0) < nodeSize(9))
    assert.ok(nodeSize(10_000) <= 16)
    assert.equal(nodeSize(null), nodeSize(undefined))
  })
})

describe('merging progressively loaded neighbourhoods', () => {
  it('unions nodes by id rather than appending them', () => {
    const merged = mergeNodes([node('a'), node('b')], [node('b'), node('c')])
    assert.deepEqual(merged.map(item => item.id).sort(), ['a', 'b', 'c'])
  })

  it('never lets a thinner record erase what a richer one established', () => {
    // /graph returns degree and evidence counts; a neighbour payload may not.
    const rich = node('a', { degree: 12, evidence_count: 4, description: 'Detail' })
    const thin = node('a', { degree: null, evidence_count: null, description: null })
    const [merged] = mergeNodes([rich], [thin])
    assert.equal(merged.degree, 12)
    assert.equal(merged.evidence_count, 4)
    assert.equal(merged.description, 'Detail')
  })

  it('unions relationships by the same key the renderer uses', () => {
    const merged = mergeEdges([edge('a', 'b')], [edge('a', 'b'), edge('b', 'c')])
    assert.equal(merged.length, 2)
  })

  it('prefers the copy that actually explains the relationship', () => {
    const bare = edge('a', 'b')
    const described = { ...edge('a', 'b'), description: 'Blocks the launch' }
    assert.equal(mergeEdges([bare], [described])[0].description, 'Blocks the launch')
  })
})

describe('reading the neighbourhood', () => {
  const nodes = [node('a'), node('b'), node('c'), node('d')]
  const edges = [edge('a', 'b'), edge('c', 'a'), edge('c', 'd')]

  it('includes both directions and the node itself', () => {
    assert.deepEqual([...neighborhoodIds('a', edges)].sort(), ['a', 'b', 'c'])
  })

  it('lists direct neighbours without the node itself', () => {
    assert.deepEqual(directNeighbors('a', nodes, edges).map(item => item.id), ['b', 'c'])
  })

  it('counts only relationships that are actually on screen', () => {
    assert.equal(visibleDegree('a', edges), 2)
    assert.equal(visibleDegree('d', edges), 1)
  })
})

describe('trusting the API payload only as far as it can be checked', () => {
  it('drops a node with no usable id instead of drawing an anonymous dot', () => {
    assert.equal(normalizeNode({ name: 'No id' }), null)
    assert.equal(normalizeNode(null), null)
    assert.equal(normalizeNode('nonsense'), null)
  })

  it('falls back from name to statement, which is where entities keep their text', () => {
    assert.equal(normalizeNode({ id: 'a', statement: 'Ship in September' })?.name, 'Ship in September')
  })

  it('reduces an unrecognised status to unknown rather than guessing', () => {
    assert.equal(normalizeNode({ id: 'a', status: 'rejected' })?.status, undefined)
    assert.equal(normalizeNode({ id: 'a', status: 'proposed' })?.status, 'proposed')
  })

  it('keeps a missing count missing so the panel can say so', () => {
    const parsed = normalizeNode({ id: 'a' })
    assert.equal(parsed?.degree, null)
    assert.equal(parsed?.evidence_count, null)
  })

  it('drops an edge missing an endpoint', () => {
    assert.equal(normalizeEdge({ source: 'a' }), null)
    assert.equal(normalizeEdge({ source: 'a', target: 'b' })?.type, 'RELATED_TO')
  })
})

describe('presenting values without inventing precision', () => {
  it('shows a score as a percentage and a label as a word', () => {
    assert.equal(formatConfidence(0.82), '82%')
    assert.equal(formatConfidence('high'), 'High')
  })

  it('says nothing rather than something when confidence is absent', () => {
    assert.equal(formatConfidence(null), '—')
    assert.equal(formatConfidence(undefined), '—')
    assert.equal(formatConfidence(''), '—')
  })

  it('reads a relationship type back as prose', () => {
    assert.equal(relationshipLabel('AFFECTS_DELIVERY'), 'Affects delivery')
    assert.equal(relationshipLabel(''), 'Related')
  })

  it('shortens a statement for the canvas without losing it', () => {
    const statement = 'Launch the Northstar pilot in September across every region'
    const label = truncateLabel(statement)
    assert.ok(label.length <= 24)
    assert.ok(label.endsWith('…'))
    assert.equal(truncateLabel('Short one'), 'Short one')
  })

  it('gives an unknown entity type a colour rather than nothing', () => {
    assert.equal(typeColor('Decision', 'light'), '#e8641b')
    assert.notEqual(typeColor('Decision', 'dark'), typeColor('Decision', 'light'))
    assert.ok(typeColor('Something', 'light'))
    assert.ok(typeColor(undefined, 'dark'))
  })
})
