'use client'

import { FormEvent, useCallback, useEffect, useState } from 'react'
import { UsersRound } from 'lucide-react'
import AppLayout from '../../../components/AppLayout'
import { useAuth } from '../../../components/AuthProvider'
import StudioTopbar from '../../../components/StudioTopbar'
import { API_URL, apiFetch } from '../../../lib/api'

interface Member {
  id: string
  user_id: string
  name: string
  email: string
  role: 'owner' | 'admin' | 'member' | 'viewer'
}

export default function TeamSettingsPage() {
  const { user } = useAuth()
  const [members, setMembers] = useState<Member[]>([])
  const [loading, setLoading] = useState(true)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<'admin' | 'member' | 'viewer'>('member')
  const [submitting, setSubmitting] = useState(false)
  const [inviteUrl, setInviteUrl] = useState('')
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState('')

  const loadMembers = useCallback(async () => {
    if (!user) return
    setLoading(true)
    setError('')
    try {
      const response = await apiFetch(`${API_URL}/auth/organizations/${user.org_id}/members`)
      if (!response.ok) throw new Error('Could not load organization members')
      const payload = await response.json()
      setMembers(payload.members || [])
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load members')
    } finally {
      setLoading(false)
    }
  }, [user])

  useEffect(() => {
    loadMembers()
  }, [loadMembers])

  const createInvitation = async (event: FormEvent) => {
    event.preventDefault()
    if (!user) return
    setSubmitting(true)
    setInviteUrl('')
    setError('')
    try {
      const response = await apiFetch(`${API_URL}/auth/organizations/${user.org_id}/invitations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, role }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not create invitation')
      setInviteUrl(payload.invite_url)
      setEmail('')
      setCopied(false)
    } catch (inviteError) {
      setError(inviteError instanceof Error ? inviteError.message : 'Could not create invitation')
    } finally {
      setSubmitting(false)
    }
  }

  const copyInvite = async () => {
    await navigator.clipboard.writeText(inviteUrl)
    setCopied(true)
  }

  const canInvite = user?.role === 'owner' || user?.role === 'admin'

  return (
    <AppLayout>
      <StudioTopbar
        section="Settings"
        title="Team & roles"
        description={`Manage access to ${user?.organization.name ?? 'this workspace'}`}
        icon={UsersRound}
        actions={<span className="badge badge-orange hidden sm:inline-flex">Your role: {user?.role}</span>}
      />

      <div className="page-body team-page">
        {error && <div className="team-alert" role="alert">{error}</div>}

        <section className="card team-card">
          <div className="team-section-heading">
            <div>
              <h2 className="text-h2">Members</h2>
              <p className="text-caption text-muted">People with access to this organization&apos;s brain.</p>
            </div>
            <span className="text-caption text-muted">{members.length} total</span>
          </div>

          {loading ? (
            <p className="text-small text-muted team-loading">Loading members…</p>
          ) : members.length === 0 ? (
            <p className="text-small text-muted team-loading">No members found.</p>
          ) : (
            <div className="member-list">
              {members.map((member) => (
                <div className="member-row" key={member.id}>
                  <div className="member-avatar" aria-hidden="true">
                    {member.name.slice(0, 1).toUpperCase()}
                  </div>
                  <div className="member-copy">
                    <div className="text-small font-medium">
                      {member.name}{member.user_id === user?.id ? ' (you)' : ''}
                    </div>
                    <div className="text-caption text-muted">{member.email}</div>
                  </div>
                  <span className="badge">{member.role}</span>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="card team-card">
          <h2 className="text-h2 mb-1">Invite a teammate</h2>
          {canInvite ? (
            <>
              <p className="text-caption text-muted mb-4">
                Create a single-use link for the teammate&apos;s Komponist account. Links expire after seven days.
              </p>
              <form className="invite-form" onSubmit={createInvitation}>
                <label className="field-label" htmlFor="invite-email">Email address</label>
                <input
                  id="invite-email"
                  className="input"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="teammate@company.com"
                  required
                />
                <label className="field-label" htmlFor="invite-role">Role</label>
                <select
                  id="invite-role"
                  className="input"
                  value={role}
                  onChange={(event) => setRole(event.target.value as typeof role)}
                >
                  {user?.role === 'owner' && <option value="admin">Admin</option>}
                  <option value="member">Member</option>
                  <option value="viewer">Viewer</option>
                </select>
                <button className="btn btn-primary invite-submit" disabled={submitting}>
                  {submitting ? 'Creating…' : 'Create invite link'}
                </button>
              </form>

              {inviteUrl && (
                <div className="invite-result">
                  <p className="text-small font-medium mb-2">Invite link ready</p>
                  <div className="invite-link-row">
                    <input className="input" readOnly value={inviteUrl} aria-label="Invite link" />
                    <button className="btn btn-secondary" type="button" onClick={copyInvite}>
                      {copied ? 'Copied' : 'Copy'}
                    </button>
                  </div>
                  <p className="text-caption text-muted mt-2">Share this link only with {inviteUrl ? 'the invited teammate' : ''}.</p>
                </div>
              )}
            </>
          ) : (
            <p className="text-small text-muted mt-2">Only organization owners and admins can create invitations.</p>
          )}
        </section>
      </div>
    </AppLayout>
  )
}
