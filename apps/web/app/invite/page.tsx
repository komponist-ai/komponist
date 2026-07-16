'use client'

import { Suspense, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import AppLayout from '../../components/AppLayout'
import { useAuth } from '../../components/AuthProvider'
import { API_URL, apiFetch } from '../../lib/api'

function InviteContent() {
  const searchParams = useSearchParams()
  const { refresh } = useAuth()
  const token = searchParams.get('token')
  const [joining, setJoining] = useState(false)
  const [joined, setJoined] = useState(false)
  const [error, setError] = useState('')

  const acceptInvitation = async () => {
    if (!token) return
    setJoining(true)
    setError('')
    try {
      const response = await apiFetch(`${API_URL}/auth/invitations/accept`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not accept this invitation')
      await refresh()
      setJoined(true)
    } catch (acceptError) {
      setError(acceptError instanceof Error ? acceptError.message : 'Could not accept this invitation')
    } finally {
      setJoining(false)
    }
  }

  return (
    <AppLayout>
      <div className="page-body invite-page">
        <div className="card invite-card">
          <div className="invite-symbol">◎</div>
          <p className="text-caption text-muted invite-eyebrow">ORGANIZATION INVITATION</p>
          <h1 className="text-h1 mb-3">{joined ? 'You joined the workspace' : 'Join your team in Komponist'}</h1>
          <p className="text-small text-muted invite-description">
            {joined
              ? 'Your active workspace has been switched. You can now work with your team’s shared company brain.'
              : 'Accept the invitation using the same Google email address it was sent to.'}
          </p>
          {error && <div className="team-alert" role="alert">{error}</div>}
          {!token && !joined && <div className="team-alert" role="alert">This invitation link is incomplete.</div>}
          {joined ? (
            <Link href="/" className="btn btn-primary">Open workspace</Link>
          ) : (
            <button className="btn btn-primary" onClick={acceptInvitation} disabled={!token || joining}>
              {joining ? 'Joining…' : 'Accept invitation'}
            </button>
          )}
        </div>
      </div>
    </AppLayout>
  )
}

export default function InvitePage() {
  return <Suspense fallback={null}><InviteContent /></Suspense>
}
