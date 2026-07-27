'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Archive, Braces, Check, Database, Download, FileCheck2, FileText,
  GitBranch, LoaderCircle, RefreshCcw, ShieldCheck,
} from 'lucide-react'
import AppLayout from '../../../components/AppLayout'
import StudioTopbar from '../../../components/StudioTopbar'
import { useAuth } from '../../../components/AuthProvider'
import { Badge } from '../../../components/ui/badge'
import { Button } from '../../../components/ui/button'
import { API_URL, apiFetch, getActiveOrgId } from '../../../lib/api'

type ExportSummary = {
  entities: { total: number; confirmed: number; proposed: number; rejected: number }
  by_type: Record<string, number>
  relationships: number
  evidence: number
  connected_sources: number
}

const emptySummary: ExportSummary = {
  entities: { total: 0, confirmed: 0, proposed: 0, rejected: 0 },
  by_type: {},
  relationships: 0,
  evidence: 0,
  connected_sources: 0,
}

export default function ExportPage() {
  const { user } = useAuth()
  const [summary, setSummary] = useState<ExportSummary>(emptySummary)
  const [includeRejected, setIncludeRejected] = useState(false)
  const [includeEmbeddings, setIncludeEmbeddings] = useState(false)
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const canManage = user?.role === 'owner' || user?.role === 'admin'
  const exportedEntityCount = useMemo(
    () => summary.entities.total - (includeRejected ? 0 : summary.entities.rejected),
    [includeRejected, summary.entities.rejected, summary.entities.total],
  )

  const loadSummary = useCallback(async () => {
    if (!canManage) {
      setLoading(false)
      return
    }
    setLoading(true)
    setMessage(null)
    try {
      const orgId = getActiveOrgId()
      const response = await apiFetch(`${API_URL}/export/summary?org_id=${encodeURIComponent(orgId)}`)
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not load export summary')
      setSummary(payload)
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Could not load export summary' })
    } finally {
      setLoading(false)
    }
  }, [canManage])

  useEffect(() => {
    void loadSummary()
  }, [loadSummary])

  const downloadExport = async () => {
    if (!canManage) return
    setDownloading(true)
    setMessage(null)
    try {
      const orgId = getActiveOrgId()
      const params = new URLSearchParams({
        org_id: orgId,
        include_rejected: String(includeRejected),
        include_embeddings: String(includeEmbeddings),
      })
      const response = await apiFetch(`${API_URL}/export?${params.toString()}`)
      if (!response.ok) {
        const payload = await response.json().catch(() => null)
        throw new Error(payload?.detail || 'Could not create export')
      }
      const blob = await response.blob()
      const disposition = response.headers.get('Content-Disposition') || ''
      const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || `komponist-export-${orgId}.yaml`
      const objectUrl = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = objectUrl
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(objectUrl)
      setMessage({ type: 'success', text: `${filename} was downloaded to this device.` })
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Could not create export' })
    } finally {
      setDownloading(false)
    }
  }

  return (
    <AppLayout>
      <StudioTopbar
        section="Settings"
        title="Export"
        description="Download a portable snapshot of this organization"
        icon={Download}
        actions={canManage ? (
          <Button variant="outline" size="sm" onClick={() => void loadSummary()} disabled={loading}>
            <RefreshCcw className={loading ? 'animate-spin' : ''} />
            <span className="hidden sm:inline">Refresh</span>
          </Button>
        ) : undefined}
      />

      <div className="page-body max-w-6xl space-y-6">
        {message && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            className={`rounded-xl border-2 px-4 py-3 text-sm font-semibold ${message.type === 'success' ? 'border-teal bg-success-soft text-teal-dark' : 'border-danger bg-danger-soft text-danger'}`}
            role="status"
          >
            {message.text}
          </motion.div>
        )}

        {!canManage ? (
          <div className="grid min-h-[420px] place-items-center rounded-2xl border-2 border-ink bg-white p-8 text-center shadow-[6px_6px_0_var(--color-shadow-soft)]">
            <div className="max-w-md">
              <span className="mx-auto grid size-14 place-items-center rounded-xl border-2 border-ink bg-warning-soft shadow-[3px_3px_0_var(--color-shadow-strong)]"><ShieldCheck className="size-6" /></span>
              <h2 className="mt-6 text-3xl font-bold tracking-tight">Admin access required</h2>
              <p className="mt-3 leading-7 text-muted">A workspace export can contain the organization&apos;s complete reviewed context. Only owners and admins can download it.</p>
            </div>
          </div>
        ) : (
          <>
            <section className="grid overflow-hidden rounded-2xl border-2 border-ink bg-white shadow-[7px_7px_0_var(--color-shadow-strong)] lg:grid-cols-[0.9fr_1.1fr]">
              <div className="relative overflow-hidden border-b-2 border-ink bg-ink p-7 text-white lg:border-b-0 lg:border-r-2 sm:p-9">
                <div className="absolute -right-16 -top-16 size-52 rounded-full border-[34px] border-orange/80" />
                <div className="relative">
                  <Badge variant="dark" className="border-white/25">Portable YAML · v1.0</Badge>
                  <h2 className="mt-7 max-w-lg text-4xl font-bold leading-tight tracking-tight sm:text-5xl">Your company context is yours.</h2>
                  <p className="mt-5 max-w-lg leading-7 text-white/65">Create a machine-readable snapshot of entities, citations, relationships, and work packs. The download does not modify Komponist or any connected source.</p>
                  <div className="mt-8 flex flex-wrap gap-3 font-mono text-[10px] font-bold uppercase tracking-wider text-white/70">
                    <span className="flex items-center gap-2"><Check className="size-4 text-teal-light" /> Organization scoped</span>
                    <span className="flex items-center gap-2"><Check className="size-4 text-teal-light" /> Human readable</span>
                    <span className="flex items-center gap-2"><Check className="size-4 text-teal-light" /> Import compatible</span>
                  </div>
                </div>
              </div>

              <div className="p-6 sm:p-9">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-orange-dark">Export preview</p>
                    <h3 className="mt-2 text-2xl font-bold">{user?.organization.name}</h3>
                  </div>
                  <Badge variant="teal"><ShieldCheck className="size-3.5" /> Owner-controlled</Badge>
                </div>

                <div className="mt-7 grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <Metric icon={Braces} label="Entities" value={loading ? '—' : exportedEntityCount} />
                  <Metric icon={GitBranch} label="Relations" value={loading ? '—' : summary.relationships} />
                  <Metric icon={FileCheck2} label="Evidence" value={loading ? '—' : summary.evidence} />
                  <Metric icon={Database} label="Sources" value={loading ? '—' : summary.connected_sources} />
                </div>

                <div className="mt-7 rounded-xl border-2 border-ink bg-paper-2 p-4">
                  <div className="flex items-center gap-3">
                    <span className="grid size-10 place-items-center rounded-lg border-2 border-ink bg-white shadow-[2px_2px_0_var(--color-shadow-strong)]"><FileText className="size-5" /></span>
                    <div className="min-w-0"><strong className="block text-sm">Komponist portable export</strong><span className="font-mono text-[10px] text-muted">.yaml · schema version 1.0</span></div>
                    <span className="ml-auto rounded-full bg-success-soft px-2 py-1 font-mono text-[9px] font-bold uppercase text-teal-dark">Recommended</span>
                  </div>
                </div>
              </div>
            </section>

            <section className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
              <div className="rounded-2xl border-2 border-ink bg-white p-6 shadow-[5px_5px_0_var(--color-shadow-soft)] sm:p-8">
                <div className="flex items-start gap-4">
                  <span className="grid size-11 shrink-0 place-items-center rounded-xl border-2 border-ink bg-orange text-white shadow-[3px_3px_0_var(--color-shadow-strong)]"><Archive className="size-5" /></span>
                  <div><h3 className="text-2xl font-bold">Configure snapshot</h3><p className="mt-1 text-sm leading-6 text-muted">The default export is compact and excludes rejected knowledge.</p></div>
                </div>

                <div className="mt-7 divide-y-2 divide-line border-y-2 border-line">
                  <ExportOption
                    title="Include rejected entities"
                    description={`${summary.entities.rejected} rejected ${summary.entities.rejected === 1 ? 'entity' : 'entities'} currently excluded.`}
                    checked={includeRejected}
                    onChange={setIncludeRejected}
                  />
                  <ExportOption
                    title="Include embedding vectors"
                    description="Useful for exact backups, but significantly increases file size. Usually unnecessary for migration."
                    checked={includeEmbeddings}
                    onChange={setIncludeEmbeddings}
                  />
                </div>

                <Button className="mt-7 w-full sm:w-auto" size="lg" onClick={() => void downloadExport()} disabled={downloading || loading}>
                  {downloading ? <LoaderCircle className="animate-spin" /> : <Download />}
                  {downloading ? 'Building export…' : 'Download YAML export'}
                </Button>
              </div>

              <div className="rounded-2xl border-2 border-ink bg-paper-2 p-6 sm:p-8">
                <h3 className="text-xl font-bold">Included data</h3>
                <ul className="mt-5 space-y-3 text-sm">
                  {[
                    `${exportedEntityCount} proposed, confirmed, and superseded entities`,
                    `${summary.evidence} evidence records and source references`,
                    `${summary.relationships} graph relationships`,
                    'Work packs and their entity links',
                  ].map(item => <li key={item} className="flex items-start gap-3"><Check className="mt-0.5 size-4 shrink-0 text-teal" /><span>{item}</span></li>)}
                </ul>
                <div className="mt-7 rounded-xl border-2 border-ink bg-white p-4">
                  <div className="flex gap-3"><ShieldCheck className="mt-0.5 size-5 shrink-0 text-orange-dark" /><div><strong className="text-sm">Secrets stay out</strong><p className="mt-1 text-xs leading-5 text-muted">Passwords, API keys, member accounts, OAuth tokens, and connector credentials are never included.</p></div></div>
                </div>
                {Object.keys(summary.by_type).length > 0 && (
                  <div className="mt-6 flex flex-wrap gap-2">
                    {Object.entries(summary.by_type).map(([type, count]) => <Badge key={type}>{type} · {count}</Badge>)}
                  </div>
                )}
              </div>
            </section>
          </>
        )}
      </div>
    </AppLayout>
  )
}

function Metric({ icon: Icon, label, value }: { icon: typeof Braces; label: string; value: string | number }) {
  return (
    <div className="rounded-xl border-2 border-ink bg-white p-3 shadow-[2px_2px_0_var(--color-shadow-soft)]">
      <Icon className="size-4 text-orange-dark" />
      <strong className="mt-3 block text-2xl">{value}</strong>
      <span className="font-mono text-[9px] font-bold uppercase tracking-wider text-muted">{label}</span>
    </div>
  )
}

function ExportOption({ title, description, checked, onChange }: { title: string; description: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-start gap-4 py-5">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="peer sr-only" />
      <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-md border-2 border-ink bg-white shadow-[2px_2px_0_var(--color-shadow-strong)] peer-checked:bg-orange peer-checked:text-white">
        {checked && <Check className="size-4" />}
      </span>
      <span><strong className="block text-sm">{title}</strong><span className="mt-1 block text-xs leading-5 text-muted">{description}</span></span>
    </label>
  )
}
