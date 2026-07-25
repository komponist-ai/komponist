'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Activity, ArrowRight, Bot, Check, CheckCircle2, ChevronRight, Circle,
  Clock3, FileText, Loader2, Pause, Play, Plus, RadioTower, RotateCcw,
  Send, ShieldCheck, Sparkles, UserRound, UsersRound, X,
} from 'lucide-react'
import AppLayout from '../../components/AppLayout'
import StudioTopbar from '../../components/StudioTopbar'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { API_URL, apiFetch, getActiveOrgId } from '../../lib/api'

type Department = { id: string; name: string; color?: string }
type WorkroomTask = {
  id: string
  title: string
  description: string
  status: 'todo' | 'in_progress' | 'completed'
  assignee_type: 'agent' | 'human'
  assignee_name: string
  artifact_id?: string | null
}
type WorkroomSource = {
  id: string
  title?: string
  reference?: string
  excerpt?: string
  page?: number
  line_start?: number
  line_end?: number
  komponist_path?: string
}
type WorkroomRun = {
  id: string
  task_id?: string | null
  agent_name: string
  instruction: string
  status:
    | 'queued'
    | 'running'
    | 'pause_requested'
    | 'paused'
    | 'cancel_requested'
    | 'cancelled'
    | 'awaiting_approval'
    | 'completed'
    | 'failed'
    | 'redirected'
  current_step: string
  context_snapshot: {
    findings?: Array<{ id: string; type: string; statement: string; source_ids: string[] }>
    sources?: WorkroomSource[]
  }
  result: {
    summary?: string
    finding_count?: number
    source_count?: number
    artifact_id?: string
    artifact_title?: string
    compose_path?: string
  }
  redirected_from_run_id?: string | null
  created_at: string
}
type WorkroomEvent = {
  id: number
  run_id?: string | null
  actor_type: 'human' | 'agent' | 'system'
  actor_name: string
  event_type: string
  message: string
  payload: Record<string, unknown>
  created_at: string
}
type RoomRole = 'owner' | 'editor' | 'approver' | 'viewer'
type RoomVisibility = 'organization' | 'departments' | 'private'
type WorkroomMember = {
  id: string
  user_id: string
  name: string
  email?: string | null
  room_role: RoomRole
  status: string
}
type WorkroomSummary = {
  id: string
  title: string
  objective: string
  status: string
  visibility: RoomVisibility
  room_role: RoomRole
  department_ids: string[]
  creator: { id: string; name: string }
  member_count: number
  task_count: number
  completed_task_count: number
  latest_run?: WorkroomRun | null
  updated_at: string
}
type Workroom = Omit<
  WorkroomSummary,
  'task_count' | 'completed_task_count' | 'latest_run' | 'member_count'
> & {
  members: WorkroomMember[]
  tasks: WorkroomTask[]
  runs: WorkroomRun[]
  events: WorkroomEvent[]
}

// Mirrors the server's room permission table so the UI hides actions the API
// would reject anyway.
const roomPermissions: Record<RoomRole, ReadonlyArray<string>> = {
  owner: ['view', 'comment', 'edit', 'approve', 'manage'],
  editor: ['view', 'comment', 'edit'],
  approver: ['view', 'comment', 'approve'],
  viewer: ['view', 'comment'],
}

function roomCan(role: RoomRole | undefined, permission: string) {
  return !!role && roomPermissions[role].includes(permission)
}

const runLabels: Record<WorkroomRun['status'], string> = {
  queued: 'Queued',
  running: 'Working',
  // An external model call cannot be interrupted, so the agent stops at the
  // next safe step rather than immediately.
  pause_requested: 'Pausing',
  paused: 'Paused',
  cancel_requested: 'Cancelling',
  cancelled: 'Cancelled',
  awaiting_approval: 'Needs approval',
  completed: 'Completed',
  failed: 'Failed',
  redirected: 'Redirected',
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('en', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function sourceLocation(source: WorkroomSource) {
  if (source.page != null) return `Page ${source.page}`
  if (source.line_start != null) {
    return source.line_end && source.line_end !== source.line_start
      ? `Lines ${source.line_start}–${source.line_end}`
      : `Line ${source.line_start}`
  }
  return 'Source passage'
}

function RunStatus({ run }: { run: WorkroomRun }) {
  const tone = {
    awaiting_approval: 'border-orange/40 bg-warning-soft text-orange-dark',
    completed: 'border-teal/30 bg-success-soft text-teal',
    failed: 'border-danger/30 bg-danger-soft text-danger',
    cancelled: 'border-line bg-paper-2 text-muted',
    cancel_requested: 'border-line bg-paper-2 text-ink-2',
    paused: 'border-line bg-paper-2 text-ink-2',
    pause_requested: 'border-line bg-paper-2 text-ink-2',
    redirected: 'border-info/30 bg-info-soft text-info',
    queued: 'border-line bg-paper-2 text-muted',
    running: 'border-orange/40 bg-warning-soft text-orange-dark',
  }[run.status]
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[9px] font-bold uppercase tracking-wider ${tone}`}>
      {['running', 'pause_requested', 'cancel_requested'].includes(run.status) && (
        <span className="size-1.5 animate-pulse rounded-full bg-orange" />
      )}
      {runLabels[run.status]}
    </span>
  )
}

export default function WorkroomsPage() {
  const [rooms, setRooms] = useState<WorkroomSummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [room, setRoom] = useState<Workroom | null>(null)
  const [departments, setDepartments] = useState<Department[]>([])
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newObjective, setNewObjective] = useState('')
  const [newDepartments, setNewDepartments] = useState<string[]>([])
  const [newTask, setNewTask] = useState('')
  const [direction, setDirection] = useState('')

  const loadRooms = useCallback(async () => {
    const orgId = getActiveOrgId()
    const response = await apiFetch(`${API_URL}/workrooms?org_id=${encodeURIComponent(orgId)}`)
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.detail || 'Could not load Workrooms')
    setRooms(payload.workrooms)
    setSelectedId((current) => current ?? payload.workrooms[0]?.id ?? null)
  }, [])

  const loadRoom = useCallback(async (roomId: string, quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      const orgId = getActiveOrgId()
      const response = await apiFetch(`${API_URL}/workrooms/${roomId}?org_id=${encodeURIComponent(orgId)}`)
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not load Workroom')
      setRoom(payload)
    } finally {
      if (!quiet) setLoading(false)
    }
  }, [])

  useEffect(() => {
    const bootstrap = async () => {
      setLoading(true)
      setError(null)
      try {
        const orgId = getActiveOrgId()
        const [roomsResponse, departmentsResponse] = await Promise.all([
          apiFetch(`${API_URL}/workrooms?org_id=${encodeURIComponent(orgId)}`),
          apiFetch(`${API_URL}/auth/organizations/${encodeURIComponent(orgId)}/departments`),
        ])
        const roomsPayload = await roomsResponse.json()
        const departmentsPayload = await departmentsResponse.json()
        if (!roomsResponse.ok) throw new Error(roomsPayload.detail || 'Could not load Workrooms')
        setRooms(roomsPayload.workrooms)
        setDepartments(departmentsResponse.ok ? departmentsPayload.departments ?? [] : [])
        setSelectedId(roomsPayload.workrooms[0]?.id ?? null)
        if (!roomsPayload.workrooms.length) setShowCreate(true)
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : 'Could not load Workrooms')
      } finally {
        setLoading(false)
      }
    }
    void bootstrap()
  }, [])

  useEffect(() => {
    if (selectedId) void loadRoom(selectedId)
    else setRoom(null)
  }, [loadRoom, selectedId])

  useEffect(() => {
    if (!selectedId) return
    const orgId = getActiveOrgId()
    const after = room?.events.at(-1)?.id ?? 0
    const stream = new EventSource(
      `${API_URL}/workrooms/${selectedId}/events?org_id=${encodeURIComponent(orgId)}&after=${after}`,
      { withCredentials: true },
    )
    stream.onmessage = () => {
      void Promise.all([loadRoom(selectedId, true), loadRooms()])
    }
    return () => stream.close()
  }, [loadRoom, loadRooms, room?.events, selectedId])

  const activeRun = useMemo(
    () => room?.runs.find((run) => !['completed', 'cancelled', 'redirected', 'failed'].includes(run.status))
      ?? room?.runs[0]
      ?? null,
    [room?.runs],
  )

  // The server is the authority on room permissions; this only avoids
  // offering actions that would come back as 403.
  const canEdit = roomCan(room?.room_role, 'edit') && room?.status !== 'archived'
  const canApprove = roomCan(room?.room_role, 'approve') && room?.status !== 'archived'

  const mutate = async (path: string, init: RequestInit = {}) => {
    setWorking(true)
    setError(null)
    try {
      const orgId = getActiveOrgId()
      const response = await apiFetch(`${API_URL}${path}${path.includes('?') ? '&' : '?'}org_id=${encodeURIComponent(orgId)}`, init)
      const payload = response.status === 204 ? null : await response.json()
      if (!response.ok) throw new Error(payload?.detail || 'The action could not be completed')
      if (selectedId) await loadRoom(selectedId, true)
      await loadRooms()
      return payload
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : 'The action could not be completed')
      return null
    } finally {
      setWorking(false)
    }
  }

  const createRoom = async () => {
    if (!newTitle.trim() || !newObjective.trim()) return
    const created = await mutate('/workrooms', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: newTitle,
        objective: newObjective,
        department_ids: newDepartments,
      }),
    })
    if (created) {
      setSelectedId(created.id)
      setNewTitle('')
      setNewObjective('')
      setNewDepartments([])
      setShowCreate(false)
    }
  }

  const addTask = async () => {
    if (!room || !newTask.trim()) return
    const created = await mutate(`/workrooms/${room.id}/tasks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: newTask,
        description: newTask,
        assignee_type: 'agent',
        assignee_name: 'Komponist Analyst',
      }),
    })
    if (created) setNewTask('')
  }

  const startAgent = async (taskId?: string) => {
    if (!room) return
    await mutate(`/workrooms/${room.id}/runs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId, instruction: direction }),
    })
    setDirection('')
  }

  const redirect = async () => {
    if (!activeRun || !direction.trim()) return
    await mutate(`/workroom-runs/${activeRun.id}/redirect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instruction: direction }),
    })
    setDirection('')
  }

  return (
    <AppLayout>
      <StudioTopbar
        section="Multiplayer AI"
        title="Workrooms"
        description="People and agents working from the same governed context"
        icon={RadioTower}
        actions={
          <Button size="sm" onClick={() => setShowCreate(true)}>
            <Plus /> New room
          </Button>
        }
      />

      <main className="min-h-[calc(100vh-78px)] bg-paper">
        <AnimatePresence>
          {showCreate && (
            <motion.section
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden border-b-2 border-ink bg-ink text-white"
            >
              <div className="mx-auto grid max-w-[1440px] gap-6 px-5 py-7 sm:px-8 lg:grid-cols-[1fr_1.35fr_auto] lg:items-end lg:px-10">
                <label className="block">
                  <span className="font-mono text-[9px] font-bold uppercase tracking-[0.16em] text-orange-light">Room name</span>
                  <input
                    value={newTitle}
                    onChange={(event) => setNewTitle(event.target.value)}
                    placeholder="Prepare the board meeting"
                    className="mt-2 w-full rounded-lg border-2 border-paper-3/30 bg-white/10 px-4 py-3 text-sm text-white outline-none placeholder:text-paper-3/50 focus:border-orange-light"
                  />
                </label>
                <label className="block">
                  <span className="font-mono text-[9px] font-bold uppercase tracking-[0.16em] text-orange-light">Shared objective</span>
                  <input
                    value={newObjective}
                    onChange={(event) => setNewObjective(event.target.value)}
                    placeholder="Research the current priorities and prepare a cited briefing"
                    className="mt-2 w-full rounded-lg border-2 border-paper-3/30 bg-white/10 px-4 py-3 text-sm text-white outline-none placeholder:text-paper-3/50 focus:border-orange-light"
                  />
                </label>
                <div className="flex gap-2">
                  <Button onClick={() => void createRoom()} disabled={working || !newTitle.trim() || !newObjective.trim()}>
                    {working ? <Loader2 className="animate-spin" /> : <Sparkles />} Create
                  </Button>
                  <Button variant="ghost" className="text-white" onClick={() => setShowCreate(false)}><X /></Button>
                </div>
                {departments.length > 0 && (
                  <div className="lg:col-span-3">
                    <p className="mb-2 font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-paper-3">Knowledge scope · no selection means organization-wide facts only</p>
                    <div className="flex flex-wrap gap-2">
                      {departments.map((department) => {
                        const selected = newDepartments.includes(department.id)
                        return (
                          <button
                            key={department.id}
                            type="button"
                            onClick={() => setNewDepartments((current) => selected ? current.filter((id) => id !== department.id) : [...current, department.id])}
                            className={`rounded-full border px-3 py-1.5 text-xs font-bold transition ${selected ? 'border-orange-light bg-orange text-white' : 'border-paper-3/30 text-paper-3 hover:border-paper-3'}`}
                          >
                            {selected && <Check className="mr-1 inline size-3" />}{department.name}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>
            </motion.section>
          )}
        </AnimatePresence>

        {error && (
          <div className="mx-auto max-w-[1440px] px-5 pt-5 sm:px-8 lg:px-10">
            <div className="flex items-center justify-between rounded-lg border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger">
              {error}<button onClick={() => setError(null)} aria-label="Dismiss"><X className="size-4" /></button>
            </div>
          </div>
        )}

        <div className="mx-auto grid max-w-[1440px] gap-0 px-0 lg:grid-cols-[270px_minmax(0,1fr)_330px]">
          <aside className="border-b-2 border-ink bg-paper-2 p-4 lg:min-h-[calc(100vh-78px)] lg:border-b-0 lg:border-r-2">
            <div className="mb-3 flex items-center justify-between">
              <span className="font-mono text-[9px] font-bold uppercase tracking-[0.16em] text-muted">Active rooms</span>
              <span className="font-mono text-[10px] text-muted">{rooms.length.toString().padStart(2, '0')}</span>
            </div>
            <div className="flex gap-3 overflow-x-auto pb-2 lg:block lg:space-y-2 lg:overflow-visible">
              {rooms.map((item) => {
                const active = item.id === selectedId
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setSelectedId(item.id)}
                    className={`w-[280px] max-w-[82vw] shrink-0 rounded-xl border-2 p-3 text-left transition lg:w-full lg:max-w-none ${active ? 'border-ink bg-white shadow-[3px_3px_0_#dd6b2f]' : 'border-line bg-paper hover:border-ink'}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="line-clamp-2 text-sm font-bold leading-5">{item.title}</p>
                      <ChevronRight className={`mt-0.5 size-4 shrink-0 ${active ? 'text-orange' : 'text-faint'}`} />
                    </div>
                    <p className="mt-2 line-clamp-2 break-words text-[11px] leading-4 text-muted">{item.objective}</p>
                    <div className="mt-3 flex items-center justify-between">
                      <span className="text-[10px] text-muted">{item.completed_task_count}/{item.task_count} tasks</span>
                      {item.latest_run && <RunStatus run={item.latest_run} />}
                    </div>
                  </button>
                )
              })}
            </div>
            {!rooms.length && !loading && (
              <div className="rounded-xl border-2 border-dashed border-line p-5 text-center">
                <RadioTower className="mx-auto size-7 text-orange" />
                <p className="mt-3 text-sm font-bold">No shared rooms yet</p>
                <p className="mt-1 text-xs leading-5 text-muted">Create a room around a real team objective.</p>
              </div>
            )}
          </aside>

          <section className="min-w-0 bg-paper">
            {loading && !room ? (
              <div className="grid min-h-[520px] place-items-center"><Loader2 className="size-7 animate-spin text-orange" /></div>
            ) : room ? (
              <>
                <div className="border-b-2 border-ink bg-white px-5 py-6 sm:px-7">
                  <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-start">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 font-mono text-[9px] font-bold uppercase tracking-[0.16em] text-orange-dark">
                        <Activity className="size-3.5" /> Live workroom
                      </div>
                      <h2 className="mt-2 break-words text-2xl font-black tracking-tight sm:text-3xl">{room.title}</h2>
                      <p className="mt-2 max-w-2xl break-words text-sm leading-6 text-muted">{room.objective}</p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {activeRun && <RunStatus run={activeRun} />}
                      {!activeRun || ['completed', 'failed', 'cancelled', 'redirected'].includes(activeRun.status) ? (
                        <Button onClick={() => void startAgent()} disabled={working || !canEdit}>
                          {working ? <Loader2 className="animate-spin" /> : <Play />} Start agent
                        </Button>
                      ) : ['paused', 'pause_requested'].includes(activeRun.status) ? (
                        <Button onClick={() => void mutate(`/workroom-runs/${activeRun.id}/resume`, { method: 'POST' })} disabled={working || !canEdit}>
                          <Play /> Resume
                        </Button>
                      ) : activeRun.status === 'cancel_requested' ? (
                        <Button variant="outline" disabled>
                          <Loader2 className="animate-spin" /> Stopping after this step
                        </Button>
                      ) : activeRun.current_step === 'creating_compose_briefing' ? (
                        <Button variant="outline" disabled>
                          <Loader2 className="animate-spin" /> Creating briefing
                        </Button>
                      ) : (
                        <Button variant="outline" onClick={() => void mutate(`/workroom-runs/${activeRun.id}/pause`, { method: 'POST' })} disabled={working || !canEdit || activeRun.status === 'awaiting_approval'}>
                          <Pause /> Pause
                        </Button>
                      )}
                    </div>
                  </div>
                </div>

                <div className="p-5 sm:p-7">
                  {activeRun?.status === 'awaiting_approval' && (
                    <motion.div
                      initial={{ opacity: 0, y: -8 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="mb-6 rounded-xl border-2 border-ink bg-warning-soft p-5 shadow-[4px_4px_0_#dd6b2f]"
                    >
                      <div className="flex items-start gap-3">
                        <span className="grid size-10 shrink-0 place-items-center rounded-lg border-2 border-ink bg-orange text-white"><ShieldCheck /></span>
                        <div className="min-w-0 flex-1">
                          <p className="font-mono text-[9px] font-bold uppercase tracking-[0.16em] text-orange-dark">Human checkpoint</p>
                          <h3 className="mt-1 text-lg font-black">Approve the Compose handoff?</h3>
                          <p className="mt-2 text-sm leading-6 text-ink-2">{activeRun.result.summary}</p>
                          <div className="mt-4 flex flex-wrap gap-2">
                            <Button onClick={() => void mutate(`/workroom-runs/${activeRun.id}/approval`, {
                              method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approved: true }),
                            })} disabled={working || !canApprove}><Check /> Approve & create briefing</Button>
                            <Button variant="outline" onClick={() => void mutate(`/workroom-runs/${activeRun.id}/approval`, {
                              method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approved: false }),
                            })} disabled={working || !canApprove}><X /> Reject</Button>
                          </div>
                        </div>
                      </div>
                    </motion.div>
                  )}

                  <div className="mb-4 flex items-center justify-between">
                    <div>
                      <p className="font-mono text-[9px] font-bold uppercase tracking-[0.16em] text-muted">Activity stream</p>
                      <h3 className="mt-1 text-xl font-black">What the team and agent did</h3>
                    </div>
                    <span className="flex items-center gap-1.5 text-[10px] text-muted"><span className="size-2 animate-pulse rounded-full bg-teal" /> Live</span>
                  </div>

                  <div className="relative space-y-3 before:absolute before:bottom-4 before:left-[19px] before:top-4 before:w-px before:bg-line">
                    {room.events.map((event) => (
                      <article key={event.id} className="relative flex gap-3 rounded-xl border border-line bg-white p-4">
                        <span className={`relative z-10 grid size-10 shrink-0 place-items-center rounded-lg border-2 border-ink ${event.actor_type === 'agent' ? 'bg-ink text-white' : event.actor_type === 'human' ? 'bg-orange text-white' : 'bg-paper-2 text-ink'}`}>
                          {event.actor_type === 'agent' ? <Bot className="size-5" /> : event.actor_type === 'human' ? <UserRound className="size-5" /> : <Sparkles className="size-5" />}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-bold">{event.actor_name}</span>
                              <span className="font-mono text-[8px] uppercase tracking-wider text-muted">{event.event_type.replaceAll('_', ' ')}</span>
                            </div>
                            <span className="text-[10px] text-muted">{formatTime(event.created_at)}</span>
                          </div>
                          <p className="mt-1 break-words text-sm leading-6 text-ink-2">{event.message}</p>
                          {event.event_type === 'artifact_created' && typeof event.payload.compose_path === 'string' && (
                            <Link href={event.payload.compose_path} className="mt-3 inline-flex items-center gap-2 rounded-lg border-2 border-ink bg-paper-2 px-3 py-2 text-xs font-bold hover:bg-orange hover:text-white">
                              <FileText className="size-4" /> Open in Compose <ArrowRight className="size-4" />
                            </Link>
                          )}
                        </div>
                      </article>
                    ))}
                  </div>

                  <div className="mt-6 rounded-xl border-2 border-ink bg-white p-3 shadow-[3px_3px_0_#d9cfc0]">
                    <label className="font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-muted" htmlFor="workroom-direction">
                      {activeRun && !['completed', 'failed', 'cancelled', 'redirected'].includes(activeRun.status) ? 'Redirect the agent' : 'Give the agent a direction'}
                    </label>
                    <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                      <input
                        id="workroom-direction"
                        value={direction}
                        onChange={(event) => setDirection(event.target.value)}
                        placeholder="Focus on risks and board-level decisions…"
                        className="min-w-0 flex-1 rounded-lg border border-line bg-paper px-3 py-2.5 text-sm outline-none focus:border-orange"
                      />
                      <Button onClick={() => void (activeRun && !['completed', 'failed', 'cancelled', 'redirected'].includes(activeRun.status) ? redirect() : startAgent())} disabled={working || !canEdit || (!direction.trim() && !!activeRun)}>
                        {working ? <Loader2 className="animate-spin" /> : activeRun && !['completed', 'failed', 'cancelled', 'redirected'].includes(activeRun.status) ? <RotateCcw /> : <Send />}
                        {activeRun && !['completed', 'failed', 'cancelled', 'redirected'].includes(activeRun.status) ? 'Redirect' : 'Start'}
                      </Button>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div className="grid min-h-[620px] place-items-center p-8 text-center">
                <div>
                  <RadioTower className="mx-auto size-10 text-orange" />
                  <h2 className="mt-4 text-2xl font-black">Create the first shared Workroom</h2>
                  <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted">Give your team and Komponist Analyst one objective, one permission scope, and one visible activity trail.</p>
                  <Button className="mt-5" onClick={() => setShowCreate(true)}><Plus /> New room</Button>
                </div>
              </div>
            )}
          </section>

          <aside className="border-t-2 border-ink bg-paper-2 p-5 lg:min-h-[calc(100vh-78px)] lg:border-l-2 lg:border-t-0">
            {room ? (
              <div className="space-y-7">
                <section>
                  <div className="mb-3 flex items-center justify-between">
                    <span className="font-mono text-[9px] font-bold uppercase tracking-[0.16em] text-muted">Shared plan</span>
                    <span className="text-[10px] text-muted">{room.tasks.filter((task) => task.status === 'completed').length}/{room.tasks.length}</span>
                  </div>
                  <div className="space-y-2">
                    {room.tasks.map((task, index) => (
                      <div key={task.id} className="rounded-lg border border-line bg-white p-3">
                        <div className="flex gap-2.5">
                          {task.status === 'completed' ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-teal" /> : task.status === 'in_progress' ? <Clock3 className="mt-0.5 size-4 shrink-0 animate-pulse text-orange" /> : <Circle className="mt-0.5 size-4 shrink-0 text-faint" />}
                          <div className="min-w-0 flex-1">
                            <p className="text-xs font-bold leading-5">{index + 1}. {task.title}</p>
                            <p className="mt-1 flex items-center gap-1 text-[10px] text-muted"><Bot className="size-3" /> {task.assignee_name}</p>
                          </div>
                          {task.status === 'todo' && (
                            <button type="button" onClick={() => void startAgent(task.id)} className="grid size-7 place-items-center rounded-md border border-line hover:border-ink hover:bg-orange hover:text-white" aria-label={`Start ${task.title}`}><Play className="size-3" /></button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-3 flex gap-2">
                    <input value={newTask} onChange={(event) => setNewTask(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void addTask() }} placeholder="Add a task…" className="min-w-0 flex-1 rounded-lg border border-line bg-white px-3 py-2 text-xs outline-none focus:border-orange" />
                    <button type="button" onClick={() => void addTask()} disabled={!newTask.trim() || working || !canEdit} className="grid size-9 place-items-center rounded-lg border-2 border-ink bg-white hover:bg-orange hover:text-white disabled:opacity-40"><Plus className="size-4" /></button>
                  </div>
                </section>

                <section>
                  <span className="font-mono text-[9px] font-bold uppercase tracking-[0.16em] text-muted">People & agents</span>
                  <div className="mt-3 space-y-2">
                    <div className="flex items-center gap-3 rounded-lg border border-line bg-white p-3">
                      <span className="grid size-8 place-items-center rounded-md border border-ink bg-orange text-white"><UserRound className="size-4" /></span>
                      <div><p className="text-xs font-bold">{room.creator.name}</p><p className="text-[10px] text-muted">Room creator · Human</p></div>
                    </div>
                    <div className="flex items-center gap-3 rounded-lg border border-line bg-ink p-3 text-white">
                      <span className="grid size-8 place-items-center rounded-md border border-white/30 bg-white/10"><Bot className="size-4" /></span>
                      <div><p className="text-xs font-bold">Komponist Analyst</p><p className="text-[10px] text-paper-3">Graph research · Compose</p></div>
                      <span className="ml-auto size-2 rounded-full bg-teal-light" />
                    </div>
                  </div>
                </section>

                <section>
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[9px] font-bold uppercase tracking-[0.16em] text-muted">Context used</span>
                    <ShieldCheck className="size-4 text-teal" />
                  </div>
                  <div className="mt-3 rounded-lg border border-line bg-white p-3">
                    <div className="flex items-center gap-2 text-xs font-bold"><UsersRound className="size-4 text-orange" /> Permission scope</div>
                    <p className="mt-2 text-[11px] leading-5 text-muted">
                      {room.department_ids.length
                        ? departments.filter((department) => room.department_ids.includes(department.id)).map((department) => department.name).join(', ') || `${room.department_ids.length} selected departments`
                        : 'Organization-wide facts only'}
                    </p>
                  </div>
                  <div className="mt-2 space-y-2">
                    {(activeRun?.context_snapshot.sources ?? []).slice(0, 5).map((source) => (
                      <Link
                        key={source.id}
                        href={source.komponist_path || `/sources?evidence=${encodeURIComponent(source.id)}`}
                        className="block rounded-lg border border-line bg-white p-3 hover:border-orange"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <p className="truncate text-xs font-bold">{source.title || source.reference || 'Company source'}</p>
                          <ArrowRight className="size-3 shrink-0 text-orange" />
                        </div>
                        <p className="mt-1 font-mono text-[8px] uppercase tracking-wider text-muted">{sourceLocation(source)}</p>
                        {source.excerpt && <p className="mt-2 line-clamp-2 text-[10px] leading-4 text-muted">“{source.excerpt}”</p>}
                      </Link>
                    ))}
                    {!(activeRun?.context_snapshot.sources?.length) && (
                      <p className="rounded-lg border border-dashed border-line p-3 text-[11px] leading-5 text-muted">Sources appear here after the agent researches the company brain.</p>
                    )}
                  </div>
                </section>
              </div>
            ) : (
              <div className="rounded-xl border-2 border-dashed border-line p-5 text-center text-xs leading-5 text-muted">Select a Workroom to see its plan, participants, and permission-scoped sources.</div>
            )}
          </aside>
        </div>
      </main>
    </AppLayout>
  )
}
