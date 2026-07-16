'use client'

import { useEffect, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import {
  BrainCircuit, Check, ChevronDown, ChevronUp, FileCheck2, Network,
  Search, UserRound,
} from 'lucide-react'
import EvidenceChip from './EvidenceChip'
import { Badge } from './ui/badge'

interface Source {
  id: string
  entity_id: string
  type: string
  statement: string
  source: string
  reference: string
  url?: string
  excerpt?: string
  source_date?: string
}

interface ChatMessageProps {
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
  isStreaming?: boolean
}

export default function ChatMessage({ role, content, sources, isStreaming }: ChatMessageProps) {
  const isUser = role === 'user'
  const isThinking = !isUser && isStreaming && content.length === 0
  const [showAllSources, setShowAllSources] = useState(false)
  const visibleSources = showAllSources ? sources : sources?.slice(0, 3)

  const renderedContent = content.split(/(\[\d+\])/g).map((part, index) =>
    /^\[\d+\]$/.test(part) ? (
      <span className="mx-0.5 inline-grid h-5 min-w-5 place-items-center rounded-full bg-warning-soft px-1.5 align-px font-mono text-[10px] font-bold text-orange-dark" key={`${part}-${index}`}>{part.slice(1, -1)}</span>
    ) : part
  )

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28 }}
      data-chat-role={role}
      className={isUser ? 'flex flex-row-reverse gap-3' : 'flex gap-3'}
    >
      <div className={`relative grid size-9 shrink-0 place-items-center rounded-lg border-2 border-ink shadow-[2px_2px_0_#201c15] ${isUser ? 'bg-ink text-white' : 'bg-orange text-white'}`}>
        {isThinking && (
          <motion.span
            className="absolute -inset-1.5 -z-10 rounded-xl border-2 border-orange/40"
            animate={{ scale: [0.92, 1.2], opacity: [0.8, 0] }}
            transition={{ duration: 1.4, repeat: Infinity, ease: 'easeOut' }}
          />
        )}
        {isUser ? <UserRound className="size-4" /> : <BrainCircuit className="size-4" />}
      </div>
      <div className={`min-w-0 ${isUser ? 'max-w-[78%]' : 'flex-1'}`}>
        <div className={`mb-1 font-mono text-[9px] font-bold uppercase tracking-wider text-muted ${isUser ? 'text-right' : ''}`}>{isUser ? 'You' : 'Komponist'}</div>
        <div className={`overflow-hidden whitespace-pre-wrap rounded-xl border-2 border-ink leading-7 shadow-[3px_3px_0_#201c15] ${isUser ? 'rounded-tr-sm bg-ink px-4 py-3 text-white shadow-[3px_3px_0_#e8641b]' : isThinking ? 'rounded-tl-sm bg-paper-2' : 'rounded-tl-sm bg-white px-4 py-3 text-ink-2'}`}>
          {isThinking ? (
            <ThinkingIndicator />
          ) : (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }}>
              {renderedContent}
              {isStreaming && <span className="ml-1 inline-block animate-pulse text-orange">▋</span>}
            </motion.div>
          )}
        </div>
        {sources && sources.length > 0 && (
          <div className="mt-3 overflow-hidden rounded-xl border-2 border-ink bg-white shadow-[3px_3px_0_#0e8a7d]">
            <div className="flex items-center justify-between border-b-2 border-ink bg-paper-2 px-4 py-3 font-mono text-[10px] font-bold uppercase tracking-wider text-muted">
              <span>Evidence bundle</span>
              <span>{sources.length} {sources.length === 1 ? 'source' : 'sources'}</span>
            </div>
            <div className="flex flex-col">
              {visibleSources?.map((source, index) => (
                <div className="grid grid-cols-[28px_minmax(0,1fr)] gap-3 border-b border-line p-4 last:border-b-0" key={source.id}>
                  <span className="grid size-7 place-items-center rounded-full border border-line bg-paper font-mono text-[10px] font-bold text-orange-dark">{index + 1}</span>
                  <div className="min-w-0">
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <Badge variant={source.type === 'Constraint' ? 'orange' : source.type === 'Goal' ? 'teal' : 'default'} className="px-2 py-0.5 text-[9px]">{source.type}</Badge>
                      <EvidenceChip
                        source={source.source}
                        reference={source.reference}
                        url={source.url}
                        date={source.source_date?.slice(0, 10)}
                      />
                    </div>
                    <p className="text-sm leading-6 text-ink-2">{source.statement}</p>
                    {source.excerpt && <blockquote className="mt-2 border-l-2 border-orange-light pl-3 text-xs leading-5 text-muted">“{source.excerpt}”</blockquote>}
                  </div>
                </div>
              ))}
            </div>
            {sources.length > 3 && (
              <button
                className="flex w-full items-center justify-center gap-2 border-t-2 border-ink bg-paper-2 px-4 py-3 text-xs font-bold text-ink-2 hover:bg-paper-3"
                onClick={() => setShowAllSources((current) => !current)}
              >
                {showAllSources
                  ? 'Show fewer sources'
                  : `Show ${sources.length - 3} more ${sources.length - 3 === 1 ? 'source' : 'sources'}`}
                {showAllSources ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
              </button>
            )}
          </div>
        )}
      </div>
    </motion.div>
  )
}

const THINKING_STEPS = [
  { label: 'Searching confirmed knowledge', icon: Search },
  { label: 'Checking evidence and relationships', icon: Network },
  { label: 'Composing a grounded answer', icon: FileCheck2 },
] as const

function ThinkingIndicator() {
  const [activeStep, setActiveStep] = useState(0)
  const reduceMotion = useReducedMotion()

  useEffect(() => {
    const evidenceTimer = window.setTimeout(() => setActiveStep(1), 900)
    const answerTimer = window.setTimeout(() => setActiveStep(2), 2200)
    return () => {
      window.clearTimeout(evidenceTimer)
      window.clearTimeout(answerTimer)
    }
  }, [])

  const ActiveIcon = THINKING_STEPS[activeStep].icon

  return (
    <div className="min-w-0 px-4 py-4 sm:min-w-[430px]" role="status" aria-live="polite" aria-label={THINKING_STEPS[activeStep].label}>
      <div className="flex items-center gap-3">
        <span className="relative grid size-9 shrink-0 place-items-center rounded-lg border-2 border-ink bg-white shadow-[2px_2px_0_#201c15]">
          <motion.span
            className="absolute inset-1 rounded-full border-2 border-line border-t-orange"
            animate={reduceMotion ? undefined : { rotate: 360 }}
            transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
          />
          <ActiveIcon className="size-3.5" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-orange-dark">
            Komponist is thinking
            <span className="flex gap-1" aria-hidden="true">
              {[0, 1, 2].map((dot) => (
                <motion.span
                  key={dot}
                  className="size-1 rounded-full bg-orange"
                  animate={reduceMotion ? undefined : { y: [0, -3, 0], opacity: [0.35, 1, 0.35] }}
                  transition={{ duration: 0.9, repeat: Infinity, delay: dot * 0.14 }}
                />
              ))}
            </span>
          </div>
          <AnimatePresence mode="wait" initial={false}>
            <motion.p
              key={activeStep}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.2 }}
              className="mt-1 truncate text-sm font-semibold text-ink"
            >
              {THINKING_STEPS[activeStep].label}
            </motion.p>
          </AnimatePresence>
        </div>
      </div>

      <div className="relative mt-4 grid grid-cols-3 gap-2 border-t-2 border-line pt-3">
        {THINKING_STEPS.map((step, index) => {
          const Icon = step.icon
          const complete = index < activeStep
          const active = index === activeStep
          return (
            <div key={step.label} className={`flex items-center gap-1.5 font-mono text-[8px] font-bold uppercase tracking-wide ${active ? 'text-orange-dark' : complete ? 'text-teal-dark' : 'text-faint'}`}>
              <span className={`grid size-4 shrink-0 place-items-center rounded-full border ${active ? 'border-orange bg-warning-soft' : complete ? 'border-teal bg-success-soft' : 'border-line bg-white'}`}>
                {complete ? <Check className="size-2.5" /> : <Icon className="size-2.5" />}
              </span>
              <span className="hidden truncate sm:block">{index === 0 ? 'Search' : index === 1 ? 'Verify' : 'Answer'}</span>
            </div>
          )
        })}
        <motion.span
          className="absolute -top-0.5 left-0 h-0.5 bg-orange"
          animate={{ width: `${((activeStep + 1) / THINKING_STEPS.length) * 100}%` }}
          transition={{ duration: reduceMotion ? 0 : 0.35, ease: 'easeOut' }}
        />
      </div>
    </div>
  )
}
