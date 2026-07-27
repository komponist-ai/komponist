'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Braces, Check, Clipboard, Clock3, KeyRound, LoaderCircle,
  LockKeyhole, Network, Plus, RefreshCcw, ShieldCheck, TerminalSquare,
  Trash2, X,
} from 'lucide-react'
import AppLayout from '../../../components/AppLayout'
import SettingsNotice, { type SettingsMessage } from '../../../components/SettingsNotice'
import StudioTopbar from '../../../components/StudioTopbar'
import { useAuth } from '../../../components/AuthProvider'
import { Badge } from '../../../components/ui/badge'
import { Button } from '../../../components/ui/button'
import { API_URL, apiFetch, getActiveOrgId } from '../../../lib/api'

type ApiKey = {
  id: string
  name: string
  prefix: string
  created_at: string
  last_used_at: string | null
  revoked_at: string | null
}

type IntegrationTab = 'mcp' | 'sdk' | 'rest'

const MCP_URL = process.env.NEXT_PUBLIC_MCP_URL || 'http://localhost:8080/mcp'

export default function ApiConnectPage() {
  const { user } = useAuth()
  const [keys, setKeys] = useState<ApiKey[]>([])
  const [name, setName] = useState('My agent')
  const [newKey, setNewKey] = useState('')
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [revokingId, setRevokingId] = useState<string | null>(null)
  const [confirmRevokeId, setConfirmRevokeId] = useState<string | null>(null)
  const [message, setMessage] = useState<SettingsMessage | null>(null)
  const [activeTab, setActiveTab] = useState<IntegrationTab>('mcp')

  const canManage = user?.role === 'owner' || user?.role === 'admin'
  const activeKeys = keys.filter(key => !key.revoked_at)
  const revokedKeys = keys.filter(key => key.revoked_at)

  const examples = useMemo<Record<IntegrationTab, { title: string; description: string; code: string }>>(() => ({
    mcp: {
      title: 'Connect an MCP client',
      description: 'Use the same organization key in Codex or another remote MCP client.',
      code: `[mcp_servers.komponist]\nurl = "${MCP_URL}"\nbearer_token_env_var = "KOMPONIST_API_KEY"`,
    },
    sdk: {
      title: 'Use the TypeScript SDK',
      description: 'Call reviewed context from trusted server-side TypeScript.',
      code: `import { createKomponistClient } from '@komponist/sdk'\n\nconst komponist = createKomponistClient({\n  url: process.env.KOMPONIST_URL ?? '${API_URL}',\n  apiKey: process.env.KOMPONIST_API_KEY!,\n})\n\nconst { data, error } = await komponist.context.search(\n  'What did we decide about authentication?',\n  { types: ['Decision', 'Constraint'], limit: 8 },\n)\n\nif (error) throw new Error(error.message)\nconsole.log(data.items[0].evidence)`,
    },
    rest: {
      title: 'Call the REST API',
      description: 'Search confirmed, cited workspace context over HTTP.',
      code: `curl -H "Authorization: Bearer $KOMPONIST_API_KEY" \\\n+  "${API_URL}/v1/context?query=authentication"`,
    },
  }), [])

  const load = useCallback(async () => {
    if (!canManage) {
      setLoading(false)
      return
    }
    setLoading(true)
    setMessage(null)
    try {
      const orgId = getActiveOrgId()
      const response = await apiFetch(`${API_URL}/auth/organizations/${encodeURIComponent(orgId)}/api-keys`)
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not load API keys')
      setKeys(payload.keys || [])
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Could not load API keys' })
    } finally {
      setLoading(false)
    }
  }, [canManage])

  useEffect(() => {
    void load()
  }, [load])

  const createKey = async () => {
    const normalizedName = name.trim()
    if (!canManage || !normalizedName) return
    setCreating(true)
    setNewKey('')
    setMessage(null)
    try {
      const orgId = getActiveOrgId()
      const response = await apiFetch(`${API_URL}/auth/organizations/${encodeURIComponent(orgId)}/api-keys`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: normalizedName }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not create API key')
      setNewKey(payload.key)
      setName('')
      setMessage({ type: 'success', text: 'API key created. Copy it now — the full value is shown only once.' })
      await load()
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Could not create API key' })
    } finally {
      setCreating(false)
    }
  }

  const revokeKey = async (id: string) => {
    if (!canManage) return
    setRevokingId(id)
    setMessage(null)
    try {
      const orgId = getActiveOrgId()
      const response = await apiFetch(`${API_URL}/auth/organizations/${encodeURIComponent(orgId)}/api-keys/${encodeURIComponent(id)}`, { method: 'DELETE' })
      if (!response.ok) {
        const payload = await response.json().catch(() => null)
        throw new Error(payload?.detail || 'Could not revoke API key')
      }
      setNewKey('')
      setConfirmRevokeId(null)
      setMessage({ type: 'success', text: 'API key revoked. Clients using it can no longer access this organization.' })
      await load()
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Could not revoke API key' })
    } finally {
      setRevokingId(null)
    }
  }

  const copy = async (value: string, label: string) => {
    try {
      await navigator.clipboard.writeText(value)
      setMessage({ type: 'success', text: `${label} copied to the clipboard.` })
    } catch {
      setMessage({ type: 'error', text: `The browser could not copy ${label.toLowerCase()}. Select and copy it manually.` })
    }
  }

  const example = examples[activeTab]

  return (
    <AppLayout>
      <StudioTopbar
        section="Settings"
        title="API & MCP"
        description="Revocable organization access for agents and server-side apps"
        icon={KeyRound}
        actions={canManage ? (
          <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading || creating}>
            <RefreshCcw className={loading ? 'animate-spin' : ''} />
            <span className="hidden sm:inline">Refresh</span>
          </Button>
        ) : <Badge>Your role: {user?.role}</Badge>}
      />

      <div className="page-body max-w-6xl space-y-6">
        {message && <SettingsNotice message={message} />}

        {!canManage ? (
          <section className="grid min-h-[440px] place-items-center rounded-2xl border-2 border-ink bg-white p-8 text-center shadow-[7px_7px_0_var(--color-shadow-strong)]">
            <div className="max-w-md">
              <span className="mx-auto grid size-14 place-items-center rounded-xl border-2 border-ink bg-warning-soft shadow-[3px_3px_0_var(--color-shadow-strong)]"><LockKeyhole className="size-6" /></span>
              <h2 className="mt-6 text-3xl font-bold tracking-tight">Admin access required</h2>
              <p className="mt-3 leading-7 text-muted">API keys grant machine access to reviewed organization context. Only owners and admins can view, create, or revoke them.</p>
            </div>
          </section>
        ) : (
          <>
            <section className="grid overflow-hidden rounded-2xl border-2 border-ink bg-white shadow-[7px_7px_0_var(--color-shadow-strong)] lg:grid-cols-[0.9fr_1.1fr]">
              <div className="relative overflow-hidden border-b-2 border-ink bg-ink p-7 text-white lg:border-b-0 lg:border-r-2 sm:p-9">
                <div className="absolute -right-16 -top-16 size-52 rounded-full border-[34px] border-orange/80" />
                <div className="relative">
                  <Badge variant="dark" className="border-white/25"><ShieldCheck className="size-3.5" /> Organization scoped</Badge>
                  <h2 className="mt-7 max-w-lg text-4xl font-bold leading-tight tracking-tight sm:text-5xl">Give agents context, not your account.</h2>
                  <p className="mt-5 max-w-lg leading-7 text-white/65">Create one credential per agent or environment. Every key is isolated to this organization and can be revoked independently.</p>
                  <div className="mt-8 flex flex-wrap gap-3 font-mono text-[10px] font-bold uppercase tracking-wider text-white/70">
                    <span className="flex items-center gap-2"><Check className="size-4 text-teal-light" /> Confirmed facts</span>
                    <span className="flex items-center gap-2"><Check className="size-4 text-teal-light" /> Citations</span>
                    <span className="flex items-center gap-2"><Check className="size-4 text-teal-light" /> Revocable</span>
                  </div>
                </div>
              </div>

              <div className="p-6 sm:p-9">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div><p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-orange-dark">Credential inventory</p><h3 className="mt-2 text-3xl font-bold">{loading ? 'Loading keys…' : `${activeKeys.length} active ${activeKeys.length === 1 ? 'key' : 'keys'}`}</h3></div>
                  <Badge variant={activeKeys.length > 0 ? 'teal' : 'default'}>{activeKeys.length > 0 ? <Network /> : <KeyRound />}{activeKeys.length > 0 ? 'Agent access on' : 'No active access'}</Badge>
                </div>
                <div className="mt-7 grid grid-cols-2 gap-3">
                  <ApiMetric icon={KeyRound} label="Active" value={loading ? '—' : activeKeys.length} />
                  <ApiMetric icon={Trash2} label="Revoked" value={loading ? '—' : revokedKeys.length} />
                </div>
                <div className="mt-7 rounded-xl border-2 border-ink bg-paper-2 p-4">
                  <div className="flex items-start gap-3"><LockKeyhole className="mt-0.5 size-5 shrink-0 text-orange-dark" /><div><strong className="text-sm">Server-side use only</strong><p className="mt-1 text-xs leading-5 text-muted">Never place an organization key in a browser bundle, public repository, or mobile application.</p></div></div>
                </div>
              </div>
            </section>

            {newKey && (
              <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="overflow-hidden rounded-2xl border-2 border-teal bg-success-soft shadow-[5px_5px_0_var(--color-teal)]">
                <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:p-6">
                  <span className="grid size-11 shrink-0 place-items-center rounded-xl border-2 border-ink bg-white shadow-[2px_2px_0_var(--color-shadow-strong)]"><KeyRound className="size-5 text-teal" /></span>
                  <div className="min-w-0 flex-1"><p className="font-mono text-[10px] font-bold uppercase tracking-wider text-teal">One-time secret</p><code className="mt-2 block overflow-x-auto whitespace-nowrap rounded-lg border-2 border-ink bg-white px-3 py-2 text-xs">{newKey}</code></div>
                  <Button onClick={() => void copy(newKey, 'API key')}><Clipboard /> Copy key</Button>
                </div>
              </motion.section>
            )}

            <section className="grid gap-6 lg:grid-cols-[0.82fr_1.18fr]">
              <div className="rounded-2xl border-2 border-ink bg-white p-6 shadow-[5px_5px_0_var(--color-shadow-soft)] sm:p-8">
                <span className="grid size-11 place-items-center rounded-xl border-2 border-ink bg-orange text-white shadow-[3px_3px_0_var(--color-shadow-strong)]"><Plus className="size-5" /></span>
                <h3 className="mt-5 text-2xl font-bold">Create a key</h3>
                <p className="mt-2 text-sm leading-6 text-muted">Name it after the exact agent, server, or environment that will use it.</p>
                <label className="mt-6 block">
                  <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-muted">Credential name</span>
                  <input
                    className="mt-2 h-12 w-full rounded-xl border-2 border-ink bg-white px-4 text-sm outline-none shadow-[2px_2px_0_var(--color-shadow-soft)] focus:shadow-[3px_3px_0_var(--color-orange)]"
                    value={name}
                    maxLength={100}
                    onChange={event => setName(event.target.value)}
                    placeholder="Production agent"
                    onKeyDown={event => {
                      if (event.key === 'Enter') {
                        event.preventDefault()
                        void createKey()
                      }
                    }}
                  />
                </label>
                <Button className="mt-4 w-full" onClick={() => void createKey()} disabled={creating || !name.trim()}>
                  {creating ? <LoaderCircle className="animate-spin" /> : <KeyRound />}
                  {creating ? 'Creating secure key…' : 'Create API key'}
                </Button>
              </div>

              <div className="overflow-hidden rounded-2xl border-2 border-ink bg-white shadow-[5px_5px_0_var(--color-shadow-soft)]">
                <div className="flex items-center justify-between gap-4 border-b-2 border-ink bg-paper-2 px-6 py-5 sm:px-8">
                  <div><p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-orange-dark">Credentials</p><h3 className="mt-2 text-2xl font-bold">Organization keys</h3></div>
                  <Badge>{keys.length} total</Badge>
                </div>
                {loading ? (
                  <div className="space-y-3 p-6 sm:p-8">{[0, 1].map(item => <div key={item} className="h-20 animate-pulse rounded-xl bg-paper-2" />)}</div>
                ) : keys.length === 0 ? (
                  <div className="grid min-h-64 place-items-center p-8 text-center"><div><KeyRound className="mx-auto size-8 text-muted" /><h4 className="mt-4 text-lg font-bold">No API keys yet</h4><p className="mt-2 text-sm text-muted">Create one to connect your first agent.</p></div></div>
                ) : (
                  <div className="divide-y-2 divide-line">
                    {keys.map(key => (
                      <div className={`px-6 py-5 sm:px-8 ${key.revoked_at ? 'bg-paper-2 opacity-65' : ''}`} key={key.id}>
                        <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                          <span className="grid size-10 shrink-0 place-items-center rounded-lg border-2 border-ink bg-white shadow-[2px_2px_0_var(--color-shadow-strong)]"><KeyRound className="size-4" /></span>
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2"><strong className="text-sm">{key.name}</strong><Badge variant={key.revoked_at ? 'default' : 'teal'} className="px-2 py-0.5 text-[9px]">{key.revoked_at ? 'Revoked' : 'Active'}</Badge></div>
                            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[9px] uppercase tracking-wider text-muted">
                              <span>{key.prefix}</span>
                              <span className="flex items-center gap-1"><Clock3 className="size-3" /> Created {formatDate(key.created_at)}</span>
                              <span>Last used {key.last_used_at ? formatDate(key.last_used_at) : 'never'}</span>
                            </div>
                          </div>
                          {!key.revoked_at && (
                            confirmRevokeId === key.id ? (
                              <div className="flex gap-2">
                                <Button variant="ghost" size="sm" onClick={() => setConfirmRevokeId(null)}><X /> Cancel</Button>
                                <Button size="sm" onClick={() => void revokeKey(key.id)} disabled={revokingId === key.id}>
                                  {revokingId === key.id ? <LoaderCircle className="animate-spin" /> : <Trash2 />}{revokingId === key.id ? 'Revoking…' : 'Confirm revoke'}
                                </Button>
                              </div>
                            ) : (
                              <Button variant="outline" size="sm" onClick={() => setConfirmRevokeId(key.id)}><Trash2 /> Revoke</Button>
                            )
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>

            <section className="overflow-hidden rounded-2xl border-2 border-ink bg-white shadow-[7px_7px_0_var(--color-shadow-strong)]">
              <div className="grid border-b-2 border-ink bg-paper-2 sm:grid-cols-[auto_1fr]">
                <div className="flex border-b-2 border-ink sm:border-b-0 sm:border-r-2">
                  {(['mcp', 'sdk', 'rest'] as IntegrationTab[]).map(tab => (
                    <button
                      type="button"
                      key={tab}
                      onClick={() => setActiveTab(tab)}
                      className={`min-w-20 border-r-2 border-ink px-4 py-4 font-mono text-[10px] font-bold uppercase tracking-wider transition last:border-r-0 ${activeTab === tab ? 'bg-ink text-white' : 'bg-white hover:bg-warning-soft'}`}
                    >
                      {tab}
                    </button>
                  ))}
                </div>
                <div className="flex items-center px-5 py-3 font-mono text-[9px] font-bold uppercase tracking-wider text-muted">Agent integration recipes</div>
              </div>
              <div className="grid lg:grid-cols-[0.72fr_1.28fr]">
                <div className="border-b-2 border-ink p-6 lg:border-b-0 lg:border-r-2 sm:p-8">
                  <span className="grid size-11 place-items-center rounded-xl border-2 border-ink bg-warning-soft shadow-[3px_3px_0_var(--color-shadow-strong)]">{activeTab === 'mcp' ? <Network className="size-5" /> : activeTab === 'sdk' ? <Braces className="size-5" /> : <TerminalSquare className="size-5" />}</span>
                  <h3 className="mt-5 text-2xl font-bold">{example.title}</h3>
                  <p className="mt-3 text-sm leading-6 text-muted">{example.description}</p>
                  <Button variant="outline" className="mt-6" onClick={() => void copy(example.code, `${activeTab.toUpperCase()} configuration`)}><Clipboard /> Copy example</Button>
                </div>
                <div className="min-w-0 bg-code-bg p-5 text-code-text sm:p-8">
                  <div className="mb-4 flex items-center justify-between gap-3"><div className="flex gap-1.5"><span className="size-2.5 rounded-full bg-danger" /><span className="size-2.5 rounded-full bg-warning" /><span className="size-2.5 rounded-full bg-teal" /></div><span className="font-mono text-[9px] uppercase tracking-wider text-code-muted">{activeTab === 'mcp' ? 'config.toml' : activeTab === 'sdk' ? 'context.ts' : 'terminal'}</span></div>
                  <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-xs leading-6"><code>{example.code}</code></pre>
                </div>
              </div>
            </section>
          </>
        )}
      </div>
    </AppLayout>
  )
}

function ApiMetric({ icon: Icon, label, value }: { icon: typeof KeyRound; label: string; value: string | number }) {
  return (
    <div className="rounded-xl border-2 border-ink bg-white p-4 shadow-[2px_2px_0_var(--color-shadow-soft)]">
      <Icon className="size-4 text-orange-dark" />
      <strong className="mt-3 block text-2xl">{value}</strong>
      <span className="font-mono text-[9px] font-bold uppercase tracking-wider text-muted">{label}</span>
    </div>
  )
}

function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'unknown' : date.toLocaleDateString(undefined, { dateStyle: 'medium' })
}
