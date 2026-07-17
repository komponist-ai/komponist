'use client'

import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Check, Clipboard, Crown, Eye, LoaderCircle, LockKeyhole,
  MailPlus, RefreshCcw, UserRound, UsersRound,
} from 'lucide-react'
import AppLayout from '../../../components/AppLayout'
import SettingsNotice, { type SettingsMessage } from '../../../components/SettingsNotice'
import StudioTopbar from '../../../components/StudioTopbar'
import { useAuth } from '../../../components/AuthProvider'
import { Badge } from '../../../components/ui/badge'
import { Button } from '../../../components/ui/button'
import { API_URL, apiFetch } from '../../../lib/api'

interface Member {
  id: string
  user_id: string
  name: string
  email: string
  role: 'owner' | 'admin' | 'member' | 'viewer'
}

type InviteRole = 'admin' | 'member' | 'viewer'

export default function TeamSettingsPage() {
  const { user } = useAuth()
  const [members, setMembers] = useState<Member[]>([])
  const [loading, setLoading] = useState(true)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<InviteRole>('member')
  const [submitting, setSubmitting] = useState(false)
  const [inviteUrl, setInviteUrl] = useState('')
  const [copied, setCopied] = useState(false)
  const [message, setMessage] = useState<SettingsMessage | null>(null)

  const canInvite = user?.role === 'owner' || user?.role === 'admin'
  const isInviteEmailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())
  const roleCounts = useMemo(() => members.reduce<Record<string, number>>((counts, member) => {
    counts[member.role] = (counts[member.role] || 0) + 1
    return counts
  }, {}), [members])

  const loadMembers = useCallback(async () => {
    if (!user) return
    setLoading(true)
    setMessage(null)
    try {
      const response = await apiFetch(`${API_URL}/auth/organizations/${encodeURIComponent(user.org_id)}/members`)
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not load organization members')
      setMembers(payload.members || [])
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Could not load organization members' })
    } finally {
      setLoading(false)
    }
  }, [user])

  useEffect(() => {
    void loadMembers()
  }, [loadMembers])

  const createInvitation = async (event: FormEvent) => {
    event.preventDefault()
    const normalizedEmail = email.trim().toLowerCase()
    if (!user || !canInvite || !isInviteEmailValid) return
    setSubmitting(true)
    setInviteUrl('')
    setCopied(false)
    setMessage(null)
    try {
      const response = await apiFetch(`${API_URL}/auth/organizations/${encodeURIComponent(user.org_id)}/invitations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: normalizedEmail, role }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not create invitation')
      setInviteUrl(payload.invite_url)
      setEmail('')
      setMessage({ type: 'success', text: `Invite link created for ${normalizedEmail}.` })
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Could not create invitation' })
    } finally {
      setSubmitting(false)
    }
  }

  const copyInvite = async () => {
    try {
      await navigator.clipboard.writeText(inviteUrl)
      setCopied(true)
      setMessage({ type: 'success', text: 'Invite link copied to the clipboard.' })
    } catch {
      setMessage({ type: 'error', text: 'The browser could not copy the invite link. Select and copy it manually.' })
    }
  }

  return (
    <AppLayout>
      <StudioTopbar
        section="Settings"
        title="Team & roles"
        description={`Manage access to ${user?.organization.name ?? 'this workspace'}`}
        icon={UsersRound}
        actions={(
          <Button variant="outline" size="sm" onClick={() => void loadMembers()} disabled={loading}>
            <RefreshCcw className={loading ? 'animate-spin' : ''} />
            <span className="hidden sm:inline">Refresh</span>
          </Button>
        )}
      />

      <div className="page-body max-w-6xl space-y-6">
        {message && <SettingsNotice message={message} />}

        <section className="grid overflow-hidden rounded-2xl border-2 border-ink bg-white shadow-[7px_7px_0_#201c15] lg:grid-cols-[1.08fr_0.92fr]">
          <div className="border-b-2 border-ink p-6 lg:border-b-0 lg:border-r-2 sm:p-9">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <Badge variant="orange"><UsersRound className="size-3.5" /> Shared workspace</Badge>
                <h2 className="mt-6 max-w-xl text-4xl font-bold leading-tight tracking-tight sm:text-5xl">Right context. Right people.</h2>
                <p className="mt-5 max-w-xl leading-7 text-muted">Everyone in an organization shares one reviewed company brain. Roles decide who can change its configuration and membership.</p>
              </div>
            </div>
            <div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <TeamMetric label="Total" value={loading ? '—' : members.length} />
              <TeamMetric label="Owners" value={loading ? '—' : roleCounts.owner || 0} />
              <TeamMetric label="Admins" value={loading ? '—' : roleCounts.admin || 0} />
              <TeamMetric label="Members" value={loading ? '—' : (roleCounts.member || 0) + (roleCounts.viewer || 0)} />
            </div>
          </div>

          <div className="relative overflow-hidden bg-ink p-6 text-white sm:p-9">
            <div className="absolute -right-16 -top-16 size-52 rounded-full border-[34px] border-orange/75" />
            <div className="relative">
              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-teal-light">Access model</p>
              <h3 className="mt-3 text-2xl font-bold">Organization isolated by default.</h3>
              <div className="mt-7 space-y-4">
                <RoleSummary icon={Crown} role="Owner / admin" description="Configuration, integrations, keys, exports, and invitations." />
                <RoleSummary icon={UserRound} role="Member" description="Review, upload, sync, chat, and use confirmed context." />
                <RoleSummary icon={Eye} role="Viewer" description="Read confirmed knowledge without changing workspace state." />
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-6 lg:grid-cols-[1.18fr_0.82fr]">
          <div className="overflow-hidden rounded-2xl border-2 border-ink bg-white shadow-[5px_5px_0_#d9cfc0]">
            <div className="flex items-center justify-between gap-4 border-b-2 border-ink bg-paper-2 px-6 py-5 sm:px-8">
              <div><p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-orange-dark">Directory</p><h3 className="mt-2 text-2xl font-bold">Workspace members</h3></div>
              <Badge>{members.length} total</Badge>
            </div>

            {loading ? (
              <div className="space-y-3 p-6 sm:p-8">
                {[0, 1, 2].map(item => <div key={item} className="h-16 animate-pulse rounded-xl bg-paper-2" />)}
              </div>
            ) : members.length === 0 ? (
              <div className="grid min-h-64 place-items-center p-8 text-center"><div><UsersRound className="mx-auto size-8 text-muted" /><h4 className="mt-4 text-lg font-bold">No members found</h4><p className="mt-2 text-sm text-muted">Refresh the page or verify the active organization.</p></div></div>
            ) : (
              <div className="divide-y-2 divide-line">
                {members.map((member, index) => (
                  <motion.div
                    key={member.id}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: Math.min(index * 0.04, 0.2) }}
                    className="flex items-center gap-4 px-6 py-4 sm:px-8"
                  >
                    <div className="grid size-11 shrink-0 place-items-center rounded-xl border-2 border-ink bg-warning-soft font-display text-sm font-black shadow-[2px_2px_0_#201c15]" aria-hidden="true">
                      {(member.name || member.email).slice(0, 1).toUpperCase()}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-bold">{member.name || member.email}{member.user_id === user?.id ? <span className="ml-2 text-xs font-normal text-muted">You</span> : null}</div>
                      <div className="mt-1 truncate text-xs text-muted">{member.email}</div>
                    </div>
                    <Badge variant={member.role === 'owner' || member.role === 'admin' ? 'orange' : member.role === 'viewer' ? 'default' : 'teal'}>{member.role}</Badge>
                  </motion.div>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-2xl border-2 border-ink bg-white p-6 shadow-[5px_5px_0_#d9cfc0] sm:p-8">
            <span className="grid size-11 place-items-center rounded-xl border-2 border-ink bg-orange text-white shadow-[3px_3px_0_#201c15]"><MailPlus className="size-5" /></span>
            <h3 className="mt-5 text-2xl font-bold">Invite a teammate</h3>
            {canInvite ? (
              <>
                <p className="mt-2 text-sm leading-6 text-muted">Create a single-use link tied to their email. It expires after seven days.</p>
                <form className="mt-6 space-y-4" onSubmit={createInvitation}>
                  <label className="block">
                    <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-muted">Email address</span>
                    <input
                      className="mt-2 h-12 w-full rounded-xl border-2 border-ink bg-white px-4 text-sm outline-none shadow-[2px_2px_0_#d9cfc0] focus:shadow-[3px_3px_0_#e8641b]"
                      type="email"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      placeholder="teammate@company.com"
                      autoComplete="email"
                      required
                    />
                  </label>
                  <label className="block">
                    <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-muted">Role</span>
                    <select
                      className="mt-2 h-12 w-full rounded-xl border-2 border-ink bg-white px-4 text-sm font-semibold outline-none shadow-[2px_2px_0_#d9cfc0] focus:shadow-[3px_3px_0_#e8641b]"
                      value={role}
                      onChange={(event) => setRole(event.target.value as InviteRole)}
                    >
                      {user?.role === 'owner' && <option value="admin">Admin</option>}
                      <option value="member">Member</option>
                      <option value="viewer">Viewer</option>
                    </select>
                  </label>
                  <Button className="w-full" disabled={submitting || !isInviteEmailValid}>
                    {submitting ? <LoaderCircle className="animate-spin" /> : <MailPlus />}
                    {submitting ? 'Creating invite…' : 'Create invite link'}
                  </Button>
                </form>

                {inviteUrl && (
                  <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="mt-6 rounded-xl border-2 border-teal bg-success-soft p-4">
                    <div className="flex items-center gap-2 text-sm font-bold text-teal"><Check className="size-4" /> Link ready</div>
                    <input className="mt-3 w-full rounded-lg border-2 border-ink bg-white px-3 py-2 font-mono text-xs" readOnly value={inviteUrl} aria-label="Invite link" />
                    <Button variant="outline" className="mt-3 w-full" type="button" onClick={() => void copyInvite()}>
                      {copied ? <Check /> : <Clipboard />}{copied ? 'Copied' : 'Copy invite link'}
                    </Button>
                    <p className="mt-3 text-xs leading-5 text-muted">Email delivery is not connected yet. Send this link directly to the invited person.</p>
                  </motion.div>
                )}
              </>
            ) : (
              <div className="mt-6 rounded-xl border-2 border-ink bg-paper-2 p-4">
                <LockKeyhole className="size-5 text-orange-dark" />
                <strong className="mt-3 block text-sm">Admin access required</strong>
                <p className="mt-1 text-xs leading-5 text-muted">Only owners and admins can create organization invitations.</p>
              </div>
            )}
          </div>
        </section>
      </div>
    </AppLayout>
  )
}

function TeamMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border-2 border-ink bg-paper-2 p-3 shadow-[2px_2px_0_#d9cfc0]">
      <strong className="block text-2xl">{value}</strong>
      <span className="font-mono text-[9px] font-bold uppercase tracking-wider text-muted">{label}</span>
    </div>
  )
}

function RoleSummary({ icon: Icon, role, description }: { icon: typeof Crown; role: string; description: string }) {
  return (
    <div className="flex gap-3 border-b border-white/15 pb-4 last:border-0 last:pb-0">
      <span className="grid size-9 shrink-0 place-items-center rounded-lg border border-white/25 bg-white/10"><Icon className="size-4 text-teal-light" /></span>
      <div><strong className="block text-sm">{role}</strong><p className="mt-1 text-xs leading-5 text-white/55">{description}</p></div>
    </div>
  )
}
