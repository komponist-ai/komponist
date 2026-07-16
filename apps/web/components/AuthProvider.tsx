'use client'

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface Organization {
  id: string
  name: string
  role: 'owner' | 'admin' | 'member' | 'viewer'
  active: boolean
}

export interface AuthUser {
  id: string
  org_id: string
  email: string
  name: string
  avatar_url?: string | null
  role: Organization['role']
  organization: { id: string; name: string }
}

interface AuthContextValue {
  user: AuthUser | null
  organizations: Organization[]
  loading: boolean
  refresh: () => Promise<void>
  login: () => void
  logout: () => Promise<void>
  switchOrganization: (orgId: string) => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

function storeActiveOrganization(user: AuthUser | null) {
  if (user) {
    localStorage.setItem('komponist_active_org_id', user.org_id)
  } else {
    localStorage.removeItem('komponist_active_org_id')
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [organizations, setOrganizations] = useState<Organization[]>([])
  const [loading, setLoading] = useState(true)

  const loadOrganizations = useCallback(async () => {
    const response = await fetch(`${API_URL}/auth/organizations`, {
      credentials: 'include',
      cache: 'no-store',
    })
    if (!response.ok) return []
    const payload = await response.json()
    return (payload.organizations || []) as Organization[]
  }, [])

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const response = await fetch(`${API_URL}/auth/session`, {
        credentials: 'include',
        cache: 'no-store',
      })
      if (!response.ok) throw new Error('Could not load session')
      const payload = await response.json()
      const nextUser = payload.authenticated ? payload.user as AuthUser : null
      storeActiveOrganization(nextUser)
      setUser(nextUser)
      setOrganizations(nextUser ? await loadOrganizations() : [])
    } catch {
      storeActiveOrganization(null)
      setUser(null)
      setOrganizations([])
    } finally {
      setLoading(false)
    }
  }, [loadOrganizations])

  useEffect(() => {
    refresh()
  }, [refresh])

  const login = useCallback(() => {
    const returnTo = `${window.location.pathname}${window.location.search}`
    window.location.href = `${API_URL}/auth/login/google?return_to=${encodeURIComponent(returnTo)}`
  }, [])

  const logout = useCallback(async () => {
    await fetch(`${API_URL}/auth/logout`, {
      method: 'POST',
      credentials: 'include',
    })
    storeActiveOrganization(null)
    setUser(null)
    setOrganizations([])
  }, [])

  const switchOrganization = useCallback(async (orgId: string) => {
    const response = await fetch(`${API_URL}/auth/organizations/${orgId}/select`, {
      method: 'POST',
      credentials: 'include',
    })
    if (!response.ok) throw new Error('Could not switch organization')
    const payload = await response.json()
    const nextUser = payload.user as AuthUser
    storeActiveOrganization(nextUser)
    setUser(nextUser)
    setOrganizations(await loadOrganizations())
  }, [loadOrganizations])

  const value = useMemo(() => ({
    user,
    organizations,
    loading,
    refresh,
    login,
    logout,
    switchOrganization,
  }), [user, organizations, loading, refresh, login, logout, switchOrganization])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
