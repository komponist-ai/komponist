'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import {
  ArrowRight, CircleCheck, Gauge, Info, LoaderCircle, LockKeyhole,
  Save, Settings, ShieldCheck, Sparkles, UsersRound,
} from 'lucide-react'
import AppLayout from '../../components/AppLayout'
import SettingsNotice, { type SettingsMessage } from '../../components/SettingsNotice'
import StudioTopbar from '../../components/StudioTopbar'
import { useAuth } from '../../components/AuthProvider'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { API_URL, apiFetch, getActiveOrgId } from '../../lib/api'

interface OrgSettings {
  auto_confirm: boolean
  parallel_batch_size: number
}

const defaults: OrgSettings = { auto_confirm: false, parallel_batch_size: 5 }

export default function SettingsPage() {
  const { user } = useAuth()
  const [settings, setSettings] = useState<OrgSettings>(defaults)
  const [savedSettings, setSavedSettings] = useState<OrgSettings>(defaults)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<SettingsMessage | null>(null)

  const canManage = user?.role === 'owner' || user?.role === 'admin'
  const dirty = useMemo(
    () => settings.auto_confirm !== savedSettings.auto_confirm || settings.parallel_batch_size !== savedSettings.parallel_batch_size,
    [savedSettings, settings],
  )

  const fetchSettings = useCallback(async () => {
    setLoading(true)
    setMessage(null)
    try {
      const response = await apiFetch(`${API_URL}/settings?org_id=${encodeURIComponent(getActiveOrgId())}`)
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not load workspace settings')
      const next = {
        auto_confirm: Boolean(payload.auto_confirm),
        parallel_batch_size: Number(payload.parallel_batch_size) || defaults.parallel_batch_size,
      }
      setSettings(next)
      setSavedSettings(next)
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Could not load workspace settings' })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchSettings()
  }, [fetchSettings])

  const saveSettings = async () => {
    if (!canManage || !dirty) return
    setSaving(true)
    setMessage(null)
    try {
      const response = await apiFetch(`${API_URL}/settings?org_id=${encodeURIComponent(getActiveOrgId())}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not save workspace settings')
      const next = {
        auto_confirm: Boolean(payload.auto_confirm),
        parallel_batch_size: Number(payload.parallel_batch_size),
      }
      setSettings(next)
      setSavedSettings(next)
      setMessage({ type: 'success', text: 'Workspace behavior updated.' })
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Could not save workspace settings' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <AppLayout>
      <StudioTopbar
        section="Settings"
        title="General"
        description="Control review behavior and ingestion throughput"
        icon={Settings}
        actions={canManage ? (
          <Button size="sm" onClick={() => void saveSettings()} disabled={loading || saving || !dirty}>
            {saving ? <LoaderCircle className="animate-spin" /> : <Save />}
            <span className="hidden sm:inline">{saving ? 'Saving…' : dirty ? 'Save changes' : 'Saved'}</span>
          </Button>
        ) : <Badge>Your role: {user?.role}</Badge>}
      />

      <div className="page-body max-w-6xl space-y-6">
        {message && <SettingsNotice message={message} />}

        <section className="grid overflow-hidden rounded-2xl border-2 border-ink bg-white shadow-[7px_7px_0_#201c15] lg:grid-cols-[0.88fr_1.12fr]">
          <div className="relative overflow-hidden border-b-2 border-ink bg-ink p-7 text-white lg:border-b-0 lg:border-r-2 sm:p-9">
            <div className="absolute -right-14 -top-16 size-48 rounded-full border-[32px] border-orange/80" />
            <div className="relative">
              <Badge variant="dark" className="border-white/25"><ShieldCheck className="size-3.5" /> Governance defaults</Badge>
              <h2 className="mt-7 max-w-lg text-4xl font-bold leading-tight tracking-tight sm:text-5xl">Decide how knowledge earns trust.</h2>
              <p className="mt-5 max-w-lg leading-7 text-white/65">Keep humans in the loop by default, then tune ingestion speed to the capacity of this workspace.</p>
            </div>
          </div>

          <div className="grid content-center gap-4 p-6 sm:p-9">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-orange-dark">Current policy</p>
                <h3 className="mt-2 text-2xl font-bold">{settings.auto_confirm ? 'Automatic publishing' : 'Review-first workflow'}</h3>
              </div>
              <Badge variant={settings.auto_confirm ? 'orange' : 'teal'}>
                {loading ? 'Loading' : settings.auto_confirm ? 'Automation on' : 'Human review on'}
              </Badge>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <StatusTile icon={CircleCheck} label="New extractions" value={settings.auto_confirm ? 'Published directly' : 'Sent to review'} />
              <StatusTile icon={Gauge} label="Sync concurrency" value={`${settings.parallel_batch_size} pages at once`} />
            </div>
            {!canManage && (
              <div className="flex gap-3 rounded-xl border-2 border-ink bg-paper-2 p-4 text-sm">
                <LockKeyhole className="mt-0.5 size-5 shrink-0 text-orange-dark" />
                <p><strong>Read-only settings.</strong><span className="mt-1 block text-xs leading-5 text-muted">Only workspace owners and admins can change ingestion behavior.</span></p>
              </div>
            )}
          </div>
        </section>

        <section className="grid gap-6 lg:grid-cols-[1.25fr_0.75fr]">
          <div className="overflow-hidden rounded-2xl border-2 border-ink bg-white shadow-[5px_5px_0_#d9cfc0]">
            <div className="border-b-2 border-ink bg-paper-2 px-6 py-5 sm:px-8">
              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-orange-dark">Extraction & sync</p>
              <h3 className="mt-2 text-2xl font-bold">Workspace behavior</h3>
            </div>

            {loading ? (
              <div className="space-y-4 p-6 sm:p-8">
                <div className="h-24 animate-pulse rounded-xl bg-paper-2" />
                <div className="h-32 animate-pulse rounded-xl bg-paper-2" />
              </div>
            ) : (
              <div className="divide-y-2 divide-line px-6 sm:px-8">
                <SettingRow
                  icon={Sparkles}
                  title="Auto-publish extracted knowledge"
                  description="Skip the Review Queue and immediately make newly extracted entities available to search, chat, and agents."
                  aside={(
                    <button
                      type="button"
                      role="switch"
                      aria-checked={settings.auto_confirm}
                      aria-label="Auto-publish extracted knowledge"
                      onClick={() => setSettings(current => ({ ...current, auto_confirm: !current.auto_confirm }))}
                      disabled={!canManage}
                      className={`relative h-8 w-14 shrink-0 rounded-full border-2 border-ink transition disabled:cursor-not-allowed disabled:opacity-45 ${settings.auto_confirm ? 'bg-orange' : 'bg-paper-3'}`}
                    >
                      <span className={`absolute top-1 size-5 rounded-full border-2 border-ink bg-white transition-transform ${settings.auto_confirm ? 'translate-x-6' : 'translate-x-1'}`} />
                    </button>
                  )}
                />
                <SettingRow
                  icon={Gauge}
                  title="Parallel processing batch size"
                  description="Higher values finish large syncs faster but create more simultaneous AI and database work."
                  aside={<Badge variant="orange">{settings.parallel_batch_size} pages</Badge>}
                >
                  <div className="mt-5 grid grid-cols-[1fr_auto] items-center gap-4">
                    <input
                      aria-label="Parallel processing batch size"
                      type="range"
                      min="1"
                      max="10"
                      value={settings.parallel_batch_size}
                      onChange={(event) => setSettings(current => ({ ...current, parallel_batch_size: Number(event.target.value) }))}
                      className="h-2 w-full cursor-pointer accent-orange disabled:cursor-not-allowed disabled:opacity-45"
                      disabled={!canManage}
                    />
                    <span className="w-8 text-right font-mono text-sm font-bold">{settings.parallel_batch_size}</span>
                  </div>
                  <div className="mt-2 flex justify-between font-mono text-[9px] font-bold uppercase tracking-wider text-faint"><span>Gentle</span><span>Fast</span></div>
                </SettingRow>
              </div>
            )}
          </div>

          <div className="space-y-6">
            <div className="rounded-2xl border-2 border-ink bg-warning-soft p-6 shadow-[5px_5px_0_#d9cfc0]">
              <span className="grid size-11 place-items-center rounded-xl border-2 border-ink bg-white shadow-[3px_3px_0_#201c15]"><Info className="size-5 text-orange-dark" /></span>
              <h3 className="mt-5 text-xl font-bold">Why review-first?</h3>
              <p className="mt-3 text-sm leading-6 text-muted">Confirmed context is what chat, MCP, and the SDK can trust. Manual review prevents a weak extraction from silently becoming company truth.</p>
            </div>

            <div className="rounded-2xl border-2 border-ink bg-white p-6 shadow-[5px_5px_0_#d9cfc0]">
              <div className="flex items-start gap-3">
                <span className="grid size-10 shrink-0 place-items-center rounded-lg border-2 border-ink bg-success-soft"><UsersRound className="size-5 text-teal" /></span>
                <div><p className="font-mono text-[9px] font-bold uppercase tracking-wider text-muted">Organization</p><h3 className="mt-1 text-xl font-bold">{user?.organization.name}</h3></div>
              </div>
              <p className="mt-4 text-sm leading-6 text-muted">You are a <strong className="text-ink">{user?.role}</strong> in this workspace. Membership and invites are managed separately.</p>
              <Button asChild variant="outline" className="mt-5 w-full">
                <Link href="/settings/team">Manage team <ArrowRight /></Link>
              </Button>
            </div>
          </div>
        </section>
      </div>
    </AppLayout>
  )
}

function StatusTile({ icon: Icon, label, value }: { icon: typeof Gauge; label: string; value: string }) {
  return (
    <div className="rounded-xl border-2 border-ink bg-paper-2 p-4 shadow-[2px_2px_0_#d9cfc0]">
      <Icon className="size-4 text-orange-dark" />
      <span className="mt-3 block font-mono text-[9px] font-bold uppercase tracking-wider text-muted">{label}</span>
      <strong className="mt-1 block text-sm">{value}</strong>
    </div>
  )
}

function SettingRow({ icon: Icon, title, description, aside, children }: {
  icon: typeof Gauge
  title: string
  description: string
  aside: React.ReactNode
  children?: React.ReactNode
}) {
  return (
    <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} className="py-6">
      <div className="flex items-start gap-4">
        <span className="grid size-10 shrink-0 place-items-center rounded-lg border-2 border-ink bg-white shadow-[2px_2px_0_#201c15]"><Icon className="size-5" /></span>
        <div className="min-w-0 flex-1"><strong className="block text-sm">{title}</strong><p className="mt-1 max-w-2xl text-xs leading-5 text-muted">{description}</p>{children}</div>
        {aside}
      </div>
    </motion.div>
  )
}
