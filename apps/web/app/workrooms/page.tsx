'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Activity, AlertTriangle, Archive, ArchiveRestore, Bot, Check, CheckCircle2,
  ChevronDown, Circle, Clock3, FileText, Layers, Loader2, Lock, MessageSquare,
  Pause, Pin, PinOff, Play, Plus, RadioTower, RotateCcw, Send, ShieldCheck,
  Sparkles, Square, Trash2, Users, X,
} from 'lucide-react'
import AppLayout from '../../components/AppLayout'
import StudioTopbar from '../../components/StudioTopbar'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import {
  API_URL, apiFetch, getActiveOrgId, installCampusKollektivDemo,
} from '../../lib/api'

// ---------------------------------------------------------------- types ----

type Department = { id: string; name: string; color?: string }
type RoomRole = 'owner' | 'editor' | 'approver' | 'viewer'
type RoomVisibility = 'organization' | 'departments' | 'private'

type WorkroomTask = {
  id: string
  title: string
  description: string
  status: 'todo' | 'in_progress' | 'completed' | 'blocked'
  assignee_type: 'agent' | 'human'
  assignee_name: string
  assignee_user_id?: string | null
  client_key?: string | null
  depends_on: string[]
  requires_approval: boolean
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
type RunStatusValue =
  | 'queued' | 'running' | 'pause_requested' | 'paused' | 'cancel_requested'
  | 'cancelled' | 'awaiting_approval' | 'completed' | 'failed' | 'redirected'
type WorkroomRun = {
  id: string
  task_id?: string | null
  agent_name: string
  instruction: string
  status: RunStatusValue
  current_step: string
  context_snapshot: {
    findings?: Array<{ id: string; type: string; statement: string; source_ids: string[] }>
    sources?: WorkroomSource[]
    permission_scope?: { visibility?: string; department_ids?: string[] }
  }
  result: {
    summary?: string
    finding_count?: number
    source_count?: number
    artifact_id?: string
    artifact_title?: string
    compose_path?: string
    error?: string
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
type WorkroomMember = {
  id: string
  user_id: string
  name: string
  email?: string | null
  room_role: RoomRole
  status: string
}
type WorkroomMessage = {
  id: string
  author_type: 'human' | 'agent' | 'system'
  author_name: string
  body: string
  reply_to_message_id?: string | null
  references: Array<{ kind: string; id: string; label?: string }>
  edited_at?: string | null
  deleted: boolean
  created_at: string
}
type PlanTask = {
  client_key: string
  title: string
  description: string
  assignee_type: 'agent' | 'human'
  depends_on: string[]
  requires_approval: boolean
}
type PlanVersion = {
  id: string
  version: number
  status: 'draft' | 'approved' | 'superseded' | 'rejected'
  summary: string
  spec: { summary: string; tasks: PlanTask[] }
  provider?: string | null
  model?: string | null
  approved_at?: string | null
}
type ContextPreview = {
  visibility: RoomVisibility
  department_ids: string[]
  confirmed_fact_count: number
  accessible_source_count: number
  pinned: Array<{ id: string; item_kind: string; reference_id: string; label?: string | null }>
  excluded: Array<{ id: string; item_kind: string; reference_id: string; label?: string | null }>
  excluded_fact_count: number
  excluded_source_count: number
  omitted_inaccessible_count: number
  last_context_update_at?: string | null
  sources: Array<{
    id: string
    title?: string
    reference?: string
    excerpt?: string
    komponist_path?: string
    pinned: boolean
  }>
}
type Deliverable = {
  artifact_id: string
  title: string
  artifact_type: string
  run_id?: string | null
  task_id?: string | null
  approved_by_name?: string | null
  source_count: number
  artifact_created_at: string
  compose_path: string
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
  WorkroomSummary, 'task_count' | 'completed_task_count' | 'latest_run' | 'member_count'
> & {
  members: WorkroomMember[]
  tasks: WorkroomTask[]
  runs: WorkroomRun[]
  events: WorkroomEvent[]
}
type WorkerHealth = { workers_online: number; queued: number; status: string }

type TabKey = 'overview' | 'plan' | 'conversation' | 'context' | 'deliverables' | 'activity'
const ROOM_PAGE_SIZE = 24
const MESSAGE_PAGE_SIZE = 100

// ------------------------------------------------------------ constants ----

// Mirrors the server's room permission table so the UI never offers an action
// the API would reject.
const roomPermissions: Record<RoomRole, ReadonlyArray<string>> = {
  owner: ['view', 'comment', 'edit', 'approve', 'manage'],
  editor: ['view', 'comment', 'edit'],
  approver: ['view', 'comment', 'approve'],
  viewer: ['view', 'comment'],
}
function roomCan(role: RoomRole | undefined, permission: string) {
  return !!role && roomPermissions[role].includes(permission)
}

const runLabels: Record<RunStatusValue, string> = {
  queued: 'Queued',
  running: 'Working',
  // An external model call cannot be interrupted, so the agent stops at the
  // next safe step rather than instantly.
  pause_requested: 'Pausing',
  paused: 'Paused',
  cancel_requested: 'Cancelling',
  cancelled: 'Cancelled',
  awaiting_approval: 'Needs approval',
  completed: 'Completed',
  failed: 'Failed',
  redirected: 'Redirected',
}
const runTones: Record<RunStatusValue, string> = {
  queued: 'border-line bg-paper-2 text-muted',
  running: 'border-orange/40 bg-warning-soft text-orange-dark',
  pause_requested: 'border-line bg-paper-2 text-ink-2',
  paused: 'border-line bg-paper-2 text-ink-2',
  cancel_requested: 'border-line bg-paper-2 text-ink-2',
  cancelled: 'border-line bg-paper-2 text-muted',
  awaiting_approval: 'border-orange/40 bg-warning-soft text-orange-dark',
  completed: 'border-teal/30 bg-success-soft text-teal',
  failed: 'border-danger/30 bg-danger-soft text-danger',
  redirected: 'border-info/30 bg-info-soft text-info',
}
const activeRunStatuses: RunStatusValue[] = [
  'queued', 'running', 'pause_requested', 'paused', 'cancel_requested',
  'awaiting_approval',
]
const visibilityLabels: Record<RoomVisibility, string> = {
  organization: 'Everyone in the organization',
  departments: 'Selected departments',
  private: 'Invited participants only',
}
const tabs: Array<{ key: TabKey; label: string; icon: typeof Activity }> = [
  { key: 'overview', label: 'Overview', icon: Layers },
  { key: 'plan', label: 'Plan', icon: CheckCircle2 },
  { key: 'conversation', label: 'Conversation', icon: MessageSquare },
  { key: 'context', label: 'Context', icon: ShieldCheck },
  { key: 'deliverables', label: 'Deliverables', icon: FileText },
  { key: 'activity', label: 'Activity', icon: Activity },
]

// -------------------------------------------------------------- helpers ----

function formatTime(value: string) {
  return new Intl.DateTimeFormat('en', { hour: '2-digit', minute: '2-digit' })
    .format(new Date(value))
}
function formatDate(value: string) {
  return new Intl.DateTimeFormat('en', { day: 'numeric', month: 'short' })
    .format(new Date(value))
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

function RunStatusChip({ run }: { run: WorkroomRun }) {
  const busy = ['running', 'pause_requested', 'cancel_requested', 'queued']
    .includes(run.status)
  return (
    <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[9px] font-bold uppercase tracking-wider ${runTones[run.status]}`}>
      {busy && <span className="size-1.5 animate-pulse rounded-full bg-orange" />}
      {runLabels[run.status]}
    </span>
  )
}

function SectionCard({
  title, icon: Icon, children, action,
}: {
  title: string
  icon: typeof Activity
  children: React.ReactNode
  action?: React.ReactNode
}) {
  return (
    <section className="min-w-0 rounded-xl border-2 border-ink bg-white">
      <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
        <h3 className="flex min-w-0 items-center gap-2 break-words font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-ink-2">
          <Icon className="size-3.5 shrink-0 text-orange" /> {title}
        </h3>
        {action && <div className="shrink-0">{action}</div>}
      </header>
      <div className="p-4">{children}</div>
    </section>
  )
}

function EmptyState({ icon: Icon, title, hint }: {
  icon: typeof Activity; title: string; hint?: string
}) {
  return (
    <div className="grid place-items-center gap-2 px-4 py-10 text-center">
      <Icon className="size-6 text-faint" />
      <p className="text-sm font-bold">{title}</p>
      {hint && <p className="max-w-sm text-xs leading-5 text-muted">{hint}</p>}
    </div>
  )
}

// ----------------------------------------------------------------- page ----

export default function WorkroomsPage() {
  const [rooms, setRooms] = useState<WorkroomSummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [room, setRoom] = useState<Workroom | null>(null)
  const [plans, setPlans] = useState<{ draft: PlanVersion | null; current: PlanVersion | null; plans: PlanVersion[] }>(
    { draft: null, current: null, plans: [] },
  )
  const [messages, setMessages] = useState<WorkroomMessage[]>([])
  const [context, setContext] = useState<ContextPreview | null>(null)
  const [deliverables, setDeliverables] = useState<Deliverable[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [worker, setWorker] = useState<WorkerHealth | null>(null)

  const [tab, setTab] = useState<TabKey>('overview')
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [planning, setPlanning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showArchived, setShowArchived] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [showRoomPicker, setShowRoomPicker] = useState(false)
  const [roomOffset, setRoomOffset] = useState(0)
  const [roomsHaveMore, setRoomsHaveMore] = useState(false)
  const [roomPageLoading, setRoomPageLoading] = useState(false)
  const [messageHistoryLoading, setMessageHistoryLoading] = useState(false)
  const [messageHistoryHasMore, setMessageHistoryHasMore] = useState(false)
  const [messageHistoryCursor, setMessageHistoryCursor] = useState<string | null>(null)
  const eventCursorRef = useRef(0)
  const eventRefreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const [newTitle, setNewTitle] = useState('')
  const [newObjective, setNewObjective] = useState('')
  const [newVisibility, setNewVisibility] = useState<RoomVisibility>('organization')
  const [newDepartments, setNewDepartments] = useState<string[]>([])
  const [newTask, setNewTask] = useState('')
  const [direction, setDirection] = useState('')
  const [draftMessage, setDraftMessage] = useState('')

  const orgId = () => getActiveOrgId()

  const loadRooms = useCallback(async (
    archived: boolean,
    offset = 0,
    append = false,
  ) => {
    setRoomPageLoading(true)
    try {
      const response = await apiFetch(
        `${API_URL}/workrooms?org_id=${encodeURIComponent(orgId())}&include_archived=${archived}`
          + `&limit=${ROOM_PAGE_SIZE}&offset=${offset}`,
      )
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not load Workrooms')
      setRooms((current) => append ? [...current, ...payload.workrooms] : payload.workrooms)
      setRoomOffset(offset)
      setRoomsHaveMore(Boolean(payload.has_more))
      setSelectedId((current) => current ?? payload.workrooms[0]?.id ?? null)
    } finally {
      setRoomPageLoading(false)
    }
  }, [])

  const loadRoom = useCallback(async (roomId: string, quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      const org = encodeURIComponent(orgId())
      const [roomResponse, plansResponse, messagesResponse, deliverablesResponse] =
        await Promise.all([
          apiFetch(`${API_URL}/workrooms/${roomId}?org_id=${org}`),
          apiFetch(`${API_URL}/workrooms/${roomId}/plans?org_id=${org}`),
          apiFetch(
            `${API_URL}/workrooms/${roomId}/messages?org_id=${org}&limit=${MESSAGE_PAGE_SIZE}`,
          ),
          apiFetch(`${API_URL}/workrooms/${roomId}/deliverables?org_id=${org}`),
        ])
      const payload = await roomResponse.json()
      if (!roomResponse.ok) throw new Error(payload.detail || 'Could not load Workroom')
      eventCursorRef.current = Math.max(
        eventCursorRef.current,
        ...(payload.events ?? []).map((event: WorkroomEvent) => event.id),
      )
      setRoom(payload)
      if (plansResponse.ok) setPlans(await plansResponse.json())
      if (messagesResponse.ok) {
        const messagePayload = await messagesResponse.json()
        setMessages(messagePayload.messages)
        setMessageHistoryHasMore(Boolean(messagePayload.has_more))
        setMessageHistoryCursor(messagePayload.next_before ?? null)
      }
      if (deliverablesResponse.ok) {
        setDeliverables((await deliverablesResponse.json()).deliverables)
      }
    } finally {
      if (!quiet) setLoading(false)
    }
  }, [])

  const loadContext = useCallback(async (roomId: string) => {
    const response = await apiFetch(
      `${API_URL}/workrooms/${roomId}/context?org_id=${encodeURIComponent(orgId())}`,
    )
    if (response.ok) setContext(await response.json())
  }, [])

  useEffect(() => {
    const bootstrap = async () => {
      setLoading(true)
      setError(null)
      try {
        const org = encodeURIComponent(orgId())
        const [departmentsResponse, healthResponse] = await Promise.all([
          apiFetch(`${API_URL}/departments?org_id=${org}`).catch(() => null),
          fetch(`${API_URL}/healthz`).catch(() => null),
        ])
        if (departmentsResponse?.ok) {
          const payload = await departmentsResponse.json()
          setDepartments(payload.departments ?? [])
        }
        if (healthResponse?.ok) {
          const payload = await healthResponse.json()
          setWorker(payload.services?.workroom_worker ?? null)
        }
        await loadRooms(showArchived)
      } catch (bootError) {
        setError(bootError instanceof Error ? bootError.message : 'Could not load Workrooms')
      } finally {
        setLoading(false)
      }
    }
    void bootstrap()
  }, [loadRooms, showArchived])

  useEffect(() => {
    if (!selectedId) {
      setRoom(null)
      setMessages([])
      setMessageHistoryHasMore(false)
      setMessageHistoryCursor(null)
      return
    }
    void loadRoom(selectedId).catch((loadError) => {
      setError(loadError instanceof Error ? loadError.message : 'Could not load Workroom')
    })
  }, [selectedId, loadRoom])

  useEffect(() => {
    if (selectedId && tab === 'context') void loadContext(selectedId)
  }, [selectedId, tab, loadContext])

  // Live updates: the persisted event stream resumes from its own cursor, so a
  // dropped connection never duplicates the timeline.
  useEffect(() => {
    if (!selectedId || room?.id !== selectedId) return
    const source = new EventSource(
      `${API_URL}/workrooms/${selectedId}/events?org_id=${encodeURIComponent(orgId())}`
        + `&after=${eventCursorRef.current}`,
      { withCredentials: true },
    )
    source.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as WorkroomEvent
        eventCursorRef.current = Math.max(eventCursorRef.current, event.id)
      } catch {
        // The persisted room state remains authoritative if an event is malformed.
      }
      if (eventRefreshTimerRef.current) clearTimeout(eventRefreshTimerRef.current)
      eventRefreshTimerRef.current = setTimeout(() => {
        void loadRoom(selectedId, true)
      }, 250)
    }
    source.onerror = () => source.close()
    return () => {
      source.close()
      if (eventRefreshTimerRef.current) {
        clearTimeout(eventRefreshTimerRef.current)
        eventRefreshTimerRef.current = null
      }
    }
  }, [selectedId, room?.id, loadRoom])

  const activeRun = useMemo(
    () => room?.runs.find((run) => activeRunStatuses.includes(run.status))
      ?? room?.runs[0] ?? null,
    [room?.runs],
  )
  const completedTaskIds = useMemo(
    () => new Set(
      room?.tasks
        .filter((task) => task.status === 'completed')
        .map((task) => task.id) ?? [],
    ),
    [room?.tasks],
  )
  const runnableAgentTasks = useMemo(
    () => room?.tasks.filter((task) => (
      task.assignee_type === 'agent'
      && task.status !== 'completed'
      && task.depends_on.every((dependencyId) => completedTaskIds.has(dependencyId))
    )) ?? [],
    [completedTaskIds, room?.tasks],
  )
  const isArchived = room?.status === 'archived'
  const canEdit = roomCan(room?.room_role, 'edit') && !isArchived
  const canApprove = roomCan(room?.room_role, 'approve') && !isArchived
  const canManage = roomCan(room?.room_role, 'manage')
  const workerOffline = worker != null && worker.workers_online === 0

  const nextAction = useMemo(() => {
    if (isArchived) return 'This Workroom is archived. Reopen it to continue.'
    if (activeRun?.status === 'awaiting_approval') {
      return canApprove
        ? 'Review the agent’s cited findings and approve the deliverable.'
        : 'Waiting for an approver to review the agent’s findings.'
    }
    if (activeRun?.status === 'failed') return 'The last attempt failed. Retry it or change its direction.'
    if (activeRun?.status === 'paused') return 'The agent is paused. Resume it when you are ready.'
    if (plans.draft) return 'A proposed plan is waiting for approval.'
    if (!plans.current && !room?.tasks.length) return 'Generate a plan to get started.'
    if (activeRun && activeRunStatuses.includes(activeRun.status)) return 'The agent is working. Nothing to do right now.'
    return 'Start an agent task, or add work to the plan.'
  }, [activeRun, canApprove, isArchived, plans, room?.tasks.length])

  const mutate = async (path: string, init: RequestInit = {}) => {
    setWorking(true)
    setError(null)
    try {
      const separator = path.includes('?') ? '&' : '?'
      const response = await apiFetch(
        `${API_URL}${path}${separator}org_id=${encodeURIComponent(orgId())}`,
        { headers: { 'Content-Type': 'application/json' }, ...init },
      )
      const payload = response.status === 204 ? null : await response.json().catch(() => null)
      if (!response.ok) throw new Error(payload?.detail || 'The action could not be completed')
      if (selectedId) await loadRoom(selectedId, true)
      await loadRooms(showArchived)
      if (selectedId && tab === 'context') await loadContext(selectedId)
      return payload
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : 'The action could not be completed')
      return null
    } finally {
      setWorking(false)
    }
  }

  const createRoom = async () => {
    const created = await mutate('/workrooms', {
      method: 'POST',
      body: JSON.stringify({
        title: newTitle,
        objective: newObjective,
        visibility: newVisibility,
        department_ids: newVisibility === 'departments' ? newDepartments : [],
      }),
    })
    if (created?.id) {
      setShowCreate(false)
      setNewTitle('')
      setNewObjective('')
      setNewDepartments([])
      setNewVisibility('organization')
      setSelectedId(created.id)
      setTab('overview')
    }
  }

  const loadCampusKollektivExample = async () => {
    setWorking(true)
    setError(null)
    try {
      await installCampusKollektivDemo()
      setNewTitle('Campus Forum launch room')
      setNewObjective(
        'Prepare a cited board-ready readiness update for the Campus Forum covering the approved plan, budget, volunteers, sponsors, dependencies, and next decisions.',
      )
      setNewVisibility('organization')
      setNewDepartments([])
    } catch (exampleError) {
      setError(exampleError instanceof Error
        ? exampleError.message
        : 'Could not load the CampusKollektiv example')
    } finally {
      setWorking(false)
    }
  }

  const generatePlan = async () => {
    if (!selectedId) return
    setPlanning(true)
    try {
      await mutate(`/workrooms/${selectedId}/plans`, {
        method: 'POST',
        body: JSON.stringify({ guidance: direction }),
      })
      const response = await apiFetch(
        `${API_URL}/workrooms/${selectedId}/plans?org_id=${encodeURIComponent(orgId())}`,
      )
      if (response.ok) setPlans(await response.json())
      setTab('plan')
    } finally {
      setPlanning(false)
    }
  }

  const decidePlan = async (planId: string, approved: boolean) => {
    if (!selectedId) return
    await mutate(`/workrooms/${selectedId}/plans/${planId}/approval`, {
      method: 'POST',
      body: JSON.stringify({ approved }),
    })
    const response = await apiFetch(
      `${API_URL}/workrooms/${selectedId}/plans?org_id=${encodeURIComponent(orgId())}`,
    )
    if (response.ok) setPlans(await response.json())
  }

  const startAgent = async (taskId?: string) => {
    if (!selectedId) return
    await mutate(`/workrooms/${selectedId}/runs`, {
      method: 'POST',
      body: JSON.stringify({ task_id: taskId ?? null, instruction: direction }),
    })
    setDirection('')
  }

  const redirectAgent = async () => {
    if (!activeRun || !direction.trim()) return
    await mutate(`/workroom-runs/${activeRun.id}/redirect`, {
      method: 'POST',
      body: JSON.stringify({ instruction: direction }),
    })
    setDirection('')
  }

  const addTask = async () => {
    if (!selectedId || !newTask.trim()) return
    await mutate(`/workrooms/${selectedId}/tasks`, {
      method: 'POST',
      body: JSON.stringify({ title: newTask, description: newTask, assignee_type: 'agent' }),
    })
    setNewTask('')
  }

  const moveTask = async (index: number, delta: number) => {
    if (!room || !selectedId) return
    const ordered = [...room.tasks]
    const target = index + delta
    if (target < 0 || target >= ordered.length) return
    const [moved] = ordered.splice(index, 1)
    ordered.splice(target, 0, moved)
    await mutate(`/workrooms/${selectedId}/tasks/reorder`, {
      method: 'POST',
      body: JSON.stringify({ task_ids: ordered.map((task) => task.id) }),
    })
  }

  const postMessage = async () => {
    if (!selectedId || !draftMessage.trim()) return
    await mutate(`/workrooms/${selectedId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ body: draftMessage }),
    })
    setDraftMessage('')
  }

  const loadOlderMessages = async () => {
    if (!selectedId || !messageHistoryCursor || messageHistoryLoading) return
    setMessageHistoryLoading(true)
    try {
      const response = await apiFetch(
        `${API_URL}/workrooms/${selectedId}/messages?org_id=${encodeURIComponent(orgId())}`
          + `&limit=${MESSAGE_PAGE_SIZE}&before=${encodeURIComponent(messageHistoryCursor)}`,
      )
      if (!response.ok) return
      const payload = await response.json()
      setMessages((current) => [...payload.messages, ...current])
      setMessageHistoryHasMore(Boolean(payload.has_more))
      setMessageHistoryCursor(payload.next_before ?? null)
    } finally {
      setMessageHistoryLoading(false)
    }
  }

  const toggleContextPin = async (sourceId: string, pinned: boolean) => {
    if (!selectedId) return
    if (pinned) {
      const item = context?.pinned.find((entry) => entry.reference_id === sourceId)
      if (item) await mutate(`/workrooms/${selectedId}/context/${item.id}`, { method: 'DELETE' })
      return
    }
    await mutate(`/workrooms/${selectedId}/context`, {
      method: 'POST',
      body: JSON.stringify({ item_kind: 'source', reference_id: sourceId, mode: 'include' }),
    })
  }

  const excludeSource = async (sourceId: string) => {
    if (!selectedId) return
    await mutate(`/workrooms/${selectedId}/context`, {
      method: 'POST',
      body: JSON.stringify({ item_kind: 'source', reference_id: sourceId, mode: 'exclude' }),
    })
  }

  // ------------------------------------------------------------ render ----

  const roomList = (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
        <h2 className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-ink-2">
          Workrooms
        </h2>
        <label className="flex cursor-pointer items-center gap-1.5 text-[10px] text-muted">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(event) => setShowArchived(event.target.checked)}
            className="size-3 accent-orange"
          />
          Archived
        </label>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {rooms.length === 0 ? (
          <EmptyState icon={RadioTower} title="No Workrooms yet" hint="Create one to bring people and agents into the same governed context." />
        ) : (
          <ul className="space-y-1.5">
            {rooms.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => { setSelectedId(item.id); setShowRoomPicker(false); setTab('overview') }}
                  aria-current={item.id === selectedId}
                  className={`w-full rounded-lg border px-3 py-2.5 text-left transition ${
                    item.id === selectedId
                      ? 'border-ink bg-paper-2 shadow-[2px_2px_0_var(--color-ink)]'
                      : 'border-line bg-white hover:border-ink'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="min-w-0 break-words text-sm font-bold leading-5">{item.title}</span>
                    {item.visibility === 'private' && <Lock className="mt-0.5 size-3 shrink-0 text-muted" />}
                  </div>
                  <p className="mt-1 line-clamp-2 text-[11px] leading-4 text-muted">{item.objective}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-muted">
                    <span>{item.completed_task_count}/{item.task_count} tasks</span>
                    <span aria-hidden>·</span>
                    <span>{item.member_count} people</span>
                    {item.status === 'archived' && (
                      <Badge className="border-line bg-paper-2 text-[9px] text-muted">Archived</Badge>
                    )}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
        {roomsHaveMore && (
          <Button
            type="button"
            variant="subtle"
            size="sm"
            className="mt-2 w-full"
            disabled={roomPageLoading}
            onClick={() => void loadRooms(showArchived, roomOffset + ROOM_PAGE_SIZE, true)}
          >
            {roomPageLoading ? <Loader2 className="animate-spin" /> : <ChevronDown />}
            Load more Workrooms
          </Button>
        )}
      </div>
    </div>
  )

  const rightRail = room && (
    <div className="space-y-4">
      <SectionCard title="Next human action" icon={Sparkles}>
        <p className="text-xs leading-5 text-ink-2">{nextAction}</p>
      </SectionCard>

      <SectionCard title="Current agent" icon={Bot}>
        {activeRun ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-bold">{activeRun.agent_name}</span>
              <RunStatusChip run={activeRun} />
            </div>
            <p className="font-mono text-[10px] text-muted">{activeRun.current_step.replace(/_/g, ' ')}</p>
            {activeRun.status === 'pause_requested' && (
              <p className="text-[11px] leading-4 text-muted">
                Stopping after the current step. A model request already in flight cannot be interrupted.
              </p>
            )}
            {activeRun.result?.summary && (
              <p className="line-clamp-3 text-[11px] leading-4 text-muted">{activeRun.result.summary}</p>
            )}
          </div>
        ) : (
          <p className="text-xs text-muted">No agent run yet.</p>
        )}
      </SectionCard>

      <SectionCard title="Participants" icon={Users}>
        <ul className="space-y-2">
          {room.members.map((member) => (
            <li key={member.id} className="flex items-center justify-between gap-2">
              <span className="min-w-0 truncate text-xs">{member.name}</span>
              <Badge className="shrink-0 border-line bg-paper-2 text-[9px] uppercase text-muted">
                {member.room_role}
              </Badge>
            </li>
          ))}
        </ul>
      </SectionCard>

      <SectionCard title="Knowledge scope" icon={ShieldCheck}>
        <p className="text-xs font-bold">{visibilityLabels[room.visibility]}</p>
        <p className="mt-1 text-[11px] leading-4 text-muted">
          The agent reads only confirmed knowledge inside this scope, never the
          wider access of whoever starts it.
        </p>
        {room.department_ids.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {room.department_ids.map((id) => (
              <Badge key={id} className="border-line bg-paper-2 text-[9px] text-muted">
                {departments.find((department) => department.id === id)?.name ?? 'Department'}
              </Badge>
            ))}
          </div>
        )}
      </SectionCard>
    </div>
  )

  const agentControls = room && (
    <div className="flex flex-wrap items-center gap-2">
      {activeRun && ['paused', 'pause_requested'].includes(activeRun.status) ? (
        <Button size="sm" onClick={() => void mutate(`/workroom-runs/${activeRun.id}/resume`, { method: 'POST' })} disabled={working || !canEdit}>
          <Play /> Resume
        </Button>
      ) : activeRun?.status === 'cancel_requested' ? (
        <Button size="sm" variant="outline" disabled>
          <Loader2 className="animate-spin" /> Stopping
        </Button>
      ) : activeRun?.status === 'failed' ? (
        <Button size="sm" onClick={() => void mutate(`/workroom-runs/${activeRun.id}/retry`, { method: 'POST' })} disabled={working || !canEdit}>
          <RotateCcw /> Retry
        </Button>
      ) : activeRun && activeRunStatuses.includes(activeRun.status) ? (
        <>
          <Button size="sm" variant="outline" onClick={() => void mutate(`/workroom-runs/${activeRun.id}/pause`, { method: 'POST' })} disabled={working || !canEdit || activeRun.current_step === 'creating_compose_briefing'}>
            <Pause /> Pause
          </Button>
          <Button size="sm" variant="outline" onClick={() => void mutate(`/workroom-runs/${activeRun.id}/cancel`, { method: 'POST' })} disabled={working || !canEdit}>
            <Square /> Cancel
          </Button>
        </>
      ) : (
        <Button
          size="sm"
          onClick={() => void startAgent()}
          disabled={working || !canEdit || runnableAgentTasks.length === 0}
        >
          {working ? <Loader2 className="animate-spin" /> : <Play />}
          {runnableAgentTasks.length === 0 ? 'No agent task ready' : 'Start agent'}
        </Button>
      )}
    </div>
  )

  const approvalPanel = room && activeRun?.status === 'awaiting_approval' && (
    <SectionCard title="Approval required" icon={ShieldCheck}>
          <p className="text-xs leading-5 text-ink-2">{activeRun.result?.summary}</p>
          <div className="mt-3 space-y-2">
            {(activeRun.context_snapshot.sources ?? []).slice(0, 4).map((source) => (
              <a
                key={source.id}
                href={source.komponist_path ?? '#'}
                className="block rounded-lg border border-line bg-paper-2 px-3 py-2 hover:border-ink"
              >
                <p className="text-[11px] font-bold">{source.title ?? 'Source'}</p>
                <p className="mt-0.5 line-clamp-2 text-[11px] leading-4 text-muted">“{source.excerpt}”</p>
                <p className="mt-1 font-mono text-[9px] uppercase text-faint">{sourceLocation(source)}</p>
              </a>
            ))}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" onClick={() => void mutate(`/workroom-runs/${activeRun.id}/approval`, { method: 'POST', body: JSON.stringify({ approved: true }) })} disabled={working || !canApprove}>
              <Check /> Approve &amp; create deliverable
            </Button>
            <Button size="sm" variant="outline" onClick={() => void mutate(`/workroom-runs/${activeRun.id}/approval`, { method: 'POST', body: JSON.stringify({ approved: false }) })} disabled={working || !canApprove}>
              <X /> Reject
            </Button>
          </div>
          {!canApprove && (
            <p className="mt-2 text-[11px] text-muted">Your room role cannot approve deliverables.</p>
          )}
    </SectionCard>
  )

  const overviewTab = room && (
    <div className="space-y-4">
      {activeRun?.status === 'failed' && (
        <SectionCard title="Last attempt failed" icon={AlertTriangle}>
          <p className="text-xs leading-5 text-ink-2">
            {activeRun.result?.summary ?? 'The agent run failed.'}
          </p>
          <div className="mt-3">{agentControls}</div>
        </SectionCard>
      )}

      <SectionCard title="Progress" icon={Layers}>
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-black">
            {room.tasks.filter((task) => task.status === 'completed').length}
          </span>
          <span className="text-sm text-muted">of {room.tasks.length} tasks complete</span>
        </div>
        <div className="mt-3 h-2 overflow-hidden rounded-full border border-line bg-paper-2">
          <div
            className="h-full bg-orange transition-all"
            style={{
              width: `${room.tasks.length
                ? (room.tasks.filter((task) => task.status === 'completed').length / room.tasks.length) * 100
                : 0}%`,
            }}
          />
        </div>
        <ul className="mt-3 space-y-2">
          {room.tasks.slice(0, 4).map((task) => (
            <li key={task.id} className="flex items-start gap-2">
              {task.status === 'completed'
                ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-teal" />
                : task.status === 'in_progress'
                  ? <Clock3 className="mt-0.5 size-4 shrink-0 animate-pulse text-orange" />
                  : <Circle className="mt-0.5 size-4 shrink-0 text-faint" />}
              <span className="min-w-0 break-words text-xs leading-5">{task.title}</span>
            </li>
          ))}
        </ul>
      </SectionCard>

      {deliverables.length > 0 && (
        <SectionCard title="Latest deliverable" icon={FileText}>
          <Link href={deliverables[0].compose_path} className="block rounded-lg border border-line bg-paper-2 px-3 py-2 hover:border-ink">
            <p className="text-xs font-bold">{deliverables[0].title}</p>
            <p className="mt-1 text-[11px] text-muted">
              {deliverables[0].source_count} cited sources
              {deliverables[0].approved_by_name ? ` · approved by ${deliverables[0].approved_by_name}` : ''}
            </p>
          </Link>
        </SectionCard>
      )}
    </div>
  )

  const planTab = room && (
    <div className="space-y-4">
      {plans.draft ? (
        <SectionCard
          title={`Proposed plan v${plans.draft.version}`}
          icon={Sparkles}
          action={
            <span className="font-mono text-[9px] uppercase text-faint">
              {plans.draft.provider ?? 'provider'}
            </span>
          }
        >
          <p className="text-xs leading-5 text-ink-2">{plans.draft.spec.summary}</p>
          <ol className="mt-3 space-y-2">
            {plans.draft.spec.tasks.map((task, index) => (
              <li key={task.client_key} className="rounded-lg border border-line bg-paper-2 px-3 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[10px] text-faint">{index + 1}</span>
                  <span className="min-w-0 break-words text-xs font-bold">{task.title}</span>
                  <Badge className="border-line bg-white text-[9px] uppercase text-muted">
                    {task.assignee_type}
                  </Badge>
                  {task.requires_approval && (
                    <Badge className="border-orange/40 bg-warning-soft text-[9px] uppercase text-orange-dark">
                      Approval
                    </Badge>
                  )}
                </div>
                <p className="mt-1 break-words text-[11px] leading-4 text-muted">{task.description}</p>
                {task.depends_on.length > 0 && (
                  <p className="mt-1 font-mono text-[9px] uppercase text-faint">
                    after {task.depends_on.join(', ')}
                  </p>
                )}
              </li>
            ))}
          </ol>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" onClick={() => void decidePlan(plans.draft!.id, true)} disabled={working || !canApprove}>
              <Check /> Approve plan
            </Button>
            <Button size="sm" variant="outline" onClick={() => void decidePlan(plans.draft!.id, false)} disabled={working || !canApprove}>
              <X /> Reject
            </Button>
            <Button size="sm" variant="ghost" onClick={() => void generatePlan()} disabled={planning || !canEdit}>
              {planning ? <Loader2 className="animate-spin" /> : <RotateCcw />} Regenerate
            </Button>
          </div>
          {!canApprove && (
            <p className="mt-2 text-[11px] text-muted">Your room role cannot approve the plan.</p>
          )}
        </SectionCard>
      ) : (
        <SectionCard title="Plan" icon={Sparkles}>
          {planning ? (
            <div className="flex items-center gap-2 px-1 py-6 text-xs text-muted">
              <Loader2 className="size-4 animate-spin text-orange" />
              Asking the model for a structured plan…
            </div>
          ) : plans.current ? (
            <>
              <p className="text-xs leading-5 text-ink-2">{plans.current.spec.summary}</p>
              <p className="mt-2 font-mono text-[9px] uppercase text-faint">
                Approved plan v{plans.current.version}
              </p>
              <Button size="sm" variant="outline" className="mt-3" onClick={() => void generatePlan()} disabled={!canEdit}>
                <Sparkles /> Propose a new plan
              </Button>
            </>
          ) : (
            <EmptyState
              icon={Sparkles}
              title="No plan yet"
              hint="Ask the model to propose a structured plan from this room's objective and governed context. You approve it before anything becomes active."
            />
          )}
          {!plans.current && !planning && (
            <div className="flex justify-center pb-2">
              <Button size="sm" onClick={() => void generatePlan()} disabled={!canEdit}>
                <Sparkles /> Generate plan
              </Button>
            </div>
          )}
        </SectionCard>
      )}

      <SectionCard
        title="Tasks"
        icon={CheckCircle2}
        action={<span className="font-mono text-[9px] text-faint">{room.tasks.length}</span>}
      >
        {room.tasks.length === 0 ? (
          <EmptyState icon={CheckCircle2} title="No tasks yet" hint="Approve a plan or add a task by hand." />
        ) : (
          <ul className="space-y-2">
            {room.tasks.map((task, index) => {
              const runs = room.runs.filter((run) => run.task_id === task.id)
              const blockedBy = task.depends_on.filter(
                (dependency) => !completedTaskIds.has(dependency),
              )
              return (
                <li key={task.id} className="rounded-lg border border-line bg-paper-2 px-3 py-2">
                  <div className="flex items-start gap-2">
                    {task.status === 'completed'
                      ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-teal" />
                      : task.status === 'in_progress'
                        ? <Clock3 className="mt-0.5 size-4 shrink-0 animate-pulse text-orange" />
                        : <Circle className="mt-0.5 size-4 shrink-0 text-faint" />}
                    <div className="min-w-0 flex-1">
                      <p className="break-words text-xs font-bold leading-5">{task.title}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        <Badge className="border-line bg-white text-[9px] uppercase text-muted">
                          {task.assignee_type === 'agent' ? task.assignee_name : task.assignee_name}
                        </Badge>
                        {task.depends_on.length > 0 && (
                          <Badge className="border-line bg-white text-[9px] text-muted">
                            {blockedBy.length > 0
                              ? `Waiting for ${blockedBy.length}`
                              : `${task.depends_on.length} dependencies ready`}
                          </Badge>
                        )}
                        {runs.length > 0 && (
                          <span className="font-mono text-[9px] text-faint">
                            {runs.length} attempt{runs.length === 1 ? '' : 's'}
                          </span>
                        )}
                      </div>
                    </div>
                    {/* Accessible reordering: no drag-and-drop dependency. */}
                    <div className="flex shrink-0 flex-col gap-0.5">
                      <button
                        type="button"
                        aria-label={`Move ${task.title} up`}
                        onClick={() => void moveTask(index, -1)}
                        disabled={index === 0 || working || !canEdit}
                        className="grid size-5 place-items-center rounded border border-line bg-white text-[9px] hover:border-ink disabled:opacity-30"
                      >▲</button>
                      <button
                        type="button"
                        aria-label={`Move ${task.title} down`}
                        onClick={() => void moveTask(index, 1)}
                        disabled={index === room.tasks.length - 1 || working || !canEdit}
                        className="grid size-5 place-items-center rounded border border-line bg-white text-[9px] hover:border-ink disabled:opacity-30"
                      >▼</button>
                    </div>
                  </div>
                  {task.assignee_type === 'agent' && task.status !== 'completed' && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        variant="subtle"
                        onClick={() => void startAgent(task.id)}
                        disabled={working || !canEdit || blockedBy.length > 0}
                      >
                        {blockedBy.length > 0 ? <Clock3 /> : <Play />}
                        {blockedBy.length > 0 ? 'Waiting for dependencies' : 'Run this task'}
                      </Button>
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}
        {canEdit && (
          <div className="mt-3 flex gap-2">
            <input
              value={newTask}
              onChange={(event) => setNewTask(event.target.value)}
              onKeyDown={(event) => { if (event.key === 'Enter') void addTask() }}
              placeholder="Add a task…"
              aria-label="New task title"
              className="min-w-0 flex-1 rounded-lg border border-line bg-white px-3 py-2 text-xs outline-none focus:border-orange"
            />
            <button
              type="button"
              onClick={() => void addTask()}
              disabled={!newTask.trim() || working}
              aria-label="Add task"
              className="grid size-9 shrink-0 place-items-center rounded-lg border-2 border-ink bg-white hover:bg-orange hover:text-white disabled:opacity-40"
            >
              <Plus className="size-4" />
            </button>
          </div>
        )}
      </SectionCard>
    </div>
  )

  const conversationTab = room && (
    <SectionCard title="Conversation" icon={MessageSquare}>
      {messages.length === 0 ? (
        <EmptyState
          icon={MessageSquare}
          title="No messages yet"
          hint="Talk through the objective here. Messages never command the agent — use Redirect for that."
        />
      ) : (
        <>
          {messageHistoryHasMore && (
            <div className="mb-4 flex justify-center">
              <Button
                type="button"
                variant="subtle"
                size="sm"
                disabled={messageHistoryLoading}
                onClick={() => void loadOlderMessages()}
              >
                {messageHistoryLoading
                  ? <Loader2 className="animate-spin" />
                  : <ChevronDown className="rotate-180" />}
                Load older messages
              </Button>
            </div>
          )}
          <ul className="space-y-3">
            {messages.map((message) => (
            <li key={message.id} className="flex gap-2.5">
              <span className={`mt-0.5 grid size-6 shrink-0 place-items-center rounded-full border ${
                message.author_type === 'agent'
                  ? 'border-orange/40 bg-warning-soft text-orange-dark'
                  : 'border-line bg-paper-2 text-muted'
              }`}>
                {message.author_type === 'agent' ? <Bot className="size-3" /> : <Users className="size-3" />}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="text-xs font-bold">{message.author_name}</span>
                  <span className="font-mono text-[9px] text-faint">{formatTime(message.created_at)}</span>
                  {message.edited_at && <span className="font-mono text-[9px] text-faint">edited</span>}
                </div>
                <p className={`mt-0.5 break-words text-xs leading-5 ${message.deleted ? 'italic text-faint' : 'text-ink-2'}`}>
                  {message.deleted ? 'This message was removed.' : message.body}
                </p>
                {message.references.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {message.references.map((reference) => (
                      <Badge key={`${reference.kind}-${reference.id}`} className="border-line bg-paper-2 text-[9px] text-muted">
                        {reference.label || reference.kind}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            </li>
            ))}
          </ul>
        </>
      )}
      {roomCan(room.room_role, 'comment') && !isArchived && (
        <div className="mt-4 flex gap-2">
          <input
            value={draftMessage}
            onChange={(event) => setDraftMessage(event.target.value)}
            onKeyDown={(event) => { if (event.key === 'Enter') void postMessage() }}
            placeholder="Write a message…"
            aria-label="New message"
            className="min-w-0 flex-1 rounded-lg border border-line bg-white px-3 py-2 text-xs outline-none focus:border-orange"
          />
          <Button size="sm" onClick={() => void postMessage()} disabled={working || !draftMessage.trim()}>
            <Send /> Send
          </Button>
        </div>
      )}
    </SectionCard>
  )

  const contextTab = room && (
    <div className="space-y-4">
      <SectionCard title="What the agent may read" icon={ShieldCheck}>
        {context ? (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-lg border border-line bg-paper-2 px-3 py-2">
                <p className="text-lg font-black">{context.confirmed_fact_count}</p>
                <p className="text-[10px] uppercase tracking-wide text-muted">Confirmed facts</p>
              </div>
              <div className="rounded-lg border border-line bg-paper-2 px-3 py-2">
                <p className="text-lg font-black">{context.accessible_source_count}</p>
                <p className="text-[10px] uppercase tracking-wide text-muted">Cited sources</p>
              </div>
            </div>
            <p className="mt-3 text-[11px] leading-4 text-muted">
              {visibilityLabels[context.visibility]}. Pins rank a source first;
              exclusions remove it from every run.
            </p>
            {(context.excluded_source_count > 0 || context.omitted_inaccessible_count > 0) && (
              <p className="mt-2 text-[11px] leading-4 text-muted">
                {context.excluded_source_count} excluded by this room
                {context.omitted_inaccessible_count > 0
                  ? `, ${context.omitted_inaccessible_count} outside this room's permission scope`
                  : ''}.
              </p>
            )}
          </>
        ) : (
          <div className="flex items-center gap-2 py-4 text-xs text-muted">
            <Loader2 className="size-4 animate-spin text-orange" /> Loading the context preview…
          </div>
        )}
      </SectionCard>

      <SectionCard title="Sources in scope" icon={FileText}>
        {!context || context.sources.length === 0 ? (
          <EmptyState icon={FileText} title="No sources in scope" hint="Confirm knowledge in the review queue to give this room something to work from." />
        ) : (
          <ul className="space-y-2">
            {context.sources.map((source) => (
              <li key={source.id} className="rounded-lg border border-line bg-paper-2 px-3 py-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="break-words text-[11px] font-bold">{source.title ?? 'Source'}</p>
                    {source.excerpt && (
                      <p className="mt-0.5 line-clamp-2 text-[11px] leading-4 text-muted">“{source.excerpt}”</p>
                    )}
                    {source.komponist_path && (
                      <Link href={source.komponist_path} className="mt-1 inline-block font-mono text-[9px] uppercase text-orange-dark hover:underline">
                        Open passage
                      </Link>
                    )}
                  </div>
                  {canEdit && (
                    <div className="flex shrink-0 gap-1">
                      <button
                        type="button"
                        aria-label={source.pinned ? 'Unpin source' : 'Pin source'}
                        onClick={() => void toggleContextPin(source.id, source.pinned)}
                        className={`grid size-7 place-items-center rounded border hover:border-ink ${
                          source.pinned ? 'border-orange bg-warning-soft text-orange-dark' : 'border-line bg-white text-muted'
                        }`}
                      >
                        {source.pinned ? <PinOff className="size-3" /> : <Pin className="size-3" />}
                      </button>
                      <button
                        type="button"
                        aria-label="Exclude source"
                        onClick={() => void excludeSource(source.id)}
                        className="grid size-7 place-items-center rounded border border-line bg-white text-muted hover:border-danger hover:text-danger"
                      >
                        <X className="size-3" />
                      </button>
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      {context && context.excluded.length > 0 && (
        <SectionCard title="Excluded" icon={X}>
          <ul className="space-y-1.5">
            {context.excluded.map((item) => (
              <li key={item.id} className="flex items-center justify-between gap-2">
                <span className="min-w-0 truncate text-[11px] text-muted">
                  {item.label || item.reference_id}
                </span>
                {canEdit && (
                  <button
                    type="button"
                    onClick={() => void mutate(`/workrooms/${room.id}/context/${item.id}`, { method: 'DELETE' })}
                    className="shrink-0 font-mono text-[9px] uppercase text-orange-dark hover:underline"
                  >
                    Restore
                  </button>
                )}
              </li>
            ))}
          </ul>
        </SectionCard>
      )}
    </div>
  )

  const deliverablesTab = room && (
    <SectionCard title="Shared deliverables" icon={FileText}>
      {deliverables.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No deliverables yet"
          hint="When you approve an agent's findings, the resulting cited deliverable is shared with everyone in this room."
        />
      ) : (
        <ul className="space-y-2">
          {deliverables.map((item) => (
            <li key={item.artifact_id} className="rounded-lg border border-line bg-paper-2 px-3 py-2">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="break-words text-xs font-bold">{item.title}</p>
                  <p className="mt-1 text-[11px] text-muted">
                    {item.source_count} cited sources · {formatDate(item.artifact_created_at)}
                    {item.approved_by_name ? ` · approved by ${item.approved_by_name}` : ''}
                  </p>
                  <Badge className="mt-1.5 border-teal/30 bg-success-soft text-[9px] uppercase text-teal">
                    Shared with Workroom
                  </Badge>
                </div>
                <div className="flex shrink-0 flex-wrap gap-1.5">
                  <Link href={item.compose_path}>
                    <Button size="sm" variant="outline">Open</Button>
                  </Link>
                  <a href={`${API_URL}/artifacts/${item.artifact_id}/download?org_id=${encodeURIComponent(orgId())}&format=markdown`}>
                    <Button size="sm" variant="ghost">Download</Button>
                  </a>
                  {canManage && (
                    <button
                      type="button"
                      aria-label={`Withdraw ${item.title}`}
                      onClick={() => void mutate(`/workrooms/${room.id}/deliverables/${item.artifact_id}`, { method: 'DELETE' })}
                      className="grid size-9 place-items-center rounded-lg border border-line bg-white text-muted hover:border-danger hover:text-danger"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  )

  const activityTab = room && (
    <SectionCard title="Activity" icon={Activity}>
      <p className="mb-3 text-[11px] leading-4 text-muted">
        An immutable audit trail of what happened in this Workroom.
      </p>
      {room.events.length === 0 ? (
        <EmptyState icon={Activity} title="Nothing has happened yet" />
      ) : (
        <ul className="space-y-2">
          {[...room.events].reverse().map((event) => (
            <li key={event.id} className="flex gap-2.5 border-b border-line pb-2 last:border-0">
              <span className="mt-1 font-mono text-[9px] text-faint">{formatTime(event.created_at)}</span>
              <div className="min-w-0">
                <p className="break-words text-[11px] leading-4">{event.message}</p>
                <p className="font-mono text-[9px] uppercase text-faint">
                  {event.actor_name} · {event.event_type.replace(/_/g, ' ')}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  )

  const tabContent: Record<TabKey, React.ReactNode> = {
    overview: overviewTab,
    plan: planTab,
    conversation: conversationTab,
    context: contextTab,
    deliverables: deliverablesTab,
    activity: activityTab,
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
        {workerOffline && (
          <div className="flex items-start gap-2 border-b-2 border-ink bg-warning-soft px-4 py-2.5 sm:px-8">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-orange-dark" />
            <p className="text-[11px] leading-4 text-orange-dark">
              No Workroom worker is online. New agent work is stored durably and
              will run as soon as a worker starts.
            </p>
          </div>
        )}

        {error && (
          <div className="flex items-start justify-between gap-3 border-b-2 border-ink bg-danger-soft px-4 py-2.5 sm:px-8">
            <p className="text-[11px] leading-4 text-danger">{error}</p>
            <button type="button" onClick={() => setError(null)} aria-label="Dismiss error">
              <X className="size-4 text-danger" />
            </button>
          </div>
        )}

        {/* Mobile room selector: the list becomes a compact disclosure so the
            page never needs a three-column layout to be usable. */}
        <div className="border-b-2 border-ink bg-white px-4 py-2 lg:hidden">
          <button
            type="button"
            onClick={() => setShowRoomPicker((open) => !open)}
            aria-expanded={showRoomPicker}
            className="flex w-full items-center justify-between gap-2 rounded-lg border border-line bg-paper-2 px-3 py-2 text-left"
          >
            <span className="min-w-0 truncate text-xs font-bold">
              {room?.title ?? 'Choose a Workroom'}
            </span>
            <ChevronDown className={`size-4 shrink-0 transition ${showRoomPicker ? 'rotate-180' : ''}`} />
          </button>
          <AnimatePresence>
            {showRoomPicker && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden"
              >
                <div className="mt-2 max-h-[50vh] overflow-y-auto rounded-lg border border-line">
                  {roomList}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <div className="mx-auto grid w-full max-w-[1600px] grid-cols-1 gap-0 lg:grid-cols-[260px_minmax(0,1fr)] xl:grid-cols-[260px_minmax(0,1fr)_300px]">
          <aside className="hidden border-r-2 border-ink bg-white lg:block">
            {roomList}
          </aside>

          <section className="min-w-0">
            {loading ? (
              <div className="grid min-h-[420px] place-items-center">
                <Loader2 className="size-7 animate-spin text-orange" />
              </div>
            ) : !room ? (
              <div className="grid min-h-[420px] place-items-center px-4">
                <EmptyState
                  icon={RadioTower}
                  title="Select or create a Workroom"
                  hint="A Workroom gives people and agents one objective, one governed context, and one shared deliverable."
                />
              </div>
            ) : (
              <>
                <header className="border-b-2 border-ink bg-white px-4 py-4 sm:px-6 sm:py-5">
                  <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        {isArchived && (
                          <Badge className="border-line bg-paper-2 text-[9px] uppercase text-muted">Archived</Badge>
                        )}
                        <Badge className="border-line bg-paper-2 text-[9px] uppercase text-muted">
                          {room.room_role}
                        </Badge>
                        {room.visibility === 'private' && (
                          <Badge className="border-line bg-paper-2 text-[9px] uppercase text-muted">
                            <Lock className="mr-1 inline size-2.5" /> Private
                          </Badge>
                        )}
                      </div>
                      <h2 className="mt-2 break-words text-xl font-black tracking-tight sm:text-2xl">
                        {room.title}
                      </h2>
                      <p className="mt-1.5 max-w-2xl break-words text-sm leading-6 text-muted">
                        {room.objective}
                      </p>
                    </div>
                    <div className="flex min-w-0 flex-wrap items-center gap-2 md:shrink-0 md:justify-end">
                      {activeRun && <RunStatusChip run={activeRun} />}
                      {agentControls}
                      {canManage && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => void mutate(`/workrooms/${room.id}/${isArchived ? 'reopen' : 'archive'}`, { method: 'POST' })}
                          disabled={working}
                        >
                          {isArchived ? <ArchiveRestore /> : <Archive />}
                          {isArchived ? 'Reopen' : 'Archive'}
                        </Button>
                      )}
                    </div>
                  </div>

                  {canEdit && (
                    <div className="mt-4 flex flex-col gap-2 sm:flex-row">
                      <input
                        value={direction}
                        onChange={(event) => setDirection(event.target.value)}
                        placeholder={activeRun && activeRunStatuses.includes(activeRun.status)
                          ? 'Change the agent’s direction…'
                          : 'Give the agent a direction…'}
                        aria-label="Agent direction"
                        className="min-w-0 flex-1 rounded-lg border border-line bg-paper-2 px-3 py-2 text-xs outline-none focus:border-orange"
                      />
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void (activeRun && activeRunStatuses.includes(activeRun.status)
                          ? redirectAgent()
                          : startAgent())}
                        disabled={
                          working
                          || (!direction.trim() && !!activeRun)
                          || (
                            (!activeRun || !activeRunStatuses.includes(activeRun.status))
                            && runnableAgentTasks.length === 0
                          )
                        }
                      >
                        {activeRun && activeRunStatuses.includes(activeRun.status)
                          ? <><RotateCcw /> Redirect</>
                          : <><Send /> Start</>}
                      </Button>
                    </div>
                  )}
                </header>

                {approvalPanel && (
                  <div className="border-b-2 border-ink bg-warning-soft p-3 sm:px-6 sm:py-4">
                    {approvalPanel}
                  </div>
                )}

                <nav
                  className="grid grid-cols-3 border-b-2 border-ink bg-white px-2 sm:flex sm:gap-1 sm:overflow-x-auto sm:px-4"
                  aria-label="Workroom sections"
                >
                  {tabs.map(({ key, label, icon: Icon }) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setTab(key)}
                      aria-current={tab === key ? 'page' : undefined}
                      className={`flex min-w-0 items-center justify-center gap-1 border-b-2 px-1.5 py-2.5 text-[10px] font-bold transition sm:shrink-0 sm:justify-start sm:gap-1.5 sm:px-3 sm:text-xs ${
                        tab === key
                          ? 'border-orange text-orange-dark'
                          : 'border-transparent text-muted hover:text-ink'
                      }`}
                    >
                      <Icon className="size-3.5 shrink-0" />
                      <span className="min-w-0 truncate">{label}</span>
                    </button>
                  ))}
                </nav>

                <div className="p-4 sm:p-6">
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={tab}
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.15 }}
                    >
                      {tabContent[tab]}
                    </motion.div>
                  </AnimatePresence>

                  {/* Supporting status cards belong to Overview on compact
                      layouts; repeating them below every tab makes mobile
                      conversations and plans unnecessarily long. */}
                  {tab === 'overview' && (
                    <div className="mt-4 xl:hidden">{rightRail}</div>
                  )}
                </div>
              </>
            )}
          </section>

          <aside className="hidden border-l-2 border-ink bg-paper p-4 xl:block">
            {rightRail}
          </aside>
        </div>
      </main>

      <AnimatePresence>
        {showCreate && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4"
            onClick={() => setShowCreate(false)}
          >
            <motion.div
              initial={{ scale: 0.97, y: 8 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.97, y: 8 }}
              onClick={(event) => event.stopPropagation()}
              className="max-h-[calc(100dvh-2rem)] w-full max-w-lg overflow-y-auto rounded-xl border-2 border-ink bg-white p-4 shadow-[6px_6px_0_var(--color-ink)] sm:p-5"
            >
              <h2 className="text-lg font-black">New Workroom</h2>
              <p className="mt-1 text-xs text-muted">
                Give it one outcome. People and agents will work from the same governed context.
              </p>
              <button
                type="button"
                onClick={() => void loadCampusKollektivExample()}
                disabled={working}
                className="mt-4 flex w-full items-center gap-3 rounded-lg border-2 border-ink bg-success-soft p-3 text-left transition hover:shadow-[2px_2px_0_var(--color-ink)] disabled:cursor-wait disabled:opacity-60"
              >
                <span className="grid size-9 shrink-0 place-items-center rounded-lg border border-ink bg-white">
                  {working
                    ? <Loader2 className="size-4 animate-spin" />
                    : <Sparkles className="size-4 text-teal" />}
                </span>
                <span>
                  <strong className="block text-xs">Use the CampusKollektiv example</strong>
                  <span className="mt-0.5 block text-[10px] leading-4 text-muted">
                    Load the fictional student initiative and prefill a real Campus Forum objective.
                  </span>
                </span>
              </button>
              <div className="mt-4 space-y-3">
                <div>
                  <label htmlFor="room-title" className="font-mono text-[10px] font-bold uppercase tracking-wide text-ink-2">Title</label>
                  <input
                    id="room-title"
                    value={newTitle}
                    onChange={(event) => setNewTitle(event.target.value)}
                    placeholder="e.g. Campus Forum launch room"
                    className="mt-1 w-full rounded-lg border border-line bg-paper-2 px-3 py-2 text-sm outline-none focus:border-orange"
                  />
                </div>
                <div>
                  <label htmlFor="room-objective" className="font-mono text-[10px] font-bold uppercase tracking-wide text-ink-2">Objective</label>
                  <textarea
                    id="room-objective"
                    value={newObjective}
                    onChange={(event) => setNewObjective(event.target.value)}
                    rows={3}
                    placeholder="e.g. Prepare a cited readiness update for the initiative board"
                    className="mt-1 w-full resize-none rounded-lg border border-line bg-paper-2 px-3 py-2 text-sm outline-none focus:border-orange"
                  />
                </div>
                <div>
                  <span className="font-mono text-[10px] font-bold uppercase tracking-wide text-ink-2">Who can see it</span>
                  <div className="mt-1 flex flex-col gap-1.5">
                    {(Object.keys(visibilityLabels) as RoomVisibility[]).map((value) => (
                      <label key={value} className="flex cursor-pointer items-center gap-2 text-xs">
                        <input
                          type="radio"
                          name="visibility"
                          checked={newVisibility === value}
                          onChange={() => setNewVisibility(value)}
                          className="accent-orange"
                        />
                        {visibilityLabels[value]}
                      </label>
                    ))}
                  </div>
                </div>
                {newVisibility === 'departments' && departments.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {departments.map((department) => {
                      const selected = newDepartments.includes(department.id)
                      return (
                        <button
                          key={department.id}
                          type="button"
                          onClick={() => setNewDepartments((current) =>
                            selected
                              ? current.filter((id) => id !== department.id)
                              : [...current, department.id])}
                          className={`rounded-full border px-2.5 py-1 text-[10px] ${
                            selected ? 'border-ink bg-orange text-white' : 'border-line bg-paper-2 text-muted'
                          }`}
                        >
                          {department.name}
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
              <div className="mt-5 flex justify-end gap-2">
                <Button variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
                <Button
                  onClick={() => void createRoom()}
                  disabled={working || !newTitle.trim() || !newObjective.trim()
                    || (newVisibility === 'departments' && newDepartments.length === 0)}
                >
                  {working ? <Loader2 className="animate-spin" /> : <Plus />} Create
                </Button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </AppLayout>
  )
}
