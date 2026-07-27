'use client'

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Check,
  CheckCircle2,
  Clock3,
  FileCheck2,
  FolderKanban,
  GitMerge,
  Loader2,
  PencilLine,
  ShieldCheck,
  Sparkles,
  Target,
  X,
  XCircle,
  type LucideIcon,
} from 'lucide-react'
import EvidenceChip from './EvidenceChip'
import { Badge } from './ui/badge'
import { Button } from './ui/button'

type FactCardProps = {
  id: string
  position: number
  total: number
  type: string
  statement: string
  detail?: string
  confidence?: string | number
  createdAt?: string
  evidence: Array<{
    id: string
    source: string
    reference: string
    url?: string
    source_date?: string
  }>
  relatedTo?: Array<{ id: string; statement: string; score: number }>
  onConfirm: (id: string, statement: string) => Promise<unknown>
  onReject: (id: string) => Promise<unknown>
  onMerge: (id: string, targetId: string) => Promise<unknown>
}

const TYPE_META: Record<string, {
  icon: LucideIcon
  tone: string
  badge: 'default' | 'orange' | 'teal' | 'dark'
}> = {
  Decision: { icon: FileCheck2, tone: 'border-info/30 bg-info-soft text-info', badge: 'default' },
  Goal: { icon: Target, tone: 'border-teal/30 bg-success-soft text-teal', badge: 'teal' },
  Constraint: { icon: ShieldCheck, tone: 'border-orange/30 bg-warning-soft text-orange-dark', badge: 'orange' },
  Project: { icon: FolderKanban, tone: 'border-line bg-paper-2 text-ink', badge: 'dark' },
}

function confidenceMeta(value?: string | number) {
  if (typeof value === 'number') {
    const percentage = Math.round(value * 100)
    return {
      label: `${percentage}% confidence`,
      tone: percentage >= 80 ? 'text-teal' : percentage >= 55 ? 'text-orange-dark' : 'text-danger',
    }
  }

  const normalized = value?.toLocaleLowerCase()
  if (normalized === 'high') return { label: 'High confidence', tone: 'text-teal' }
  if (normalized === 'medium') return { label: 'Medium confidence', tone: 'text-orange-dark' }
  if (normalized === 'low') return { label: 'Low confidence', tone: 'text-danger' }
  return { label: 'Unscored', tone: 'text-muted' }
}

function formatDate(value?: string) {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return new Intl.DateTimeFormat('en', { day: '2-digit', month: 'short', year: 'numeric' }).format(date)
}

function evidenceDate(value?: string) {
  if (!value) return undefined
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return undefined
  return new Intl.DateTimeFormat('en', { day: '2-digit', month: 'short' }).format(date)
}

export default function FactCard({
  id,
  position,
  total,
  type,
  statement: initialStatement,
  detail,
  confidence,
  createdAt,
  evidence,
  relatedTo,
  onConfirm,
  onReject,
  onMerge,
}: FactCardProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [statement, setStatement] = useState(initialStatement)
  const [showMerge, setShowMerge] = useState(false)
  const [pendingAction, setPendingAction] = useState<'confirm' | 'reject' | 'merge' | null>(null)

  useEffect(() => setStatement(initialStatement), [initialStatement])

  const typeMeta = TYPE_META[type] ?? { icon: Sparkles, tone: 'border-line bg-paper-2 text-ink', badge: 'default' as const }
  const TypeIcon = typeMeta.icon
  const confidenceInfo = confidenceMeta(confidence)
  const createdLabel = formatDate(createdAt)
  const hasDuplicates = Boolean(relatedTo?.length)
  const isBusy = pendingAction !== null

  const runAction = async (action: 'confirm' | 'reject' | 'merge', callback: () => Promise<unknown>) => {
    setPendingAction(action)
    try {
      await callback()
    } finally {
      setPendingAction(null)
    }
  }

  const confirm = () => {
    const cleanedStatement = statement.trim()
    if (!cleanedStatement) return Promise.resolve()
    return runAction('confirm', () => onConfirm(id, cleanedStatement))
  }

  const cancelEdit = () => {
    setStatement(initialStatement)
    setIsEditing(false)
  }

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: 28, scale: 0.98 }}
      transition={{ duration: 0.22 }}
      className="overflow-hidden rounded-xl border-2 border-ink bg-white shadow-[5px_5px_0_var(--color-shadow-soft)]"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b-2 border-ink bg-paper-2 px-4 py-3 sm:px-5">
        <div className="flex items-center gap-3">
          <span className="grid size-8 place-items-center rounded-md border-2 border-ink bg-ink font-mono text-[9px] font-bold text-white">
            {String(position).padStart(2, '0')}
          </span>
          <span className={`grid size-8 place-items-center rounded-md border ${typeMeta.tone}`}><TypeIcon className="size-4" /></span>
          <Badge variant={typeMeta.badge}>{type}</Badge>
        </div>
        <div className="flex items-center gap-3 font-mono text-[9px] font-bold uppercase tracking-wider">
          <span className={confidenceInfo.tone}>{confidenceInfo.label}</span>
          <span className="text-faint">{position}/{total}</span>
        </div>
      </div>

      <div className="p-5 sm:p-6">
        {createdLabel && (
          <div className="mb-4 flex items-center gap-1.5 font-mono text-[9px] font-bold uppercase tracking-wider text-faint">
            <Clock3 className="size-3" /> Proposed {createdLabel}
          </div>
        )}

        {isEditing ? (
          <div>
            <label htmlFor={`statement-${id}`} className="mb-2 block font-mono text-[10px] font-bold uppercase tracking-wider text-muted">Fact statement</label>
            <textarea
              id={`statement-${id}`}
              value={statement}
              onChange={(event) => setStatement(event.target.value)}
              onKeyDown={(event) => {
                if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
                  event.preventDefault()
                  void confirm()
                }
              }}
              rows={4}
              autoFocus
              className="w-full resize-y rounded-lg border-2 border-ink bg-white p-4 text-base font-semibold leading-6 outline-none shadow-[3px_3px_0_var(--color-orange)] transition focus:-translate-y-0.5 focus:shadow-[5px_5px_0_var(--color-orange)]"
            />
            <div className="mt-2 flex items-center justify-between gap-3 text-[10px] text-muted">
              <span>Keep the statement clear, atomic, and reusable.</span>
              <span className="hidden font-mono sm:inline">⌘ Enter to confirm</span>
            </div>
          </div>
        ) : (
          <p className="max-w-3xl text-lg font-bold leading-7 text-ink sm:text-xl sm:leading-8">{statement}</p>
        )}

        {detail && <p className="mt-3 max-w-3xl text-sm leading-6 text-muted">{detail}</p>}

        {evidence.length > 0 ? (
          <div className="mt-6 rounded-lg border border-line bg-paper-2 p-3.5">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 font-mono text-[9px] font-bold uppercase tracking-[0.12em] text-muted">
                <CheckCircle2 className="size-3.5 text-teal" /> Supporting evidence
              </div>
              <span className="font-mono text-[9px] text-faint">{evidence.length} source{evidence.length === 1 ? '' : 's'}</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {evidence.map((item) => (
                <EvidenceChip
                  key={item.id}
                  source={item.source}
                  reference={item.reference}
                  url={item.url}
                  date={evidenceDate(item.source_date)}
                />
              ))}
            </div>
          </div>
        ) : (
          <div className="mt-6 flex items-center gap-2 rounded-lg border border-dashed border-orange bg-warning-soft px-3 py-2.5 text-xs font-semibold text-orange-dark">
            <XCircle className="size-4" /> No source evidence is attached to this fact.
          </div>
        )}

        {hasDuplicates && (
          <div className="mt-4 overflow-hidden rounded-lg border-2 border-orange bg-warning-soft">
            <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
              <div>
                <div className="flex items-center gap-2 text-xs font-bold text-orange-dark"><GitMerge className="size-4" /> Possible duplicate</div>
                <p className="mt-1 text-[11px] text-muted">A similar fact already exists in the brain.</p>
              </div>
              <Button type="button" variant="outline" size="sm" onClick={() => setShowMerge((current) => !current)} disabled={isBusy}>
                {showMerge ? <><X /> Close</> : <><GitMerge /> Review match</>}
              </Button>
            </div>

            {showMerge && (
              <div className="space-y-2 border-t-2 border-orange p-3">
                {relatedTo?.map((related) => (
                  <button
                    key={related.id}
                    type="button"
                    disabled={isBusy}
                    onClick={() => void runAction('merge', () => onMerge(id, related.id))}
                    className="group flex w-full items-center justify-between gap-4 rounded-md border border-line bg-white p-3 text-left transition hover:border-ink disabled:opacity-50"
                  >
                    <span className="text-xs font-semibold leading-5 text-ink">{related.statement}</span>
                    <span className="shrink-0 rounded-full bg-paper-2 px-2 py-1 font-mono text-[9px] font-bold text-muted">
                      {pendingAction === 'merge' ? <Loader2 className="size-3 animate-spin" /> : `${Math.round(related.score * 100)}% match`}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="flex flex-col-reverse gap-3 border-t-2 border-ink bg-paper px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
        {isEditing ? (
          <>
            <Button type="button" variant="ghost" size="sm" onClick={cancelEdit} disabled={isBusy}><X /> Cancel</Button>
            <Button type="button" size="sm" onClick={() => void confirm()} disabled={isBusy || !statement.trim()}>
              {pendingAction === 'confirm' ? <Loader2 className="animate-spin" /> : <Check />} Save & confirm
            </Button>
          </>
        ) : (
          <>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => void runAction('reject', () => onReject(id))}
              disabled={isBusy}
              className="text-danger hover:bg-danger-soft hover:text-danger"
            >
              {pendingAction === 'reject' ? <Loader2 className="animate-spin" /> : <XCircle />} Reject
            </Button>
            <div className="flex gap-2">
              <Button type="button" variant="outline" size="sm" onClick={() => setIsEditing(true)} disabled={isBusy}><PencilLine /> Edit</Button>
              <Button type="button" size="sm" onClick={() => void confirm()} disabled={isBusy}>
                {pendingAction === 'confirm' ? <Loader2 className="animate-spin" /> : <CheckCircle2 />} Confirm fact
              </Button>
            </div>
          </>
        )}
      </div>
    </motion.article>
  )
}
