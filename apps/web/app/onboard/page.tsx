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

type SourceType = 'notion' | 'slack' | 'google' | 'local' | 'upload'
type ConnectorStatus = 'idle' | 'connecting' | 'connected' | 'error'

type UploadResult = {
  filename: string
  status: 'processed' | 'error'
  entities_created?: number
  error?: string
}

const SOURCE_OPTIONS: Array<{
  type: SourceType
  title: string
  description: string
  meta: string
  badge: string
}> = [
  { type: 'notion', title: 'Notion', description: 'Turn shared pages and databases into reviewed company context.', meta: 'Pages · databases · docs', badge: 'Integration token' },
  { type: 'slack', title: 'Slack', description: 'Capture durable decisions and context from the channels you choose.', meta: 'Channels · threads · decisions', badge: 'OAuth' },
  { type: 'google', title: 'Google Drive', description: 'Sync the Docs and workspace files your agents should understand.', meta: 'Docs · Sheets · Drive', badge: 'OAuth' },
  { type: 'upload', title: 'Upload documents', description: 'Test the full extraction and review loop from your browser.', meta: 'Markdown · text · YAML', badge: 'Fastest start' },
  { type: 'local', title: 'Local documents', description: 'Index mounted files without sending raw documents to another platform.', meta: 'Self-hosted folder', badge: 'Local' },
]

const SOURCE_TITLES: Record<SourceType, string> = {
  notion: 'Notion',
  slack: 'Slack',
  google: 'Google Drive',
  upload: 'Document uploads',
  local: 'Local documents',
}

function OnboardContent() {
  const router = useRouter()
  const searchParams = useSearchParams()

  const [selectedSource, setSelectedSource] = useState<SourceType | null>(null)
  const [status, setStatus] = useState<ConnectorStatus>('idle')
  const [error, setError] = useState<string | null>(null)

  // Form fields
  const [notionToken, setNotionToken] = useState('')
  const [localDocsPath, setLocalDocsPath] = useState('/data/docs')
  const [uploadFiles, setUploadFiles] = useState<File[]>([])
  const [uploadResults, setUploadResults] = useState<UploadResult[]>([])

  const [orgId, setOrgId] = useState('')

  useEffect(() => {
    setOrgId(getActiveOrgId())
  }, [])

  // Handle OAuth callback
  useEffect(() => {
    const source = searchParams.get('source')
    const callbackStatus = searchParams.get('status')

    if (source && callbackStatus === 'connected') {
      // OAuth callback succeeded
      router.push('/sources')
    }
  }, [searchParams, router])

  const handleConnectNotion = async () => {
    if (!notionToken.trim()) {
      setError('Please enter your Notion integration token')
      return
    }

    setStatus('connecting')
    setError(null)

    try {
      const response = await apiFetch(
        `${API_URL}/auth/notion/token?org_id=${orgId}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: notionToken }),
        }
      )
      const data = await response.json()

      if (response.ok && data.status === 'connected') {
        setStatus('connected')
        // Redirect to sources page after short delay
        setTimeout(() => router.push('/sources'), 1000)
      } else {
        throw new Error(data.detail || data.error || 'Failed to validate token')
      }
    } catch (err: any) {
      console.error('Notion connection error:', err)
      setError(err.message || 'Failed to connect. Check your token.')
      setStatus('error')
    }
  }

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
      setError('Slack OAuth not configured. Add SLACK_CLIENT_ID to .env')
      setStatus('error')
    }
  }

  const handleConnectGoogle = async () => {
    setStatus('connecting')
    setError(null)

    try {
      const response = await apiFetch(`${API_URL}/auth/google?org=${orgId}`)
      const data = await response.json()

      if (data.auth_url) {
        window.location.href = data.auth_url
      } else if (data.error) {
        throw new Error(data.error)
      }
    } catch (err: any) {
      setError('Google OAuth not configured. Add GOOGLE_CLIENT_ID to .env')
      setStatus('error')
    }
  }

  const handleConnectLocalDocs = async () => {
    if (!localDocsPath.trim()) {
      setError('Please enter a path')
      return
    }

    setStatus('connecting')
    setError(null)

    try {
      const addResponse = await apiFetch(
        `${API_URL}/sources?org_id=${orgId}&source_type=local&name=${encodeURIComponent('Local Documents')}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: localDocsPath }),
        }
      )
      const source = await addResponse.json()
      if (!addResponse.ok || !source.id) {
        throw new Error(source.detail || source.error || 'Failed to register local documents')
      }

      const syncResponse = await apiFetch(
        `${API_URL}/sources/${source.id}/sync?org_id=${orgId}`,
        { method: 'POST' }
      )
      const syncResult = await syncResponse.json()

      if (syncResponse.ok && syncResult.status !== 'error') {
        setStatus('connected')
        setTimeout(() => router.push('/sources'), 1000)
      } else {
        throw new Error(syncResult.detail || syncResult.error || 'Failed to scan documents')
      }
    } catch (err: any) {
      setError(err.message || 'Failed to scan local documents')
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
        `${API_URL}/sources/upload?org_id=${orgId}`,
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

            <section className="mt-9 grid gap-4 md:grid-cols-2" aria-label="Available source connectors">
              {SOURCE_OPTIONS.map((source, index) => (
                <motion.button
                  key={source.type}
                  type="button"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.04 }}
                  whileHover={{ y: -3 }}
                  onClick={() => setSelectedSource(source.type)}
                  className={`group min-h-[190px] rounded-xl border-2 border-ink bg-white p-5 text-left shadow-[4px_4px_0_#d9cfc0] transition hover:bg-[#fffaf0] hover:shadow-[6px_6px_0_#201c15] ${source.type === 'upload' ? 'md:col-span-2' : ''}`}
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
        title={`Connect ${selectedSource === 'notion' ? 'Notion' :
          selectedSource === 'slack' ? 'Slack' :
          selectedSource === 'google' ? 'Google Workspace' :
          selectedSource === 'upload' ? 'Upload Documents' : 'Local Documents'}`}
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

          {/* Notion form */}
          {selectedSource === 'notion' && (
            <div className="card">
              <div className="flex items-center gap-3 mb-4">
                <SourceLogo type="notion" className="size-9 rounded-lg shadow-none" />
                <h2 className="text-h3">Notion Integration</h2>
              </div>

              <div className="bg-paper-2 rounded-md p-4 mb-6 border border-line">
                <p className="text-small font-medium mb-2">Quick setup (2 minutes):</p>
                <ol className="text-small text-muted space-y-2">
                  <li>1. Go to <a href="https://www.notion.so/my-integrations" target="_blank" rel="noopener" className="text-teal underline">notion.so/my-integrations</a></li>
                  <li>2. Click "New integration" → name it "Komponist"</li>
                  <li>3. Copy the "Internal Integration Secret"</li>
                  <li>4. Paste it below</li>
                </ol>
              </div>

              <div className="mb-6">
                <label className="block text-small font-medium mb-2">
                  Integration Token
                </label>
                <input
                  type="password"
                  value={notionToken}
                  onChange={(e) => setNotionToken(e.target.value)}
                  placeholder="secret_..."
                  className="input font-mono"
                  disabled={status === 'connecting'}
                />
                <p className="text-caption text-faint mt-2">
                  Starts with "secret_" or "ntn_"
                </p>
              </div>

              <div className="bg-paper-2 rounded-md p-4 mb-6 border border-line">
                <p className="text-small font-medium mb-2">After connecting:</p>
                <p className="text-small text-muted">
                  Share pages with your integration by clicking ••• → Connections → Komponist on each page you want to sync.
                </p>
              </div>

              <button
                onClick={handleConnectNotion}
                className="btn btn-primary"
                disabled={status === 'connecting' || status === 'connected'}
              >
                {status === 'connecting' ? 'Connecting...' :
                 status === 'connected' ? 'Connected ✓' : 'Connect Notion'}
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

              <p className="text-muted mb-6">
                Connect your Slack workspace to extract decisions and context from channels.
              </p>

              <div className="bg-paper-2 rounded-md p-4 mb-6 border border-line">
                <p className="text-small font-medium mb-2">Requirements:</p>
                <p className="text-small text-muted">
                  Slack OAuth requires SLACK_CLIENT_ID and SLACK_CLIENT_SECRET in your .env file.
                  Create an app at <a href="https://api.slack.com/apps" target="_blank" rel="noopener" className="text-teal underline">api.slack.com/apps</a>
                </p>
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

          {/* Google form */}
          {selectedSource === 'google' && (
            <div className="card">
              <div className="flex items-center gap-3 mb-4">
                <SourceLogo type="google" className="size-9 rounded-lg shadow-none" />
                <h2 className="text-h3">Google Workspace</h2>
              </div>

              <p className="text-muted mb-6">
                Connect Google Drive to sync Docs, Sheets, and other files.
              </p>

              <div className="bg-paper-2 rounded-md p-4 mb-6 border border-line">
                <p className="text-small font-medium mb-2">Requirements:</p>
                <p className="text-small text-muted">
                  Google OAuth requires GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in your .env file.
                  Create credentials at <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener" className="text-teal underline">Google Cloud Console</a>
                </p>
              </div>

              <button
                onClick={handleConnectGoogle}
                className="btn btn-primary"
                disabled={status === 'connecting'}
              >
                {status === 'connecting' ? 'Redirecting...' : 'Connect Google'}
              </button>
            </div>
          )}

          {/* Local docs form */}
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
                <span className="text-caption text-muted">Markdown, text, or YAML · up to 10 files · 1 MB each</span>
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
                disabled={status === 'connecting' || uploadFiles.length === 0}>
                {status === 'connecting' ? 'Extracting with OpenAI…' : `Upload ${uploadFiles.length || ''} document${uploadFiles.length === 1 ? '' : 's'}`}
              </button>
              {uploadResults.length > 0 && <div className="upload-results mt-6">
                <h3 className="text-h3 mb-3">Extraction results</h3>
                {uploadResults.map(result => <div key={result.filename} className="result-row">
                  <div><p className="text-small font-medium">{result.filename}</p>
                    <p className="text-caption text-muted">{result.status === 'processed' ? `${result.entities_created || 0} entities extracted` : result.error}</p></div>
                  <span className={`badge ${result.status === 'processed' ? 'badge-teal' : ''}`}>{result.status}</span>
                </div>)}
                <div className="flex gap-2 mt-4">
                  <button className="btn btn-primary" onClick={() => router.push('/queue')}>Open Review Queue</button>
                  <button className="btn btn-secondary" onClick={() => router.push('/graph')}>View Graph</button>
                </div>
              </div>}
              <style jsx>{`.upload-zone{display:flex;flex-direction:column;gap:8px;padding:24px;border:1px dashed var(--color-line);border-radius:8px;background:var(--color-paper-2);cursor:pointer}.file-list,.upload-results{border-top:1px solid var(--color-line)}.file-row,.result-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 0;border-bottom:1px solid var(--color-line)}`}</style>
            </div>
          )}

          {/* Local docs form */}
          {selectedSource === 'local' && (
            <div className="card">
              <div className="flex items-center gap-3 mb-4">
                <SourceLogo type="local" className="size-9 rounded-lg shadow-none" />
                <h2 className="text-h3">Local Documents</h2>
              </div>

              <p className="text-muted mb-6">
                Point to a folder of markdown, text, or YAML files to extract facts.
              </p>

              <div className="mb-6">
                <label className="block text-small font-medium mb-2">
                  Documents path
                </label>
                <input
                  type="text"
                  value={localDocsPath}
                  onChange={(e) => setLocalDocsPath(e.target.value)}
                  placeholder="/data/docs"
                  className="input font-mono"
                  disabled={status === 'connecting'}
                />
                <p className="text-caption text-faint mt-2">
                  Docker mounts KOMPONIST_LOCAL_DOCS_HOST_PATH here by default
                </p>
              </div>

              <div className="bg-paper-2 rounded-md p-4 mb-6 border border-line">
                <p className="text-small font-medium mb-2">Supported files:</p>
                <ul className="text-small text-muted space-y-1">
                  <li>• Markdown (.md)</li>
                  <li>• Text files (.txt)</li>
                  <li>• YAML configs (.yaml, .yml)</li>
                </ul>
              </div>

              <button
                onClick={handleConnectLocalDocs}
                className="btn btn-primary"
                disabled={status === 'connecting' || status === 'connected'}
              >
                {status === 'connecting' ? 'Scanning...' :
                 status === 'connected' ? 'Added ✓' : 'Add Documents'}
              </button>
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
