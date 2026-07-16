'use client'

import Link from 'next/link'
import { motion } from 'framer-motion'
import {
  ArrowRight, Braces, Check, ChevronRight, DatabaseZap, FileCheck2,
  FileText, GitBranch, KeyRound, MessageSquareText, Network, Search,
  ShieldCheck, Sparkles, TerminalSquare, Upload, UsersRound,
} from 'lucide-react'
import BrandMark from '@/components/BrandMark'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

const reveal = {
  initial: { opacity: 0, y: 24 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: '-80px' },
  transition: { duration: 0.5, ease: 'easeOut' as const },
}

const features = [
  {
    icon: Upload,
    number: '01',
    title: 'Ingest the useful stuff',
    copy: 'Upload documents or connect Notion. Komponist extracts decisions, goals, constraints, and projects — not another pile of chunks.',
    tag: 'Sources → facts',
  },
  {
    icon: FileCheck2,
    number: '02',
    title: 'Review before trust',
    copy: 'Every new fact enters a human review queue with confidence, exact evidence, and its original source attached.',
    tag: 'Governed by default',
  },
  {
    icon: Network,
    number: '03',
    title: 'Keep the relationships',
    copy: 'Projects advance goals. Decisions affect projects. Constraints stay connected to the work they shape.',
    tag: 'Context graph',
  },
  {
    icon: MessageSquareText,
    number: '04',
    title: 'Ask with receipts',
    copy: 'Chat across confirmed company knowledge. Every answer carries citations an engineer — or an agent — can inspect.',
    tag: 'Cited answers',
  },
  {
    icon: KeyRound,
    number: '05',
    title: 'One brain per workspace',
    copy: 'Organization-scoped users, roles, credentials, API keys, and revocation keep customer context separated.',
    tag: 'Multi-tenant',
  },
  {
    icon: Braces,
    number: '06',
    title: 'Built for agents too',
    copy: 'Expose the same confirmed brain over MCP and API so coding agents stop guessing what the company decided.',
    tag: 'MCP + API',
  },
]

const steps = [
  ['Drop in a document', 'Markdown, text, or YAML. Raw uploads are processed in memory.', Upload],
  ['Confirm the facts', 'Approve what is true, reject what is noise, keep every citation.', FileCheck2],
  ['Call the brain', 'Ask in Studio or connect an agent through your scoped MCP key.', TerminalSquare],
] as const

export default function LandingPage() {
  return (
    <main className="min-h-screen overflow-hidden bg-paper text-ink">
      <div className="border-b-2 border-ink bg-ink px-4 py-2 text-center font-mono text-[11px] text-white sm:text-xs">
        <span className="mr-2 inline-block size-2 rounded-full bg-orange" />
        Local-first MVP in active development. The brain is awake, mildly caffeinated.
      </div>

      <header className="sticky top-0 z-40 border-b-2 border-ink bg-paper/95 backdrop-blur">
        <div className="mx-auto flex h-20 max-w-[1440px] items-center justify-between px-5 sm:px-8 lg:px-12">
          <Link href="/" className="flex items-center gap-3 text-xl font-bold tracking-tight">
            <BrandMark />
            Komponist
          </Link>
          <nav className="hidden items-center gap-8 text-sm font-bold md:flex">
            <a href="#platform" className="hover:text-orange">Platform</a>
            <a href="#workflow" className="hover:text-orange">How it works</a>
            <a href="#developers" className="hover:text-orange">Developers</a>
          </nav>
          <div className="flex items-center gap-3">
            <Button asChild variant="ghost" className="hidden sm:inline-flex">
              <Link href="/studio">Sign in</Link>
            </Button>
            <Button asChild size="sm">
              <Link href="/studio">Open Studio <ArrowRight /></Link>
            </Button>
          </div>
        </div>
      </header>

      <section className="relative border-b-2 border-ink">
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(#d9cfbf55_1px,transparent_1px),linear-gradient(90deg,#d9cfbf55_1px,transparent_1px)] bg-[size:40px_40px] [mask-image:linear-gradient(to_bottom,black,transparent_85%)]" />
        <div className="relative mx-auto grid max-w-[1440px] gap-14 px-5 py-20 sm:px-8 sm:py-28 lg:grid-cols-[0.92fr_1.08fr] lg:items-center lg:px-12 lg:py-32">
          <motion.div initial={{ opacity: 0, x: -30 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.6 }}>
            <Badge variant="default" className="mb-7 normal-case tracking-normal">
              <span className="size-2 rounded-full bg-teal" />
              The programmable company brain
            </Badge>
            <h1 className="max-w-[760px] font-display text-[clamp(3.5rem,7vw,7rem)] font-bold leading-[0.86] tracking-[-0.065em]">
              Your agents know the model.
              <span className="mt-2 block text-orange">Give them the company.</span>
            </h1>
            <p className="mt-8 max-w-2xl text-lg leading-8 text-ink-2 sm:text-xl">
              Komponist turns documents and company tools into a reviewed context graph with citations — then serves it to humans and AI agents without the archaeology.
            </p>
            <div className="mt-9 flex flex-wrap gap-4">
              <Button asChild size="lg" variant="dark">
                <Link href="/studio">Try the company brain <ArrowRight /></Link>
              </Button>
              <Button asChild size="lg" variant="outline">
                <a href="#platform">See what is inside <ChevronRight /></a>
              </Button>
            </div>
            <div className="mt-8 flex flex-wrap gap-x-6 gap-y-2 font-mono text-xs text-muted">
              <span className="flex items-center gap-2"><Check className="size-4 text-teal" /> Human-reviewed</span>
              <span className="flex items-center gap-2"><Check className="size-4 text-teal" /> Cited by default</span>
              <span className="flex items-center gap-2"><Check className="size-4 text-teal" /> MCP-ready</span>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, rotate: 1.5, y: 30 }}
            animate={{ opacity: 1, rotate: 0, y: 0 }}
            transition={{ duration: 0.65, delay: 0.1 }}
            className="relative lg:pl-6"
          >
            <div className="overflow-hidden rounded-xl border-2 border-ink bg-white shadow-[10px_10px_0_#e8641b]">
              <div className="flex items-center justify-between border-b-2 border-ink bg-ink px-4 py-3 text-white">
                <div className="flex items-center gap-2">
                  <span className="size-2.5 rounded-full bg-orange" />
                  <span className="size-2.5 rounded-full bg-teal" />
                  <span className="size-2.5 rounded-full bg-white/25" />
                  <span className="ml-2 font-mono text-xs text-white/60">company-brain / live</span>
                </div>
                <Badge variant="dark" className="border-white/20 px-2 py-0.5 text-[9px]">Local MVP</Badge>
              </div>

              <div className="grid min-h-[480px] md:grid-cols-[180px_1fr]">
                <div className="border-b-2 border-ink bg-paper-2 p-4 md:border-b-0 md:border-r-2">
                  <p className="mb-4 font-mono text-[10px] font-bold uppercase tracking-wider text-muted">Sources</p>
                  {[
                    ['UP', 'Product strategy', '6 facts'],
                    ['UP', 'Security policy', '6 facts'],
                    ['NO', 'Notion workspace', 'connected'],
                  ].map(([abbr, name, meta], index) => (
                    <div key={name} className="mb-2 flex items-center gap-2 rounded-md border border-line bg-white p-2.5 shadow-sm">
                      <span className={`grid size-8 place-items-center rounded border border-line font-mono text-[9px] font-bold ${index === 2 ? 'bg-ink text-white' : 'bg-warning-soft text-orange-dark'}`}>{abbr}</span>
                      <span className="min-w-0">
                        <strong className="block truncate text-xs">{name}</strong>
                        <span className="font-mono text-[9px] text-muted">{meta}</span>
                      </span>
                    </div>
                  ))}
                  <div className="mt-5 rounded-md border border-dashed border-muted/50 p-3 text-center font-mono text-[10px] text-muted">+ connect source</div>
                </div>

                <div className="relative overflow-hidden p-5 sm:p-7">
                  <div className="mb-6 flex items-center justify-between">
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-wider text-muted">Context graph</p>
                      <h3 className="mt-1 text-xl font-bold">MVP launch</h3>
                    </div>
                    <Badge variant="teal"><span className="size-1.5 rounded-full bg-teal" /> confirmed</Badge>
                  </div>

                  <div className="relative mx-auto h-52 max-w-md">
                    <svg className="absolute inset-0 size-full" viewBox="0 0 440 210" aria-hidden="true">
                      <path d="M218 102 L78 46 M218 102 L365 45 M218 102 L82 168 M218 102 L360 168" fill="none" stroke="#d6a679" strokeWidth="2" strokeDasharray="5 5" />
                    </svg>
                    <div className="absolute left-1/2 top-1/2 z-10 flex size-24 -translate-x-1/2 -translate-y-1/2 flex-col items-center justify-center rounded-full border-2 border-ink bg-orange text-center text-white shadow-[4px_4px_0_#201c15]">
                      <Network className="mb-1 size-5" />
                      <span className="text-xs font-bold">Project</span>
                    </div>
                    <GraphNode className="left-0 top-2" icon={Sparkles} label="Goal" detail="10 partners" color="bg-success-soft" />
                    <GraphNode className="right-0 top-1" icon={GitBranch} label="Decision" detail="4 entity types" color="bg-info-soft" />
                    <GraphNode className="bottom-0 left-0" icon={ShieldCheck} label="Constraint" detail="Review first" color="bg-warning-soft" />
                    <GraphNode className="bottom-0 right-0" icon={FileText} label="Evidence" detail="strategy.md" color="bg-paper-2" />
                  </div>

                  <div className="mt-5 rounded-lg border-2 border-ink bg-paper p-4 shadow-[4px_4px_0_#0e8a7d]">
                    <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-muted">
                      <Search className="size-3.5" /> Answer compiled
                    </div>
                    <p className="mt-2 text-sm font-semibold leading-6">Ship upload → extraction → review → cited search.</p>
                    <p className="mt-2 font-mono text-[10px] text-orange-dark">[1] 01-product-strategy.md</p>
                  </div>
                </div>
              </div>
            </div>
            <div className="absolute -bottom-7 -left-2 rotate-[-2deg] rounded-md border-2 border-ink bg-[#f4d06f] px-4 py-3 text-sm font-bold shadow-[4px_4px_0_#201c15]">
              No Dave required. ✓
            </div>
          </motion.div>
        </div>
      </section>

      <section className="border-b-2 border-ink bg-[#eee9db] px-5 py-5 sm:px-8 lg:px-12">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-center gap-x-10 gap-y-3 font-mono text-xs font-semibold uppercase tracking-wider text-ink-2">
          <span className="text-orange-dark">One brain underneath</span>
          <span>Humans</span><span className="text-faint">+</span><span>Claude</span><span className="text-faint">+</span><span>OpenAI</span><span className="text-faint">+</span><span>Codex</span><span className="text-faint">+</span><span>Your agent</span>
        </div>
      </section>

      <section id="platform" className="mx-auto max-w-[1440px] px-5 py-24 sm:px-8 lg:px-12 lg:py-32">
        <motion.div {...reveal} className="max-w-4xl">
          <Badge variant="orange">The whole brain</Badge>
          <h2 className="mt-6 font-display text-[clamp(2.8rem,5.8vw,6rem)] font-bold leading-[0.92] tracking-[-0.055em]">
            Company context without the <span className="text-orange">document archaeology.</span>
          </h2>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-ink-2">Six primitives, one governed graph. Start with uploads today; connect every agent tomorrow.</p>
        </motion.div>

        <div className="mt-14 grid border-l-2 border-t-2 border-ink md:grid-cols-2 xl:grid-cols-3">
          {features.map((feature, index) => (
            <motion.article
              key={feature.title}
              {...reveal}
              transition={{ ...reveal.transition, delay: index * 0.05 }}
              className="group min-h-[330px] border-b-2 border-r-2 border-ink bg-white p-7 transition-colors hover:bg-warning-soft sm:p-9"
            >
              <div className="flex items-start justify-between">
                <span className="font-mono text-xs text-muted">{feature.number}</span>
                <span className="grid size-12 place-items-center rounded-lg border-2 border-ink bg-paper shadow-[3px_3px_0_#201c15] transition-transform group-hover:-rotate-3 group-hover:scale-105">
                  <feature.icon className="size-5" />
                </span>
              </div>
              <h3 className="mt-12 text-2xl font-bold tracking-tight">{feature.title}</h3>
              <p className="mt-3 leading-7 text-ink-2">{feature.copy}</p>
              <div className="mt-6 font-mono text-[10px] font-semibold uppercase tracking-wider text-orange-dark">{feature.tag} →</div>
            </motion.article>
          ))}
        </div>
      </section>

      <section id="workflow" className="border-y-2 border-ink bg-ink text-white">
        <div className="mx-auto grid max-w-[1440px] lg:grid-cols-[0.75fr_1.25fr]">
          <motion.div {...reveal} className="border-b-2 border-white/20 p-8 sm:p-12 lg:border-b-0 lg:border-r-2 lg:p-16">
            <Badge variant="dark" className="border-white/30">Three steps</Badge>
            <h2 className="mt-7 text-4xl font-bold leading-tight tracking-tight sm:text-6xl">From messy source to useful brain.</h2>
            <p className="mt-6 max-w-lg text-lg leading-8 text-white/65">No migration project. No ontology workshop. No mysterious answer without a source.</p>
          </motion.div>
          <div>
            {steps.map(([title, copy, Icon], index) => (
              <motion.div key={title} {...reveal} className="grid gap-5 border-b-2 border-white/20 p-8 last:border-b-0 sm:grid-cols-[64px_1fr] sm:p-10">
                <span className="grid size-14 place-items-center rounded-lg border-2 border-white/70 bg-orange text-lg font-bold shadow-[4px_4px_0_#fff]">0{index + 1}</span>
                <div>
                  <div className="flex items-center gap-3"><Icon className="size-5 text-orange-light" /><h3 className="text-2xl font-bold">{title}</h3></div>
                  <p className="mt-2 max-w-xl leading-7 text-white/65">{copy}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <section id="developers" className="mx-auto grid max-w-[1440px] gap-14 px-5 py-24 sm:px-8 lg:grid-cols-2 lg:items-center lg:px-12 lg:py-32">
        <motion.div {...reveal}>
          <Badge variant="teal">Agent interface</Badge>
          <h2 className="mt-6 text-5xl font-bold leading-[0.95] tracking-[-0.05em] sm:text-7xl">A company brain you can call.</h2>
          <p className="mt-6 max-w-xl text-lg leading-8 text-ink-2">Use the same confirmed context in Studio, your own product, or any MCP-compatible coding agent.</p>
          <ul className="mt-8 space-y-4">
            {['Organization-scoped API keys', 'Citations and entity metadata', 'Revocable access for every agent'].map(item => (
              <li key={item} className="flex items-center gap-3 font-semibold"><span className="grid size-6 place-items-center rounded-full bg-success-soft text-teal"><Check className="size-4" /></span>{item}</li>
            ))}
          </ul>
          <Button asChild className="mt-9" variant="outline"><Link href="/studio">Open API settings <ArrowRight /></Link></Button>
        </motion.div>

        <motion.div {...reveal} className="overflow-hidden rounded-xl border-2 border-ink bg-code-bg text-code-text shadow-[9px_9px_0_#0e8a7d]">
          <div className="flex items-center justify-between border-b border-white/15 bg-code-surface px-5 py-3 font-mono text-xs text-code-muted">
            <span>ask-komponist.ts</span><span>MCP · API</span>
          </div>
          <pre className="overflow-x-auto p-6 font-mono text-[13px] leading-7 sm:p-8"><code><span className="text-code-keyword">const</span> context = <span className="text-code-keyword">await</span> brain.search({'{'}{`\n`}  query: <span className="text-code-string">&quot;What did we decide?&quot;</span>,{`\n`}  types: [<span className="text-code-string">&quot;Decision&quot;</span>, <span className="text-code-string">&quot;Constraint&quot;</span>],{`\n`}  status: <span className="text-code-string">&quot;confirmed&quot;</span>{`\n`}{'}'}){`\n\n`}<span className="text-code-comment">// 3 facts · 3 citations · org isolated</span>{`\n`}<span className="text-code-number">context.evidence</span></code></pre>
          <div className="border-t border-white/15 bg-black/20 px-6 py-4 font-mono text-xs text-teal-light">✓ Context compiled. Nothing invented.</div>
        </motion.div>
      </section>

      <section className="border-y-2 border-ink bg-orange px-5 py-20 sm:px-8 lg:px-12">
        <motion.div {...reveal} className="mx-auto flex max-w-[1200px] flex-col items-start justify-between gap-8 lg:flex-row lg:items-center">
          <div>
            <p className="font-mono text-xs font-bold uppercase tracking-widest text-ink/70">Local MVP · ready to test</p>
            <h2 className="mt-3 max-w-4xl text-4xl font-bold leading-tight tracking-tight sm:text-6xl">Give your company&apos;s decisions object permanence.</h2>
          </div>
          <Button asChild size="lg" variant="dark" className="shrink-0 shadow-[6px_6px_0_#fff]">
            <Link href="/studio">Open Komponist <ArrowRight /></Link>
          </Button>
        </motion.div>
      </section>

      <footer className="bg-paper px-5 py-12 sm:px-8 lg:px-12">
        <div className="mx-auto flex max-w-[1440px] flex-col justify-between gap-8 sm:flex-row sm:items-end">
          <div><div className="flex items-center gap-3 text-xl font-bold"><BrandMark /> Komponist</div><p className="mt-4 max-w-md text-sm text-muted">The programmable company brain. Built by people who also forgot where the roadmap lives.</p></div>
          <div className="font-mono text-xs text-muted">© 2026 Komponist · SELECT * FROM company_brain;</div>
        </div>
      </footer>
    </main>
  )
}

function GraphNode({ className, icon: Icon, label, detail, color }: { className: string; icon: typeof Sparkles; label: string; detail: string; color: string }) {
  return (
    <div className={`absolute flex w-32 items-center gap-2 rounded-lg border-2 border-ink ${color} p-2.5 shadow-[3px_3px_0_#201c15] ${className}`}>
      <Icon className="size-4 shrink-0" />
      <span className="min-w-0"><strong className="block text-xs">{label}</strong><span className="block truncate font-mono text-[8px] text-muted">{detail}</span></span>
    </div>
  )
}
