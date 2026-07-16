'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState } from 'react'
import {
  Braces, CircleDot, Database, Download, KeyRound, MessageSquareText,
  Network, Plus, Settings, Sparkles, UsersRound,
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
      { name: 'Team & roles', href: '/settings/team', icon: UsersRound },
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

      <div className="sidebar-footer">
        <div className="sidebar-user">
          <div className="user-avatar" aria-hidden="true">
            {user?.name?.slice(0, 1).toUpperCase() || '?'}
          </div>
          <div className="sidebar-user-copy">
            <div className="text-small sidebar-user-name">{user?.name}</div>
            <div className="text-caption text-muted">{user?.role}</div>
          </div>
          <button className="sidebar-logout" onClick={logout} title="Sign out" aria-label="Sign out">
            ↪
          </button>
        </div>
      </div>
    </aside>
  )
}
