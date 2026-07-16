'use client'

import { useState } from 'react'
import { motion } from 'framer-motion'
import { BrainCircuit, ChevronDown, ChevronUp, UserRound } from 'lucide-react'
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
      <div className={`grid size-9 shrink-0 place-items-center rounded-lg border-2 border-ink shadow-[2px_2px_0_#201c15] ${isUser ? 'bg-ink text-white' : 'bg-orange text-white'}`}>
        {isUser ? <UserRound className="size-4" /> : <BrainCircuit className="size-4" />}
      </div>
      <div className={`min-w-0 ${isUser ? 'max-w-[78%]' : 'flex-1'}`}>
        <div className={`mb-1 font-mono text-[9px] font-bold uppercase tracking-wider text-muted ${isUser ? 'text-right' : ''}`}>{isUser ? 'You' : 'Komponist'}</div>
        <div className={`whitespace-pre-wrap rounded-xl border-2 border-ink px-4 py-3 leading-7 shadow-[3px_3px_0_#201c15] ${isUser ? 'rounded-tr-sm bg-ink text-white shadow-[3px_3px_0_#e8641b]' : 'rounded-tl-sm bg-white text-ink-2'}`}>
          {renderedContent}
          {isStreaming && <span className="ml-1 inline-block animate-pulse text-orange">▋</span>}
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
