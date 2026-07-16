const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

function getOrgId(): string {
  if (typeof window !== 'undefined') {
    return localStorage.getItem('komponist_org_id') || 'default-org'
  }
  return 'default-org'
}

export async function fetchQueue() {
  const orgId = getOrgId()
  const res = await fetch(`${API_URL}/queue?org_id=${orgId}`)
  if (!res.ok) throw new Error('Failed to fetch queue')
  return res.json()
}

export async function fetchEntities(status: string = 'confirmed') {
  const orgId = getOrgId()
  const res = await fetch(`${API_URL}/entities?org_id=${orgId}&status=${status}`)
  if (!res.ok) throw new Error('Failed to fetch entities')
  return res.json()
}

export async function fetchEntity(id: string) {
  const orgId = getOrgId()
  const res = await fetch(`${API_URL}/entities/${id}?org_id=${orgId}`)
  if (!res.ok) throw new Error('Failed to fetch entity')
  return res.json()
}

export async function fetchEntityNeighborhood(id: string) {
  const orgId = getOrgId()
  const res = await fetch(`${API_URL}/entities/${id}/neighborhood?org_id=${orgId}`)
  if (!res.ok) throw new Error('Failed to fetch neighborhood')
  return res.json()
}

export async function confirmEntity(id: string, statement: string) {
  const orgId = getOrgId()
  const res = await fetch(`${API_URL}/entities/${id}/confirm?org_id=${orgId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ statement }),
  })
  if (!res.ok) throw new Error('Failed to confirm entity')
  return res.json()
}

export async function rejectEntity(id: string) {
  const orgId = getOrgId()
  const res = await fetch(`${API_URL}/entities/${id}/reject?org_id=${orgId}`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('Failed to reject entity')
  return res.json()
}

export async function mergeEntity(id: string, targetId: string) {
  const orgId = getOrgId()
  const res = await fetch(`${API_URL}/entities/${id}/merge?org_id=${orgId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_id: targetId }),
  })
  if (!res.ok) throw new Error('Failed to merge entity')
  return res.json()
}

export async function fetchDashboardStats() {
  const orgId = getOrgId()
  const [entitiesRes, queueRes] = await Promise.all([
    fetch(`${API_URL}/entities?org_id=${orgId}&status=confirmed&limit=5`),
    fetch(`${API_URL}/queue?org_id=${orgId}`)
  ])

  const entities = await entitiesRes.json()
  const queue = await queueRes.json()

  return {
    entities: entities.total || 0,
    pending: queue.total || 0,
    recentEntities: entities.entities?.slice(0, 5) || []
  }
}
