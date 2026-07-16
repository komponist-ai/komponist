'use client'

import Image from 'next/image'
import { FormEvent, useState } from 'react'
import { useAuth } from './AuthProvider'

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading, login, loginWithEmail, registerWithEmail } = useAuth()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const submitEmailAuth = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      if (mode === 'register') {
        await registerWithEmail(name, email, password)
      } else {
        await loginWithEmail(email, password)
      }
    } catch (authError) {
      setError(authError instanceof Error ? authError.message : 'Authentication failed')
    } finally {
      setSubmitting(false)
    }
  }

  const changeMode = (nextMode: 'login' | 'register') => {
    setMode(nextMode)
    setError('')
    setPassword('')
  }

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
          <form className="auth-form" onSubmit={submitEmailAuth}>
            {mode === 'register' && (
              <div>
                <label className="auth-label" htmlFor="auth-name">Full name</label>
                <input
                  className="input auth-input"
                  id="auth-name"
                  name="name"
                  autoComplete="name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  required
                  maxLength={255}
                />
              </div>
            )}
            <div>
              <label className="auth-label" htmlFor="auth-email">Email address</label>
              <input
                className="input auth-input"
                id="auth-email"
                name="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                maxLength={255}
              />
            </div>
            <div>
              <label className="auth-label" htmlFor="auth-password">Password</label>
              <input
                className="input auth-input"
                id="auth-password"
                name="password"
                type="password"
                autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                minLength={mode === 'register' ? 12 : 1}
                maxLength={128}
              />
              {mode === 'register' && (
                <p className="text-caption text-muted auth-password-help">Use at least 12 characters.</p>
              )}
            </div>
            {error && <div className="auth-error" role="alert">{error}</div>}
            <button className="btn btn-primary btn-lg auth-email-submit" disabled={submitting}>
              {submitting ? 'Please wait…' : mode === 'register' ? 'Create account' : 'Sign in'}
            </button>
          </form>
          <button className="auth-mode-toggle" type="button" onClick={() => changeMode(mode === 'login' ? 'register' : 'login')}>
            {mode === 'login' ? 'New to Komponist? Create an account' : 'Already have an account? Sign in'}
          </button>
          <div className="auth-divider"><span>or</span></div>
          <button className="btn btn-secondary btn-lg auth-submit" onClick={login}>
            <span className="google-mark">G</span>
            Continue with Google
          </button>
          <p className="text-caption text-muted auth-note">
            Use any email address. New accounts receive a personal workspace and can join organizations by invitation.
          </p>
        </section>
      </main>
    )
  }

  return <>{children}</>
}
