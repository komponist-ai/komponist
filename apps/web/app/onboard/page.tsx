'use client'

import { useState, useEffect, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import AppLayout from '../../components/AppLayout'
import { API_URL, apiFetch, getActiveOrgId } from '../../lib/api'

type SourceType = 'notion' | 'slack' | 'google' | 'local' | 'upload'
type ConnectorStatus = 'idle' | 'connecting' | 'connected' | 'error'

type UploadResult = {
  filename: string
  status: 'processed' | 'error'
  entities_created?: number
  error?: string
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
        `${API_URL}/auth/notion/token?org_id=${orgId}&token=${encodeURIComponent(notionToken)}`,
        { method: 'POST' }
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
        <div className="page-header">
          <h1 className="page-title">Add Source</h1>
        </div>

        <div className="page-body">
          <p className="text-muted mb-6">
            Choose a source to connect to your company brain.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-2xl">
            {/* Notion */}
            <button
              onClick={() => setSelectedSource('notion')}
              className="card hover:shadow-card transition-shadow text-left"
            >
              <div className="flex items-center gap-4">
                <span className="source-badge source-badge-notion text-lg">NO</span>
                <div>
                  <h3 className="text-h3">Notion</h3>
                  <p className="text-small text-muted">
                    Pages, databases, docs
                  </p>
                </div>
              </div>
            </button>

            {/* Slack */}
            <button
              onClick={() => setSelectedSource('slack')}
              className="card hover:shadow-card transition-shadow text-left"
            >
              <div className="flex items-center gap-4">
                <span className="source-badge source-badge-slack text-lg">SL</span>
                <div>
                  <h3 className="text-h3">Slack</h3>
                  <p className="text-small text-muted">
                    Channels, threads, decisions
                  </p>
                </div>
              </div>
            </button>

            {/* Google */}
            <button
              onClick={() => setSelectedSource('google')}
              className="card hover:shadow-card transition-shadow text-left"
            >
              <div className="flex items-center gap-4">
                <span className="source-badge source-badge-google text-lg">GD</span>
                <div>
                  <h3 className="text-h3">Google Workspace</h3>
                  <p className="text-small text-muted">
                    Docs, Sheets, Drive
                  </p>
                </div>
              </div>
            </button>

            {/* Local Docs */}
            <button
              onClick={() => setSelectedSource('upload')}
              className="card hover:shadow-card transition-shadow text-left"
            >
              <div className="flex items-center gap-4">
                <span className="text-2xl">↑</span>
                <div>
                  <h3 className="text-h3">Upload Documents</h3>
                  <p className="text-small text-muted">
                    Test the MVP directly from your browser
                  </p>
                </div>
              </div>
            </button>

            {/* Local Docs */}
            <button
              onClick={() => setSelectedSource('local')}
              className="card hover:shadow-card transition-shadow text-left"
            >
              <div className="flex items-center gap-4">
                <span className="text-2xl">📁</span>
                <div>
                  <h3 className="text-h3">Local Documents</h3>
                  <p className="text-small text-muted">
                    Markdown, text, YAML files
                  </p>
                </div>
              </div>
            </button>
          </div>
        </div>
      </AppLayout>
    )
  }

  // Connection form view
  return (
    <AppLayout>
      <div className="page-header">
        <div>
          <button
            onClick={() => {
              setSelectedSource(null)
              setStatus('idle')
              setError(null)
            }}
            className="text-small text-muted hover:text-ink mb-2 flex items-center gap-1"
          >
            ← Back to sources
          </button>
          <h1 className="page-title">
            Connect {selectedSource === 'notion' ? 'Notion' :
                     selectedSource === 'slack' ? 'Slack' :
                     selectedSource === 'google' ? 'Google Workspace' :
                     selectedSource === 'upload' ? 'Upload Documents' : 'Local Documents'}
          </h1>
        </div>
      </div>

      <div className="page-body">
        <div className="max-w-xl">
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
                <span className="source-badge source-badge-notion">NO</span>
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
                <span className="source-badge source-badge-slack">SL</span>
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
                <span className="source-badge source-badge-google">GD</span>
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
                <span className="text-2xl">↑</span>
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
                <span className="text-2xl">📁</span>
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
    </AppLayout>
  )
}

export default function OnboardPage() {
  return (
    <Suspense fallback={
      <AppLayout>
        <div className="page-header">
          <h1 className="page-title">Add Source</h1>
        </div>
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
