'use client'

import Link from 'next/link'
import Image from 'next/image'
import { usePathname } from 'next/navigation'

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
      { name: 'API Keys', href: '/settings/api', icon: '⌘' },
      { name: 'Export', href: '/settings/export', icon: '↓' },
    ],
  },
]

export default function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <Link href="/" className="sidebar-brand flex items-center gap-2">
          <Image
            src="/komponist-logo.png"
            alt="K"
            width={32}
            height={32}
            className="rounded"
          />
          Komponist
        </Link>
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
        <div className="text-caption text-muted mb-1">Self-hosted</div>
        <div className="text-small font-mono">v0.1.0</div>
      </div>
    </aside>
  )
}
