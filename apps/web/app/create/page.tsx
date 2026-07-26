'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  AlignLeft, ArrowUpRight, BookOpenCheck, Check, Clock3, Download,
  ExternalLink, FileText, LoaderCircle, Presentation, Sparkles, Trash2, UsersRound,
  WandSparkles,
  type LucideIcon,
} from 'lucide-react'
import AppLayout from '../../components/AppLayout'
import StudioTopbar from '../../components/StudioTopbar'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { API_URL, apiFetch, getActiveOrgId } from '../../lib/api'

type ArtifactType = 'presentation' | 'briefing' | 'summary'
type Language = 'english' | 'german'
type DownloadFormat = 'pdf' | 'markdown' | 'pptx'

type ArtifactSource = {
  id: string
  entity_id: string
  type: string
  statement: string
  source: string
  reference: string
  excerpt?: string
  url?: string
  title?: string
  page?: number
  line_start?: number
  line_end?: number
  komponist_path?: string
}

type ArtifactBlock = {
  layout?: 'statement' | 'list' | 'split' | 'timeline' | 'quote'
  eyebrow?: string
  title: string
  body: string
  bullets: string[]
  takeaway?: string
  speaker_notes: string
  source_ids: string[]
}

type Artifact = {
  id: string
  artifact_type: ArtifactType
  title: string
  topic: string
  audience: string
  language: Language
  content: {
    title: string
    subtitle: string
    executive_summary: string
    source_ids: string[]
    blocks: ArtifactBlock[]
  }
  sources: ArtifactSource[]
  created_at: string
  updated_at: string
}

type ArtifactSummary = Pick<
  Artifact,
  'id' | 'artifact_type' | 'title' | 'topic' | 'audience' | 'language' | 'created_at' | 'updated_at'
>

const formats: Array<{
  value: ArtifactType
  label: string
  description: string
  output: string
  icon: LucideIcon
}> = [
  {
    value: 'presentation',
    label: 'Presentation',
    description: 'An editable, consultant-ready deck with cited slides.',
    output: 'PowerPoint',
    icon: Presentation,
  },
  {
    value: 'briefing',
    label: 'Briefing',
    description: 'A structured decision brief for leaders and stakeholders.',
    output: 'Markdown',
    icon: FileText,
  },
  {
    value: 'summary',
    label: 'Summary',
    description: 'A concise synthesis of the context that matters right now.',
    output: 'Markdown',
    icon: AlignLeft,
  },
]

const audienceOptions = [
  'Leadership team',
  'Client stakeholders',
  'Project team',
  'Board members',
  'New team members',
]

function formatDate(value: string) {
  return new Intl.DateTimeFormat('en', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value))
}

function ArtifactIcon({ type, className = 'size-4' }: { type: ArtifactType; className?: string }) {
  const Icon = formats.find((format) => format.value === type)?.icon ?? FileText
  return <Icon className={className} />
}

function sourceHref(source: ArtifactSource) {
  return source.komponist_path || `/sources?evidence=${encodeURIComponent(source.id)}`
}

function sourceLocation(source: ArtifactSource) {
  if (source.page != null) return `Page ${source.page}`
  if (source.line_start != null) {
    return source.line_end && source.line_end !== source.line_start
      ? `Lines ${source.line_start}–${source.line_end}`
      : `Line ${source.line_start}`
  }
  return {
    slack: 'Thread passage',
    notion: 'Notion passage',
    google: 'Drive passage',
    upload: 'Uploaded passage',
    manual: 'Local passage',
  }[source.source] || 'Source passage'
}

export default function CreatePage() {
  const [artifacts, setArtifacts] = useState<ArtifactSummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selected, setSelected] = useState<Artifact | null>(null)
  const [artifactType, setArtifactType] = useState<ArtifactType>('presentation')
  const [topic, setTopic] = useState('Company overview')
  const [audience, setAudience] = useState('Leadership team')
  const [language, setLanguage] = useState<Language>('english')
  const [instructions, setInstructions] = useState('')
  const [loading, setLoading] = useState(true)
  const [artifactLoading, setArtifactLoading] = useState(false)
  const [artifactOffset, setArtifactOffset] = useState(0)
  const [artifactsHaveMore, setArtifactsHaveMore] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [downloadFormat, setDownloadFormat] = useState<DownloadFormat>('pdf')
  const [error, setError] = useState<string | null>(null)

  const downloadOptions = useMemo<Array<{ value: DownloadFormat; label: string }>>(
    () => selected?.artifact_type === 'presentation'
      ? [
          { value: 'pdf', label: 'PDF' },
          { value: 'pptx', label: 'PowerPoint' },
          { value: 'markdown', label: 'Markdown' },
        ]
      : [
          { value: 'pdf', label: 'PDF' },
          { value: 'markdown', label: 'Markdown' },
        ],
    [selected?.artifact_type],
  )

  useEffect(() => {
    setDownloadFormat('pdf')
  }, [selected?.id])

  const loadArtifacts = useCallback(async (offset = 0, append = false) => {
    if (!append) setLoading(true)
    try {
      const orgId = getActiveOrgId()
      const response = await apiFetch(
        `${API_URL}/artifacts?org_id=${encodeURIComponent(orgId)}&limit=24&offset=${offset}`,
      )
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not load deliverables')
      const summaries: ArtifactSummary[] = payload.artifacts ?? []
      setArtifacts(current => append ? [...current, ...summaries] : summaries)
      setArtifactOffset(offset)
      setArtifactsHaveMore(Boolean(payload.has_more))
      const requestedId = typeof window === 'undefined'
        ? null
        : new URLSearchParams(window.location.search).get('artifact')
      setSelectedId((current) => (
        requestedId || current || summaries[0]?.id || null
      ))
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load deliverables')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadArtifacts()
  }, [loadArtifacts])

  useEffect(() => {
    if (!selectedId) {
      setSelected(null)
      return
    }
    let cancelled = false
    setArtifactLoading(true)
    const loadSelected = async () => {
      try {
        const orgId = getActiveOrgId()
        const response = await apiFetch(
          `${API_URL}/artifacts/${selectedId}?org_id=${encodeURIComponent(orgId)}`,
        )
        const payload = await response.json()
        if (!response.ok) throw new Error(payload.detail || 'Could not open deliverable')
        if (!cancelled) setSelected(payload)
      } catch (loadError) {
        if (!cancelled) {
          setSelected(null)
          setError(loadError instanceof Error ? loadError.message : 'Could not open deliverable')
        }
      } finally {
        if (!cancelled) setArtifactLoading(false)
      }
    }
    void loadSelected()
    return () => { cancelled = true }
  }, [selectedId])

  const generate = async () => {
    if (topic.trim().length < 3 || generating) return
    setGenerating(true)
    setError(null)
    try {
      const orgId = getActiveOrgId()
      const response = await apiFetch(
        `${API_URL}/artifacts/generate?org_id=${encodeURIComponent(orgId)}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            artifact_type: artifactType,
            topic: topic.trim(),
            audience,
            language,
            instructions: instructions.trim(),
          }),
        },
      )
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not create deliverable')
      const summary: ArtifactSummary = payload
      setArtifacts((current) => [summary, ...current.filter((item) => item.id !== payload.id)])
      setSelected(payload)
      setSelectedId(payload.id)
    } catch (generateError) {
      setError(generateError instanceof Error ? generateError.message : 'Could not create deliverable')
    } finally {
      setGenerating(false)
    }
  }

  const download = async (artifact: Artifact, format: DownloadFormat) => {
    setDownloading(true)
    setError(null)
    try {
      const orgId = getActiveOrgId()
      const response = await apiFetch(
        `${API_URL}/artifacts/${artifact.id}/download?org_id=${encodeURIComponent(orgId)}&format=${format}`,
      )
      if (!response.ok) {
        const payload = await response.json().catch(() => null)
        throw new Error(payload?.detail || 'Could not download deliverable')
      }
      const blob = await response.blob()
      const disposition = response.headers.get('Content-Disposition') || ''
      const extension = format === 'markdown' ? 'md' : format
      const fallback = `komponist-${artifact.artifact_type}.${extension}`
      const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || fallback
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (downloadError) {
      setError(downloadError instanceof Error ? downloadError.message : 'Could not download deliverable')
    } finally {
      setDownloading(false)
    }
  }

  const remove = async (artifact: ArtifactSummary) => {
    if (!window.confirm(`Delete “${artifact.title}”?`)) return
    setError(null)
    try {
      const orgId = getActiveOrgId()
      const response = await apiFetch(
        `${API_URL}/artifacts/${artifact.id}?org_id=${encodeURIComponent(orgId)}`,
        { method: 'DELETE' },
      )
      if (!response.ok) throw new Error('Could not delete deliverable')
      setArtifacts((current) => {
        const next = current.filter((item) => item.id !== artifact.id)
        setSelectedId((currentId) => currentId === artifact.id ? next[0]?.id ?? null : currentId)
        if (selected?.id === artifact.id) setSelected(null)
        return next
      })
    } catch (removeError) {
      setError(removeError instanceof Error ? removeError.message : 'Could not delete deliverable')
    }
  }

  return (
    <AppLayout>
      <StudioTopbar
        section="Compose"
        title="Compose"
        description="Turn reviewed company context into cited client-ready work"
        icon={WandSparkles}
        actions={selected ? (
          <div className="flex items-center gap-2">
            <select
              value={downloadFormat}
              onChange={(event) => setDownloadFormat(event.target.value as DownloadFormat)}
              aria-label="Download format"
              className="h-9 rounded-md border-2 border-ink bg-white px-2 text-xs font-bold outline-none focus:ring-2 focus:ring-orange/30"
            >
              {downloadOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            <Button size="sm" onClick={() => void download(selected, downloadFormat)} disabled={downloading}>
              {downloading ? <LoaderCircle className="animate-spin" /> : <Download />}
              <span className="hidden sm:inline">Download</span>
            </Button>
          </div>
        ) : undefined}
      />

      <div className="min-h-[calc(100vh-78px)] bg-paper p-4 sm:p-6 lg:p-8">
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}
            className="mx-auto mb-5 max-w-[1500px] rounded-xl border-2 border-danger bg-danger-soft px-4 py-3 text-sm font-semibold text-danger"
            role="alert"
          >
            {error}
          </motion.div>
        )}

        <div className="mx-auto grid max-w-[1500px] gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
          <aside className="space-y-5">
            <section className="overflow-hidden rounded-2xl border-2 border-ink bg-white shadow-[5px_5px_0_#201c15]">
              <div className="border-b-2 border-ink bg-ink p-5 text-white">
                <div className="flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-orange-light">
                  <Sparkles className="size-3.5" /> Compose from your brain
                </div>
                <h2 className="mt-2 text-2xl font-bold">Create something useful.</h2>
                <p className="mt-2 text-sm leading-6 text-white/65">Every factual section stays linked to reviewed source material.</p>
              </div>

              <div className="space-y-5 p-5">
                <fieldset>
                  <legend className="mb-2 font-mono text-[10px] font-bold uppercase tracking-wider text-muted">Format</legend>
                  <div className="grid grid-cols-3 gap-2">
                    {formats.map((format) => {
                      const Icon = format.icon
                      const active = artifactType === format.value
                      return (
                        <button
                          key={format.value}
                          type="button"
                          onClick={() => setArtifactType(format.value)}
                          className={`relative rounded-xl border-2 p-3 text-left transition ${active ? 'border-ink bg-warning-soft shadow-[3px_3px_0_#201c15]' : 'border-line bg-paper-2 hover:border-ink'}`}
                          aria-pressed={active}
                        >
                          <Icon className={`size-5 ${active ? 'text-orange-dark' : 'text-muted'}`} />
                          <span className="mt-2 block truncate text-[11px] font-bold">{format.label}</span>
                          {active && <Check className="absolute right-2 top-2 size-3.5 text-orange-dark" />}
                        </button>
                      )
                    })}
                  </div>
                </fieldset>

                <label className="block">
                  <span className="mb-2 block font-mono text-[10px] font-bold uppercase tracking-wider text-muted">What should it cover?</span>
                  <textarea
                    value={topic}
                    onChange={(event) => setTopic(event.target.value)}
                    rows={3}
                    placeholder="e.g. Northstar pilot progress and constraints"
                    className="w-full resize-none rounded-xl border-2 border-ink bg-paper px-3.5 py-3 text-sm font-semibold outline-none transition focus:bg-white focus:ring-2 focus:ring-orange/30"
                  />
                </label>

                <div className="grid grid-cols-2 gap-3">
                  <label className="block">
                    <span className="mb-2 block font-mono text-[10px] font-bold uppercase tracking-wider text-muted">Audience</span>
                    <select
                      value={audience}
                      onChange={(event) => setAudience(event.target.value)}
                      className="h-11 w-full rounded-xl border-2 border-ink bg-white px-3 text-xs font-semibold outline-none focus:ring-2 focus:ring-orange/30"
                    >
                      {audienceOptions.map((option) => <option key={option}>{option}</option>)}
                    </select>
                  </label>
                  <label className="block">
                    <span className="mb-2 block font-mono text-[10px] font-bold uppercase tracking-wider text-muted">Language</span>
                    <select
                      value={language}
                      onChange={(event) => setLanguage(event.target.value as Language)}
                      className="h-11 w-full rounded-xl border-2 border-ink bg-white px-3 text-xs font-semibold outline-none focus:ring-2 focus:ring-orange/30"
                    >
                      <option value="english">English</option>
                      <option value="german">German</option>
                    </select>
                  </label>
                </div>

                <label className="block">
                  <span className="mb-2 block font-mono text-[10px] font-bold uppercase tracking-wider text-muted">Instructions <span className="normal-case tracking-normal text-faint">(optional)</span></span>
                  <textarea
                    value={instructions}
                    onChange={(event) => setInstructions(event.target.value)}
                    rows={3}
                    placeholder="e.g. Lead with the launch decision, compare current priorities, and close with documented constraints…"
                    className="w-full resize-none rounded-xl border-2 border-line bg-white px-3 py-3 text-sm leading-5 outline-none transition focus:border-ink focus:ring-2 focus:ring-orange/30"
                  />
                </label>

                <Button className="w-full" size="lg" onClick={() => void generate()} disabled={generating || topic.trim().length < 3}>
                  {generating ? <LoaderCircle className="animate-spin" /> : <WandSparkles />}
                  {generating ? 'Composing from context…' : `Create ${formats.find((format) => format.value === artifactType)?.label}`}
                </Button>

                <div className="flex items-start gap-2.5 rounded-xl border border-teal/25 bg-success-soft p-3 text-xs leading-5 text-teal-dark">
                  <BookOpenCheck className="mt-0.5 size-4 shrink-0" />
                  Only confirmed knowledge you can access is included. Every citation opens the exact source passage in Komponist.
                </div>
              </div>
            </section>

            <section className="rounded-2xl border-2 border-ink bg-white p-4 shadow-[4px_4px_0_#d9cfc0]">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-bold">Recent deliverables</h3>
                <Badge variant="default" className="px-2 py-0.5 text-[9px]">Private</Badge>
              </div>
              <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
                {loading ? (
                  <div className="grid h-24 place-items-center text-muted"><LoaderCircle className="animate-spin" /></div>
                ) : artifacts.length === 0 ? (
                  <p className="rounded-xl bg-paper-2 p-4 text-center text-xs leading-5 text-muted">Your generated work will appear here.</p>
                ) : artifacts.map((artifact) => (
                  <button
                    type="button"
                    key={artifact.id}
                    onClick={() => setSelectedId(artifact.id)}
                    className={`group flex w-full items-start gap-3 rounded-xl border-2 p-3 text-left transition ${selectedId === artifact.id ? 'border-ink bg-warning-soft' : 'border-transparent bg-paper-2 hover:border-line'}`}
                  >
                    <span className="grid size-8 shrink-0 place-items-center rounded-lg border border-ink bg-white"><ArtifactIcon type={artifact.artifact_type} /></span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-xs font-bold">{artifact.title}</span>
                      <span className="mt-1 flex items-center gap-1 font-mono text-[9px] text-muted"><Clock3 className="size-3" /> {formatDate(artifact.updated_at)}</span>
                    </span>
                  </button>
                ))}
                {artifactsHaveMore && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="w-full"
                    onClick={() => void loadArtifacts(artifactOffset + 24, true)}
                  >
                    Load older deliverables
                  </Button>
                )}
              </div>
            </section>
          </aside>

          <main className="min-w-0">
            <AnimatePresence mode="wait">
              {generating ? (
                <GeneratingState type={artifactType} />
              ) : artifactLoading ? (
                <div className="grid min-h-[680px] place-items-center rounded-2xl border-2 border-ink bg-white">
                  <LoaderCircle className="size-6 animate-spin text-orange-dark" />
                </div>
              ) : selected ? (
                <ArtifactPreview
                  key={selected.id}
                  artifact={selected}
                  onDelete={() => void remove(selected)}
                />
              ) : (
                <EmptyState />
              )}
            </AnimatePresence>
          </main>
        </div>
      </div>
    </AppLayout>
  )
}

function GeneratingState({ type }: { type: ArtifactType }) {
  const steps = ['Selecting visible context', 'Composing the narrative', 'Attaching citations']
  return (
    <motion.div
      key="generating" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="grid min-h-[680px] place-items-center rounded-2xl border-2 border-ink bg-white p-8 shadow-[6px_6px_0_#d9cfc0]"
    >
      <div className="max-w-md text-center">
        <motion.div
          animate={{ rotate: 360 }} transition={{ duration: 3, repeat: Infinity, ease: 'linear' }}
          className="mx-auto grid size-20 place-items-center rounded-2xl border-2 border-ink bg-orange text-white shadow-[5px_5px_0_#201c15]"
        >
          <ArtifactIcon type={type} className="size-9" />
        </motion.div>
        <h2 className="mt-7 text-3xl font-bold">Composing your {type}</h2>
        <p className="mt-3 text-sm leading-6 text-muted">Komponist is turning reviewed knowledge into a deliverable you can verify and edit.</p>
        <div className="mt-7 space-y-2 text-left">
          {steps.map((step, index) => (
            <motion.div
              key={step}
              initial={{ opacity: 0.25 }} animate={{ opacity: [0.25, 1, 0.25] }}
              transition={{ delay: index * 0.5, duration: 1.5, repeat: Infinity }}
              className="flex items-center gap-3 rounded-xl border border-line bg-paper-2 px-4 py-3 text-xs font-semibold"
            >
              <span className="grid size-6 place-items-center rounded-full bg-ink font-mono text-[9px] text-white">{index + 1}</span>{step}
            </motion.div>
          ))}
        </div>
      </div>
    </motion.div>
  )
}

function EmptyState() {
  return (
    <motion.div
      key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      className="relative grid min-h-[680px] overflow-hidden rounded-2xl border-2 border-dashed border-ink/40 bg-white/60 p-8 text-center"
    >
      <div className="m-auto max-w-lg">
        <span className="mx-auto grid size-16 place-items-center rounded-2xl border-2 border-ink bg-warning-soft shadow-[4px_4px_0_#201c15]"><WandSparkles className="size-7 text-orange-dark" /></span>
        <h2 className="mt-6 text-3xl font-bold tracking-tight">Your company context, presentation-ready.</h2>
        <p className="mt-3 leading-7 text-muted">Choose a format and topic. Komponist will build the first draft from confirmed graph knowledge and keep every claim connected to its source.</p>
        <div className="mt-7 flex flex-wrap justify-center gap-2">
          {['Editable output', 'Evidence included', 'Permission aware'].map((label) => <Badge key={label} variant="default">{label}</Badge>)}
        </div>
      </div>
    </motion.div>
  )
}

function ArtifactPreview({
  artifact, onDelete,
}: {
  artifact: Artifact
  onDelete: () => void
}) {
  const sourceNumbers = useMemo(() => {
    const result = new Map<string, number[]>()
    artifact.sources.forEach((source, index) => {
      result.set(source.entity_id, [...(result.get(source.entity_id) ?? []), index + 1])
    })
    return result
  }, [artifact.sources])

  const citations = (entityIds: string[]) => Array.from(new Set(
    entityIds.flatMap((entityId) => sourceNumbers.get(entityId) ?? []),
  )).sort((a, b) => a - b)

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
      className="overflow-hidden rounded-2xl border-2 border-ink bg-white shadow-[6px_6px_0_#201c15]"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b-2 border-ink bg-paper-2 px-5 py-4">
        <div className="flex min-w-0 items-center gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl border-2 border-ink bg-white shadow-[2px_2px_0_#201c15]"><ArtifactIcon type={artifact.artifact_type} /></span>
          <div className="min-w-0">
            <div className="flex items-center gap-2"><Badge variant="orange" className="px-2 py-0.5 text-[9px]">{artifact.artifact_type}</Badge><span className="font-mono text-[9px] text-muted">{formatDate(artifact.updated_at)}</span></div>
            <h2 className="mt-1 truncate text-lg font-bold">{artifact.title}</h2>
          </div>
        </div>
        <div className="flex gap-2">
          <Badge variant="teal"><Download className="size-3.5" /> Cited exports</Badge>
          <Button variant="ghost" size="icon" onClick={onDelete} aria-label="Delete deliverable"><Trash2 /></Button>
        </div>
      </div>

      <div className="max-h-[calc(100vh-190px)] overflow-y-auto bg-paper p-4 sm:p-7">
        <div className="mx-auto max-w-5xl space-y-5">
          {artifact.artifact_type === 'presentation' ? (
            <PresentationPreview artifact={artifact} citations={citations} />
          ) : (
            <DocumentPreview artifact={artifact} citations={citations} />
          )}

          <section className="rounded-2xl border-2 border-ink bg-white p-5 shadow-[4px_4px_0_#d9cfc0] sm:p-7">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="font-mono text-[10px] font-bold uppercase tracking-wider text-orange-dark">Evidence appendix</p>
                <h3 className="mt-1 text-2xl font-bold">Sources</h3>
              </div>
              <Badge variant="teal"><BookOpenCheck className="size-3.5" /> {artifact.sources.length} citations</Badge>
            </div>
            <div className="mt-5 grid gap-3 lg:grid-cols-2">
              {artifact.sources.map((source, index) => (
                <article key={source.id} className="group rounded-xl border border-line bg-paper-2 p-4 transition hover:border-orange/50 hover:bg-white">
                  <div className="flex items-start gap-3">
                    <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-ink font-mono text-[10px] font-bold text-white">{index + 1}</span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2"><strong className="break-all text-xs">{source.title || source.reference}</strong><Badge variant="default" className="px-2 py-0 text-[8px]">{source.type}</Badge><span className="font-mono text-[8px] font-bold uppercase tracking-wide text-orange-dark">{sourceLocation(source)}</span></div>
                      <p className="mt-2 border-l-2 border-orange/40 pl-3 text-xs leading-5 text-muted">{source.excerpt || source.statement}</p>
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        <Button asChild variant="outline" size="sm">
                          <Link href={sourceHref(source)}><BookOpenCheck /> Open highlighted passage <ArrowUpRight /></Link>
                        </Button>
                        {source.url && /^https?:\/\//i.test(source.url) && (
                          <Button asChild variant="ghost" size="sm">
                            <a href={source.url} target="_blank" rel="noreferrer">Original <ExternalLink /></a>
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </section>
        </div>
      </div>
    </motion.section>
  )
}

function CitationMarkers({ numbers, sources }: { numbers: number[]; sources: ArtifactSource[] }) {
  if (!numbers.length) return null
  return (
    <span className="ml-2 inline-flex flex-wrap gap-1 align-middle font-mono text-[9px] font-bold text-orange-dark">
      {numbers.map((number) => {
        const source = sources[number - 1]
        return source ? (
          <Link
            key={number}
            href={sourceHref(source)}
            title={`Open ${source.reference} · ${sourceLocation(source)}`}
            className="rounded bg-orange/10 px-1 py-0.5 transition hover:bg-orange hover:text-white"
          >
            [{number}]
          </Link>
        ) : <span key={number}>[{number}]</span>
      })}
    </span>
  )
}

function PresentationPreview({ artifact, citations }: { artifact: Artifact; citations: (ids: string[]) => number[] }) {
  const slides = [
    {
      layout: 'statement' as const, eyebrow: 'Executive synthesis',
      title: 'Executive summary', body: artifact.content.executive_summary,
      bullets: [] as string[], takeaway: '', source_ids: artifact.content.source_ids,
    },
    ...artifact.content.blocks,
  ]
  return (
    <>
      <div className="aspect-video overflow-hidden rounded-2xl border-2 border-ink bg-ink p-7 text-white shadow-[5px_5px_0_#e8641b] sm:p-12">
        <div className="font-mono text-[9px] font-bold uppercase tracking-[0.16em] text-orange-light">Composed from reviewed company context</div>
        <div className="flex h-full flex-col justify-center border-l-4 border-orange pl-6 sm:pl-10">
          <h1 className="max-w-3xl text-3xl font-bold leading-tight sm:text-5xl">{artifact.content.title}</h1>
          <p className="mt-5 max-w-2xl text-sm text-white/60 sm:text-lg">{artifact.content.subtitle}</p>
        </div>
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        {slides.map((slide, index) => (
          <article key={`${slide.title}-${index}`} className="relative flex aspect-video min-h-[300px] flex-col overflow-hidden rounded-2xl border-2 border-ink bg-white p-5 shadow-[4px_4px_0_#d9cfc0] sm:p-7">
            <div className="absolute inset-x-0 top-0 h-1.5 bg-orange" />
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-mono text-[8px] font-bold uppercase tracking-[0.14em] text-teal">{slide.eyebrow || 'Key context'}</p>
                <h3 className="mt-2 text-xl font-bold leading-tight sm:text-2xl">{slide.title}</h3>
              </div>
              <span className="font-mono text-[10px] text-muted">{String(index + 2).padStart(2, '0')}</span>
            </div>
            <div className={`mt-4 grid min-h-0 flex-1 gap-4 ${slide.takeaway ? 'sm:grid-cols-[minmax(0,1fr)_34%]' : ''}`}>
              <div className="min-w-0">
                {slide.body && <p className={`${slide.layout === 'quote' ? 'border-l-4 border-orange pl-4 text-lg font-semibold' : ''} line-clamp-5 text-sm leading-6 text-ink-2`}>{slide.body}</p>}
                {!!slide.bullets?.length && (
                  <ul className={`mt-4 ${slide.layout === 'split' ? 'grid grid-cols-2 gap-2' : 'space-y-2'} text-xs leading-5 sm:text-sm`}>
                    {slide.bullets.map((bullet, bulletIndex) => (
                      <li key={bullet} className={`flex gap-2 ${slide.layout === 'split' || slide.layout === 'timeline' ? 'rounded-lg border border-line bg-paper-2 p-2.5' : ''}`}>
                        <span className={`${slide.layout === 'timeline' ? 'grid size-5 shrink-0 place-items-center rounded-full bg-orange font-mono text-[8px] font-bold text-white' : 'mt-2 size-1.5 shrink-0 rounded-full bg-orange'}`}>{slide.layout === 'timeline' ? bulletIndex + 1 : ''}</span>
                        <span className="line-clamp-3">{bullet}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              {slide.takeaway && (
                <aside className="rounded-xl border border-line bg-warning-soft p-3">
                  <p className="font-mono text-[8px] font-bold uppercase tracking-wider text-orange-dark">Key takeaway</p>
                  <p className="mt-2 line-clamp-5 text-xs font-bold leading-5 sm:text-sm">{slide.takeaway}</p>
                </aside>
              )}
            </div>
            <div className="mt-3 border-t border-line pt-2"><CitationMarkers numbers={citations(slide.source_ids)} sources={artifact.sources} /></div>
          </article>
        ))}
      </div>
    </>
  )
}

function DocumentPreview({ artifact, citations }: { artifact: Artifact; citations: (ids: string[]) => number[] }) {
  return (
    <article className="rounded-2xl border-2 border-ink bg-white p-6 shadow-[5px_5px_0_#d9cfc0] sm:p-10 lg:p-14">
      <div className="border-b-2 border-ink pb-8">
        <Badge variant="orange">{artifact.artifact_type}</Badge>
        <h1 className="mt-5 max-w-3xl text-4xl font-bold leading-tight sm:text-5xl">{artifact.content.title}</h1>
        <p className="mt-4 text-lg text-muted">{artifact.content.subtitle}</p>
        <div className="mt-5 flex items-center gap-2 text-xs text-muted"><UsersRound className="size-4" /> Prepared for {artifact.audience}</div>
      </div>
      <section className="py-8">
        <p className="font-mono text-[10px] font-bold uppercase tracking-wider text-orange-dark">Executive summary</p>
        <div className="mt-3 rounded-2xl border border-orange/30 bg-warning-soft p-5 sm:p-6">
          <p className="text-lg leading-8 text-ink-2">{artifact.content.executive_summary}<CitationMarkers numbers={citations(artifact.content.source_ids)} sources={artifact.sources} /></p>
        </div>
      </section>
      {artifact.content.blocks.map((block, index) => (
        <section key={`${block.title}-${index}`} className="border-t border-line py-8">
          <div className="flex items-start gap-4">
            <span className="grid size-8 shrink-0 place-items-center rounded-lg border border-ink bg-ink font-mono text-[10px] font-bold text-white">{String(index + 1).padStart(2, '0')}</span>
            <div className="min-w-0 flex-1">
              <p className="font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-teal">{block.eyebrow || 'Key context'}</p>
              <h2 className="mt-2 text-2xl font-bold">{block.title}</h2>
            </div>
          </div>
          {block.body && <p className="mt-4 leading-7 text-ink-2">{block.body}<CitationMarkers numbers={citations(block.source_ids)} sources={artifact.sources} /></p>}
          {!!block.bullets.length && <ul className={`mt-5 ${block.layout === 'split' ? 'grid gap-3 sm:grid-cols-2' : 'space-y-3'}`}>{block.bullets.map((bullet) => <li key={bullet} className={`flex gap-3 leading-6 ${block.layout === 'split' ? 'rounded-xl border border-line bg-paper-2 p-4' : ''}`}><span className="mt-2.5 size-1.5 shrink-0 rounded-full bg-orange" /><span>{bullet}<CitationMarkers numbers={citations(block.source_ids)} sources={artifact.sources} /></span></li>)}</ul>}
          {block.takeaway && (
            <div className="mt-5 rounded-xl border border-orange/30 bg-warning-soft p-4">
              <p className="font-mono text-[9px] font-bold uppercase tracking-wider text-orange-dark">Key takeaway</p>
              <p className="mt-2 font-bold leading-6">{block.takeaway}</p>
            </div>
          )}
        </section>
      ))}
    </article>
  )
}
