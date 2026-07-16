'use client'

import Image from 'next/image'
import { useAuth } from './AuthProvider'

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading, login } = useAuth()

  if (loading) {
    return (
      <main className="auth-shell" aria-live="polite">
        <div className="auth-card auth-card-compact">
          <div className="auth-loader" />
          <p className="text-small text-muted">Loading your workspace…</p>
        </div>
      </main>
    )
  }

  if (!user) {
    return (
      <main className="auth-shell">
        <section className="auth-card">
          <div className="auth-brand">
            <Image src="/komponist-logo.png" alt="" width={44} height={44} priority unoptimized />
            <span>Komponist</span>
          </div>
          <p className="eyebrow">Your company brain</p>
          <h1 className="auth-title">Context your whole team can trust.</h1>
          <p className="auth-copy">
            Sign in to open your governed company context, sources, and agent workflows.
          </p>
          <button className="btn btn-primary btn-lg auth-submit" onClick={login}>
            <span className="google-mark">G</span>
            Continue with Google
          </button>
          <p className="text-caption text-muted auth-note">
            New accounts receive a personal workspace and can join customer organizations by invitation.
          </p>
        </section>
      </main>
    )
  }

  return <>{children}</>
}
