export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export function getActiveOrgId(): string {
  if (typeof window === 'undefined') throw new Error('Active organization is client-only')
  const orgId = localStorage.getItem('komponist_active_org_id')
  if (!orgId) throw new Error('No active organization in the current session')
  return orgId
}

export function apiFetch(input: string, init: RequestInit = {}) {
  return fetch(input, { ...init, credentials: 'include' })
}

export async function installCampusKollektivDemo() {
  const orgId = getActiveOrgId()
  const response = await apiFetch(
    `${API_URL}/demo/workspace?org_id=${encodeURIComponent(orgId)}`,
    { method: 'POST' },
  )
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(payload?.detail || 'Could not load the CampusKollektiv example')
  }
  return payload
}

export async function fetchQueue(options: {
  entityType?: string
  query?: string
  limit?: number
  offset?: number
} = {}) {
  const orgId = getActiveOrgId()
  const params = new URLSearchParams({
    org_id: orgId,
    limit: String(options.limit ?? 24),
    offset: String(options.offset ?? 0),
  })
  if (options.entityType) params.set('entity_type', options.entityType)
  if (options.query) params.set('query', options.query)
  const res = await apiFetch(`${API_URL}/queue?${params}`)
  if (!res.ok) throw new Error('Failed to fetch queue')
  return res.json()
}

export async function fetchEntities(options: {
  status?: string
  entityType?: string
  query?: string
  limit?: number
  offset?: number
} = {}) {
  const orgId = getActiveOrgId()
  const params = new URLSearchParams({
    org_id: orgId,
    status: options.status ?? 'confirmed',
    limit: String(options.limit ?? 24),
    offset: String(options.offset ?? 0),
  })
  if (options.entityType) params.set('entity_type', options.entityType)
  if (options.query) params.set('query', options.query)
  const res = await apiFetch(`${API_URL}/entities?${params}`)
  if (!res.ok) throw new Error('Failed to fetch entities')
  return res.json()
}

export async function fetchEntity(id: string) {
  const orgId = getActiveOrgId()
  const res = await apiFetch(`${API_URL}/entities/${id}?org_id=${orgId}`)
  if (!res.ok) throw new Error('Failed to fetch entity')
  return res.json()
}

export async function fetchEntityNeighborhood(id: string) {
  const orgId = getActiveOrgId()
  const res = await apiFetch(`${API_URL}/entities/${id}/neighborhood?org_id=${orgId}`)
  if (!res.ok) throw new Error('Failed to fetch neighborhood')
  return res.json()
}

export async function confirmEntity(id: string, statement: string) {
  const orgId = getActiveOrgId()
  const res = await apiFetch(`${API_URL}/entities/${id}/confirm?org_id=${orgId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ statement }),
  })
  if (!res.ok) throw new Error('Failed to confirm entity')
  return res.json()
}

export async function rejectEntity(id: string) {
  const orgId = getActiveOrgId()
  const res = await apiFetch(`${API_URL}/entities/${id}/reject?org_id=${orgId}`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('Failed to reject entity')
  return res.json()
}

export async function mergeEntity(id: string, targetId: string) {
  const orgId = getActiveOrgId()
  const res = await apiFetch(`${API_URL}/entities/${id}/merge?org_id=${orgId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_id: targetId }),
  })
  if (!res.ok) throw new Error('Failed to merge entity')
  return res.json()
}

export async function fetchDashboardStats() {
  const orgId = getActiveOrgId()
  const [entitiesRes, queueRes] = await Promise.all([
    apiFetch(`${API_URL}/entities?org_id=${orgId}&status=confirmed&limit=5`),
    apiFetch(`${API_URL}/queue?org_id=${orgId}&limit=1`)
  ])

  const entities = await entitiesRes.json()
  const queue = await queueRes.json()

  return {
    entities: entities.total || 0,
    pending: queue.total || 0,
    recentEntities: entities.entities?.slice(0, 5) || []
  }
}
