'use client'

import { useCallback, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Bot, BrainCircuit, Check, CloudCog, Cpu, Fingerprint, KeyRound,
  LoaderCircle, LockKeyhole, RefreshCcw, Sparkles, TestTube2, Workflow,
} from 'lucide-react'
import AppLayout from '../../../components/AppLayout'
import SettingsNotice, { type SettingsMessage } from '../../../components/SettingsNotice'
import StudioTopbar from '../../../components/StudioTopbar'
import { useAuth } from '../../../components/AuthProvider'
import { Badge } from '../../../components/ui/badge'
import { Button } from '../../../components/ui/button'
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
  const { user } = useAuth()
  const [status, setStatus] = useState<AIStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [testing, setTesting] = useState(false)
  const [message, setMessage] = useState<SettingsMessage | null>(null)

  const canManage = user?.role === 'owner' || user?.role === 'admin'

  const load = useCallback(async () => {
    setLoading(true)
    setMessage(null)
    try {
      const response = await apiFetch(`${API_URL}/settings/ai?org_id=${encodeURIComponent(getActiveOrgId())}`)
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not load AI status')
      setStatus(payload)
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Could not load AI status' })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const testConnection = async () => {
    if (!canManage) return
    setTesting(true)
    setMessage(null)
    try {
      const response = await apiFetch(`${API_URL}/settings/ai/test?org_id=${encodeURIComponent(getActiveOrgId())}`, { method: 'POST' })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Connection test failed')
      setMessage({ type: 'success', text: payload.message || 'Generation and embeddings are ready.' })
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Connection test failed' })
    } finally {
      setTesting(false)
    }
  }

  const ready = Boolean(status?.configured)

  return (
    <AppLayout>
      <StudioTopbar
        section="Settings"
        title="AI Provider"
        description="One managed AI layer for generation and embeddings"
        icon={Sparkles}
        actions={(
          <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading || testing}>
            <RefreshCcw className={loading ? 'animate-spin' : ''} />
            <span className="hidden sm:inline">Refresh</span>
          </Button>
        )}
      />

      <div className="page-body max-w-6xl space-y-6">
        {message && <SettingsNotice message={message} />}

        <section className="grid overflow-hidden rounded-2xl border-2 border-ink bg-white shadow-[7px_7px_0_#201c15] lg:grid-cols-[0.9fr_1.1fr]">
          <div className="relative overflow-hidden border-b-2 border-ink bg-orange p-7 text-white lg:border-b-0 lg:border-r-2 sm:p-9">
            <div className="absolute -bottom-24 -right-20 size-64 rounded-full border-[38px] border-white/15" />
            <div className="relative">
              <Badge variant="dark"><CloudCog className="size-3.5" /> Komponist managed</Badge>
              <h2 className="mt-7 max-w-lg text-4xl font-bold leading-tight tracking-tight sm:text-5xl">One provider. Every workflow.</h2>
              <p className="mt-5 max-w-lg leading-7 text-white/80">Extraction, chat, semantic retrieval, and agents share the same protected platform configuration. Workspace members never handle the provider secret.</p>
            </div>
          </div>

          <div className="p-6 sm:p-9">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-orange-dark">Platform status</p>
                <h3 className="mt-2 text-3xl font-bold">{loading ? 'Checking provider…' : ready ? 'Ready for context work' : 'Configuration required'}</h3>
              </div>
              <Badge variant={ready ? 'teal' : 'orange'}>{loading ? <LoaderCircle className="animate-spin" /> : ready ? <Check /> : <KeyRound />}{loading ? 'Checking' : ready ? 'Connected' : 'Missing key'}</Badge>
            </div>

            <div className="mt-7 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <ProviderMetric icon={Bot} label="Provider" value={loading ? '—' : status?.provider || '—'} />
              <ProviderMetric icon={Workflow} label="Mode" value={loading ? '—' : status?.mode || '—'} />
              <ProviderMetric icon={BrainCircuit} label="Generation" value={loading ? '—' : compactModel(status?.model)} />
              <ProviderMetric icon={Fingerprint} label="Embeddings" value={loading ? '—' : compactModel(status?.embedding_model)} />
            </div>

            <div className="mt-7 flex flex-wrap items-center gap-3">
              {canManage ? (
                <Button onClick={() => void testConnection()} disabled={loading || testing || !ready}>
                  {testing ? <LoaderCircle className="animate-spin" /> : <TestTube2 />}
                  {testing ? 'Testing both models…' : 'Test generation & embeddings'}
                </Button>
              ) : (
                <div className="flex items-center gap-2 text-xs font-semibold text-muted"><LockKeyhole className="size-4" /> Owners and admins can run live tests.</div>
              )}
            </div>
          </div>
        </section>

        <section className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="rounded-2xl border-2 border-ink bg-white shadow-[5px_5px_0_#d9cfc0]">
            <div className="border-b-2 border-ink bg-paper-2 px-6 py-5 sm:px-8">
              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-orange-dark">Runtime map</p>
              <h3 className="mt-2 text-2xl font-bold">How Komponist uses AI</h3>
            </div>
            <div className="grid divide-y-2 divide-line sm:grid-cols-2 sm:divide-x-2 sm:divide-y-0">
              <RuntimeCard
                icon={Cpu}
                title="Generation model"
                model={status?.model || 'Not available'}
                description="Extracts structured company facts and writes grounded answers from retrieved evidence."
                tasks={['Document extraction', 'Grounded chat', 'Constraint reasoning']}
              />
              <RuntimeCard
                icon={Fingerprint}
                title="Embedding model"
                model={status?.embedding_model || 'Not available'}
                description="Maps queries and reviewed facts into the same semantic space for reliable retrieval."
                tasks={['Context search', 'Duplicate detection', 'Related fact discovery']}
              />
            </div>
          </div>

          <div className="space-y-6">
            <div className="rounded-2xl border-2 border-ink bg-ink p-6 text-white shadow-[5px_5px_0_#e8641b] sm:p-8">
              <span className="grid size-11 place-items-center rounded-xl border-2 border-white/70 bg-orange shadow-[3px_3px_0_#fff]"><KeyRound className="size-5" /></span>
              <h3 className="mt-5 text-2xl font-bold">Secrets stay server-side.</h3>
              <p className="mt-3 text-sm leading-6 text-white/65">Customers use Komponist without supplying an AI key. Provider credentials are read only by the backend deployment.</p>
              <div className="mt-6 space-y-2 font-mono text-[10px] uppercase tracking-wider text-white/70">
                <div className="flex items-center justify-between border-b border-white/15 pb-2"><span>Managed by</span><strong className="text-white">{status?.managed_by || 'Komponist'}</strong></div>
                <div className="flex items-center justify-between border-b border-white/15 pb-2"><span>Client exposure</span><strong className="text-teal-light">None</strong></div>
              </div>
            </div>

            <div className="rounded-2xl border-2 border-ink bg-warning-soft p-6">
              <h3 className="text-xl font-bold">Deployment configuration</h3>
              <p className="mt-3 text-sm leading-6 text-muted">Set <code className="rounded bg-white px-1.5 py-0.5 text-ink">OPENAI_API_KEY</code> and <code className="rounded bg-white px-1.5 py-0.5 text-ink">KOMPONIST_AI_MODE=live</code> on the API and MCP services. Restart them after changing secrets.</p>
            </div>
          </div>
        </section>
      </div>
    </AppLayout>
  )
}

function compactModel(model?: string) {
  if (!model) return '—'
  return model.length > 20 ? `${model.slice(0, 17)}…` : model
}

function ProviderMetric({ icon: Icon, label, value }: { icon: typeof Bot; label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-xl border-2 border-ink bg-paper-2 p-3 shadow-[2px_2px_0_#d9cfc0]">
      <Icon className="size-4 text-orange-dark" />
      <strong className="mt-3 block truncate text-sm capitalize" title={value}>{value}</strong>
      <span className="font-mono text-[9px] font-bold uppercase tracking-wider text-muted">{label}</span>
    </div>
  )
}

function RuntimeCard({ icon: Icon, title, model, description, tasks }: {
  icon: typeof Cpu
  title: string
  model: string
  description: string
  tasks: string[]
}) {
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="p-6 sm:p-8">
      <span className="grid size-11 place-items-center rounded-xl border-2 border-ink bg-white shadow-[3px_3px_0_#201c15]"><Icon className="size-5" /></span>
      <h4 className="mt-5 text-xl font-bold">{title}</h4>
      <Badge variant="orange" className="mt-3 normal-case tracking-normal">{model}</Badge>
      <p className="mt-4 text-sm leading-6 text-muted">{description}</p>
      <ul className="mt-5 space-y-2 text-xs font-semibold">
        {tasks.map(task => <li key={task} className="flex items-center gap-2"><Check className="size-3.5 text-teal" />{task}</li>)}
      </ul>
    </motion.div>
  )
}
