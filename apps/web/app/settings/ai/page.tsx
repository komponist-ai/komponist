'use client'

import { useEffect, useState } from 'react'
import AppLayout from '../../../components/AppLayout'
import { API_URL, apiFetch, getActiveOrgId } from '../../../lib/api'

type AIStatus = {
  mode: 'mock' | 'live'
  provider: 'mock' | 'openai'
  model: string
  embedding_model: string
  configured: boolean
  managed_by: string
}

export default function AISettingsPage() {
  const [status, setStatus] = useState<AIStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  const load = async () => {
    const response = await apiFetch(`${API_URL}/settings/ai?org_id=${getActiveOrgId()}`)
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || 'Could not load AI status')
    setStatus(data)
  }

  useEffect(() => { load().catch(error => setMessage(error.message)) }, [])

  const test = async () => {
    setBusy(true); setMessage('')
    try {
      const response = await apiFetch(`${API_URL}/settings/ai/test?org_id=${getActiveOrgId()}`, { method: 'POST' })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Connection failed')
      setMessage(data.message)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Connection failed')
    } finally { setBusy(false) }
  }

  return <AppLayout>
    <div className="page-header"><div><h1 className="page-title">AI Provider</h1>
      <p className="text-small text-muted">Komponist manages the AI provider centrally for every workspace.</p>
    </div></div>
    <div className="page-body max-w-2xl space-y-6">
      {message && <div className="card"><p className="text-small">{message}</p></div>}
      <div className="card">
        <div className="status-head"><div><h2 className="text-h2 mb-1">Platform AI</h2><p className="text-small text-muted">Customers never provide or see an OpenAI API key.</p></div>
          <span className={`badge ${status?.configured ? 'ready' : 'missing'}`}>{status?.configured ? 'Ready' : 'Not configured'}</span></div>
        <dl className="status-grid">
          <div><dt>Mode</dt><dd>{status?.mode || 'Loading…'}</dd></div>
          <div><dt>Provider</dt><dd>{status?.provider || '—'}</dd></div>
          <div><dt>Generation</dt><dd>{status?.model || '—'}</dd></div>
          <div><dt>Embeddings</dt><dd>{status?.embedding_model || '—'}</dd></div>
        </dl>
        <div className="actions"><button className="btn btn-secondary" disabled={busy || !status?.configured} onClick={test}>{busy ? 'Testing…' : 'Test platform connection'}</button></div>
      </div>
      <div className="card bg-paper-2"><h3 className="text-h3 mb-2">Server-managed configuration</h3>
        <p className="text-small text-muted">Set <code>OPENAI_API_KEY</code> and <code>KOMPONIST_AI_MODE=live</code> in the deployment environment. Only the backend receives the secret.</p>
      </div>
    </div>
    <style jsx>{`.status-head,.actions{display:flex;align-items:center;justify-content:space-between;gap:16px}.badge{padding:5px 9px;border-radius:999px;font-size:12px}.ready{background:var(--color-success-soft);color:var(--color-success)}.missing{background:var(--color-danger-soft);color:var(--color-danger)}.status-grid{display:grid;grid-template-columns:1fr 1fr;margin:24px 0;border-top:1px solid var(--color-line)}.status-grid div{padding:14px 0;border-bottom:1px solid var(--color-line)}dt{font-size:12px;color:var(--color-ink-muted)}dd{font-size:14px;font-weight:600;margin-top:4px}`}</style>
  </AppLayout>
}
