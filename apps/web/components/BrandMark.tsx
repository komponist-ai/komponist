import { cn } from '@/lib/utils'

export default function BrandMark({ className }: { className?: string }) {
  return (
    <span
      className={cn('inline-grid size-9 place-items-center rounded-lg border-2 border-ink bg-orange text-white shadow-[2px_2px_0_#201c15]', className)}
      aria-label="Komponist"
      role="img"
    >
      <svg viewBox="0 0 32 32" className="size-6" fill="none" aria-hidden="true">
        <path d="M4 8.5h24M4 13.5h24M4 18.5h24M4 23.5h24" stroke="currentColor" strokeWidth="1.1" opacity=".28" />
        <path d="m8.5 21 8-10 7.5 5.5" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M10.5 20.5V9.25M18.5 10.5V5.75M26 16v-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        <ellipse cx="8.5" cy="21" rx="3" ry="2.35" fill="currentColor" transform="rotate(-18 8.5 21)" />
        <ellipse cx="16.5" cy="11" rx="3" ry="2.35" fill="currentColor" transform="rotate(-18 16.5 11)" />
        <ellipse cx="24" cy="16.5" rx="3" ry="2.35" fill="currentColor" transform="rotate(-18 24 16.5)" />
      </svg>
    </span>
  )
}
