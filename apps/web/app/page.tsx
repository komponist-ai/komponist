'use client'

import Link from 'next/link'
import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  ArrowRight,
  BarChart3,
  BookOpenCheck,
  Bot,
  Braces,
  Check,
  ChevronRight,
  CircleCheck,
  Download,
  FileCheck2,
  FileClock,
  FileText,
  GitBranch,
  LayoutDashboard,
  Menu,
  MessageSquareText,
  Music2,
  Network,
  Play,
  Presentation,
  Radio,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Upload,
  UsersRound,
  WandSparkles,
  X,
} from 'lucide-react'
import BrandMark from '@/components/BrandMark'
import GitHubMark from '@/components/GitHubMark'
import GitHubStars from '@/components/GitHubStars'
import SourceLogo from '@/components/SourceLogo'
import ThemeToggle from '@/components/ThemeToggle'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

const reveal = {
  initial: { opacity: 0, y: 22 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: '-80px' },
  transition: { duration: 0.48, ease: 'easeOut' as const },
}

type Surface = 'workrooms' | 'canvas' | 'compose'

const surfaces: Array<{
  id: Surface
  title: string
  label: string
  icon: typeof UsersRound
  color: string
  summary: string
}> = [
  {
    id: 'workrooms',
    title: 'Workrooms',
    label: 'Run the work',
    icon: UsersRound,
    color: 'bg-orange',
    summary: 'People and agents share one objective, plan, context, and approval trail.',
  },
  {
    id: 'canvas',
    title: 'Canvas',
    label: 'See the work',
    icon: LayoutDashboard,
    color: 'bg-teal',
    summary: 'Turn a question into a live, permission-aware company interface.',
  },
  {
    id: 'compose',
    title: 'Compose',
    label: 'Share the work',
    icon: Presentation,
    color: 'bg-[#f4d06f]',
    summary: 'Create cited decks, briefings, and summaries ready to export.',
  },
]

const scoreSteps = [
  {
    number: '01',
    verb: 'Collect',
    title: 'Bring the instruments.',
    copy: 'Documents, Notion, and selected Slack channels.',
    icon: Upload,
    tone: 'bg-warning-soft',
  },
  {
    number: '02',
    verb: 'Conduct',
    title: 'Turn noise into a score.',
    copy: 'Review facts. Connect decisions, goals, constraints, and projects.',
    icon: Music2,
    tone: 'bg-success-soft',
  },
  {
    number: '03',
    verb: 'Play',
    title: 'Make context do work.',
    copy: 'Ask, coordinate, visualize, present, or call it from an agent.',
    icon: Play,
    tone: 'bg-info-soft',
  },
] as const

const smallSurfaces = [
  {
    icon: MessageSquareText,
    title: 'Ask',
    label: 'Answers',
    copy: 'Direct answers. Exact citations.',
    href: '/studio',
    tone: 'bg-success-soft',
  },
  {
    icon: FileClock,
    title: 'Versions',
    label: 'History',
    copy: 'Find the latest file. Keep the conflict.',
    href: '/versions',
    tone: 'bg-warning-soft',
  },
  {
    icon: Braces,
    title: 'API + MCP',
    label: 'Agents',
    copy: 'The same brain inside your own tools.',
    href: '/settings/api',
    tone: 'bg-info-soft',
  },
] as const

export default function LandingPage() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [activeSurface, setActiveSurface] = useState<Surface>('workrooms')

  return (
    <main className="min-h-screen overflow-hidden bg-paper text-ink">
      <div className="border-b-2 border-ink bg-ink px-4 py-2 text-center font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-white sm:text-xs">
        <span className="mr-2 inline-block size-2 rounded-full bg-orange" />
        Open-source company context · now playing
      </div>

      <header className="sticky top-0 z-40 border-b-2 border-ink bg-paper/95 backdrop-blur">
        <div className="mx-auto flex h-[72px] max-w-[1440px] items-center justify-between px-5 sm:px-8 lg:px-12">
          <Link href="/" className="flex items-center gap-3 text-xl font-bold tracking-tight" aria-label="Komponist home">
            <BrandMark />
            <span>Komponist</span>
          </Link>
          <nav className="hidden items-center gap-8 text-sm font-bold md:flex" aria-label="Main navigation">
            <a href="#score" className="transition hover:text-orange">How it works</a>
            <a href="#surfaces" className="transition hover:text-orange">What it makes</a>
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
                ['How it works', '#score'],
                ['What it makes', '#surfaces'],
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
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(#d9cfbf44_1px,transparent_1px),linear-gradient(90deg,#d9cfbf44_1px,transparent_1px)] bg-[size:44px_44px] [mask-image:linear-gradient(to_bottom,black,transparent_90%)]" />
        <div className="relative mx-auto max-w-[1440px] px-5 py-16 sm:px-8 sm:py-24 lg:px-12 lg:py-28">
          <div className="grid gap-14 lg:grid-cols-[0.82fr_1.18fr] lg:items-center">
            <motion.div initial={{ opacity: 0, x: -24 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.55 }}>
              <Badge variant="orange" className="mb-7 normal-case tracking-normal">
                <Music2 className="size-3.5" />
                Score = shared, connected company context
              </Badge>
              <h1 className="max-w-3xl font-display text-[clamp(3.4rem,13vw,7.6rem)] font-bold leading-[0.84] tracking-[-0.07em] sm:text-[clamp(4.4rem,7.4vw,7.6rem)]">
                Turn company
                <span className="relative mx-2 inline-block rotate-[-2deg] border-b-[0.12em] border-orange text-orange">noise</span>
                into one shared score.
              </h1>
              <p className="mt-8 max-w-xl text-lg font-semibold leading-8 text-ink-2 sm:text-xl">
                Komponist connects what your company knows — so people and AI can finally work from the same context.
              </p>
              <div className="mt-5 flex max-w-xl items-start gap-3 rounded-lg border-2 border-ink bg-white px-4 py-3 shadow-[3px_3px_0_#201c15]">
                <span className="grid size-8 shrink-0 place-items-center rounded-md border border-ink bg-warning-soft">
                  <Music2 className="size-4 text-orange" />
                </span>
                <p className="text-sm font-semibold leading-6 text-ink-2">
                  <strong className="text-ink">The score is not a rating.</strong>{' '}
                  It is your living map of reviewed facts, decisions, goals, projects, and evidence — connected in one place.
                </p>
              </div>
              <div className="mt-9 flex flex-col gap-3 min-[430px]:flex-row">
                <Button asChild size="lg" variant="dark">
                  <Link href="/studio">Start composing <ArrowRight /></Link>
                </Button>
                <Button asChild size="lg" variant="outline">
                  <a href="#surfaces">See what it creates <ChevronRight /></a>
                </Button>
              </div>
              <div className="mt-8 flex flex-wrap gap-x-5 gap-y-2 font-mono text-[10px] font-semibold uppercase tracking-wider text-muted">
                <span className="flex items-center gap-1.5"><Check className="size-3.5 text-teal" /> cited</span>
                <span className="flex items-center gap-1.5"><Check className="size-3.5 text-teal" /> reviewed</span>
                <span className="flex items-center gap-1.5"><Check className="size-3.5 text-teal" /> permission-aware</span>
              </div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 28, rotate: 1 }}
              animate={{ opacity: 1, y: 0, rotate: 0 }}
              transition={{ duration: 0.62, delay: 0.08 }}
              className="relative min-w-0"
            >
              <div className="overflow-hidden rounded-xl border-2 border-ink bg-white shadow-[8px_8px_0_#201c15]">
                <div className="flex items-center justify-between border-b-2 border-ink bg-ink px-4 py-3 text-white">
                  <div className="flex items-center gap-2">
                    <span className="size-2.5 rounded-full bg-orange" />
                    <span className="size-2.5 rounded-full bg-teal-light" />
                    <span className="size-2.5 rounded-full bg-white/25" />
                    <span className="ml-2 font-mono text-[9px] text-white/55">company-score.live</span>
                  </div>
                  <span className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-wider text-teal-light">
                    <Radio className="size-3" /> in sync
                  </span>
                </div>

                <div className="relative overflow-hidden bg-paper-2 p-4 sm:p-6">
                  <div className="pointer-events-none absolute inset-0 opacity-45">
                    {[22, 38, 54, 70].map(top => (
                      <div key={top} className="absolute left-0 right-0 border-t border-line" style={{ top: `${top}%` }} />
                    ))}
                  </div>

                  <div className="relative grid gap-4 md:grid-cols-[0.8fr_70px_1fr] md:items-center">
                    <div>
                      <p className="mb-3 font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-muted">The instruments</p>
                      <div className="grid grid-cols-3 gap-2 md:grid-cols-1">
                        <SourceChip icon={FileText} label="Documents" count="14" tone="bg-warning-soft" delay={0} />
                        <SourceChip sourceType="notion" label="Notion" count="8" tone="bg-white" delay={0.08} />
                        <SourceChip sourceType="slack" label="Slack" count="3 ch." tone="bg-success-soft" delay={0.16} />
                      </div>
                    </div>

                    <div className="relative hidden h-full min-h-52 items-center justify-center md:flex">
                      <svg className="absolute inset-0 size-full" viewBox="0 0 70 210" preserveAspectRatio="none" aria-hidden="true">
                        <path d="M0 35 C35 35 35 105 70 105 M0 105 L70 105 M0 175 C35 175 35 105 70 105" fill="none" stroke="var(--color-ink)" strokeWidth="2" strokeDasharray="4 5" />
                      </svg>
                      {[0, 1, 2].map(index => (
                        <motion.span
                          key={index}
                          className="absolute size-3 rounded-full border border-ink bg-orange"
                          initial={{ left: -4, top: `${16 + index * 33}%` }}
                          animate={{ left: 62, top: '48%' }}
                          transition={{ duration: 1.8, delay: index * 0.35, repeat: Infinity, repeatDelay: 1.2, ease: 'easeInOut' }}
                        />
                      ))}
                    </div>

                    <div className="rounded-xl border-2 border-ink bg-ink p-4 text-white shadow-[4px_4px_0_#e8641b] sm:p-5">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-wider text-orange-light">
                          <Network className="size-4" /> Shared score
                        </div>
                        <BrandMark className="size-8 rounded-md shadow-none" />
                      </div>
                      <div className="relative mt-5 h-36">
                        <svg className="absolute inset-0 size-full" viewBox="0 0 300 140" aria-hidden="true">
                          <path d="M150 70 L48 28 M150 70 L252 28 M150 70 L48 115 M150 70 L252 115" fill="none" stroke="#655b4e" strokeWidth="2" />
                        </svg>
                        <ScoreNode positionClassName="left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2" toneClassName="bg-orange text-white" label="Project" />
                        <ScoreNode positionClassName="left-0 top-0" toneClassName="bg-[#f4d06f] text-ink" label="Decision" />
                        <ScoreNode positionClassName="right-0 top-0" toneClassName="bg-teal text-white" label="Goal" />
                        <ScoreNode positionClassName="bottom-0 left-0" toneClassName="bg-white text-ink" label="Evidence" />
                        <ScoreNode positionClassName="bottom-0 right-0" toneClassName="bg-orange-light text-ink" label="Constraint" />
                      </div>
                      <div className="mt-4 flex items-center gap-2 rounded-md border border-white/20 bg-white/5 p-2.5">
                        <CircleCheck className="size-4 shrink-0 text-teal-light" />
                        <span className="text-[11px] font-semibold">24 reviewed facts · 17 relationships</span>
                      </div>
                    </div>
                  </div>

                  <div className="relative mt-5 grid grid-cols-3 gap-2">
                    {surfaces.map(surface => {
                      const Icon = surface.icon
                      const active = surface.id === activeSurface
                      return (
                        <button
                          key={surface.id}
                          type="button"
                          onClick={() => setActiveSurface(surface.id)}
                          className={`group rounded-lg border-2 border-ink p-2.5 text-left transition sm:p-3 ${
                            active ? `${surface.color} ${surface.id === 'compose' ? 'text-ink' : 'text-white'} shadow-[3px_3px_0_#201c15] -translate-y-0.5` : 'bg-white hover:bg-paper'
                          }`}
                          aria-pressed={active}
                        >
                          <Icon className="size-4" />
                          <strong className="mt-2 block truncate text-[11px] sm:text-sm">{surface.title}</strong>
                          <span className={`mt-0.5 hidden font-mono text-[8px] sm:block ${active ? 'opacity-70' : 'text-muted'}`}>{surface.label}</span>
                        </button>
                      )
                    })}
                  </div>

                  <div className="relative mt-3 min-h-[190px] overflow-hidden rounded-xl border-2 border-ink bg-white p-4 shadow-[4px_4px_0_#d9cfbf] sm:p-5">
                    <AnimatePresence mode="wait">
                      <motion.div
                        key={activeSurface}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -8 }}
                        transition={{ duration: 0.2 }}
                      >
                        {activeSurface === 'workrooms' && <WorkroomPreview />}
                        {activeSurface === 'canvas' && <CanvasPreview />}
                        {activeSurface === 'compose' && <ComposePreview />}
                      </motion.div>
                    </AnimatePresence>
                  </div>
                </div>
              </div>
              <div className="absolute -bottom-6 -left-2 rotate-[-3deg] rounded-md border-2 border-ink bg-[#f4d06f] px-4 py-2.5 font-mono text-[10px] font-bold uppercase tracking-wider shadow-[3px_3px_0_#201c15] sm:left-6">
                Less archaeology. More action.
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      <section className="border-b-2 border-ink bg-orange px-5 py-5 text-white sm:px-8 lg:px-12">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-center gap-x-9 gap-y-2 font-mono text-[10px] font-bold uppercase tracking-wider">
          <span className="text-white/65">One score plays everywhere</span>
          <span>Ask</span><span className="text-white/40">♪</span>
          <span>Workrooms</span><span className="text-white/40">♪</span>
          <span>Canvas</span><span className="text-white/40">♪</span>
          <span>Compose</span><span className="text-white/40">♪</span>
          <span>Agents</span>
        </div>
      </section>

      <section id="score" className="border-b-2 border-ink bg-white px-5 py-24 sm:px-8 lg:px-12 lg:py-28">
        <div className="mx-auto max-w-[1440px]">
          <motion.div {...reveal} className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <Badge variant="teal"><Music2 className="size-3.5" /> Three movements</Badge>
              <h2 className="mt-6 max-w-4xl font-display text-[clamp(3.2rem,6.4vw,6.5rem)] font-bold leading-[0.88] tracking-[-0.065em]">
                From scattered notes to <span className="text-orange">coordinated work.</span>
              </h2>
            </div>
            <p className="max-w-sm text-lg font-semibold leading-7 text-ink-2">
              Sources enter once. Trusted context plays everywhere.
            </p>
          </motion.div>

          <div className="mt-14 grid border-l-2 border-t-2 border-ink lg:grid-cols-3">
            {scoreSteps.map((step, index) => (
              <motion.article
                key={step.title}
                {...reveal}
                transition={{ ...reveal.transition, delay: index * 0.08 }}
                className={`group relative min-h-[330px] border-b-2 border-r-2 border-ink p-7 sm:p-9 ${step.tone}`}
              >
                <div className="flex items-start justify-between">
                  <span className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-orange-dark">{step.number} · {step.verb}</span>
                  <span className="grid size-12 place-items-center rounded-lg border-2 border-ink bg-white shadow-[3px_3px_0_#201c15] transition-transform group-hover:-rotate-6 group-hover:scale-105">
                    <step.icon className="size-5" />
                  </span>
                </div>
                <h3 className="mt-16 max-w-xs text-3xl font-bold leading-tight">{step.title}</h3>
                <p className="mt-4 max-w-sm text-base font-semibold leading-7 text-ink-2">{step.copy}</p>
                <span className="absolute bottom-6 right-7 font-display text-6xl font-black text-ink/5">♪</span>
              </motion.article>
            ))}
          </div>
        </div>
      </section>

      <section id="surfaces" className="px-5 py-24 sm:px-8 lg:px-12 lg:py-28">
        <div className="mx-auto max-w-[1440px]">
          <motion.div {...reveal} className="text-center">
            <Badge variant="orange"><WandSparkles className="size-3.5" /> Context you can see</Badge>
            <h2 className="mx-auto mt-6 max-w-5xl font-display text-[clamp(3.2rem,6.4vw,6.5rem)] font-bold leading-[0.88] tracking-[-0.065em]">
              A company brain that actually <span className="text-orange">does things.</span>
            </h2>
          </motion.div>

          <div className="mt-14 grid gap-5 xl:grid-cols-3">
            <motion.article {...reveal} className="group overflow-hidden rounded-xl border-2 border-ink bg-info-soft shadow-[6px_6px_0_#201c15]">
              <div className="flex items-center justify-between border-b-2 border-ink px-6 py-5">
                <div>
                  <p className="font-mono text-[9px] font-bold uppercase tracking-wider text-muted">01 · Coordinate</p>
                  <h3 className="mt-1 text-3xl font-bold">Workrooms</h3>
                </div>
                <span className="grid size-12 place-items-center rounded-lg border-2 border-ink bg-orange text-white transition-transform group-hover:-rotate-6"><UsersRound /></span>
              </div>
              <div className="p-5"><WorkroomPreview expanded /></div>
              <Link href="/workrooms" className="flex items-center justify-between border-t-2 border-ink bg-white px-6 py-4 text-sm font-bold hover:bg-paper-2">
                People + agents, one room <ArrowRight className="size-4" />
              </Link>
            </motion.article>

            <motion.article {...reveal} transition={{ ...reveal.transition, delay: 0.08 }} className="group overflow-hidden rounded-xl border-2 border-ink bg-success-soft shadow-[6px_6px_0_#201c15]">
              <div className="flex items-center justify-between border-b-2 border-ink px-6 py-5">
                <div>
                  <p className="font-mono text-[9px] font-bold uppercase tracking-wider text-muted">02 · Explore</p>
                  <h3 className="mt-1 text-3xl font-bold">Canvas</h3>
                </div>
                <span className="grid size-12 place-items-center rounded-lg border-2 border-ink bg-teal text-white transition-transform group-hover:rotate-6"><LayoutDashboard /></span>
              </div>
              <div className="p-5"><CanvasPreview expanded /></div>
              <Link href="/canvas" className="flex items-center justify-between border-t-2 border-ink bg-white px-6 py-4 text-sm font-bold hover:bg-paper-2">
                Ask an interface into existence <ArrowRight className="size-4" />
              </Link>
            </motion.article>

            <motion.article {...reveal} transition={{ ...reveal.transition, delay: 0.16 }} className="group overflow-hidden rounded-xl border-2 border-ink bg-warning-soft shadow-[6px_6px_0_#201c15]">
              <div className="flex items-center justify-between border-b-2 border-ink px-6 py-5">
                <div>
                  <p className="font-mono text-[9px] font-bold uppercase tracking-wider text-muted">03 · Present</p>
                  <h3 className="mt-1 text-3xl font-bold">Compose</h3>
                </div>
                <span className="grid size-12 place-items-center rounded-lg border-2 border-ink bg-[#f4d06f] transition-transform group-hover:-rotate-6"><Presentation /></span>
              </div>
              <div className="p-5"><ComposePreview expanded /></div>
              <Link href="/create" className="flex items-center justify-between border-t-2 border-ink bg-white px-6 py-4 text-sm font-bold hover:bg-paper-2">
                From graph to deck <ArrowRight className="size-4" />
              </Link>
            </motion.article>
          </div>

          <div className="mt-5 grid gap-5 md:grid-cols-3">
            {smallSurfaces.map((surface, index) => (
              <motion.article
                key={surface.title}
                {...reveal}
                transition={{ ...reveal.transition, delay: index * 0.06 }}
                className={`group rounded-xl border-2 border-ink p-6 shadow-[4px_4px_0_#201c15] ${surface.tone}`}
              >
                <div className="flex items-start justify-between">
                  <span className="grid size-10 place-items-center rounded-lg border-2 border-ink bg-white"><surface.icon className="size-4" /></span>
                  <span className="font-mono text-[9px] font-bold uppercase tracking-wider text-muted">{surface.label}</span>
                </div>
                <h3 className="mt-8 text-2xl font-bold">{surface.title}</h3>
                <p className="mt-2 font-semibold text-ink-2">{surface.copy}</p>
                <Link href={surface.href} className="mt-5 inline-flex items-center gap-2 text-sm font-bold group-hover:text-orange">
                  Open <ArrowRight className="size-4" />
                </Link>
              </motion.article>
            ))}
          </div>
        </div>
      </section>

      <section className="border-y-2 border-ink bg-ink text-white">
        <div className="mx-auto grid max-w-[1440px] lg:grid-cols-[0.9fr_1.1fr]">
          <motion.div {...reveal} className="border-b-2 border-white/20 p-8 sm:p-12 lg:border-b-0 lg:border-r-2 lg:p-16">
            <Badge variant="dark" className="border-white/25"><ShieldCheck className="size-3.5" /> The trust layer</Badge>
            <h2 className="mt-7 text-5xl font-bold leading-[0.92] tracking-[-0.055em] sm:text-7xl">
              Every note has a source.
            </h2>
            <p className="mt-6 max-w-lg text-lg font-semibold leading-8 text-white/65">
              AI can improvise. Company truth should not.
            </p>
          </motion.div>
          <div className="grid sm:grid-cols-2">
            {[
              [FileCheck2, 'Review first', 'Proposed knowledge waits for a human.'],
              [GitBranch, 'Keep history', 'Versions and contradictions stay visible.'],
              [ShieldCheck, 'Respect scope', 'Organization and department access travels with context.'],
              [BookOpenCheck, 'Show receipts', 'Answers, decks, canvases, and runs keep citations.'],
            ].map(([Icon, title, copy], index) => {
              const TrustIcon = Icon as typeof FileCheck2
              return (
                <motion.div
                  key={title as string}
                  {...reveal}
                  className={`p-7 sm:p-9 ${index < 2 ? 'border-b-2 border-white/20' : ''} ${index % 2 === 0 ? 'sm:border-r-2 sm:border-white/20' : ''}`}
                >
                  <TrustIcon className="size-6 text-orange-light" />
                  <h3 className="mt-8 text-2xl font-bold">{title as string}</h3>
                  <p className="mt-2 max-w-xs text-sm font-semibold leading-6 text-white/55">{copy as string}</p>
                </motion.div>
              )
            })}
          </div>
        </div>
      </section>

      <section id="developers" className="mx-auto grid max-w-[1440px] gap-14 px-5 py-24 sm:px-8 lg:grid-cols-[0.82fr_1.18fr] lg:items-center lg:px-12 lg:py-28">
        <motion.div {...reveal}>
          <Badge variant="teal"><Bot className="size-3.5" /> For your agents too</Badge>
          <h2 className="mt-6 text-5xl font-bold leading-[0.92] tracking-[-0.055em] sm:text-7xl">
            Call the same score from code.
          </h2>
          <p className="mt-6 max-w-xl text-lg font-semibold leading-8 text-ink-2">
            One permission-aware context layer for Studio, your product, and every MCP-compatible agent.
          </p>
          <div className="mt-8 flex flex-wrap gap-2">
            {['REST API', 'Typed SDK', '6 MCP tools', 'Revocable keys'].map(item => (
              <span key={item} className="rounded-full border-2 border-ink bg-white px-3 py-1.5 font-mono text-[10px] font-bold">{item}</span>
            ))}
          </div>
          <Button asChild className="mt-9" variant="outline">
            <Link href="/settings/api">Open API settings <ArrowRight /></Link>
          </Button>
        </motion.div>

        <motion.div {...reveal} className="overflow-hidden rounded-xl border-2 border-ink bg-code-bg text-code-text shadow-[9px_9px_0_#0e8a7d]">
          <div className="flex items-center justify-between border-b border-white/15 bg-code-surface px-5 py-3 font-mono text-xs text-code-muted">
            <span>play-the-score.ts</span><span>SDK · MCP</span>
          </div>
          <pre className="overflow-x-auto p-6 font-mono text-[13px] leading-7 sm:p-8"><code><span className="text-code-keyword">const</span> {'{'} data {'}'} = <span className="text-code-keyword">await</span> komponist.context.search({`\n`}  <span className="text-code-string">&quot;What is blocking Campus Forum?&quot;</span>,{`\n`}  {'{'} types: [<span className="text-code-string">&quot;Constraint&quot;</span>, <span className="text-code-string">&quot;Project&quot;</span>] {'}'}{`\n`}){`\n\n`}<span className="text-code-comment">{'// confirmed facts · exact evidence · correct scope'}</span>{`\n`}data.items[0].evidence</code></pre>
          <div className="flex items-center gap-2 border-t border-white/15 bg-black/20 px-6 py-4 font-mono text-xs text-teal-light">
            <Sparkles className="size-4" /> Context in tune.
          </div>
        </motion.div>
      </section>

      <section className="border-y-2 border-ink bg-orange px-5 py-16 text-white sm:px-8 lg:px-12">
        <div className="mx-auto flex max-w-[1440px] flex-col gap-8 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-white/65">The instruments are already playing</p>
            <h2 className="mt-3 max-w-4xl text-5xl font-bold leading-[0.92] tracking-[-0.055em] sm:text-7xl">
              Give the company a score.
            </h2>
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
            <p className="mt-4 max-w-md text-sm font-semibold text-muted">One shared score for people, products, and AI.</p>
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

function SourceChip({
  icon: Icon,
  sourceType,
  label,
  count,
  tone,
  delay,
}: {
  icon?: typeof FileText
  sourceType?: 'notion' | 'slack'
  label: string
  count: string
  tone: string
  delay: number
}) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: 0.3 + delay }}
      className={`flex min-w-0 items-center gap-2 rounded-lg border-2 border-ink p-2.5 shadow-[2px_2px_0_#201c15] ${tone}`}
    >
      {sourceType ? (
        <SourceLogo type={sourceType} className="!size-8 !rounded-md !border !shadow-none" />
      ) : Icon ? (
        <span className="grid size-8 shrink-0 place-items-center rounded-md border border-ink bg-white"><Icon className="size-3.5" /></span>
      ) : null}
      <span className="min-w-0">
        <strong className="block truncate text-[10px] sm:text-xs">{label}</strong>
        <span className="font-mono text-[8px] text-muted">{count}</span>
      </span>
    </motion.div>
  )
}

function ScoreNode({
  positionClassName,
  toneClassName,
  label,
}: {
  positionClassName: string
  toneClassName: string
  label: string
}) {
  return (
    <div className={`absolute ${positionClassName}`}>
      <motion.div
        animate={{ y: [0, -3, 0] }}
        transition={{ duration: 3, repeat: Infinity, delay: label.length * 0.07 }}
        className={`grid min-h-8 min-w-[70px] place-items-center rounded-full border-2 border-ink px-2 font-mono text-[8px] font-bold uppercase shadow-[2px_2px_0_#100e0b] ${toneClassName}`}
      >
        {label}
      </motion.div>
    </div>
  )
}

function WorkroomPreview({ expanded = false }: { expanded?: boolean }) {
  return (
    <div className={`rounded-lg border-2 border-ink bg-white ${expanded ? 'min-h-[280px] p-4' : 'p-3'}`}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="font-mono text-[8px] font-bold uppercase tracking-wider text-orange-dark">Launch workroom</p>
          <strong className="mt-1 block text-sm">Prepare the board update</strong>
        </div>
        <div className="flex -space-x-2">
          {['SM', 'LK', 'AI'].map((initials, index) => (
            <span key={initials} className={`grid size-8 place-items-center rounded-full border-2 border-ink text-[8px] font-black ${index === 2 ? 'bg-orange text-white' : 'bg-paper'}`}>{initials}</span>
          ))}
        </div>
      </div>
      <div className="mt-4 space-y-2">
        {[
          ['Research current projects', 'done'],
          ['Find unresolved decisions', 'active'],
          ['Draft cited briefing', 'next'],
        ].map(([task, state], index) => (
          <div key={task} className={`flex items-center gap-2 rounded-md border px-2.5 py-2 text-[10px] font-semibold ${state === 'active' ? 'border-orange bg-warning-soft' : 'border-line bg-paper'}`}>
            <span className={`grid size-5 place-items-center rounded-full border ${state === 'done' ? 'border-teal bg-teal text-white' : 'border-ink bg-white'}`}>
              {state === 'done' ? <Check className="size-3" /> : index + 1}
            </span>
            <span className="min-w-0 flex-1 truncate">{task}</span>
            <span className="font-mono text-[7px] uppercase text-muted">{state}</span>
          </div>
        ))}
      </div>
      {expanded && (
        <div className="mt-4 flex items-center justify-between rounded-md border-2 border-ink bg-ink px-3 py-2.5 text-white">
          <span className="flex items-center gap-2 text-[10px] font-semibold"><Bot className="size-3.5 text-orange-light" /> Analyst is researching</span>
          <span className="size-2 animate-pulse rounded-full bg-teal-light" />
        </div>
      )}
    </div>
  )
}

function CanvasPreview({ expanded = false }: { expanded?: boolean }) {
  return (
    <div className={`rounded-lg border-2 border-ink bg-white ${expanded ? 'min-h-[280px] p-4' : 'p-3'}`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="font-mono text-[8px] font-bold uppercase tracking-wider text-teal">Live canvas</p>
          <strong className="mt-1 block text-sm">Projects at risk</strong>
        </div>
        <SlidersHorizontal className="size-4 text-muted" />
      </div>
      <div className="mt-4 grid grid-cols-3 gap-2">
        {[
          ['12', 'Projects'],
          ['3', 'At risk'],
          ['7', 'Open decisions'],
        ].map(([value, label], index) => (
          <div key={label} className={`rounded-md border border-line p-2 ${index === 1 ? 'bg-warning-soft' : 'bg-paper'}`}>
            <strong className="block font-mono text-lg">{value}</strong>
            <span className="text-[8px] text-muted">{label}</span>
          </div>
        ))}
      </div>
      <div className="mt-3 flex h-[72px] items-end gap-2 rounded-md border border-line bg-paper p-3">
        {[38, 67, 46, 88, 59, 76].map((height, index) => (
          <motion.span
            key={index}
            initial={{ height: 0 }}
            whileInView={{ height: `${height}%` }}
            viewport={{ once: true }}
            transition={{ delay: index * 0.05 }}
            className={`flex-1 rounded-t border border-ink ${index === 3 ? 'bg-orange' : 'bg-teal'}`}
          />
        ))}
      </div>
      {expanded && (
        <div className="mt-3 flex items-center gap-2 rounded-md border border-line bg-success-soft px-3 py-2 text-[9px] font-semibold text-teal">
          <BarChart3 className="size-3.5" /> Live data · resolved for this viewer
        </div>
      )}
    </div>
  )
}

function ComposePreview({ expanded = false }: { expanded?: boolean }) {
  return (
    <div className={`rounded-lg border-2 border-ink bg-white ${expanded ? 'min-h-[280px] p-4' : 'p-3'}`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="font-mono text-[8px] font-bold uppercase tracking-wider text-orange-dark">Generated briefing</p>
          <strong className="mt-1 block text-sm">Q3 Company Overview</strong>
        </div>
        <Sparkles className="size-4 text-orange" />
      </div>
      <div className="mt-4 grid grid-cols-[54px_1fr] gap-3">
        <div className="space-y-2">
          {[0, 1, 2].map(index => (
            <div key={index} className={`aspect-[4/3] rounded border-2 ${index === 0 ? 'border-orange bg-warning-soft' : 'border-line bg-paper'}`}>
              <div className="m-1.5 h-1 w-6 rounded bg-ink/60" />
              <div className="mx-1.5 mt-1 h-0.5 rounded bg-line" />
            </div>
          ))}
        </div>
        <div className="rounded-md border-2 border-ink bg-paper p-3">
          <span className="rounded-full border border-orange/30 bg-warning-soft px-2 py-0.5 font-mono text-[7px] font-bold text-orange-dark">EXECUTIVE BRIEFING</span>
          <div className="mt-3 h-2 w-3/4 rounded bg-ink" />
          <div className="mt-2 h-1.5 w-1/2 rounded bg-muted/40" />
          <div className="mt-4 space-y-1.5">
            <div className="h-1 rounded bg-line" />
            <div className="h-1 rounded bg-line" />
            <div className="h-1 w-4/5 rounded bg-line" />
          </div>
          <div className="mt-4 font-mono text-[7px] font-bold text-orange-dark">[1] [3] [8]</div>
        </div>
      </div>
      {expanded && (
        <div className="mt-3 flex flex-wrap gap-2">
          {['PDF', 'PowerPoint', 'Markdown'].map(format => (
            <span key={format} className="flex items-center gap-1 rounded-full border border-ink bg-white px-2 py-1 font-mono text-[7px] font-bold"><Download className="size-2.5" />{format}</span>
          ))}
        </div>
      )}
    </div>
  )
}
