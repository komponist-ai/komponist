'use client'

/**
 * The boundary between the page and the WebGL renderer.
 *
 * Everything Reagraph needs — three.js, a canvas, `window` — exists only in the
 * browser, so the renderer is behind `ssr: false`. This wrapper also refuses to
 * mount it when the browser cannot give us a WebGL context: a graph that fails
 * to initialise leaves a blank rectangle and no explanation, and the reader
 * still has the entity list to fall back on.
 */

import { useEffect, useState } from 'react'
import dynamic from 'next/dynamic'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import type { ReagraphCanvasProps } from './ReagraphCanvas'

const ReagraphCanvas = dynamic(() => import('./ReagraphCanvas'), {
  ssr: false,
  loading: () => <CanvasNotice icon="spinner" message="Preparing the graph view…" />,
})

function CanvasNotice({
  icon,
  message,
  detail,
}: {
  icon: 'spinner' | 'warning'
  message: string
  detail?: string
}) {
  return (
    <div className="absolute inset-0 grid place-items-center p-6">
      <div className="max-w-sm rounded-lg border-2 border-ink bg-white px-4 py-3 text-center shadow-[3px_3px_0_#201c15]">
        <p className="flex items-center justify-center gap-2 font-mono text-xs font-semibold">
          {icon === 'spinner' ? (
            <RefreshCw className="size-4 animate-spin" aria-hidden />
          ) : (
            <AlertTriangle className="size-4 text-orange-dark" aria-hidden />
          )}
          {message}
        </p>
        {detail && <p className="mt-2 text-[11px] leading-5 text-muted">{detail}</p>}
      </div>
    </div>
  )
}

/** Whether this browser can actually give three.js a context to draw into. */
function detectWebGl(): boolean {
  try {
    const probe = document.createElement('canvas')
    return Boolean(
      window.WebGLRenderingContext &&
      (probe.getContext('webgl') || probe.getContext('experimental-webgl')),
    )
  } catch {
    return false
  }
}

export default function KnowledgeGraphCanvas(props: ReagraphCanvasProps) {
  const [webGl, setWebGl] = useState<'unknown' | 'available' | 'missing'>('unknown')

  useEffect(() => {
    setWebGl(detectWebGl() ? 'available' : 'missing')
  }, [])

  if (webGl === 'unknown') {
    return <CanvasNotice icon="spinner" message="Preparing the graph view…" />
  }

  if (webGl === 'missing') {
    return (
      <CanvasNotice
        icon="warning"
        message="This browser cannot draw the graph"
        detail="The visual explorer needs WebGL, which is disabled or unavailable here. The entity list below stays fully usable, and Browse entities shows the same knowledge."
      />
    )
  }

  return <ReagraphCanvas {...props} />
}
