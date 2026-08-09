'use client'

import Link from 'next/link'
import { FormEvent, useState } from 'react'
import { usePathname } from 'next/navigation'
import { motion } from 'framer-motion'
import { ArrowRight, FileText, LoaderCircle, LockKeyhole, Mail, Network, ShieldCheck } from 'lucide-react'
import { useAuth } from './AuthProvider'
import BrandMark from './BrandMark'
import SourceLogo from './SourceLogo'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import ThemeToggle from './ThemeToggle'

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
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

  if (pathname === '/') {
    return <>{children}</>
  }

  if (loading) {
    return (
      <main className="grid min-h-screen place-items-center bg-paper px-5" aria-live="polite">
        <div className="flex items-center gap-3 rounded-xl border-2 border-ink bg-white px-5 py-4 shadow-[4px_4px_0_var(--color-shadow-strong)]">
          <LoaderCircle className="size-5 animate-spin text-orange" />
          <p className="font-mono text-xs font-bold uppercase tracking-wider text-muted">Loading your workspace…</p>
        </div>
      </main>
    )
  }

  if (!user) {
    return (
      <main className="relative h-screen overflow-hidden bg-paper text-ink">
        <ThemeToggle className="fixed right-4 top-4 z-50 sm:right-6 sm:top-6" />
        <div className="grid h-screen lg:grid-cols-[1.05fr_0.95fr]">
          <section className="relative hidden h-screen overflow-hidden border-r-2 border-ink bg-ink p-10 text-white lg:flex lg:flex-col xl:p-14">
            <Link className="relative z-10 inline-flex items-center gap-3 self-start font-display text-xl font-black" href="/">
              <BrandMark />
              Komponist
            </Link>

            <div className="relative z-10 my-auto max-w-xl py-16">
              <Badge variant="orange" className="mb-6 border-orange bg-orange text-white">The programmable company brain</Badge>
              <h1 className="font-display text-5xl font-black leading-[0.96] tracking-[-0.05em] xl:text-7xl">
                Stop making your agents guess.
              </h1>
              <p className="mt-6 max-w-lg text-lg leading-8 text-white/70">
                Give every teammate and AI agent the same reviewed company context — with evidence attached.
              </p>

              <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.15, duration: 0.4 }}
                className="mt-10 overflow-hidden rounded-xl border-2 border-white bg-paper text-ink shadow-[8px_8px_0_var(--color-orange)]"
              >
                <div className="flex items-center justify-between border-b-2 border-ink bg-[#111214] px-4 py-3 text-[#fffdf8]">
                  <div className="flex items-center gap-2">
                    <span className="size-2 rounded-full bg-orange" />
                    <span className="size-2 rounded-full bg-teal-light" />
                    <span className="size-2 rounded-full bg-[#fffdf8]/25" />
                  </div>
                  <span className="font-mono text-[9px] uppercase tracking-wider text-teal-light">● in sync</span>
                </div>
                <div className="relative bg-paper-2 p-5">
                  <div className="grid grid-cols-[1fr_70px_1fr] items-center gap-2">
                    <div className="flex flex-col gap-2">
                      {[
                        { label: 'Documents', count: '14', type: 'docs' as const, tone: 'bg-warning-soft' },
                        { label: 'Notion', count: '8', type: 'notion' as const, tone: 'bg-white' },
                        { label: 'Slack', count: '3 ch.', type: 'slack' as const, tone: 'bg-success-soft' },
                      ].map((source, i) => (
                        <motion.div
                          key={source.label}
                          initial={{ opacity: 0, x: -10 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: 0.3 + i * 0.08 }}
                          className={`flex items-center gap-2 rounded-lg border-2 border-ink p-2 shadow-[2px_2px_0_var(--color-shadow-strong)] ${source.tone}`}
                        >
                          {source.type === 'docs' ? (
                            <span className="grid size-8 shrink-0 place-items-center rounded-md border border-ink bg-white">
                              <FileText className="size-4" />
                            </span>
                          ) : (
                            <SourceLogo type={source.type} className="!size-8 !rounded-md !border !shadow-none" />
                          )}
                          <span className="min-w-0">
                            <strong className="block truncate text-xs">{source.label}</strong>
                            <span className="font-mono text-[8px] text-muted">{source.count}</span>
                          </span>
                        </motion.div>
                      ))}
                    </div>

                    <div className="relative flex h-full min-h-[120px] items-center justify-center">
                      <svg className="absolute inset-0 size-full" viewBox="0 0 70 120" preserveAspectRatio="none" aria-hidden="true">
                        <path d="M0 20 C35 20 35 60 70 60 M0 60 L70 60 M0 100 C35 100 35 60 70 60" fill="none" stroke="var(--color-ink)" strokeWidth="2" strokeDasharray="4 5" />
                      </svg>
                      {[0, 1, 2].map(i => (
                        <motion.span
                          key={i}
                          className="absolute size-3 rounded-full border border-ink bg-orange"
                          initial={{ left: -4, top: `${17 + i * 33}%` }}
                          animate={{ left: 62, top: '48%' }}
                          transition={{ duration: 1.8, delay: i * 0.35, repeat: Infinity, repeatDelay: 1.2, ease: 'easeInOut' }}
                        />
                      ))}
                    </div>

                    <div className="rounded-xl border-2 border-ink bg-[#111214] p-3 text-[#fffdf8] shadow-[3px_3px_0_var(--color-orange)]">
                      <div className="flex items-center gap-2 font-mono text-[8px] uppercase tracking-wider text-orange-light">
                        <Network className="size-3" /> Score
                      </div>
                      <div className="mt-2 flex items-center gap-2 rounded border border-[#fffdf8]/20 bg-[#fffdf8]/5 p-2">
                        <span className="size-2 rounded-full bg-teal-light" />
                        <span className="text-[9px] font-semibold">24 facts</span>
                      </div>
                    </div>
                  </div>
                </div>
              </motion.div>
            </div>

          </section>

          <section className="h-screen overflow-y-auto px-5 py-12 sm:px-8 lg:px-12">
            <div className="flex min-h-full items-center justify-center">
              <motion.div
                key={mode}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.28 }}
                className="w-full max-w-[500px]"
              >
              <Link className="mb-12 inline-flex items-center gap-3 font-display text-xl font-black lg:hidden" href="/">
                <BrandMark />
                Komponist
              </Link>

              <div className="mb-8">
                <p className="mb-3 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-orange-dark">
                  {mode === 'login' ? 'Welcome back' : 'Start building the brain'}
                </p>
                <h1 className="font-display text-4xl font-black tracking-[-0.04em] sm:text-5xl">
                  {mode === 'login' ? 'Open your workspace.' : 'Create your workspace.'}
                </h1>
                <p className="mt-4 max-w-md leading-7 text-muted">
                  {mode === 'login'
                    ? 'Sign in to your governed company context, sources, and agent workflows.'
                    : 'Use any email address. You can invite your team into the same organization after setup.'}
                </p>
              </div>

              <div className="mb-7 grid grid-cols-2 rounded-xl border-2 border-ink bg-paper-3 p-1 shadow-[3px_3px_0_var(--color-shadow-strong)]">
                <button
                  className={`rounded-lg px-4 py-2.5 text-sm font-bold transition ${mode === 'login' ? 'bg-ink text-white' : 'hover:bg-white/70'}`}
                  type="button"
                  onClick={() => changeMode('login')}
                >
                  Sign in
                </button>
                <button
                  className={`rounded-lg px-4 py-2.5 text-sm font-bold transition ${mode === 'register' ? 'bg-ink text-white' : 'hover:bg-white/70'}`}
                  type="button"
                  onClick={() => changeMode('register')}
                >
                  Create account
                </button>
              </div>

              <form className="space-y-5" onSubmit={submitEmailAuth}>
                {mode === 'register' && (
                  <div>
                    <label className="mb-2 block font-mono text-[10px] font-bold uppercase tracking-wider text-muted" htmlFor="auth-name">Full name</label>
                    <input
                      className="w-full rounded-xl border-2 border-ink bg-white px-4 py-3.5 text-sm outline-none shadow-[3px_3px_0_var(--color-shadow-soft)] transition focus:-translate-y-0.5 focus:shadow-[4px_4px_0_var(--color-orange)]"
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
                  <label className="mb-2 block font-mono text-[10px] font-bold uppercase tracking-wider text-muted" htmlFor="auth-email">Email address</label>
                  <div className="relative">
                    <Mail className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-muted" />
                    <input
                      className="w-full rounded-xl border-2 border-ink bg-white py-3.5 pl-11 pr-4 text-sm outline-none shadow-[3px_3px_0_var(--color-shadow-soft)] transition focus:-translate-y-0.5 focus:shadow-[4px_4px_0_var(--color-orange)]"
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
                </div>
                <div>
                  <label className="mb-2 block font-mono text-[10px] font-bold uppercase tracking-wider text-muted" htmlFor="auth-password">Password</label>
                  <div className="relative">
                    <LockKeyhole className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-muted" />
                    <input
                      className="w-full rounded-xl border-2 border-ink bg-white py-3.5 pl-11 pr-4 text-sm outline-none shadow-[3px_3px_0_var(--color-shadow-soft)] transition focus:-translate-y-0.5 focus:shadow-[4px_4px_0_var(--color-orange)]"
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
                  </div>
                  {mode === 'register' && (
                    <p className="mt-2 text-xs text-muted">Use at least 12 characters.</p>
                  )}
                </div>
                {error && <div className="rounded-lg border-2 border-danger bg-danger-soft px-4 py-3 text-sm font-medium text-danger" role="alert">{error}</div>}
                <Button className="w-full" size="lg" disabled={submitting}>
                  {submitting && <LoaderCircle className="size-4 animate-spin" />}
                  {submitting ? 'Please wait…' : mode === 'register' ? 'Create workspace' : 'Sign in'}
                  {!submitting && <ArrowRight className="size-4" />}
                </Button>
              </form>

              <div className="my-7 flex items-center gap-4 font-mono text-[9px] font-bold uppercase tracking-wider text-muted before:h-px before:flex-1 before:bg-line after:h-px after:flex-1 after:bg-line">or</div>
              <Button className="w-full" size="lg" variant="outline" type="button" onClick={login}>
                <span className="grid size-6 place-items-center rounded-full bg-white font-display text-sm font-black text-ink">G</span>
                Continue with Google
              </Button>
              <p className="mt-6 flex items-start gap-2 text-xs leading-5 text-muted">
                <ShieldCheck className="mt-0.5 size-4 shrink-0 text-teal-dark" />
                Your account belongs to an organization. Members share its brain; other organizations stay isolated.
              </p>
            </motion.div>
            </div>
          </section>
        </div>
      </main>
    )
  }

  return <>{children}</>
}
