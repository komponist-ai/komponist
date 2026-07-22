'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Menu } from 'lucide-react'
import Sidebar from '../components/Sidebar'
import BrandMark from './BrandMark'
import ThemeToggle from './ThemeToggle'

export default function AppLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const pathname = usePathname()
  const [navigationOpen, setNavigationOpen] = useState(false)

  useEffect(() => {
    setNavigationOpen(false)
  }, [pathname])

  useEffect(() => {
    document.body.style.overflow = navigationOpen ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [navigationOpen])

  return (
    <div className="app-layout">
      <header className="mobile-app-bar">
        <button className="mobile-menu-button" type="button" onClick={() => setNavigationOpen(true)} aria-label="Open navigation">
          <Menu aria-hidden="true" />
        </button>
        <Link href="/studio" className="mobile-app-brand" aria-label="Komponist Studio">
          <BrandMark className="size-8 rounded-md shadow-none" />
          <span>Komponist</span>
        </Link>
        <ThemeToggle />
      </header>
      <button
        type="button"
        className={`sidebar-backdrop ${navigationOpen ? 'is-visible' : ''}`}
        onClick={() => setNavigationOpen(false)}
        aria-label="Close navigation"
        tabIndex={navigationOpen ? 0 : -1}
      />
      <Sidebar mobileOpen={navigationOpen} onMobileClose={() => setNavigationOpen(false)} />
      <main className="main-content">
        {children}
      </main>
    </div>
  )
}
