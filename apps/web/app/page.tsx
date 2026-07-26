'use client'

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  ArrowRight,
  Blocks,
  Bot,
  Braces,
  Check,
  ChevronRight,
  FileCheck2,
  FileClock,
  Files,
  GitBranch,
  LayoutDashboard,
  LoaderCircle,
  Menu,
  MessageSquareText,
  Network,
  Presentation,
  Search,
  Send,
  Sparkles,
  Upload,
  UsersRound,
  X,
} from 'lucide-react'
import BrandMark from '@/components/BrandMark'
import GitHubMark from '@/components/GitHubMark'
import GitHubStars from '@/components/GitHubStars'
import ThemeToggle from '@/components/ThemeToggle'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { API_URL } from '@/lib/api'

const reveal = {
  initial: { opacity: 0, y: 22 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: '-80px' },
  transition: { duration: 0.5, ease: 'easeOut' as const },
}

type DemoResult = {
  mode: 'demo'
  workspace: string
  question: string
  answer: string
  sources: Array<{ id: string; number: number; title: string; excerpt: string; type: string }>
  trace: string[]
}

const demoQuestions = [
  'How long does the Campus Forum run?',
  'Who can read highly confidential board minutes?',
  'How much does the main sponsorship package cost?',
] as const

const fallbackDemoResults: DemoResult[] = [
  {
    mode: 'demo',
    workspace: 'CampusKollektiv browser demo',
    question: demoQuestions[0],
    answer: 'The Campus Forum runs for 6 weeks and ends with the event on 14 November 2026. [1]',
    sources: [{ id: 'fallback-forum', number: 1, title: '08-campus-forum-plan-v2.md', excerpt: 'The Campus Forum project runs for six weeks and ends with the event on 14 November 2026.', type: 'Project' }],
    trace: ['Confirmed entities retrieved', 'Graph context expanded', 'Citation attached'],
  },
  {
    mode: 'demo',
    workspace: 'CampusKollektiv browser demo',
    question: demoQuestions[1],
    answer: 'Highly confidential board minutes are visible only to board members. [1]',
    sources: [{ id: 'fallback-confidentiality', number: 1, title: '04-data-and-access-policy.md', excerpt: 'Board minutes marked highly confidential are visible only to board members.', type: 'Constraint' }],
    trace: ['Permission scope applied', 'Confirmed constraint retrieved', 'Citation attached'],
  },
  {
    mode: 'demo',
    workspace: 'CampusKollektiv browser demo',
    question: demoQuestions[2],
    answer: 'The main sponsorship package costs €1,500. [1]',
    sources: [{ id: 'fallback-sponsor', number: 1, title: '06-sponsorship-policy.md', excerpt: 'CampusKollektiv offers one main sponsorship package for €1,500.', type: 'Decision' }],
    trace: ['Confirmed decision retrieved', 'Direct answer composed', 'Citation attached'],
  },
]

const workflow = [
  {
    number: '01',
    icon: Upload,
    title: 'Connect the work',
    copy: 'Upload documents or sync shared Notion pages and selected Slack channels. Komponist keeps provenance, versions, and source boundaries intact.',
    meta: 'Uploads · Notion · Slack',
  },
  {
    number: '02',
    icon: FileCheck2,
    title: 'Turn activity into facts',
    copy: 'Extract Decisions, Goals, Constraints, and Projects. Review the proposed knowledge with exact evidence before it becomes trusted context.',
    meta: 'Extraction · Review · Evidence',
  },
  {
    number: '03',
    icon: Network,
    title: 'Connect what matters',
    copy: 'The graph preserves how projects support goals, how decisions affect work, and where constraints apply — instead of returning isolated chunks.',
    meta: 'Entities · Relationships · Access',
  },
  {
    number: '04',
    icon: Sparkles,
    title: 'Put context to work',
    copy: 'Ask questions, generate briefings, coordinate agent work, build live canvases, or call the same governed context from your product.',
    meta: 'Ask · Compose · Workrooms · Canvas',
  },
] as const

const interfaces = [
  {
    icon: MessageSquareText,
    title: 'Ask',
    copy: 'Direct answers grounded in confirmed company knowledge, with inspectable citations and reusable chat history.',
    href: '/studio',
    accent: 'bg-success-soft',
    label: 'Cited answers',
  },
  {
    icon: Presentation,
    title: 'Compose',
    copy: 'Create source-backed presentations, executive briefings, and summaries. Export designed PDF, PowerPoint, or Markdown.',
    href: '/create',
    accent: 'bg-warning-soft',
    label: 'Deliverables',
  },
  {
    icon: UsersRound,
    title: 'Workrooms',
    copy: 'Plan and supervise durable agent work with teammates, approvals, scoped context, conversation, and shared outputs.',
    href: '/workrooms',
    accent: 'bg-info-soft',
    label: 'Multiplayer AI',
  },
  {
    icon: LayoutDashboard,
    title: 'Canvas',
    copy: 'Ask a useful interface into existence. Komponist generates a safe dashboard over live, permission-aware graph queries.',
    href: '/canvas',
    accent: 'bg-paper-3',
    label: 'Dynamic software',
  },
  {
    icon: FileClock,
    title: 'Versions',
    copy: 'Find related files across platforms, identify the latest candidate, and compare the actual claims underneath every revision.',
    href: '/versions',
    accent: 'bg-white',
    label: 'Git for files',
  },
] as const

const trustItems = [
  ['Evidence first', 'Every fact keeps its excerpt, source, reference, and date.'],
  ['Human governed', 'New knowledge enters review by default before people or agents rely on it.'],
  ['Permission aware', 'Organization, role, department, and source scope follow every retrieval.'],
  ['Open interfaces', 'Use the Studio, REST API, typed SDK, or authenticated MCP tools.'],
] as const

function fallbackDemo(question: string) {
  const normalized = question.toLowerCase()
  if (normalized.includes('confidential') || normalized.includes('read')) return fallbackDemoResults[1]
  if (normalized.includes('sponsor') || normalized.includes('cost') || normalized.includes('price')) return fallbackDemoResults[2]
  return fallbackDemoResults[0]
}

export default function LandingPage() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [demoQuestion, setDemoQuestion] = useState<string>(demoQuestions[0])
  const [demoResult, setDemoResult] = useState<DemoResult | null>(null)
  const [demoStatus, setDemoStatus] = useState<'checking' | 'live' | 'fallback'>('checking')
  const [demoLoading, setDemoLoading] = useState(true)

  const runDemo = useCallback(async (question: string) => {
    const normalizedQuestion = question.trim()
    if (normalizedQuestion.length < 3) return
    setDemoQuestion(normalizedQuestion)
    setDemoLoading(true)
    try {
      const response = await fetch(`${API_URL}/demo/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: normalizedQuestion }),
      })
      if (!response.ok) throw new Error('Demo API unavailable')
      setDemoResult(await response.json() as DemoResult)
      setDemoStatus('live')
    } catch {
      setDemoResult(fallbackDemo(normalizedQuestion))
      setDemoStatus('fallback')
    } finally {
      setDemoLoading(false)
    }
  }, [])

  useEffect(() => {
    void runDemo(demoQuestions[0])
  }, [runDemo])

  return (
    <main className="min-h-screen overflow-hidden bg-paper text-ink">
      <div className="border-b-2 border-ink bg-ink px-4 py-2 text-center font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-white sm:text-xs">
        <span className="mr-2 inline-block size-2 rounded-full bg-teal-light" />
        Open-source MVP · self-host it or try the live pilot
      </div>

      <header className="sticky top-0 z-40 border-b-2 border-ink bg-paper/95 backdrop-blur">
        <div className="mx-auto flex h-[72px] max-w-[1440px] items-center justify-between px-5 sm:px-8 lg:px-12">
          <Link href="/" className="flex items-center gap-3 text-xl font-bold tracking-tight" aria-label="Komponist home">
            <BrandMark />
            <span>Komponist</span>
          </Link>
          <nav className="hidden items-center gap-8 text-sm font-bold md:flex" aria-label="Main navigation">
            <a href="#product" className="transition hover:text-orange">Product</a>
            <a href="#workflow" className="transition hover:text-orange">How it works</a>
            <a href="#interfaces" className="transition hover:text-orange">Interfaces</a>
            <a href="#developers" className="transition hover:text-orange">Developers</a>
            <a
              href="https://github.com/komponist-ai/komponist"
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 transition hover:text-orange"
            >
              <GitHubMark className="size-4" /> GitHub <GitHubStars />
            </a>
          </nav>
          <div className="flex items-center gap-2 sm:gap-3">
            <button
              type="button"
              className="grid size-10 place-items-center rounded-md border-2 border-ink bg-white shadow-[2px_2px_0_#201c15] md:hidden"
              aria-label={mobileMenuOpen ? 'Close navigation' : 'Open navigation'}
              aria-expanded={mobileMenuOpen}
              onClick={() => setMobileMenuOpen(current => !current)}
            >
              {mobileMenuOpen ? <X className="size-4" /> : <Menu className="size-4" />}
            </button>
            <ThemeToggle />
            <Button asChild variant="ghost" className="hidden sm:inline-flex">
              <Link href="/login">Sign in</Link>
            </Button>
            <Button asChild size="sm">
              <Link href="/studio">Open Studio <ArrowRight /></Link>
            </Button>
          </div>
        </div>
        <AnimatePresence>
          {mobileMenuOpen && (
            <motion.nav
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              className="absolute left-3 right-3 top-[calc(100%+8px)] rounded-xl border-2 border-ink bg-white p-2 text-sm font-bold shadow-[6px_6px_0_#201c15] md:hidden"
              aria-label="Mobile navigation"
            >
              {[
                ['Product', '#product'],
                ['How it works', '#workflow'],
                ['Interfaces', '#interfaces'],
                ['Developers', '#developers'],
              ].map(([label, href]) => (
                <a
                  key={href}
                  href={href}
                  className="flex min-h-11 items-center rounded-lg px-3 hover:bg-paper-2"
                  onClick={() => setMobileMenuOpen(false)}
                >
                  {label}
                </a>
              ))}
              <a
                href="https://github.com/komponist-ai/komponist"
                target="_blank"
                rel="noreferrer"
                className="flex min-h-11 items-center gap-2 rounded-lg px-3 hover:bg-paper-2"
              >
                <GitHubMark className="size-4" /> Open source <GitHubStars className="ml-auto" />
              </a>
            </motion.nav>
          )}
        </AnimatePresence>
      </header>

      <section className="relative border-b-2 border-ink">
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(#d9cfbf44_1px,transparent_1px),linear-gradient(90deg,#d9cfbf44_1px,transparent_1px)] bg-[size:44px_44px] [mask-image:linear-gradient(to_bottom,black,transparent_88%)]" />
        <div className="relative mx-auto grid max-w-[1440px] gap-14 px-5 py-16 sm:px-8 sm:py-24 lg:grid-cols-[0.92fr_1.08fr] lg:items-center lg:px-12 lg:py-28">
          <motion.div initial={{ opacity: 0, x: -24 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.55 }}>
            <Badge variant="orange" className="mb-7 normal-case tracking-normal">
              <Sparkles className="size-3.5" />
              Shared context for people and AI
            </Badge>
            <h1 className="max-w-3xl font-display text-[clamp(3.15rem,12vw,7rem)] font-bold leading-[0.86] tracking-[-0.065em] sm:text-[clamp(4rem,7vw,7rem)]">
              Turn company activity into
              <span className="mt-2 block text-orange">shared intelligence.</span>
            </h1>
            <p className="mt-8 max-w-2xl text-lg leading-8 text-ink-2 sm:text-xl">
              Komponist turns documents, Notion, and Slack into reviewed company knowledge — then makes it usable in cited answers, briefings, live interfaces, team workrooms, and AI agents.
            </p>
            <div className="mt-9 flex flex-col gap-3 min-[430px]:flex-row">
              <Button asChild size="lg" variant="dark">
                <Link href="/studio">Build your company brain <ArrowRight /></Link>
              </Button>
              <Button asChild size="lg" variant="outline">
                <a href="#product">See the product <ChevronRight /></a>
              </Button>
            </div>
            <div className="mt-8 grid max-w-2xl gap-3 text-sm sm:grid-cols-3">
              {[
                ['4', 'durable entity types'],
                ['6', 'authenticated MCP tools'],
                ['1', 'shared source of truth'],
              ].map(([value, label]) => (
                <div key={label} className="flex items-baseline gap-2 border-l-2 border-ink pl-3">
                  <strong className="font-mono text-lg text-orange-dark">{value}</strong>
                  <span className="text-xs font-semibold text-muted">{label}</span>
                </div>
              ))}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 28, rotate: 1 }}
            animate={{ opacity: 1, y: 0, rotate: 0 }}
            transition={{ duration: 0.6, delay: 0.08 }}
            className="relative min-w-0"
          >
            <div className="overflow-hidden rounded-xl border-2 border-ink bg-white shadow-[7px_7px_0_#201c15] sm:shadow-[11px_11px_0_#201c15]">
              <div className="flex items-center justify-between border-b-2 border-ink bg-ink px-4 py-3 text-white">
                <div className="flex items-center gap-2 font-mono text-[10px]">
                  <span className="size-2.5 rounded-full bg-orange" />
                  <span className="size-2.5 rounded-full bg-teal-light" />
                  <span className="ml-2 text-white/65">campuskollektiv / live context</span>
                </div>
                <Badge variant="dark" className="border-white/20 px-2 py-0.5 text-[9px]">
                  {demoStatus === 'live' ? 'API live' : demoStatus === 'fallback' ? 'Browser demo' : 'Connecting'}
                </Badge>
              </div>

              <div className="grid gap-0 lg:grid-cols-[0.82fr_1.18fr]">
                <div className="border-b-2 border-ink bg-paper-2 p-4 lg:border-b-0 lg:border-r-2 sm:p-5">
                  <div className="flex items-center justify-between">
                    <p className="font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-muted">Knowledge pipeline</p>
                    <span className="font-mono text-[9px] text-teal">synced now</span>
                  </div>
                  <div className="mt-4 space-y-3">
                    {[
                      [Files, 'Sources', '14 documents · Notion · Slack', 'bg-warning-soft'],
                      [FileCheck2, 'Review', '3 confirmed · 1 proposed', 'bg-success-soft'],
                      [Network, 'Graph', '24 entities · 17 relationships', 'bg-info-soft'],
                    ].map(([Icon, title, detail, tone]) => {
                      const ItemIcon = Icon as typeof Files
                      return (
                        <div key={title as string} className="flex items-center gap-3 rounded-lg border-2 border-ink bg-white p-3 shadow-[2px_2px_0_#201c15]">
                          <span className={`grid size-9 shrink-0 place-items-center rounded-md border border-ink ${tone}`}>
                            <ItemIcon className="size-4" />
                          </span>
                          <span className="min-w-0">
                            <strong className="block text-sm">{title as string}</strong>
                            <span className="block truncate font-mono text-[9px] text-muted">{detail as string}</span>
                          </span>
                          <Check className="ml-auto size-4 shrink-0 text-teal" />
                        </div>
                      )
                    })}
                  </div>
                  <div className="mt-5 rounded-lg border-2 border-dashed border-line bg-paper p-3">
                    <div className="flex items-center gap-2 text-xs font-bold"><GitBranch className="size-4 text-orange" /> Connected context</div>
                    <p className="mt-1 text-[11px] leading-5 text-muted">Campus Forum supports member growth and is constrained by the approved budget.</p>
                  </div>
                </div>

                <div className="min-w-0 p-4 sm:p-6">
                  <div className="mb-4 flex items-start justify-between gap-3">
                    <div>
                      <p className="font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-orange-dark">Ask the company</p>
                      <h3 className="mt-1 text-xl font-bold">Answers with receipts</h3>
                    </div>
                    <span className="grid size-10 shrink-0 place-items-center rounded-lg border-2 border-ink bg-orange text-white shadow-[2px_2px_0_#201c15]">
                      <Bot className="size-5" />
                    </span>
                  </div>
                  <form
                    className="flex gap-2"
                    onSubmit={(event) => {
                      event.preventDefault()
                      void runDemo(demoQuestion)
                    }}
                  >
                    <label className="sr-only" htmlFor="landing-demo-question">Ask the Komponist demo</label>
                    <input
                      id="landing-demo-question"
                      value={demoQuestion}
                      onChange={(event) => setDemoQuestion(event.target.value)}
                      maxLength={240}
                      className="min-w-0 flex-1 rounded-md border-2 border-ink bg-paper px-3 py-2 text-xs font-semibold outline-none focus:shadow-[2px_2px_0_#e8641b]"
                    />
                    <Button size="icon" aria-label="Ask Komponist" disabled={demoLoading || demoQuestion.trim().length < 3}>
                      {demoLoading ? <LoaderCircle className="animate-spin" /> : <Send />}
                    </Button>
                  </form>
                  <div className="mt-4 min-h-[156px] rounded-lg border-2 border-ink bg-paper p-4">
                    <div className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-wider text-muted">
                      <Search className="size-3.5" /> {demoLoading ? 'Retrieving permitted context…' : 'Confirmed context only'}
                    </div>
                    <p className="mt-3 text-sm font-semibold leading-6" aria-live="polite">
                      {demoLoading ? 'Komponist is checking the demo workspace.' : demoResult?.answer}
                    </p>
                    {demoResult?.sources[0] && !demoLoading && (
                      <div className="mt-4 rounded-md border border-line bg-white p-2.5">
                        <p className="truncate font-mono text-[9px] font-bold text-orange-dark">[{demoResult.sources[0].number}] {demoResult.sources[0].title}</p>
                        <p className="mt-1 line-clamp-2 text-[10px] leading-4 text-muted">{demoResult.sources[0].excerpt}</p>
                      </div>
                    )}
                  </div>
                  <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
                    {demoQuestions.map((question, index) => (
                      <button
                        key={question}
                        type="button"
                        onClick={() => void runDemo(question)}
                        className="min-h-8 shrink-0 rounded-full border border-line bg-white px-3 font-mono text-[9px] font-semibold transition hover:border-ink"
                      >
                        Try 0{index + 1}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
            <div className="absolute -bottom-6 right-3 rotate-2 rounded-md border-2 border-ink bg-success-soft px-4 py-2.5 font-mono text-[10px] font-bold uppercase tracking-wider shadow-[3px_3px_0_#201c15] sm:right-8">
              Source → fact → action
            </div>
          </motion.div>
        </div>
      </section>

      <section className="border-b-2 border-ink bg-ink text-white">
        <div className="mx-auto grid max-w-[1440px] divide-y-2 divide-white/15 px-5 sm:grid-cols-2 sm:divide-x-2 sm:divide-y-0 sm:px-8 lg:grid-cols-4 lg:px-12">
          {trustItems.map(([title, copy]) => (
            <div key={title} className="px-0 py-6 sm:px-5 lg:px-7">
              <div className="flex items-center gap-2 text-sm font-bold"><Check className="size-4 text-teal-light" />{title}</div>
              <p className="mt-2 text-xs leading-5 text-white/55">{copy}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="product" className="border-b-2 border-ink bg-white px-5 py-24 sm:px-8 lg:px-12 lg:py-32">
        <div className="mx-auto max-w-[1440px]">
          <motion.div {...reveal} className="grid gap-8 lg:grid-cols-[0.9fr_1.1fr] lg:items-end">
            <div>
              <Badge variant="teal">The product today</Badge>
              <h2 className="mt-6 max-w-4xl font-display text-[clamp(3rem,6vw,6rem)] font-bold leading-[0.9] tracking-[-0.06em]">
                Not another chat over a <span className="text-orange">folder.</span>
              </h2>
            </div>
            <div className="border-l-2 border-ink pl-6 sm:pl-8">
              <p className="text-xl font-semibold leading-8 text-ink-2 sm:text-2xl">
                Komponist turns scattered activity into an explicit, reviewed model of what your organization decided, wants, must respect, and is doing.
              </p>
              <p className="mt-4 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">
                Decisions · Goals · Constraints · Projects
              </p>
            </div>
          </motion.div>

          <div id="workflow" className="mt-14 grid border-l-2 border-t-2 border-ink md:grid-cols-2 xl:grid-cols-4">
            {workflow.map((step, index) => (
              <motion.article
                key={step.title}
                {...reveal}
                transition={{ ...reveal.transition, delay: index * 0.06 }}
                className="group relative min-h-[390px] border-b-2 border-r-2 border-ink bg-paper p-7 transition-colors hover:bg-warning-soft sm:p-8"
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold text-orange-dark">{step.number}</span>
                  <span className="grid size-12 place-items-center rounded-lg border-2 border-ink bg-white shadow-[3px_3px_0_#201c15] transition-transform group-hover:-rotate-3">
                    <step.icon className="size-5" />
                  </span>
                </div>
                <h3 className="mt-14 text-2xl font-bold tracking-tight">{step.title}</h3>
                <p className="mt-4 leading-7 text-ink-2">{step.copy}</p>
                <p className="absolute bottom-7 left-7 font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-muted sm:left-8">{step.meta}</p>
              </motion.article>
            ))}
          </div>
        </div>
      </section>

      <section id="interfaces" className="px-5 py-24 sm:px-8 lg:px-12 lg:py-32">
        <div className="mx-auto max-w-[1440px]">
          <motion.div {...reveal} className="max-w-4xl">
            <Badge variant="orange">One brain, many interfaces</Badge>
            <h2 className="mt-6 font-display text-[clamp(3rem,6vw,6rem)] font-bold leading-[0.9] tracking-[-0.06em]">
              Knowledge becomes useful when work can <span className="text-orange">happen on top.</span>
            </h2>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-ink-2">
              Every surface resolves the same permission-aware graph. A citation can move from an answer to a briefing, a canvas, or an agent run without losing its origin.
            </p>
          </motion.div>

          <div className="mt-14 grid gap-5 lg:grid-cols-6">
            {interfaces.map((item, index) => (
              <motion.article
                key={item.title}
                {...reveal}
                transition={{ ...reveal.transition, delay: index * 0.05 }}
                className={`group rounded-xl border-2 border-ink p-7 shadow-[5px_5px_0_#201c15] transition hover:-translate-y-1 ${item.accent} ${index < 2 ? 'lg:col-span-3' : 'lg:col-span-2'}`}
              >
                <div className="flex items-start justify-between">
                  <span className="grid size-12 place-items-center rounded-lg border-2 border-ink bg-white">
                    <item.icon className="size-5" />
                  </span>
                  <span className="font-mono text-[9px] font-bold uppercase tracking-wider text-orange-dark">{item.label}</span>
                </div>
                <h3 className="mt-12 text-3xl font-bold">{item.title}</h3>
                <p className="mt-3 max-w-xl leading-7 text-ink-2">{item.copy}</p>
                <Link href={item.href} className="mt-7 inline-flex items-center gap-2 text-sm font-bold transition group-hover:text-orange">
                  Open {item.title} <ArrowRight className="size-4" />
                </Link>
              </motion.article>
            ))}
          </div>
        </div>
      </section>

      <section className="border-y-2 border-ink bg-paper-2">
        <div className="mx-auto grid max-w-[1440px] lg:grid-cols-2">
          <motion.div {...reveal} className="border-b-2 border-ink p-7 sm:p-12 lg:border-b-0 lg:border-r-2 lg:p-16">
            <Badge variant="teal"><UsersRound className="size-3.5" /> Multiplayer AI</Badge>
            <h2 className="mt-7 text-4xl font-bold leading-[0.95] tracking-[-0.045em] sm:text-6xl">
              Agents join the team, not another private chat.
            </h2>
            <p className="mt-6 max-w-xl text-lg leading-8 text-ink-2">
              Workrooms combine a shared objective, approved plan, durable worker, scoped context, human redirects, approvals, and cited deliverables in one auditable place.
            </p>
            <div className="mt-8 grid gap-3 sm:grid-cols-2">
              {['Versioned plans', 'Room-scoped context', 'Pause and redirect', 'Shared deliverables'].map(item => (
                <div key={item} className="flex items-center gap-3 rounded-lg border border-line bg-white p-3 text-sm font-bold">
                  <Check className="size-4 text-teal" /> {item}
                </div>
              ))}
            </div>
          </motion.div>

          <motion.div {...reveal} className="bg-ink p-7 text-white sm:p-12 lg:p-16">
            <Badge variant="dark" className="border-white/25"><Blocks className="size-3.5" /> Dynamic software</Badge>
            <h2 className="mt-7 text-4xl font-bold leading-[0.95] tracking-[-0.045em] sm:text-6xl">
              Ask a live interface into existence.
            </h2>
            <p className="mt-6 max-w-xl text-lg leading-8 text-white/65">
              Canvas converts a question into a validated layout and a closed set of safe graph queries. Each viewer sees fresh data inside their own permissions — not a generated screenshot.
            </p>
            <div className="mt-9 rounded-xl border-2 border-white/25 bg-white/5 p-5">
              <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-orange-light">
                <LayoutDashboard className="size-4" /> Canvas request
              </div>
              <p className="mt-3 text-lg font-semibold">&ldquo;Show the board the projects at risk and the decisions blocking them.&rdquo;</p>
              <div className="mt-5 grid grid-cols-3 gap-2">
                {['Risk metric', 'Project table', 'Decision list'].map(item => (
                  <div key={item} className="rounded-md border border-white/20 bg-white/10 p-2 text-center font-mono text-[9px] text-white/70">{item}</div>
                ))}
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      <section id="developers" className="mx-auto grid max-w-[1440px] gap-14 px-5 py-24 sm:px-8 lg:grid-cols-[0.85fr_1.15fr] lg:items-center lg:px-12 lg:py-32">
        <motion.div {...reveal}>
          <Badge variant="orange"><Braces className="size-3.5" /> Context infrastructure</Badge>
          <h2 className="mt-6 text-5xl font-bold leading-[0.92] tracking-[-0.055em] sm:text-7xl">
            Use the brain from your own product.
          </h2>
          <p className="mt-6 max-w-xl text-lg leading-8 text-ink-2">
            Organization API keys, a typed JavaScript SDK, and authenticated MCP tools expose confirmed context with evidence — without letting callers choose another organization.
          </p>
          <ul className="mt-8 space-y-4">
            {['REST context and brain endpoints', 'Typed { data, error } SDK contract', 'Search, decisions, constraints, approvals, and writeback over MCP'].map(item => (
              <li key={item} className="flex items-start gap-3 font-semibold">
                <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-success-soft text-teal"><Check className="size-4" /></span>
                {item}
              </li>
            ))}
          </ul>
          <div className="mt-9 flex flex-wrap gap-3">
            <Button asChild variant="outline"><Link href="/settings/api">Open API settings <ArrowRight /></Link></Button>
            <Button asChild variant="ghost"><a href="https://github.com/komponist-ai/komponist" target="_blank" rel="noreferrer"><GitHubMark className="size-4" /> View source</a></Button>
          </div>
        </motion.div>

        <motion.div {...reveal} className="overflow-hidden rounded-xl border-2 border-ink bg-code-bg text-code-text shadow-[9px_9px_0_#0e8a7d]">
          <div className="flex items-center justify-between border-b border-white/15 bg-code-surface px-5 py-3 font-mono text-xs text-code-muted">
            <span>company-context.ts</span><span>SDK · REST · MCP</span>
          </div>
          <pre className="overflow-x-auto p-6 font-mono text-[13px] leading-7 sm:p-8"><code><span className="text-code-keyword">import</span> {'{'} createKomponistClient {'}'} <span className="text-code-keyword">from</span> <span className="text-code-string">&quot;@komponist/sdk&quot;</span>{`\n\n`}<span className="text-code-keyword">const</span> komponist = createKomponistClient({'{'}{`\n`}  url: process.env.KOMPONIST_URL!,{`\n`}  apiKey: process.env.KOMPONIST_API_KEY!{`\n`}{'}'}){`\n\n`}<span className="text-code-keyword">const</span> {'{'} data, error {'}'} = <span className="text-code-keyword">await</span> komponist.context.search({`\n`}  <span className="text-code-string">&quot;Which constraints affect Campus Forum?&quot;</span>,{`\n`}  {'{'} types: [<span className="text-code-string">&quot;Constraint&quot;</span>, <span className="text-code-string">&quot;Project&quot;</span>] {'}'}{`\n`}){`\n\n`}<span className="text-code-comment">{'// permission-scoped facts with source evidence'}</span>{`\n`}data?.items[0].evidence</code></pre>
          <div className="border-t border-white/15 bg-black/20 px-6 py-4 font-mono text-xs text-teal-light">
            ✓ Context retrieved · citations preserved
          </div>
        </motion.div>
      </section>

      <section className="border-y-2 border-ink bg-warning-soft px-5 py-16 sm:px-8 lg:px-12">
        <div className="mx-auto flex max-w-[1440px] flex-col gap-8 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-orange-dark">Honest MVP status</p>
            <h2 className="mt-3 max-w-4xl text-4xl font-bold leading-tight tracking-tight sm:text-6xl">
              The core loop works. We are testing the edges in public.
            </h2>
            <p className="mt-4 max-w-3xl leading-7 text-ink-2">
              Upload → extraction → review → graph → cited answers, Compose, Canvas, Workrooms, API, and MCP are implemented. Live connector lifecycles and production operations are still being validated.
            </p>
          </div>
          <Button asChild size="lg" variant="dark" className="shrink-0">
            <a href="https://github.com/komponist-ai/komponist" target="_blank" rel="noreferrer"><GitHubMark className="size-4" /> Follow the build</a>
          </Button>
        </div>
      </section>

      <section className="bg-orange px-5 py-16 text-white sm:px-8 lg:px-12">
        <div className="mx-auto flex max-w-[1440px] flex-col gap-8 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="font-mono text-xs font-bold uppercase tracking-wider text-white/70">Your company already has the context</p>
            <h2 className="mt-3 max-w-4xl text-5xl font-bold leading-[0.95] tracking-[-0.05em] sm:text-7xl">Make it usable together.</h2>
          </div>
          <Button asChild size="lg" variant="dark" className="shrink-0 shadow-[6px_6px_0_#fff]">
            <Link href="/studio">Open Komponist <ArrowRight /></Link>
          </Button>
        </div>
      </section>

      <footer className="bg-paper px-5 py-12 sm:px-8 lg:px-12">
        <div className="mx-auto flex max-w-[1440px] flex-col justify-between gap-8 sm:flex-row sm:items-end">
          <div>
            <div className="flex items-center gap-3 text-xl font-bold"><BrandMark /> Komponist</div>
            <p className="mt-4 max-w-md text-sm text-muted">The shared context layer for people, products, and AI agents.</p>
          </div>
          <div className="flex flex-col items-start gap-4 sm:items-end">
            <a
              href="https://github.com/komponist-ai/komponist"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 text-sm font-bold transition hover:text-orange"
            >
              <GitHubMark className="size-4" /> Open source on GitHub <GitHubStars />
            </a>
            <div className="font-mono text-xs text-muted">© 2026 Komponist · Apache-2.0</div>
          </div>
        </div>
      </footer>
    </main>
  )
}
