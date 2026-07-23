'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Clock3,
  Database,
  ExternalLink,
  FileText,
  Loader2,
  Layers3,
  Plus,
  Quote,
  RefreshCw,
  ShieldCheck,
  Trash2,
  Unplug,
  X,
} from 'lucide-react'
import AppLayout from '../../components/AppLayout'
import SourceLogo from '../../components/SourceLogo'
import StudioTopbar from '../../components/StudioTopbar'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { API_URL, apiFetch, getActiveOrgId } from '../../lib/api'
import { useAuth } from '../../components/AuthProvider'

interface Source {
  id: string
  type: 'notion' | 'slack' | 'google' | 'local' | 'upload'
  name: string
  status: 'connected' | 'syncing' | 'error'
  lastSync: string | null
  itemCount: number
  departmentId?: string | null
}

interface Department { id: string; name: string; color: string }

interface SyncedDocument {
  id: string
  title: string
  reference: string
  url?: string
  synced_at?: string
  evidence_count: number
  entity_count: number
  review_status: 'proposed' | 'confirmed' | 'mixed' | 'empty'
  department_id?: string | null
}

interface EvidencePassage {
  id: string
  source: string
  source_type: Source['type']
  reference: string
  title: string
  url?: string
  excerpt: string
  document_id?: string
  document_kind?: string
  source_date?: string
  entity_types: string[]
  statements: string[]
  location: {
    kind: string
    label: string
    page?: number
    line_start?: number
    line_end?: number
  }
}

interface DisconnectModal {
  source: Source | null
  loading: boolean
}

type DeleteDocumentModal = {
  source: Source
  document: SyncedDocument
} | null

const SOURCE_COPY: Record<Source['type'], { label: string; description: string }> = {
  notion: { label: 'Notion', description: 'Pages and databases shared with Komponist' },
  slack: { label: 'Slack', description: 'Channel conversations, threads, and decisions' },
  google: { label: 'Google Drive', description: 'Docs, Sheets, and workspace files' },
  local: { label: 'Local documents', description: 'Files mounted from your own infrastructure' },
  upload: { label: 'Document uploads', description: 'Files uploaded directly through the browser' },
}

function formatDate(value?: string | null) {
  if (!value) return 'Never'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown'
  return new Intl.DateTimeFormat('en', { day: '2-digit', month: 'short', year: 'numeric' }).format(date)
}

function canOpenUrl(value?: string) {
  return Boolean(value && /^https?:\/\//i.test(value))
}

export default function SourcesPage() {
  const { user, switchOrganization } = useAuth()
  const [sources, setSources] = useState<Source[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [documents, setDocuments] = useState<Record<string, SyncedDocument[]>>({})
  const [documentsLoading, setDocumentsLoading] = useState<Record<string, boolean>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [orgId, setOrgId] = useState('')
  const [syncing, setSyncing] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [disconnectModal, setDisconnectModal] = useState<DisconnectModal>({ source: null, loading: false })
  const [deleteModal, setDeleteModal] = useState<DeleteDocumentModal>(null)
  const [deletingDocument, setDeletingDocument] = useState(false)
  const [movingDocument, setMovingDocument] = useState<string | null>(null)
  const [movingSource, setMovingSource] = useState<string | null>(null)
  const [evidenceId, setEvidenceId] = useState<string | null>(null)
  const [passage, setPassage] = useState<EvidencePassage | null>(null)
  const [passageLoading, setPassageLoading] = useState(false)

  const canManage = user?.role === 'owner' || user?.role === 'admin'

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const requestedOrgId = params.get('org_id')
    const requestedEvidenceId = params.get('evidence')
    setEvidenceId(requestedEvidenceId)

    const activeOrgId = getActiveOrgId()
    if (requestedOrgId && requestedOrgId !== activeOrgId) {
      void switchOrganization(requestedOrgId)
        .then(() => setOrgId(requestedOrgId))
        .catch(() => {
          setError('You do not have access to the organization linked by this citation.')
          setOrgId(activeOrgId)
        })
      return
    }
    setOrgId(activeOrgId)
  }, [switchOrganization])

  useEffect(() => {
    if (!orgId || !evidenceId) {
      setPassage(null)
      return
    }
    setPassageLoading(true)
    void apiFetch(
      `${API_URL}/evidence/${encodeURIComponent(evidenceId)}?org_id=${encodeURIComponent(orgId)}`,
    )
      .then(async response => {
        const payload = await response.json()
        if (!response.ok) throw new Error(payload.detail || 'Could not open cited passage')
        setPassage(payload)
      })
      .catch(loadError => {
        setPassage(null)
        setError(loadError instanceof Error ? loadError.message : 'Could not open cited passage')
      })
      .finally(() => setPassageLoading(false))
  }, [evidenceId, orgId])

  const fetchDocuments = useCallback(async (sourceId: string) => {
    if (!orgId) return
    setDocumentsLoading((current) => ({ ...current, [sourceId]: true }))
    try {
      const response = await apiFetch(`${API_URL}/sources/${sourceId}/documents?org_id=${orgId}`)
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not load synced documents')
      setDocuments((current) => ({ ...current, [sourceId]: payload.documents ?? [] }))
    } catch (loadError) {
      console.error('Failed to fetch source documents:', loadError)
      setDocuments((current) => ({ ...current, [sourceId]: [] }))
    } finally {
      setDocumentsLoading((current) => ({ ...current, [sourceId]: false }))
    }
  }, [orgId])

  const fetchSources = useCallback(async () => {
    if (!orgId) return
    setError(null)
    try {
      const [response, departmentResponse] = await Promise.all([
        apiFetch(`${API_URL}/sources?org_id=${orgId}`),
        apiFetch(`${API_URL}/auth/organizations/${encodeURIComponent(orgId)}/departments`),
      ])
      const [payload, departmentPayload] = await Promise.all([response.json(), departmentResponse.json()])
      if (!response.ok) throw new Error(payload.detail || 'Could not load sources')
      if (!departmentResponse.ok) throw new Error(departmentPayload.detail || 'Could not load departments')
      const nextSources: Source[] = payload.sources ?? []
      setSources(nextSources)
      setDepartments(departmentPayload.departments ?? [])
      setExpanded((current) => current ?? nextSources[0]?.id ?? null)
      await Promise.all(nextSources.map((source) => fetchDocuments(source.id)))
    } catch (loadError) {
      console.error('Failed to fetch sources:', loadError)
      setError(loadError instanceof Error ? loadError.message : 'Could not connect to API')
      setSources([])
    } finally {
      setLoading(false)
    }
  }, [fetchDocuments, orgId])

  useEffect(() => { void fetchSources() }, [fetchSources])

  useEffect(() => {
    if (!passage || !sources.length) return
    const source = sources.find(item => (
      item.type === passage.source_type
      && (documents[item.id] ?? []).some(document => document.reference === passage.reference)
    )) ?? sources.find(item => item.type === passage.source_type)
    if (!source) return
    setExpanded(source.id)
    const targetDocument = (documents[source.id] ?? []).find(
      item => item.reference === passage.reference,
    )
    window.setTimeout(() => {
      window.document.getElementById(
        targetDocument
          ? `source-document-${source.id}-${targetDocument.id}`
          : `source-connection-${source.id}`,
      )?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 220)
  }, [documents, passage, sources])

  const closePassage = () => {
    setEvidenceId(null)
    setPassage(null)
    const url = new URL(window.location.href)
    url.searchParams.delete('evidence')
    url.searchParams.delete('org_id')
    window.history.replaceState({}, '', `${url.pathname}${url.search}`)
  }

  const handleSync = async (source: Source) => {
    setSyncing(source.id)
    setError(null)
    try {
      const response = await apiFetch(`${API_URL}/sources/${source.id}/sync?org_id=${orgId}`, { method: 'POST' })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || payload.error || 'Sync failed')
      await fetchSources()
    } catch (syncError) {
      setError(syncError instanceof Error ? syncError.message : 'Failed to sync source')
    } finally {
      setSyncing(null)
    }
  }

  const handleDisconnect = async (removeData: boolean) => {
    if (!disconnectModal.source) return
    setDisconnectModal((current) => ({ ...current, loading: true }))
    setError(null)
    try {
      const response = await apiFetch(
        `${API_URL}/sources/${disconnectModal.source.id}?org_id=${orgId}&remove_data=${removeData}`,
        { method: 'DELETE' },
      )
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || payload.error || 'Failed to disconnect')
      setDisconnectModal({ source: null, loading: false })
      await fetchSources()
    } catch (disconnectError) {
      setError(disconnectError instanceof Error ? disconnectError.message : 'Failed to disconnect source')
      setDisconnectModal((current) => ({ ...current, loading: false }))
    }
  }

  const handleDeleteDocument = async () => {
    if (!deleteModal) return
    setDeletingDocument(true)
    setError(null)
    try {
      const response = await apiFetch(
        `${API_URL}/sources/${deleteModal.source.id}/documents?org_id=${orgId}&reference=${encodeURIComponent(deleteModal.document.reference)}`,
        { method: 'DELETE' },
      )
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not remove document')
      setDeleteModal(null)
      await fetchSources()
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : 'Could not remove document')
    } finally {
      setDeletingDocument(false)
    }
  }

  const moveDocument = async (source: Source, document: SyncedDocument, departmentId: string) => {
    setMovingDocument(document.id)
    setError(null)
    try {
      const response = await apiFetch(`${API_URL}/sources/${source.id}/documents?org_id=${orgId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reference: document.reference, department_id: departmentId || null }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not move document')
      await fetchDocuments(source.id)
    } catch (moveError) {
      setError(moveError instanceof Error ? moveError.message : 'Could not move document')
    } finally {
      setMovingDocument(null)
    }
  }

  const moveSource = async (source: Source, departmentId: string) => {
    setMovingSource(source.id)
    setError(null)
    try {
      const response = await apiFetch(`${API_URL}/sources/${source.id}?org_id=${orgId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ department_id: departmentId || null }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not update source scope')
      setSources(current => current.map(item => item.id === source.id ? payload : item))
    } catch (moveError) {
      setError(moveError instanceof Error ? moveError.message : 'Could not update source scope')
    } finally {
      setMovingSource(null)
    }
  }

  const totalDocuments = useMemo(
    () => Object.values(documents).reduce((total, sourceDocuments) => total + sourceDocuments.length, 0),
    [documents],
  )
  const totalEntities = useMemo(
    () => Object.values(documents).flat().reduce((total, document) => total + document.entity_count, 0),
    [documents],
  )

  return (
    <AppLayout>
      <StudioTopbar
        section="Sources"
        title="Connected Sources"
        description="See exactly what Komponist has synced into this workspace"
        icon={Database}
        actions={<Button asChild size="sm"><Link href="/onboard"><Plus /> Add source</Link></Button>}
      />

      <main className="min-h-[calc(100vh-78px)] bg-paper px-5 py-7 sm:px-8 lg:px-10 lg:py-10">
        <div className="mx-auto max-w-[1180px]">
          {error && (
            <div className="mb-6 flex items-center justify-between gap-3 rounded-xl border-2 border-danger bg-danger-soft px-4 py-3 text-sm font-semibold text-danger" role="alert">
              <span className="flex items-center gap-3"><CircleAlert className="size-4" /> {error}</span>
              <button type="button" onClick={() => setError(null)} aria-label="Dismiss error"><X className="size-4" /></button>
            </div>
          )}

          {passageLoading && (
            <div className="mb-7 flex items-center gap-3 rounded-xl border-2 border-ink bg-white p-5 shadow-[4px_4px_0_#d9cfc0]">
              <Loader2 className="size-5 animate-spin text-orange" />
              <div><p className="text-sm font-bold">Opening cited passage</p><p className="mt-1 text-xs text-muted">Checking your current source permissions…</p></div>
            </div>
          )}

          {passage && (
            <motion.section
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              className="relative mb-7 overflow-hidden rounded-xl border-2 border-ink bg-white shadow-[6px_6px_0_#e8641b]"
              aria-label="Highlighted source passage"
            >
              <div className="absolute inset-y-0 left-0 w-2 bg-orange" />
              <div className="flex flex-col gap-5 p-5 pl-7 sm:p-6 sm:pl-8 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0 max-w-4xl">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="orange"><Quote className="size-3" /> Cited passage</Badge>
                    <Badge variant="default">{passage.location.label}</Badge>
                    {passage.entity_types.map(type => <Badge key={type} variant="teal">{type}</Badge>)}
                  </div>
                  <h2 className="mt-4 text-2xl">{passage.title}</h2>
                  <p className="mt-1 break-all font-mono text-[9px] text-faint">{passage.reference}</p>
                  <blockquote className="mt-5 rounded-xl border border-orange/30 bg-warning-soft p-4 text-sm leading-7 text-ink-2">
                    <mark className="box-decoration-clone rounded bg-[#ffdcae] px-1 py-0.5 text-ink">{passage.excerpt || passage.statements[0]}</mark>
                  </blockquote>
                  {passage.statements[0] && (
                    <p className="mt-3 text-xs leading-5 text-muted"><strong className="text-ink">Confirmed fact:</strong> {passage.statements[0]}</p>
                  )}
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  {canOpenUrl(passage.url) && (
                    <Button asChild variant="outline" size="sm">
                      <a href={passage.url} target="_blank" rel="noreferrer"><ExternalLink /> Open original</a>
                    </Button>
                  )}
                  <Button variant="ghost" size="sm" onClick={closePassage}><X /> Close</Button>
                </div>
              </div>
            </motion.section>
          )}

          <section className="mb-7 grid overflow-hidden rounded-xl border-2 border-ink bg-ink sm:grid-cols-3">
            {[
              ['Connections', sources.length, 'Active data sources'],
              ['Documents', totalDocuments, 'Visible inside Komponist'],
              ['Extracted facts', totalEntities, 'Linked to these documents'],
            ].map(([label, value, copy], index) => (
              <div key={String(label)} className="border-b-2 border-ink bg-white p-5 last:border-b-0 sm:border-b-0 sm:border-r-2 sm:last:border-r-0">
                <div className="flex items-start justify-between"><span className="font-mono text-[9px] font-bold uppercase tracking-[0.12em] text-muted">{label}</span><span className="font-mono text-[9px] text-faint">0{index + 1}</span></div>
                <div className="mt-4 font-display text-4xl font-black tracking-[-0.06em]">{loading ? '—' : value}</div>
                <p className="mt-1 text-xs text-muted">{copy}</p>
              </div>
            ))}
          </section>

          <div className="mb-5 flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
            <div>
              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-orange-dark">Workspace inputs</p>
              <h2 className="mt-1 text-3xl">Your knowledge sources</h2>
              <p className="mt-2 text-sm text-muted">Expand a connection to inspect and manage every synced document.</p>
            </div>
            <div className="flex items-center gap-2 rounded-lg border border-line bg-white px-3 py-2 text-[11px] text-muted">
              <ShieldCheck className="size-4 text-teal" /> Deleting here never deletes the original
            </div>
          </div>

          {loading ? (
            <div className="space-y-4">{[0, 1].map((index) => <div key={index} className="h-36 animate-pulse rounded-xl border-2 border-line bg-white" />)}</div>
          ) : sources.length === 0 ? (
            <div className="grid min-h-[420px] place-items-center rounded-xl border-2 border-ink bg-white p-8 text-center shadow-[5px_5px_0_#d9cfc0]">
              <div>
                <span className="mx-auto grid size-16 place-items-center rounded-xl border-2 border-ink bg-warning-soft text-orange-dark shadow-[4px_4px_0_#201c15]"><Database className="size-7" /></span>
                <h2 className="mt-6 text-3xl">Bring in your first source.</h2>
                <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-muted">Upload documents from this device or connect Notion, Slack, and Google Drive.</p>
                <Button asChild className="mt-6"><Link href="/onboard"><Plus /> Add source</Link></Button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {sources.map((source, sourceIndex) => {
                const copy = SOURCE_COPY[source.type]
                const sourceDocuments = documents[source.id] ?? []
                const isExpanded = expanded === source.id
                const isSyncing = syncing === source.id
                return (
                  <motion.article id={`source-connection-${source.id}`} key={source.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: sourceIndex * 0.04 }} className="scroll-mt-24 overflow-hidden rounded-xl border-2 border-ink bg-white shadow-[4px_4px_0_#d9cfc0]">
                    <div className="flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between">
                      <div className="flex min-w-0 items-center gap-4">
                        <SourceLogo type={source.type} />
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="truncate text-xl">{source.name || copy.label}</h3>
                            <Badge variant={source.status === 'connected' ? 'teal' : source.status === 'error' ? 'orange' : 'default'} className="px-2 py-0.5 text-[9px]">
                              <span className={`size-1.5 rounded-full ${source.status === 'connected' ? 'bg-teal' : source.status === 'syncing' ? 'animate-pulse bg-orange' : 'bg-danger'}`} /> {source.status}
                            </Badge>
                          </div>
                          <p className="mt-1 text-xs text-muted">{copy.description}</p>
                          <div className="mt-2 flex items-center gap-1.5 text-[10px] font-semibold text-muted"><Layers3 className="size-3" />{source.type === 'upload' ? 'Access is set per document' : source.departmentId ? departments.find(department => department.id === source.departmentId)?.name || 'Department scoped' : 'Entire organization'}</div>
                        </div>
                      </div>

                      <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                        <div className="mr-2 hidden text-right lg:block">
                          <div className="text-xs font-bold">{sourceDocuments.length} document{sourceDocuments.length === 1 ? '' : 's'}</div>
                          <div className="mt-0.5 text-[10px] text-muted">Last sync {formatDate(source.lastSync)}</div>
                        </div>
                        {canManage && source.type !== 'upload' && (
                          <select
                            className="h-9 max-w-44 rounded-md border-2 border-ink bg-white px-2 text-xs font-semibold outline-none"
                            value={source.departmentId || ''}
                            onChange={event => void moveSource(source, event.target.value)}
                            disabled={movingSource === source.id}
                            aria-label={`Default department for ${source.name}`}
                          >
                            <option value="">Entire organization</option>
                            {departments.map(department => <option key={department.id} value={department.id}>{department.name}</option>)}
                          </select>
                        )}
                        {source.type !== 'upload' && (
                          <Button variant="outline" size="sm" onClick={() => void handleSync(source)} disabled={isSyncing}>
                            {isSyncing ? <Loader2 className="animate-spin" /> : <RefreshCw />} {isSyncing ? 'Syncing' : 'Sync'}
                          </Button>
                        )}
                        <Button variant="ghost" size="icon" title="Disconnect source" aria-label={`Disconnect ${source.name}`} onClick={() => setDisconnectModal({ source, loading: false })}><Unplug /></Button>
                        <Button variant="subtle" size="icon" title="Show synced documents" aria-label={`Show documents from ${source.name}`} aria-expanded={isExpanded} onClick={() => setExpanded(isExpanded ? null : source.id)}>
                          <ChevronDown className={`transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                        </Button>
                      </div>
                    </div>

                    <AnimatePresence initial={false}>
                      {isExpanded && (
                        <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden border-t-2 border-ink bg-paper-2">
                          <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3 font-mono text-[9px] font-bold uppercase tracking-[0.12em] text-muted">
                            <span>Synced documents</span>
                            <span>{sourceDocuments.length} in Komponist</span>
                          </div>
                          {documentsLoading[source.id] ? (
                            <div className="flex items-center gap-2 px-5 py-8 text-sm text-muted"><Loader2 className="size-4 animate-spin" /> Loading documents…</div>
                          ) : sourceDocuments.length === 0 ? (
                            <div className="px-5 py-8 text-center"><FileText className="mx-auto size-6 text-faint" /><p className="mt-3 text-sm font-semibold">No synced documents found</p><p className="mt-1 text-xs text-muted">Run a sync or upload a document to populate this connection.</p></div>
                          ) : (
                            <div className="divide-y divide-line">
                              {sourceDocuments.map((document) => {
                                const isHighlighted = passage?.reference === document.reference
                                  && passage.source_type === source.type
                                return (
                                <div
                                  id={`source-document-${source.id}-${document.id}`}
                                  key={document.id}
                                  className={`scroll-mt-24 grid gap-4 px-4 py-4 transition sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:px-5 ${isHighlighted ? 'bg-warning-soft ring-2 ring-inset ring-orange' : 'bg-white hover:bg-[#fffaf0]'}`}
                                >
                                  <div className="flex min-w-0 items-start gap-3">
                                    <span className={`grid size-9 shrink-0 place-items-center rounded-lg border ${isHighlighted ? 'border-orange bg-white text-orange-dark' : 'border-line bg-paper-2'}`}><FileText className="size-4" /></span>
                                    <div className="min-w-0">
                                      <div className="flex flex-wrap items-center gap-2">
                                        <p className="truncate text-sm font-bold text-ink">{document.title}</p>
                                        <Badge variant={document.review_status === 'confirmed' ? 'teal' : document.review_status === 'proposed' ? 'orange' : 'default'} className="px-2 py-0.5 text-[8px]">{document.review_status}</Badge>
                                        {isHighlighted && <Badge variant="orange" className="px-2 py-0.5 text-[8px]"><Quote className="size-2.5" /> Citation</Badge>}
                                      </div>
                                      <p className="mt-1 truncate font-mono text-[9px] text-faint" title={document.reference}>{document.reference}</p>
                                      <div className="mt-2 flex flex-wrap items-center gap-3 text-[10px] text-muted">
                                        <span>{document.entity_count} extracted fact{document.entity_count === 1 ? '' : 's'}</span>
                                        <span className="flex items-center gap-1"><Clock3 className="size-3" /> {formatDate(document.synced_at)}</span>
                                      </div>
                                      {isHighlighted && passage && (
                                        <blockquote className="mt-3 max-w-2xl border-l-2 border-orange pl-3 text-xs leading-5 text-ink-2">
                                          <mark className="bg-[#ffdcae] px-0.5 text-ink">{passage.excerpt || passage.statements[0]}</mark>
                                        </blockquote>
                                      )}
                                    </div>
                                  </div>
                                  <div className="flex items-center gap-1 sm:justify-end">
                                    {canManage && (
                                      <select
                                        className="h-9 max-w-40 rounded-md border border-line bg-white px-2 text-[10px] font-semibold outline-none focus:border-ink"
                                        value={document.department_id || ''}
                                        onChange={event => void moveDocument(source, document, event.target.value)}
                                        disabled={movingDocument === document.id}
                                        aria-label={`Department for ${document.title}`}
                                      >
                                        <option value="">Entire organization</option>
                                        {departments.map(department => <option key={department.id} value={department.id}>{department.name}</option>)}
                                      </select>
                                    )}
                                    {canOpenUrl(document.url) && <Button asChild variant="ghost" size="icon" title="Open original"><a href={document.url} target="_blank" rel="noreferrer"><ExternalLink /></a></Button>}
                                    <Button variant="ghost" size="icon" title="Remove from Komponist" aria-label={`Remove ${document.title} from Komponist`} className="text-danger hover:bg-danger-soft hover:text-danger" onClick={() => setDeleteModal({ source, document })}><Trash2 /></Button>
                                  </div>
                                </div>
                              )})}
                            </div>
                          )}
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </motion.article>
                )
              })}
            </div>
          )}
        </div>
      </main>

      <AnimatePresence>
        {deleteModal && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[200] grid place-items-center bg-ink/60 p-4" onMouseDown={() => !deletingDocument && setDeleteModal(null)}>
            <motion.div initial={{ opacity: 0, y: 14, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 10, scale: 0.98 }} className="w-full max-w-lg overflow-hidden rounded-xl border-2 border-ink bg-white shadow-[7px_7px_0_#e8641b]" onMouseDown={(event) => event.stopPropagation()}>
              <div className="border-b-2 border-ink bg-danger-soft p-5"><div className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-lg border-2 border-ink bg-white"><Trash2 className="size-5 text-danger" /></span><div><p className="font-mono text-[9px] font-bold uppercase tracking-wider text-danger">Remove from Komponist</p><h2 className="mt-1 text-xl">Delete synced document?</h2></div></div></div>
              <div className="p-5">
                <p className="text-sm font-bold text-ink">{deleteModal.document.title}</p>
                <p className="mt-2 text-sm leading-6 text-muted">This removes its evidence and any facts that have no other source.</p>
                <div className="mt-4 flex gap-3 rounded-lg border border-teal bg-success-soft p-3 text-xs leading-5 text-teal"><ShieldCheck className="mt-0.5 size-4 shrink-0" /><span>The original document in {SOURCE_COPY[deleteModal.source.type].label} is not changed or deleted.</span></div>
              </div>
              <div className="flex justify-end gap-2 border-t-2 border-ink bg-paper-2 p-4"><Button variant="ghost" onClick={() => setDeleteModal(null)} disabled={deletingDocument}>Cancel</Button><Button className="bg-danger" onClick={() => void handleDeleteDocument()} disabled={deletingDocument}>{deletingDocument ? <Loader2 className="animate-spin" /> : <Trash2 />} Remove from Komponist</Button></div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {disconnectModal.source && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[200] grid place-items-center bg-ink/60 p-4" onMouseDown={() => !disconnectModal.loading && setDisconnectModal({ source: null, loading: false })}>
            <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-lg overflow-hidden rounded-xl border-2 border-ink bg-white shadow-[7px_7px_0_#201c15]" onMouseDown={(event) => event.stopPropagation()}>
              <div className="flex items-center gap-4 border-b-2 border-ink p-5"><SourceLogo type={disconnectModal.source.type} /><div><p className="font-mono text-[9px] font-bold uppercase tracking-wider text-muted">Disconnect source</p><h2 className="mt-1 text-xl">{disconnectModal.source.name}</h2></div></div>
              <div className="space-y-3 p-5">
                <button type="button" className="w-full rounded-lg border-2 border-line p-4 text-left transition hover:border-ink" onClick={() => void handleDisconnect(false)} disabled={disconnectModal.loading}><p className="text-sm font-bold">Disconnect and keep knowledge</p><p className="mt-1 text-xs leading-5 text-muted">Stop future syncs while keeping extracted facts and evidence.</p></button>
                <button type="button" className="w-full rounded-lg border-2 border-danger bg-danger-soft p-4 text-left transition hover:bg-white" onClick={() => void handleDisconnect(true)} disabled={disconnectModal.loading}><p className="text-sm font-bold text-danger">Disconnect and remove Komponist data</p><p className="mt-1 text-xs leading-5 text-muted">Delete derived facts and evidence. The original platform remains untouched.</p></button>
              </div>
              <div className="flex justify-end border-t-2 border-ink bg-paper-2 p-4"><Button variant="ghost" onClick={() => setDisconnectModal({ source: null, loading: false })} disabled={disconnectModal.loading}>{disconnectModal.loading ? <Loader2 className="animate-spin" /> : <X />} Cancel</Button></div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </AppLayout>
  )
}
