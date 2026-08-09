'use client'

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
export const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === 'true'

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
  department_ids: string[]
  access_all_departments: boolean
  organization: { id: string; name: string }
}

const DEMO_USER: AuthUser = {
  id: 'demo-user-001',
  org_id: 'demo-org-001',
  email: 'demo@komponist.local',
  name: 'Demo User',
  avatar_url: null,
  role: 'owner',
  department_ids: [],
  access_all_departments: true,
  organization: { id: 'demo-org-001', name: 'Demo Organization' },
}

const DEMO_ORGANIZATIONS: Organization[] = [
  { id: 'demo-org-001', name: 'Demo Organization', role: 'owner', active: true },
]

interface AuthContextValue {
  user: AuthUser | null
  organizations: Organization[]
  loading: boolean
  refresh: () => Promise<void>
  login: () => void
  loginWithEmail: (email: string, password: string) => Promise<void>
  registerWithEmail: (name: string, email: string, password: string) => Promise<void>
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
    if (DEMO_MODE) return DEMO_ORGANIZATIONS
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
      if (DEMO_MODE) {
        // In demo mode, check localStorage for demo session
        const demoSession = localStorage.getItem('komponist_demo_session')
        if (demoSession) {
          storeActiveOrganization(DEMO_USER)
          setUser(DEMO_USER)
          setOrganizations(DEMO_ORGANIZATIONS)
        } else {
          storeActiveOrganization(null)
          setUser(null)
          setOrganizations([])
        }
        return
      }

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
    if (DEMO_MODE) {
      localStorage.setItem('komponist_demo_session', 'true')
      storeActiveOrganization(DEMO_USER)
      setUser(DEMO_USER)
      setOrganizations(DEMO_ORGANIZATIONS)
      return
    }
    const returnTo = `${window.location.pathname}${window.location.search}`
    window.location.href = `${API_URL}/auth/login/google?return_to=${encodeURIComponent(returnTo)}`
  }, [])

  const authenticateWithEmail = useCallback(async (
    path: '/auth/login/email' | '/auth/register',
    body: Record<string, string>,
  ) => {
    if (DEMO_MODE) {
      localStorage.setItem('komponist_demo_session', 'true')
      storeActiveOrganization(DEMO_USER)
      setUser(DEMO_USER)
      setOrganizations(DEMO_ORGANIZATIONS)
      return
    }

    let response: Response
    try {
      response = await fetch(`${API_URL}${path}`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
    } catch {
      throw new Error('Could not reach the Komponist API. Please check your connection and try again.')
    }

    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload.detail || 'Authentication failed')
    await refresh()
  }, [refresh])

  const loginWithEmail = useCallback(
    (email: string, password: string) => authenticateWithEmail(
      '/auth/login/email', { email, password },
    ),
    [authenticateWithEmail],
  )

  const registerWithEmail = useCallback(
    (name: string, email: string, password: string) => authenticateWithEmail(
      '/auth/register', { name, email, password },
    ),
    [authenticateWithEmail],
  )

  const logout = useCallback(async () => {
    if (DEMO_MODE) {
      localStorage.removeItem('komponist_demo_session')
      storeActiveOrganization(null)
      setUser(null)
      setOrganizations([])
      return
    }

    await fetch(`${API_URL}/auth/logout`, {
      method: 'POST',
      credentials: 'include',
    })
    storeActiveOrganization(null)
    setUser(null)
    setOrganizations([])
  }, [])

  const switchOrganization = useCallback(async (orgId: string) => {
    if (DEMO_MODE) {
      // In demo mode, just keep the same user/org
      return
    }

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
    loginWithEmail,
    registerWithEmail,
    logout,
    switchOrganization,
  }), [user, organizations, loading, refresh, login, loginWithEmail, registerWithEmail, logout, switchOrganization])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
