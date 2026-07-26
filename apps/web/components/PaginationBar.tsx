'use client'

import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from './ui/button'

type PaginationBarProps = {
  offset: number
  limit: number
  total: number
  onOffsetChange: (offset: number) => void
  disabled?: boolean
  itemLabel?: string
}

export default function PaginationBar({
  offset,
  limit,
  total,
  onOffsetChange,
  disabled = false,
  itemLabel = 'items',
}: PaginationBarProps) {
  if (total <= limit) return null

  const start = total === 0 ? 0 : offset + 1
  const end = Math.min(offset + limit, total)
  const previousOffset = Math.max(0, offset - limit)
  const nextOffset = offset + limit

  return (
    <nav
      className="flex flex-col items-center justify-between gap-3 border-t-2 border-ink bg-paper-2 px-4 py-3 sm:flex-row"
      aria-label={`${itemLabel} pagination`}
    >
      <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-muted">
        {start}–{end} of {total} {itemLabel}
      </span>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={disabled || offset === 0}
          onClick={() => onOffsetChange(previousOffset)}
        >
          <ChevronLeft /> Previous
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={disabled || nextOffset >= total}
          onClick={() => onOffsetChange(nextOffset)}
        >
          Next <ChevronRight />
        </Button>
      </div>
    </nav>
  )
}
