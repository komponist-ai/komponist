'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState } from 'react'
import {
  Braces, CircleDot, Database, Download, KeyRound, MessageSquareText,
  LogOut, Network, Plus, Settings, Sparkles, UsersRound,
} from 'lucide-react'
import { useAuth } from './AuthProvider'
import BrandMark from './BrandMark'

const navigation = [
  {
    title: 'Brain',
    items: [
      { name: 'Chat', href: '/studio', icon: MessageSquareText },
      { name: 'Graph', href: '/graph', icon: Network },
      { name: 'Review Queue', href: '/queue', icon: CircleDot },
      { name: 'Entities', href: '/entities', icon: Braces },
    ],
  },
  {
    title: 'Sources',
    items: [
      { name: 'Connected', href: '/sources', icon: Database },
      { name: 'Add Source', href: '/onboard', icon: Plus },
    ],
  },
  {
    title: 'Settings',
    items: [
      { name: 'General', href: '/settings', icon: Settings },
      { name: 'AI Provider', href: '/settings/ai', icon: Sparkles },
      { name: 'Team & departments', href: '/settings/team', icon: UsersRound },
      { name: 'API & MCP', href: '/settings/api', icon: KeyRound },
      { name: 'Export', href: '/settings/export', icon: Download },
    ],
  },
]

export default function Sidebar() {
  const pathname = usePathname()
  const { user, organizations, logout, switchOrganization } = useAuth()
  const [switching, setSwitching] = useState(false)

  const handleOrganizationChange = async (orgId: string) => {
    setSwitching(true)
    try {
      await switchOrganization(orgId)
      window.location.reload()
    } finally {
      setSwitching(false)
    }
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <Link href="/studio" className="sidebar-brand flex items-center gap-2">
          <BrandMark className="size-8 rounded-md shadow-[2px_2px_0_#201c15]" />
          Komponist
        </Link>
        <label className="org-switcher-label" htmlFor="organization-switcher">
          Workspace
        </label>
        <select
          id="organization-switcher"
          className="org-switcher"
          value={user?.org_id || ''}
          disabled={switching}
          onChange={(event) => handleOrganizationChange(event.target.value)}
        >
          {organizations.map((organization) => (
            <option key={organization.id} value={organization.id}>
              {organization.name}
            </option>
          ))}
        </select>
      </div>

      <nav className="sidebar-nav">
        {navigation.map((section) => (
          <div key={section.title} className="nav-section">
            <div className="nav-section-title">{section.title}</div>
            {section.items.map((item) => {
              const Icon = item.icon
              return (
              <Link
                key={item.href}
                href={item.href}
                className={`nav-item ${pathname === item.href ? 'active' : ''}`}
              >
                <span className="nav-item-icon"><Icon size={16} strokeWidth={2} /></span>
                {item.name}
              </Link>
              )
            })}
          </div>
        ))}
      </nav>

      <div className="sidebar-footer !p-3">
        <div className="overflow-hidden rounded-xl border-2 border-ink bg-white shadow-[3px_3px_0_#d9cfc0]">
          <div className="flex min-w-0 items-center gap-3 p-3">
            <div className="grid size-10 shrink-0 place-items-center rounded-lg border-2 border-ink bg-orange font-display text-sm font-black text-white shadow-[2px_2px_0_#201c15]" aria-hidden="true">
              {user?.name?.slice(0, 1).toUpperCase() || '?'}
            </div>
            <div className="min-w-0 flex-1 leading-tight">
              <div className="truncate text-sm font-bold text-ink" title={user?.name}>{user?.name}</div>
              <div className="mt-1 flex min-w-0 items-center gap-2">
                <span className="rounded-full bg-teal-soft px-2 py-0.5 font-mono text-[8px] font-bold uppercase tracking-wider text-teal-dark">
                  {user?.role}
                </span>
                <span className="min-w-0 truncate text-[10px] text-muted" title={user?.email}>{user?.email}</span>
              </div>
            </div>
          </div>
          <button
            className="group flex w-full items-center justify-between border-t-2 border-ink bg-paper-2 px-3 py-2.5 text-xs font-bold text-ink-2 transition hover:bg-danger-soft hover:text-danger focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-orange"
            onClick={logout}
            title="Sign out of Komponist"
            aria-label="Sign out"
          >
            <span>Sign out</span>
            <LogOut className="size-4 transition-transform group-hover:translate-x-0.5" />
          </button>
        </div>
      </div>
    </aside>
  )
}
