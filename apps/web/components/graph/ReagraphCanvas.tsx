'use client'

/**
 * The Reagraph renderer.
 *
 * Loaded only through `KnowledgeGraphCanvas`, which imports it with
 * `ssr: false`. Reagraph draws into WebGL through three.js and touches
 * `window` on import, so it must never reach the server bundle.
 *
 * This component owns the imperative canvas ref and republishes the few camera
 * actions the page needs as a plain handle, because `next/dynamic` does not
 * forward refs through the boundary.
 */

import { useCallback, useEffect, useMemo, useRef } from 'react'
import {
  GraphCanvas,
  Ring,
  Sphere,
  type GraphCanvasRef,
  type InternalGraphEdge,
  type InternalGraphNode,
  type LabelVisibilityType,
  type NodeRendererProps,
} from 'reagraph'
import type { Theme } from '../ThemeProvider'
import { FOCUS_RING_COLOR, SELECTION_RING_COLOR, graphTheme } from './graph-theme'
import { normalizeStatus } from './graph-transform'
import type {
  GraphCanvasHandle,
  GraphNode,
  GraphViewEdge,
  GraphViewNode,
} from './types'

export interface ReagraphCanvasProps {
  nodes: GraphViewNode[]
  edges: GraphViewEdge[]
  theme: Theme
  /** Ids of the selected node or edge. Single-select, so at most one entry. */
  selections: string[]
  /** Ids kept bright while everything else dims — the focused neighborhood. */
  actives: string[]
  focusNodeId: string | null
  labelType: LabelVisibilityType
  /** Off when the reader prefers reduced motion. */
  animated: boolean
  onSelectNode: (id: string) => void
  onSelectEdge: (id: string) => void
  onClearSelection: () => void
  onExpandNode: (id: string) => void
  onHoverNode: (id: string | null) => void
  onHoverEdge: (id: string | null) => void
  onReady: (handle: GraphCanvasHandle) => void
}

/**
 * Radius multipliers, expressed against Reagraph's own geometry: a `Sphere` of
 * size *s* has radius *s*, while a `Ring` of size *s* has radius *2s*. Halving
 * the ring size therefore makes it hug the node.
 */
const PROPOSED_RING_SIZE = 0.68
const SELECTED_RING_SIZE = 1.04

function statusOf(node: InternalGraphNode): GraphNode['status'] {
  return normalizeStatus((node.data as GraphNode | undefined)?.status)
}

export default function ReagraphCanvas({
  nodes,
  edges,
  theme,
  selections,
  actives,
  focusNodeId,
  labelType,
  animated,
  onSelectNode,
  onSelectEdge,
  onClearSelection,
  onExpandNode,
  onHoverNode,
  onHoverEdge,
  onReady,
}: ReagraphCanvasProps) {
  const canvasRef = useRef<GraphCanvasRef | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const activeTheme = useMemo(() => graphTheme(theme), [theme])

  // Publish the camera handle once. The functions read `canvasRef` when they
  // are called, so handing them over before the canvas mounts is safe.
  useEffect(() => {
    onReady({
      fitView: () => canvasRef.current?.fitNodesInView(),
      zoomIn: () => canvasRef.current?.zoomIn(),
      zoomOut: () => canvasRef.current?.zoomOut(),
      centerOn: (nodeIds: string[]) => canvasRef.current?.centerGraph(nodeIds),
    })
  }, [onReady])

  const setCursor = useCallback((cursor: 'pointer' | 'default') => {
    if (containerRef.current) containerRef.current.style.cursor = cursor
  }, [])

  /**
   * Status is drawn as a shape, not only as a colour: a confirmed fact is a
   * solid disc, a proposed one is a small core inside an open ring. Selection
   * is a wider accent halo, and focus a teal one, so the three signals never
   * have to be told apart by hue alone.
   */
  const renderNode = useCallback((props: NodeRendererProps) => {
    const proposed = statusOf(props.node) === 'proposed'
    const focused = props.node.id === focusNodeId
    const ringColor = focused
      ? FOCUS_RING_COLOR[theme]
      : props.selected
        ? SELECTION_RING_COLOR[theme]
        : props.color
    const highlighted = props.selected || focused

    return (
      <>
        <Sphere
          {...props}
          selected={false}
          size={proposed ? props.size * 0.58 : props.size}
        />
        {(proposed || highlighted) && (
          <Ring
            color={ringColor}
            size={props.size * (highlighted ? SELECTED_RING_SIZE : PROPOSED_RING_SIZE)}
            opacity={props.opacity * (highlighted ? 1 : 0.9)}
            strokeWidth={highlighted ? 6 : 2}
            animated={props.animated}
          />
        )}
      </>
    )
  }, [focusNodeId, theme])

  const handleNodeClick = useCallback((node: InternalGraphNode) => {
    onSelectNode(node.id)
  }, [onSelectNode])

  const handleNodeDoubleClick = useCallback((node: InternalGraphNode) => {
    onExpandNode(node.id)
  }, [onExpandNode])

  const handleEdgeClick = useCallback((edge: InternalGraphEdge) => {
    onSelectEdge(edge.id)
  }, [onSelectEdge])

  const handleNodePointerOver = useCallback((node: InternalGraphNode) => {
    setCursor('pointer')
    onHoverNode(node.id)
  }, [onHoverNode, setCursor])

  const handleNodePointerOut = useCallback(() => {
    setCursor('default')
    onHoverNode(null)
  }, [onHoverNode, setCursor])

  const handleEdgePointerOver = useCallback((edge: InternalGraphEdge) => {
    setCursor('pointer')
    onHoverEdge(edge.id)
  }, [onHoverEdge, setCursor])

  const handleEdgePointerOut = useCallback(() => {
    setCursor('default')
    onHoverEdge(null)
  }, [onHoverEdge, setCursor])

  const handleCanvasClick = useCallback(() => {
    onClearSelection()
  }, [onClearSelection])

  return (
    <div ref={containerRef} className="absolute inset-0">
      <GraphCanvas
        ref={canvasRef}
        nodes={nodes}
        edges={edges}
        theme={activeTheme}
        // A knowledge graph has no inherent third dimension, and a rotatable
        // camera makes a 2D layout much harder to read and to click.
        layoutType="forceDirected2d"
        cameraMode="pan"
        sizingType="default"
        defaultNodeSize={7}
        // Reagraph rescales every node into this band. Keeping the floor below
        // 7 matters: `labelType="auto"` labels only nodes above that mark, so a
        // wider band is what turns label density into a relevance signal.
        minNodeSize={6}
        maxNodeSize={16}
        labelType={labelType}
        labelFontUrl="/fonts/noto-sans-regular.ttf"
        edgeArrowPosition="end"
        // Straight edges, deliberately. Curved ones sweep far outside the
        // cluster they connect, which both reads as noise and drags the
        // fit-to-view extent out until the graph itself is a dot.
        edgeInterpolation="linear"
        edgeLabelPosition="natural"
        // Without this the drawing buffer is cleared after each frame, so any
        // attempt to read the canvas back — a screenshot, an image export —
        // returns an empty rectangle.
        glOptions={{ preserveDrawingBuffer: true }}
        selections={selections}
        actives={actives}
        animated={animated}
        draggable
        onNodeClick={handleNodeClick}
        onNodeDoubleClick={handleNodeDoubleClick}
        onEdgeClick={handleEdgeClick}
        onCanvasClick={handleCanvasClick}
        onNodePointerOver={handleNodePointerOver}
        onNodePointerOut={handleNodePointerOut}
        onEdgePointerOver={handleEdgePointerOver}
        onEdgePointerOut={handleEdgePointerOut}
        renderNode={renderNode}
      />
    </div>
  )
}
