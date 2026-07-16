'use client'

import Link from 'next/link'
import Image from 'next/image'
import { usePathname } from 'next/navigation'
import { useState } from 'react'
import { useAuth } from './AuthProvider'

const navigation = [
  {
    title: 'Brain',
    items: [
      { name: 'Chat', href: '/', icon: '💬' },
      { name: 'Graph', href: '/graph', icon: '◉' },
      { name: 'Review Queue', href: '/queue', icon: '↳' },
      { name: 'Entities', href: '/entities', icon: '{ }' },
    ],
  },
  {
    title: 'Sources',
    items: [
      { name: 'Connected', href: '/sources', icon: '↗' },
      { name: 'Add Source', href: '/onboard', icon: '+' },
    ],
  },
  {
    title: 'Settings',
    items: [
      { name: 'General', href: '/settings', icon: '⚙' },
      { name: 'AI Provider', href: '/settings/ai', icon: '✦' },
      { name: 'Team & roles', href: '/settings/team', icon: '◎' },
      { name: 'API & MCP', href: '/settings/api', icon: '⌘' },
      { name: 'Export', href: '/settings/export', icon: '↓' },
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
        <Link href="/" className="sidebar-brand flex items-center gap-2">
          <Image
            src="/komponist-logo.png"
            alt="K"
            width={32}
            height={32}
            unoptimized
            className="rounded"
          />
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
            {section.items.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`nav-item ${pathname === item.href ? 'active' : ''}`}
              >
                <span className="nav-item-icon">{item.icon}</span>
                {item.name}
              </Link>
            ))}
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
