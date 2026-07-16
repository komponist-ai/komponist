'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

export default function Nav() {
  const pathname = usePathname()

  const isActive = (path: string) => pathname === path

  return (
    <nav className="border-b border-line bg-surface px-6" style={{ height: '64px' }}>
      <div className="max-w-site mx-auto h-full flex items-center justify-between">
        <div className="flex items-center gap-8">
          <Link href="/" className="font-display text-xl font-semibold text-ink">
            Komponist
          </Link>

          <div className="hidden md:flex gap-6 text-small">
            <Link
              href="/queue"
              className={`relative py-2 ${
                isActive('/queue')
                  ? 'text-ink font-medium'
                  : 'text-ink-secondary hover:text-ink'
              }`}
            >
              Queue
              {isActive('/queue') && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-accent" />
              )}
            </Link>
            <Link
              href="/entities"
              className={`relative py-2 ${
                isActive('/entities')
                  ? 'text-ink font-medium'
                  : 'text-ink-secondary hover:text-ink'
              }`}
            >
              Brain
              {isActive('/entities') && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-accent" />
              )}
            </Link>
            <Link
              href="/onboard"
              className={`relative py-2 flex items-center gap-2 ${
                isActive('/onboard')
                  ? 'text-ink font-medium'
                  : 'text-ink-secondary hover:text-ink'
              }`}
            >
              Sources
              {isActive('/onboard') && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-accent" />
              )}
            </Link>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* Command search hint */}
          <button className="hidden md:flex items-center gap-2 px-3 py-1.5 text-small text-ink-muted bg-surface-subtle border border-line rounded-md hover:border-line-strong transition-colors">
            <span>Search...</span>
            <kbd className="kbd-hint">⌘K</kbd>
          </button>

          <Link href="/onboard" className="btn btn-primary text-small">
            Connect Source
          </Link>
        </div>
      </div>
    </nav>
  )
}
