'use client'

import { useEffect, useState } from 'react'
import { Star } from 'lucide-react'
import { cn } from '../lib/utils'

export default function GitHubStars({ className }: { className?: string }) {
  const [stars, setStars] = useState<number | null>(null)
  const [available, setAvailable] = useState(true)

  useEffect(() => {
    let active = true

    fetch('/api/github-stars')
      .then(response => response.ok ? response.json() : Promise.reject())
      .then((payload: { stars?: number }) => {
        if (active && typeof payload.stars === 'number') setStars(payload.stars)
      })
      .catch(() => {
        if (active) setAvailable(false)
      })

    return () => { active = false }
  }, [])

  if (!available) return null

  const value = stars === null ? '…' : new Intl.NumberFormat('en', { notation: 'compact' }).format(stars)

  return (
    <span
      className={cn('inline-flex items-center gap-1 rounded-full border border-current/20 px-2 py-0.5 font-mono text-[10px] font-bold tabular-nums', className)}
      aria-label={stars === null ? 'Loading GitHub stars' : `${stars} GitHub stars`}
    >
      <Star className="size-3" fill="currentColor" /> {value}
    </span>
  )
}
