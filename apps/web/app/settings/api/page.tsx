'use client'

import { useEffect, useMemo, useState } from 'react'
import AppLayout from '../../../components/AppLayout'
import { API_URL, apiFetch, getActiveOrgId } from '../../../lib/api'

type ApiKey = { id: string; name: string; prefix: string; created_at: string; last_used_at: string | null; revoked_at: string | null }

export default function ApiConnectPage() {
  const [keys, setKeys] = useState<ApiKey[]>([])
  const [name, setName] = useState('My agent')
  const [newKey, setNewKey] = useState('')
  const [message, setMessage] = useState('')
  const mcpUrl = 'http://localhost:8080/mcp'
  const config = useMemo(() => `[mcp_servers.komponist]\nurl = "${mcpUrl}"\nbearer_token_env_var = "KOMPONIST_API_KEY"`, [])

  const load = async () => {
    const orgId = getActiveOrgId()
    const response = await apiFetch(`${API_URL}/auth/organizations/${orgId}/api-keys`)
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || 'Could not load API keys')
    setKeys(data.keys)
  }
  useEffect(() => { load().catch(error => setMessage(error.message)) }, [])

  const create = async () => {
    setMessage('')
    const orgId = getActiveOrgId()
    const response = await apiFetch(`${API_URL}/auth/organizations/${orgId}/api-keys`, {
      method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({name}),
    })
    const data = await response.json()
    if (!response.ok) return setMessage(data.detail || 'Could not create key')
    setNewKey(data.key); setMessage('Key created. Copy it now — it will not be shown again.'); await load()
  }
  const revoke = async (id: string) => {
    const orgId = getActiveOrgId()
    const response = await apiFetch(`${API_URL}/auth/organizations/${orgId}/api-keys/${id}`, {method:'DELETE'})
    if (!response.ok) return setMessage('Could not revoke key')
    setNewKey(''); await load(); setMessage('Key revoked.')
  }
  const copy = async (value: string) => { await navigator.clipboard.writeText(value); setMessage('Copied to clipboard.') }

  return <AppLayout>
    <div className="page-header"><div><h1 className="page-title">API & MCP</h1>
      <p className="text-small text-muted">Connect coding agents to this workspace with revocable, scoped credentials.</p>
    </div></div>
    <div className="page-body max-w-3xl space-y-6">
      {message && <div className="card"><p className="text-small">{message}</p></div>}
      {newKey && <div className="card key-reveal"><div><p className="text-small font-medium mb-2">New API key</p><code>{newKey}</code></div><button className="btn btn-primary" onClick={() => copy(newKey)}>Copy</button></div>}
      <div className="card"><h2 className="text-h2 mb-2">Create key</h2><p className="text-small text-muted mb-4">Use one key per agent or device so access can be revoked independently.</p>
        <div className="create-row"><input className="input-field" value={name} maxLength={100} onChange={event => setName(event.target.value)} /><button className="btn btn-primary" onClick={create}>Create API key</button></div>
      </div>
      <div className="card"><h2 className="text-h2 mb-4">Active keys</h2>
        {keys.length === 0 ? <p className="text-small text-muted">No API keys yet.</p> : <div className="key-list">{keys.map(key => <div className="key-row" key={key.id}><div><strong className="text-small">{key.name}</strong><div className="text-caption text-muted"><code>{key.prefix}</code> · created {new Date(key.created_at).toLocaleDateString()}</div></div><button className="btn btn-secondary" disabled={!!key.revoked_at} onClick={() => revoke(key.id)}>{key.revoked_at ? 'Revoked' : 'Revoke'}</button></div>)}</div>}
      </div>
      <div className="card"><div className="connect-head"><div><h2 className="text-h2 mb-2">Connect Codex</h2><p className="text-small text-muted">Set <code>KOMPONIST_API_KEY</code> to your key, then add this remote MCP server.</p></div><button className="btn btn-secondary" onClick={() => copy(config)}>Copy config</button></div><pre>{config}</pre></div>
      <div className="card"><h2 className="text-h2 mb-2">REST API</h2><p className="text-small text-muted mb-3">Search confirmed workspace context with the same Bearer key.</p><pre>{`curl -H "Authorization: Bearer $KOMPONIST_API_KEY" \\\n  "${API_URL}/v1/context?query=authentication"`}</pre></div>
    </div>
    <style jsx>{`.input-field{flex:1;padding:10px 12px;border:1px solid var(--color-line);border-radius:6px;background:var(--color-paper)}.create-row,.key-reveal,.connect-head,.key-row{display:flex;align-items:center;justify-content:space-between;gap:12px}.key-reveal{border-color:var(--color-teal)}.key-reveal code{overflow-wrap:anywhere}.key-list{display:flex;flex-direction:column}.key-row{padding:14px 0;border-top:1px solid var(--color-line)}.key-row:first-child{border-top:0}pre{margin-top:16px;padding:16px;overflow:auto;background:var(--color-ink);color:var(--color-paper);border-radius:6px;font-size:12px}@media(max-width:700px){.create-row,.connect-head{align-items:stretch;flex-direction:column}}`}</style>
  </AppLayout>
}
