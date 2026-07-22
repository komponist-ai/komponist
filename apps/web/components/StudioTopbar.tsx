import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

type StudioTopbarProps = {
  section: string
  title: string
  description?: string
  icon: LucideIcon
  actions?: ReactNode
}

export default function StudioTopbar({
  section,
  title,
  description,
  icon: Icon,
  actions,
}: StudioTopbarProps) {
  return (
    <header className="studio-topbar flex min-h-[78px] items-center justify-between gap-4 border-b-2 border-ink bg-white px-4 py-3 sm:px-8 lg:px-10">
      <div className="flex min-w-0 items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-lg border-2 border-ink bg-orange text-white shadow-[2px_2px_0_#201c15]">
          <Icon className="size-5" />
        </span>
        <div className="min-w-0">
          <div className="truncate font-mono text-[9px] font-bold uppercase tracking-[0.12em] text-muted">
            Studio / {section}
          </div>
          <div className="flex min-w-0 items-baseline gap-3">
            <h1 className="truncate text-xl font-bold tracking-tight sm:text-2xl">{title}</h1>
            {description && <p className="hidden truncate text-xs text-muted xl:block">{description}</p>}
          </div>
        </div>
      </div>
      {actions && <div className="studio-topbar-actions flex shrink-0 items-center gap-2 sm:gap-3">{actions}</div>}
    </header>
  )
}
