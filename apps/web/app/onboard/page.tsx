'use client'

import { useState, useEffect, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { motion } from 'framer-motion'
import { ArrowLeft, ArrowRight, CheckCircle2, FileText, LockKeyhole, PlugZap, Sparkles } from 'lucide-react'
import AppLayout from '../../components/AppLayout'
import SourceLogo from '../../components/SourceLogo'
import StudioTopbar from '../../components/StudioTopbar'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { API_URL, apiFetch, getActiveOrgId } from '../../lib/api'
import { useAuth } from '../../components/AuthProvider'

type SourceType = 'notion' | 'slack' | 'upload'
type ConnectorStatus = 'idle' | 'connecting' | 'connected' | 'error'

type UploadResult = {
  filename: string
  status: 'processed' | 'reused' | 'error'
  entities_created?: number
  entities_reused?: number
  error?: string
}

type Department = { id: string; name: string; color: string }

const SOURCE_OPTIONS: Array<{
  type: SourceType
  title: string
  description: string
  meta: string
  badge: string
}> = [
  { type: 'upload', title: 'Upload documents', description: 'Upload files from this device and send extracted company context through review.', meta: 'Markdown · text · YAML', badge: 'Fastest start' },
  { type: 'notion', title: 'Notion', description: 'Sync only the pages you explicitly share with a Komponist integration.', meta: 'Shared pages · nested blocks', badge: 'Internal integration' },
  { type: 'slack', title: 'Slack', description: 'Turn selected channels, complete threads, and attached documents into reviewed company context.', meta: 'Threads · PDF · DOCX · PPTX · text', badge: 'OAuth + channel scope' },
]

const SOURCE_TITLES: Record<SourceType, string> = {
  notion: 'Notion',
  slack: 'Slack',
  upload: 'Document uploads',
}

function OnboardContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { user } = useAuth()

  const [selectedSource, setSelectedSource] = useState<SourceType | null>(null)
  const [status, setStatus] = useState<ConnectorStatus>('idle')
  const [error, setError] = useState<string | null>(null)

  // Form fields
  const [notionToken, setNotionToken] = useState('')
  const [uploadFiles, setUploadFiles] = useState<File[]>([])
  const [uploadResults, setUploadResults] = useState<UploadResult[]>([])

  const [orgId, setOrgId] = useState('')
  const [departments, setDepartments] = useState<Department[]>([])
  const [departmentId, setDepartmentId] = useState('')

  useEffect(() => {
    setOrgId(getActiveOrgId())
  }, [])

  useEffect(() => {
    if (!orgId) return
    const loadDepartments = async () => {
      try {
        const response = await apiFetch(`${API_URL}/auth/organizations/${encodeURIComponent(orgId)}/departments`)
        const payload = await response.json()
        if (!response.ok) return
        const nextDepartments = payload.departments || []
        setDepartments(nextDepartments)
        if (!user?.access_all_departments && nextDepartments.length) {
          setDepartmentId(current => current || nextDepartments[0].id)
        }
      } catch {
        setDepartments([])
      }
    }
    void loadDepartments()
  }, [orgId, user?.access_all_departments])

  const departmentQuery = departmentId ? `&department_id=${encodeURIComponent(departmentId)}` : ''

  // Handle OAuth callback
  useEffect(() => {
    const source = searchParams.get('source')
    const callbackStatus = searchParams.get('status')

    if (source === 'slack' && callbackStatus === 'connected') {
      router.push('/sources?configure=slack')
    } else if (source === 'slack' && callbackStatus === 'error') {
      setSelectedSource('slack')
      setStatus('error')
      setError('Slack could not be connected. Check the app credentials and redirect URL.')
    }
  }, [searchParams, router])

  const handleConnectSlack = async () => {
    setStatus('connecting')
    setError(null)

    try {
      const response = await apiFetch(`${API_URL}/auth/slack?org=${orgId}`)
      const data = await response.json()

      if (data.auth_url) {
        window.location.href = data.auth_url
      } else if (data.error) {
        throw new Error(data.error)
      }
    } catch (err: any) {
      setError(err.message || 'Slack OAuth is not configured for this deployment')
      setStatus('error')
    }
  }

  const handleConnectNotion = async () => {
    const token = notionToken.trim()
    if (!token) {
      setError('Paste your Notion Internal Integration token')
      return
    }
    setStatus('connecting')
    setError(null)

    try {
      const response = await apiFetch(
        `${API_URL}/auth/notion/token?org_id=${encodeURIComponent(orgId)}${departmentQuery}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token }),
        },
      )
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Notion could not be connected')
      setNotionToken('')
      setStatus('connected')
      router.push('/sources?configure=notion')
    } catch (err: any) {
      setError(err.message || 'Notion could not be connected')
      setStatus('error')
    }
  }

  const handleDocumentUpload = async () => {
    if (uploadFiles.length === 0) {
      setError('Choose at least one document')
      return
    }
    setStatus('connecting')
    setError(null)
    setUploadResults([])

    try {
      const form = new FormData()
      uploadFiles.forEach(file => form.append('files', file))
      const response = await apiFetch(
        `${API_URL}/sources/upload?org_id=${orgId}${departmentQuery}`,
        { method: 'POST', body: form }
      )
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Upload failed')
      setUploadResults(data.results || [])
      setStatus(data.files_processed > 0 ? 'connected' : 'error')
      if (!data.files_processed) setError('No documents could be processed')
    } catch (err: any) {
      setError(err.message || 'Failed to upload documents')
      setStatus('error')
    }
  }

  // Source picker view
  if (!selectedSource) {
    return (
      <AppLayout>
        <StudioTopbar
          section="Sources"
          title="Add Source"
          description="Connect the tools and documents that hold company context"
          icon={PlugZap}
        />

        <main className="min-h-[calc(100vh-78px)] bg-paper px-5 py-8 sm:px-8 lg:px-10 lg:py-12">
          <div className="mx-auto max-w-[1180px]">
            <div className="grid gap-7 lg:grid-cols-[0.72fr_1.28fr] lg:items-end">
              <div>
                <Badge variant="orange"><Sparkles className="size-3" /> Compose your context</Badge>
                <h2 className="mt-5 text-[clamp(2.7rem,5vw,4.7rem)] leading-[0.9]">Connect where<br />your company thinks.</h2>
              </div>
              <div className="rounded-xl border-2 border-ink bg-ink p-5 text-white shadow-[5px_5px_0_#e8641b] sm:p-6">
                <p className="text-sm leading-6 text-white/70">Komponist reads the sources you explicitly connect, extracts reusable facts, and sends them through human review before agents can rely on them.</p>
                <div className="mt-5 grid gap-3 sm:grid-cols-3">
                  {[['01', 'Connect'], ['02', 'Review'], ['03', 'Use']].map(([number, label]) => <div key={number} className="border-t border-white/20 pt-3"><span className="font-mono text-[9px] text-orange">{number}</span><div className="mt-1 text-xs font-bold">{label}</div></div>)}
                </div>
              </div>
            </div>

            <section className="mt-9 grid gap-4 md:grid-cols-2 xl:grid-cols-3" aria-label="Available source connectors">
              {SOURCE_OPTIONS.map((source, index) => (
                <motion.button
                  key={source.type}
                  type="button"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.04 }}
                  whileHover={{ y: -3 }}
                  onClick={() => setSelectedSource(source.type)}
                  className="group min-h-[190px] rounded-xl border-2 border-ink bg-white p-5 text-left shadow-[4px_4px_0_#d9cfc0] transition hover:bg-[#fffaf0] hover:shadow-[6px_6px_0_#201c15]"
                >
                  <div className="flex items-start justify-between gap-4">
                    <SourceLogo type={source.type} />
                    <Badge variant={source.type === 'upload' ? 'orange' : 'default'} className="px-2 py-0.5 text-[8px]">{source.badge}</Badge>
                  </div>
                  <div className="mt-6 flex items-end justify-between gap-4">
                    <div>
                      <h3 className="text-xl">{source.title}</h3>
                      <p className="mt-2 max-w-md text-xs leading-5 text-muted">{source.description}</p>
                      <p className="mt-3 font-mono text-[9px] uppercase tracking-wider text-faint">{source.meta}</p>
                    </div>
                    <span className="grid size-9 shrink-0 place-items-center rounded-lg border-2 border-ink bg-paper-2 transition group-hover:bg-orange group-hover:text-white"><ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" /></span>
                  </div>
                </motion.button>
              ))}
            </section>
          </div>
        </main>
      </AppLayout>
    )
  }

  // Connection form view
  return (
    <AppLayout>
      <StudioTopbar
        section="Sources"
        title={`Connect ${SOURCE_TITLES[selectedSource]}`}
        description="Configure the connection, then sync company knowledge"
        icon={PlugZap}
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setSelectedSource(null)
              setStatus('idle')
              setError(null)
            }}
          >
            <ArrowLeft /> All sources
          </Button>
        }
      />

      <main className="min-h-[calc(100vh-78px)] bg-paper px-5 py-8 sm:px-8 lg:px-10 lg:py-10">
        <div className="mx-auto grid max-w-[1040px] gap-7 lg:grid-cols-[280px_minmax(0,1fr)]">
          <aside className="h-fit rounded-xl border-2 border-ink bg-ink p-5 text-white shadow-[5px_5px_0_#e8641b] lg:sticky lg:top-6">
            <SourceLogo type={selectedSource} className="shadow-[3px_3px_0_#e8641b]" />
            <p className="mt-6 font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-orange">New connection</p>
            <h2 className="mt-2 text-2xl text-white">{SOURCE_TITLES[selectedSource]}</h2>
            <p className="mt-3 text-xs leading-5 text-white/65">Only content you explicitly connect becomes available to Komponist.</p>
            <div className="mt-6 space-y-3 border-t border-white/20 pt-5">
              <div className="flex gap-2 text-[11px] text-white/70"><LockKeyhole className="mt-0.5 size-3.5 shrink-0 text-teal-light" /> Credentials stay server-side.</div>
              <div className="flex gap-2 text-[11px] text-white/70"><CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-teal-light" /> Extracted facts enter review.</div>
              <div className="flex gap-2 text-[11px] text-white/70"><FileText className="mt-0.5 size-3.5 shrink-0 text-teal-light" /> Synced documents remain manageable.</div>
            </div>
          </aside>

          <div className="min-w-0 [&_.card]:border-2 [&_.card]:border-ink [&_.card]:bg-white [&_.card]:shadow-[4px_4px_0_#d9cfc0]">
          {/* Error message */}
          {error && (
            <div className="card mb-6" style={{ background: 'var(--color-danger-soft)', borderColor: 'var(--color-danger)' }}>
              <p className="text-small" style={{ color: 'var(--color-danger)' }}>
                ⚠ {error}
              </p>
            </div>
          )}

          {/* Success message */}
          {status === 'connected' && selectedSource !== 'upload' && (
            <div className="card mb-6" style={{ background: 'var(--color-success-soft)', borderColor: 'var(--color-success)' }}>
              <p className="text-small" style={{ color: 'var(--color-success)' }}>
                ✓ Connected! Redirecting...
              </p>
            </div>
          )}

          {(selectedSource === 'notion' || selectedSource === 'upload') && (
            <div className="card mb-6">
              <div className="flex items-start gap-3">
                <span className="grid size-9 shrink-0 place-items-center rounded-lg border-2 border-ink bg-warning-soft"><LockKeyhole className="size-4" /></span>
                <div className="min-w-0 flex-1">
                  <label className="block text-small font-semibold" htmlFor="source-department">Knowledge access</label>
                  <p className="mt-1 text-caption text-muted">Choose who may retrieve facts extracted from this source.</p>
                  <select id="source-department" className="input mt-3" value={departmentId} onChange={event => setDepartmentId(event.target.value)} disabled={status === 'connecting'}>
                    {user?.access_all_departments && <option value="">Entire organization</option>}
                    {departments.map(department => <option key={department.id} value={department.id}>{department.name}</option>)}
                  </select>
                  {!user?.access_all_departments && departments.length === 0 && <p className="mt-2 text-caption text-danger">An admin must assign you to a department before you can upload knowledge.</p>}
                </div>
              </div>
            </div>
          )}

          {/* Notion form */}
          {selectedSource === 'notion' && (
            <div className="card">
              <div className="mb-4 flex items-center gap-3">
                <SourceLogo type="notion" className="size-9 rounded-lg shadow-none" />
                <h2 className="text-h3">Notion Internal Integration</h2>
              </div>
              <p className="mb-6 text-muted">
                Komponist can only discover pages you explicitly share with the integration.
                The token stays encrypted on the server and is never returned to the browser.
              </p>

              <div className="mb-6 rounded-md border border-line bg-paper-2 p-4">
                <p className="mb-3 text-small font-medium">Set up in three steps</p>
                <ol className="space-y-3 text-small text-muted">
                  <li><strong className="text-ink">1.</strong> Create an Internal Integration at <a className="font-medium text-orange-dark underline" href="https://www.notion.so/my-integrations" target="_blank" rel="noreferrer">notion.so/my-integrations</a>.</li>
                  <li><strong className="text-ink">2.</strong> In Notion, open each page you want to sync and choose <strong>••• → Connections → your integration</strong>.</li>
                  <li><strong className="text-ink">3.</strong> Paste the integration secret below, connect it, then run the first sync in Sources.</li>
                </ol>
              </div>

              <label className="mb-2 block text-small font-semibold" htmlFor="notion-token">
                Internal Integration token
              </label>
              <input
                id="notion-token"
                className="input mb-5 font-mono"
                type="password"
                autoComplete="off"
                placeholder="ntn_… or secret_…"
                value={notionToken}
                onChange={event => setNotionToken(event.target.value)}
                disabled={status === 'connecting'}
              />
              <button
                onClick={handleConnectNotion}
                className="btn btn-primary"
                disabled={status === 'connecting' || !notionToken.trim() || (!user?.access_all_departments && !departmentId)}
              >
                {status === 'connecting' ? 'Checking shared pages…' : 'Connect Notion'}
              </button>
            </div>
          )}

          {/* Slack form */}
          {selectedSource === 'slack' && (
            <div className="card">
              <div className="flex items-center gap-3 mb-4">
                <SourceLogo type="slack" className="size-9 rounded-lg shadow-none" />
                <h2 className="text-h3">Slack Integration</h2>
              </div>

              <p className="text-muted mb-6">Connect your workspace, choose explicit channels, then sync complete threads and supported file attachments into the review queue.</p>

              <div className="bg-paper-2 rounded-md p-4 mb-6 border border-line">
                <p className="text-small font-medium mb-2">What happens next</p>
                <ol className="space-y-2 text-small text-muted">
                  <li>1. Authorize the Komponist Slack app.</li>
                  <li>2. Invite it to the channels you want to use.</li>
                  <li>3. Select those channels in Sources and sync threads plus PDF, DOCX, PPTX, Markdown, text, YAML, JSON, or CSV attachments.</li>
                </ol>
              </div>

              <button
                onClick={handleConnectSlack}
                className="btn btn-primary"
                disabled={status === 'connecting'}
              >
                {status === 'connecting' ? 'Redirecting...' : 'Connect Slack'}
              </button>
            </div>
          )}

          {/* Direct document upload */}
          {selectedSource === 'upload' && (
            <div className="card">
              <div className="flex items-center gap-3 mb-4">
                <SourceLogo type="upload" className="size-9 rounded-lg shadow-none" />
                <h2 className="text-h3">Upload Documents</h2>
              </div>
              <p className="text-muted mb-6">
                Upload company context and send extracted facts to the review queue.
                Raw files are processed in memory and are not stored by Komponist.
              </p>
              <label className="upload-zone mb-5">
                <span className="text-small font-medium">Choose documents</span>
                <span className="text-caption text-muted">Markdown, text, or YAML · up to 20 files · 1 MB each</span>
                <input type="file" multiple accept=".md,.markdown,.txt,.yaml,.yml,text/plain,text/markdown"
                  onChange={event => setUploadFiles(Array.from(event.target.files || []))}
                  disabled={status === 'connecting'} />
              </label>
              {uploadFiles.length > 0 && <div className="file-list mb-5">
                {uploadFiles.map(file => <div key={`${file.name}-${file.size}`} className="file-row">
                  <span className="text-small">{file.name}</span>
                  <span className="text-caption text-muted">{Math.max(1, Math.round(file.size / 1024))} KB</span>
                </div>)}
              </div>}
              <button onClick={handleDocumentUpload} className="btn btn-primary"
                disabled={status === 'connecting' || uploadFiles.length === 0 || (!user?.access_all_departments && !departmentId)}>
                {status === 'connecting' ? 'Extracting with OpenAI…' : `Upload ${uploadFiles.length || ''} document${uploadFiles.length === 1 ? '' : 's'}`}
              </button>
              {uploadResults.length > 0 && <div className="upload-results mt-6">
                <h3 className="text-h3 mb-3">Extraction results</h3>
                {uploadResults.map(result => <div key={result.filename} className="result-row">
                  <div><p className="text-small font-medium">{result.filename}</p>
                    <p className="text-caption text-muted">{
                      result.status === 'processed'
                        ? `${result.entities_created || 0} entities extracted`
                        : result.status === 'reused'
                          ? `Identical content — reused ${result.entities_reused || 0} existing entities`
                          : result.error
                    }</p></div>
                  <span className={`badge ${result.status !== 'error' ? 'badge-teal' : ''}`}>{result.status}</span>
                </div>)}
                <div className="flex gap-2 mt-4">
                  <button className="btn btn-primary" onClick={() => router.push('/queue')}>Open Review Queue</button>
                  <button className="btn btn-secondary" onClick={() => router.push('/graph')}>View Graph</button>
                </div>
              </div>}
              <style jsx>{`.upload-zone{display:flex;flex-direction:column;gap:8px;padding:24px;border:1px dashed var(--color-line);border-radius:8px;background:var(--color-paper-2);cursor:pointer}.file-list,.upload-results{border-top:1px solid var(--color-line)}.file-row,.result-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 0;border-bottom:1px solid var(--color-line)}`}</style>
            </div>
          )}

          </div>
        </div>
      </main>
    </AppLayout>
  )
}

export default function OnboardPage() {
  return (
    <Suspense fallback={
      <AppLayout>
        <StudioTopbar section="Sources" title="Add Source" description="Loading source connectors…" icon={PlugZap} />
        <div className="page-body">
          <div className="card">
            <p className="text-muted">Loading...</p>
          </div>
        </div>
      </AppLayout>
    }>
      <OnboardContent />
    </Suspense>
  )
}
