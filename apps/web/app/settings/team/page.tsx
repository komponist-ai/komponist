'use client'

import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  ArrowRightLeft, Building2, Check, ChevronRight, Clipboard, Crown,
  Edit3, Eye, Layers3, LoaderCircle, LockKeyhole, MailPlus, Plus,
  RefreshCcw, Save, ShieldCheck, Trash2, UserMinus, UserRound, UsersRound, X,
} from 'lucide-react'
import AppLayout from '../../../components/AppLayout'
import SettingsNotice, { type SettingsMessage } from '../../../components/SettingsNotice'
import StudioTopbar from '../../../components/StudioTopbar'
import { useAuth } from '../../../components/AuthProvider'
import { Badge } from '../../../components/ui/badge'
import { Button } from '../../../components/ui/button'
import { API_URL, apiFetch } from '../../../lib/api'

type MemberRole = 'owner' | 'admin' | 'member' | 'viewer'
type InviteRole = Exclude<MemberRole, 'owner'>

interface DepartmentSummary {
  id: string
  name: string
  description?: string | null
  color: 'orange' | 'teal' | 'blue' | 'violet' | 'rose' | 'amber'
  member_count: number
}

interface Member {
  id: string
  user_id: string
  name: string
  email: string
  role: MemberRole
  departments: Pick<DepartmentSummary, 'id' | 'name' | 'color'>[]
}

const DEPARTMENT_COLORS: DepartmentSummary['color'][] = ['orange', 'teal', 'blue', 'violet', 'rose', 'amber']

export default function TeamSettingsPage() {
  const { user, refresh: refreshSession } = useAuth()
  const [members, setMembers] = useState<Member[]>([])
  const [departments, setDepartments] = useState<DepartmentSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState<SettingsMessage | null>(null)

  const [email, setEmail] = useState('')
  const [inviteRole, setInviteRole] = useState<InviteRole>('member')
  const [inviteDepartments, setInviteDepartments] = useState<string[]>([])
  const [submittingInvite, setSubmittingInvite] = useState(false)
  const [inviteUrl, setInviteUrl] = useState('')
  const [copied, setCopied] = useState(false)

  const [departmentName, setDepartmentName] = useState('')
  const [departmentDescription, setDepartmentDescription] = useState('')
  const [departmentColor, setDepartmentColor] = useState<DepartmentSummary['color']>('orange')
  const [creatingDepartment, setCreatingDepartment] = useState(false)

  const [editingMember, setEditingMember] = useState<Member | null>(null)
  const [memberRole, setMemberRole] = useState<InviteRole>('member')
  const [memberDepartments, setMemberDepartments] = useState<string[]>([])
  const [savingMember, setSavingMember] = useState(false)
  const [removeArmed, setRemoveArmed] = useState(false)

  const [editingDepartment, setEditingDepartment] = useState<DepartmentSummary | null>(null)
  const [departmentEditName, setDepartmentEditName] = useState('')
  const [departmentEditDescription, setDepartmentEditDescription] = useState('')
  const [departmentEditColor, setDepartmentEditColor] = useState<DepartmentSummary['color']>('orange')
  const [savingDepartment, setSavingDepartment] = useState(false)
  const [deletingDepartment, setDeletingDepartment] = useState<DepartmentSummary | null>(null)
  const [replacementDepartment, setReplacementDepartment] = useState('')

  const canManage = user?.role === 'owner' || user?.role === 'admin'
  const isInviteEmailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())
  const limitedInviteNeedsDepartment = inviteRole !== 'admin' && departments.length > 0
  const inviteValid = isInviteEmailValid && (!limitedInviteNeedsDepartment || inviteDepartments.length > 0)

  const roleCounts = useMemo(() => members.reduce<Record<string, number>>((counts, member) => {
    counts[member.role] = (counts[member.role] || 0) + 1
    return counts
  }, {}), [members])

  const loadTeam = useCallback(async () => {
    if (!user) return
    setLoading(true)
    setMessage(null)
    try {
      const [membersResponse, departmentsResponse] = await Promise.all([
        apiFetch(`${API_URL}/auth/organizations/${encodeURIComponent(user.org_id)}/members`),
        apiFetch(`${API_URL}/auth/organizations/${encodeURIComponent(user.org_id)}/departments`),
      ])
      const [membersPayload, departmentsPayload] = await Promise.all([
        membersResponse.json(), departmentsResponse.json(),
      ])
      if (!membersResponse.ok) throw new Error(membersPayload.detail || 'Could not load organization members')
      if (!departmentsResponse.ok) throw new Error(departmentsPayload.detail || 'Could not load departments')
      setMembers(membersPayload.members || [])
      setDepartments(departmentsPayload.departments || [])
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Could not load team structure' })
    } finally {
      setLoading(false)
    }
  }, [user])

  useEffect(() => { void loadTeam() }, [loadTeam])

  const toggleDepartment = (id: string, selected: string[], update: (value: string[]) => void) => {
    update(selected.includes(id) ? selected.filter(item => item !== id) : [...selected, id])
  }

  const createDepartment = async (event: FormEvent) => {
    event.preventDefault()
    if (!user || !canManage || !departmentName.trim()) return
    setCreatingDepartment(true)
    setMessage(null)
    try {
      const response = await apiFetch(`${API_URL}/auth/organizations/${encodeURIComponent(user.org_id)}/departments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: departmentName, description: departmentDescription, color: departmentColor }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not create department')
      setDepartmentName('')
      setDepartmentDescription('')
      setDepartmentColor('orange')
      setMessage({ type: 'success', text: `${payload.name} is ready for members and knowledge.` })
      await loadTeam()
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Could not create department' })
    } finally {
      setCreatingDepartment(false)
    }
  }

  const createInvitation = async (event: FormEvent) => {
    event.preventDefault()
    if (!user || !canManage || !inviteValid) return
    const normalizedEmail = email.trim().toLowerCase()
    setSubmittingInvite(true)
    setInviteUrl('')
    setCopied(false)
    setMessage(null)
    try {
      const response = await apiFetch(`${API_URL}/auth/organizations/${encodeURIComponent(user.org_id)}/invitations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: normalizedEmail,
          role: inviteRole,
          department_ids: inviteRole === 'admin' ? [] : inviteDepartments,
        }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not create invitation')
      setInviteUrl(payload.invite_url)
      setEmail('')
      setMessage({ type: 'success', text: `Invite link created for ${normalizedEmail}.` })
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Could not create invitation' })
    } finally {
      setSubmittingInvite(false)
    }
  }

  const copyInvite = async () => {
    try {
      await navigator.clipboard.writeText(inviteUrl)
      setCopied(true)
      setMessage({ type: 'success', text: 'Invite link copied to the clipboard.' })
    } catch {
      setMessage({ type: 'error', text: 'Copy failed. Select and copy the link manually.' })
    }
  }

  const openMemberEditor = (member: Member) => {
    setEditingMember(member)
    setMemberRole(member.role === 'owner' ? 'member' : member.role)
    setMemberDepartments(member.departments.map(department => department.id))
    setRemoveArmed(false)
  }

  const saveMember = async () => {
    if (!user || !editingMember || !canManage) return
    setSavingMember(true)
    setMessage(null)
    try {
      const response = await apiFetch(`${API_URL}/auth/organizations/${encodeURIComponent(user.org_id)}/members/${encodeURIComponent(editingMember.id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          role: memberRole,
          department_ids: memberRole === 'admin' ? [] : memberDepartments,
        }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not update member')
      setEditingMember(null)
      setMessage({ type: 'success', text: `${editingMember.name || editingMember.email} was reorganized.` })
      await Promise.all([loadTeam(), refreshSession()])
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Could not update member' })
    } finally {
      setSavingMember(false)
    }
  }

  const removeMember = async () => {
    if (!user || !editingMember || !removeArmed) return
    setSavingMember(true)
    setMessage(null)
    try {
      const response = await apiFetch(`${API_URL}/auth/organizations/${encodeURIComponent(user.org_id)}/members/${encodeURIComponent(editingMember.id)}`, { method: 'DELETE' })
      if (!response.ok) {
        const payload = await response.json()
        throw new Error(payload.detail || 'Could not remove member')
      }
      const removedName = editingMember.name || editingMember.email
      setEditingMember(null)
      setMessage({ type: 'success', text: `${removedName} no longer has access to this organization.` })
      await loadTeam()
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Could not remove member' })
    } finally {
      setSavingMember(false)
      setRemoveArmed(false)
    }
  }

  const openDepartmentEditor = (department: DepartmentSummary) => {
    setEditingDepartment(department)
    setDepartmentEditName(department.name)
    setDepartmentEditDescription(department.description || '')
    setDepartmentEditColor(department.color)
  }

  const saveDepartment = async () => {
    if (!user || !editingDepartment || !departmentEditName.trim()) return
    setSavingDepartment(true)
    setMessage(null)
    try {
      const response = await apiFetch(`${API_URL}/auth/organizations/${encodeURIComponent(user.org_id)}/departments/${encodeURIComponent(editingDepartment.id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: departmentEditName, description: departmentEditDescription, color: departmentEditColor }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not update department')
      setEditingDepartment(null)
      setMessage({ type: 'success', text: `${payload.name} was updated.` })
      await loadTeam()
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Could not update department' })
    } finally {
      setSavingDepartment(false)
    }
  }

  const removeDepartment = async () => {
    if (!user || !deletingDepartment) return
    setSavingDepartment(true)
    setMessage(null)
    try {
      const query = replacementDepartment ? `?reassign_to=${encodeURIComponent(replacementDepartment)}` : ''
      const response = await apiFetch(`${API_URL}/auth/organizations/${encodeURIComponent(user.org_id)}/departments/${encodeURIComponent(deletingDepartment.id)}${query}`, { method: 'DELETE' })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Could not delete department')
      const name = deletingDepartment.name
      setDeletingDepartment(null)
      setReplacementDepartment('')
      setMessage({ type: 'success', text: replacementDepartment ? `${name} was merged into the selected department.` : `${name} was removed.` })
      await loadTeam()
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Could not delete department' })
    } finally {
      setSavingDepartment(false)
    }
  }

  return (
    <AppLayout>
      <StudioTopbar
        section="Settings"
        title="Team & departments"
        description={`Organize governance and need-to-know access for ${user?.organization.name ?? 'this workspace'}`}
        icon={UsersRound}
        actions={<Button variant="outline" size="sm" onClick={() => void loadTeam()} disabled={loading}><RefreshCcw className={loading ? 'animate-spin' : ''} /><span className="hidden sm:inline">Refresh</span></Button>}
      />

      <div className="page-body max-w-7xl space-y-6">
        {message && <SettingsNotice message={message} />}

        <section className="grid overflow-hidden rounded-2xl border-2 border-ink bg-white shadow-[7px_7px_0_var(--color-shadow-strong)] lg:grid-cols-[1.1fr_0.9fr]">
          <div className="border-b-2 border-ink p-6 sm:p-9 lg:border-b-0 lg:border-r-2">
            <Badge variant="orange"><Building2 className="size-3.5" /> Organization structure</Badge>
            <h2 className="mt-6 max-w-2xl text-4xl font-bold leading-tight tracking-tight sm:text-5xl">One brain. Deliberate boundaries.</h2>
            <p className="mt-5 max-w-2xl leading-7 text-muted">Board and admins can work across the initiative. Members only retrieve global knowledge and content assigned to their departments.</p>
            <div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <TeamMetric label="People" value={loading ? '—' : members.length} />
              <TeamMetric label="Departments" value={loading ? '—' : departments.length} />
              <TeamMetric label="Board & admins" value={loading ? '—' : (roleCounts.owner || 0) + (roleCounts.admin || 0)} />
              <TeamMetric label="Scoped members" value={loading ? '—' : members.filter(member => member.role === 'member' || member.role === 'viewer').length} />
            </div>
          </div>
          <div className="relative overflow-hidden bg-ink p-6 text-white sm:p-9">
            <div className="absolute -right-16 -top-16 size-52 rounded-full border-[34px] border-orange/75" />
            <div className="relative">
              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-teal-light">Governance model</p>
              <h3 className="mt-3 text-2xl font-bold">Built for committees and working groups.</h3>
              <div className="mt-7 space-y-4">
                <RoleSummary icon={Crown} role="Owner" description="Controls board access and the entire organization." />
                <RoleSummary icon={ShieldCheck} role="Board / admin" description="Sees every department and manages structure, members, and sources." />
                <RoleSummary icon={UserRound} role="Member" description="Contributes and reads only assigned or organization-wide context." />
                <RoleSummary icon={Eye} role="Viewer" description="Read-only access with the same department boundaries." />
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-[1.25fr_0.75fr]">
          <div className="overflow-hidden rounded-2xl border-2 border-ink bg-white shadow-[5px_5px_0_var(--color-shadow-soft)]">
            <SectionHeading eyebrow="Structure" title="Departments" detail="Departments scope documents, graph entities, review, and chat." icon={Layers3} />
            {loading ? <LoadingRows /> : departments.length === 0 ? (
              <EmptyState icon={Layers3} title="No departments yet" detail="Create the first working group, committee, or functional department." />
            ) : (
              <div className="grid gap-3 p-5 sm:grid-cols-2 sm:p-7">
                {departments.map(department => (
                  <motion.button key={department.id} type="button" whileHover={{ y: -2 }} onClick={() => canManage && openDepartmentEditor(department)} className="rounded-xl border-2 border-ink bg-paper-2 p-4 text-left shadow-[3px_3px_0_var(--color-shadow-soft)] transition hover:shadow-[4px_4px_0_var(--color-shadow-strong)] disabled:cursor-default">
                    <div className="flex items-start justify-between gap-3">
                      <DepartmentMark color={department.color} />
                      {canManage ? <Edit3 className="size-4 text-muted" /> : null}
                    </div>
                    <h4 className="mt-4 text-lg font-bold">{department.name}</h4>
                    <p className="mt-1 min-h-10 text-xs leading-5 text-muted">{department.description || 'No description yet.'}</p>
                    <div className="mt-4 flex items-center justify-between border-t-2 border-line pt-3 text-xs font-semibold"><span>{department.member_count} member{department.member_count === 1 ? '' : 's'}</span><span className="flex items-center gap-1 text-orange-dark">Manage <ChevronRight className="size-3.5" /></span></div>
                  </motion.button>
                ))}
              </div>
            )}
          </div>

          <form className="rounded-2xl border-2 border-ink bg-white p-6 shadow-[5px_5px_0_var(--color-shadow-soft)] sm:p-8" onSubmit={createDepartment}>
            <span className="grid size-11 place-items-center rounded-xl border-2 border-ink bg-teal text-white shadow-[3px_3px_0_var(--color-shadow-strong)]"><Plus className="size-5" /></span>
            <h3 className="mt-5 text-2xl font-bold">Create a department</h3>
            {canManage ? <>
              <p className="mt-2 text-sm leading-6 text-muted">Use departments for teams such as Events, Partnerships, Product, or Finance.</p>
              <div className="mt-6 space-y-4">
                <Field label="Department name"><input className="settings-input" value={departmentName} onChange={event => setDepartmentName(event.target.value)} placeholder="e.g. Partnerships" maxLength={100} required /></Field>
                <Field label="Purpose"><textarea className="settings-input min-h-24 py-3" value={departmentDescription} onChange={event => setDepartmentDescription(event.target.value)} placeholder="What context belongs here?" maxLength={500} /></Field>
                <ColorPicker value={departmentColor} onChange={setDepartmentColor} />
                <Button className="w-full" disabled={creatingDepartment || !departmentName.trim()}>{creatingDepartment ? <LoaderCircle className="animate-spin" /> : <Plus />}{creatingDepartment ? 'Creating…' : 'Create department'}</Button>
              </div>
            </> : <AdminRequired />}
          </form>
        </section>

        <section className="grid gap-6 xl:grid-cols-[1.3fr_0.7fr]">
          <div className="overflow-hidden rounded-2xl border-2 border-ink bg-white shadow-[5px_5px_0_var(--color-shadow-soft)]">
            <SectionHeading eyebrow="Directory" title="Organization members" detail="Select a person to change their role or department access." icon={UsersRound} />
            {loading ? <LoadingRows /> : (
              <div className="divide-y-2 divide-line">
                {members.map((member, index) => {
                  const editable = canManage && member.role !== 'owner' && !(user?.role === 'admin' && member.role === 'admin')
                  return <motion.button key={member.id} type="button" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(index * 0.03, 0.18) }} onClick={() => editable && openMemberEditor(member)} className="flex w-full items-center gap-4 px-5 py-4 text-left transition hover:bg-paper-2 disabled:cursor-default sm:px-8">
                    <div className="grid size-11 shrink-0 place-items-center rounded-xl border-2 border-ink bg-warning-soft font-display text-sm font-black shadow-[2px_2px_0_var(--color-shadow-strong)]">{(member.name || member.email).slice(0, 1).toUpperCase()}</div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-bold">{member.name || member.email}{member.user_id === user?.id ? <span className="ml-2 text-xs font-normal text-muted">You</span> : null}</div>
                      <div className="mt-1 truncate text-xs text-muted">{member.email}</div>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {member.role === 'owner' || member.role === 'admin' ? <Badge variant="orange">All departments</Badge> : member.departments.length ? member.departments.map(department => <DepartmentPill key={department.id} department={department} />) : <Badge>Global only</Badge>}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2"><Badge variant={member.role === 'owner' || member.role === 'admin' ? 'orange' : member.role === 'viewer' ? 'default' : 'teal'}>{roleLabel(member.role)}</Badge>{editable ? <ChevronRight className="size-4 text-muted" /> : <LockKeyhole className="size-4 text-faint" />}</div>
                  </motion.button>
                })}
              </div>
            )}
          </div>

          <div className="rounded-2xl border-2 border-ink bg-white p-6 shadow-[5px_5px_0_var(--color-shadow-soft)] sm:p-8">
            <span className="grid size-11 place-items-center rounded-xl border-2 border-ink bg-orange text-white shadow-[3px_3px_0_var(--color-shadow-strong)]"><MailPlus className="size-5" /></span>
            <h3 className="mt-5 text-2xl font-bold">Invite a member</h3>
            {canManage ? <>
              <p className="mt-2 text-sm leading-6 text-muted">Choose governance and department access before they join.</p>
              <form className="mt-6 space-y-4" onSubmit={createInvitation}>
                <Field label="Email address"><input className="settings-input" type="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="member@initiative.org" autoComplete="email" required /></Field>
                <Field label="Role"><select className="settings-input" value={inviteRole} onChange={event => { const nextRole = event.target.value as InviteRole; setInviteRole(nextRole); if (nextRole === 'admin') setInviteDepartments([]) }}>{user?.role === 'owner' && <option value="admin">Board / admin</option>}<option value="member">Member</option><option value="viewer">Viewer</option></select></Field>
                {inviteRole !== 'admin' && <DepartmentChecklist departments={departments} selected={inviteDepartments} onToggle={id => toggleDepartment(id, inviteDepartments, setInviteDepartments)} emptyLabel="Create a department first, or invite with global-only access." />}
                <Button className="w-full" disabled={submittingInvite || !inviteValid}>{submittingInvite ? <LoaderCircle className="animate-spin" /> : <MailPlus />}{submittingInvite ? 'Creating invite…' : 'Create invite link'}</Button>
              </form>
              {inviteUrl && <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="mt-6 rounded-xl border-2 border-teal bg-success-soft p-4"><div className="flex items-center gap-2 text-sm font-bold text-teal"><Check className="size-4" /> Link ready</div><input className="mt-3 w-full rounded-lg border-2 border-ink bg-white px-3 py-2 font-mono text-xs" readOnly value={inviteUrl} aria-label="Invite link" /><Button variant="outline" className="mt-3 w-full" type="button" onClick={() => void copyInvite()}>{copied ? <Check /> : <Clipboard />}{copied ? 'Copied' : 'Copy invite link'}</Button></motion.div>}
            </> : <AdminRequired />}
          </div>
        </section>
      </div>

      <AnimatePresence>
        {editingMember && <Modal onClose={() => setEditingMember(null)} title="Reorganize member" eyebrow="Member access" icon={ArrowRightLeft}>
          <div className="flex items-center gap-3 rounded-xl border-2 border-ink bg-paper-2 p-4"><div className="grid size-10 place-items-center rounded-lg border-2 border-ink bg-warning-soft font-bold">{(editingMember.name || editingMember.email)[0].toUpperCase()}</div><div className="min-w-0"><strong className="block truncate text-sm">{editingMember.name}</strong><span className="block truncate text-xs text-muted">{editingMember.email}</span></div></div>
          <div className="mt-5 space-y-5">
            <Field label="Governance role"><select className="settings-input" value={memberRole} onChange={event => { const nextRole = event.target.value as InviteRole; setMemberRole(nextRole); if (nextRole === 'admin') setMemberDepartments([]) }}>{user?.role === 'owner' && <option value="admin">Board / admin</option>}<option value="member">Member</option><option value="viewer">Viewer</option></select></Field>
            {memberRole === 'admin' ? <div className="rounded-xl border-2 border-orange bg-warning-soft p-4 text-sm"><strong>Organization-wide access</strong><p className="mt-1 text-xs leading-5 text-muted">Board/admin members see every department and can manage the organization.</p></div> : <DepartmentChecklist departments={departments} selected={memberDepartments} onToggle={id => toggleDepartment(id, memberDepartments, setMemberDepartments)} emptyLabel="No departments exist. This member will only see organization-wide knowledge." />}
            <div className="rounded-xl border-2 border-line bg-paper-2 p-3 text-xs leading-5 text-muted"><LockKeyhole className="mr-1 inline size-3.5" /> Changing access clears this member&apos;s existing chat history so removed context cannot remain visible.</div>
            <div className="flex gap-3"><Button className="flex-1" onClick={() => void saveMember()} disabled={savingMember}>{savingMember ? <LoaderCircle className="animate-spin" /> : <Save />}Save access</Button><Button variant="outline" onClick={() => setEditingMember(null)}>Cancel</Button></div>
            <div className="border-t-2 border-line pt-5"><Button variant={removeArmed ? 'destructive' : 'outline'} className="w-full" onClick={() => removeArmed ? void removeMember() : setRemoveArmed(true)} disabled={savingMember}>{removeArmed ? <Trash2 /> : <UserMinus />}{removeArmed ? 'Confirm removal from organization' : 'Remove from organization'}</Button>{removeArmed && <p className="mt-2 text-center text-xs text-danger">This revokes their organization membership immediately.</p>}</div>
          </div>
        </Modal>}

        {editingDepartment && <Modal onClose={() => setEditingDepartment(null)} title="Edit department" eyebrow="Structure" icon={Edit3}>
          <div className="space-y-4"><Field label="Name"><input className="settings-input" value={departmentEditName} onChange={event => setDepartmentEditName(event.target.value)} /></Field><Field label="Purpose"><textarea className="settings-input min-h-24 py-3" value={departmentEditDescription} onChange={event => setDepartmentEditDescription(event.target.value)} /></Field><ColorPicker value={departmentEditColor} onChange={setDepartmentEditColor} /><div className="flex gap-3"><Button className="flex-1" onClick={() => void saveDepartment()} disabled={savingDepartment || !departmentEditName.trim()}>{savingDepartment ? <LoaderCircle className="animate-spin" /> : <Save />}Save department</Button><Button variant="outline" onClick={() => setEditingDepartment(null)}>Cancel</Button></div><div className="border-t-2 border-line pt-5"><Button variant="outline" className="w-full text-danger" onClick={() => { setDeletingDepartment(editingDepartment); setEditingDepartment(null); setReplacementDepartment(departments.find(item => item.id !== editingDepartment.id)?.id || '') }}><Trash2 />Delete or merge department</Button></div></div>
        </Modal>}

        {deletingDepartment && <Modal onClose={() => setDeletingDepartment(null)} title="Delete department" eyebrow="Reorganize knowledge" icon={Trash2}>
          <div className="rounded-xl border-2 border-danger bg-danger-soft p-4"><strong className="text-sm text-danger">{deletingDepartment.name} will be removed.</strong><p className="mt-2 text-xs leading-5 text-muted">Members, connected sources, documents, and graph knowledge can move together to another department.</p></div>
          <div className="mt-5 space-y-4"><Field label="Move everything to"><select className="settings-input" value={replacementDepartment} onChange={event => setReplacementDepartment(event.target.value)}><option value="">Do not reassign (only works when no knowledge exists)</option>{departments.filter(item => item.id !== deletingDepartment.id).map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field><Button variant="destructive" className="w-full" onClick={() => void removeDepartment()} disabled={savingDepartment}>{savingDepartment ? <LoaderCircle className="animate-spin" /> : <Trash2 />}{replacementDepartment ? 'Merge and delete department' : 'Delete empty department'}</Button><Button variant="outline" className="w-full" onClick={() => setDeletingDepartment(null)}>Cancel</Button></div>
        </Modal>}
      </AnimatePresence>
    </AppLayout>
  )
}

function roleLabel(role: MemberRole) { return role === 'admin' ? 'Board / admin' : role }

function TeamMetric({ label, value }: { label: string; value: string | number }) { return <div className="rounded-xl border-2 border-ink bg-paper-2 p-3 shadow-[2px_2px_0_var(--color-shadow-soft)]"><strong className="block text-2xl">{value}</strong><span className="font-mono text-[9px] font-bold uppercase tracking-wider text-muted">{label}</span></div> }

function RoleSummary({ icon: Icon, role, description }: { icon: typeof Crown; role: string; description: string }) { return <div className="flex gap-3 border-b border-white/15 pb-4 last:border-0 last:pb-0"><span className="grid size-9 shrink-0 place-items-center rounded-lg border border-white/25 bg-white/10"><Icon className="size-4 text-teal-light" /></span><div><strong className="block text-sm">{role}</strong><p className="mt-1 text-xs leading-5 text-white/55">{description}</p></div></div> }

function SectionHeading({ eyebrow, title, detail, icon: Icon }: { eyebrow: string; title: string; detail: string; icon: typeof Layers3 }) { return <div className="flex items-center gap-4 border-b-2 border-ink bg-paper-2 px-5 py-5 sm:px-7"><span className="grid size-10 shrink-0 place-items-center rounded-xl border-2 border-ink bg-white shadow-[2px_2px_0_var(--color-shadow-strong)]"><Icon className="size-4" /></span><div><p className="font-mono text-[9px] font-bold uppercase tracking-[0.16em] text-orange-dark">{eyebrow}</p><h3 className="mt-1 text-xl font-bold">{title}</h3><p className="mt-1 text-xs text-muted">{detail}</p></div></div> }

function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="block"><span className="font-mono text-[10px] font-bold uppercase tracking-wider text-muted">{label}</span><div className="mt-2">{children}</div></label> }

function DepartmentChecklist({ departments, selected, onToggle, emptyLabel }: { departments: DepartmentSummary[]; selected: string[]; onToggle: (id: string) => void; emptyLabel: string }) { return <fieldset><legend className="font-mono text-[10px] font-bold uppercase tracking-wider text-muted">Department access</legend>{departments.length ? <div className="mt-2 grid gap-2 sm:grid-cols-2">{departments.map(department => { const checked = selected.includes(department.id); return <button key={department.id} type="button" onClick={() => onToggle(department.id)} className={`flex items-center gap-2 rounded-xl border-2 px-3 py-2.5 text-left text-xs font-semibold transition ${checked ? 'border-ink bg-warning-soft shadow-[2px_2px_0_var(--color-shadow-strong)]' : 'border-line bg-white hover:border-ink'}`}><span className={`grid size-5 place-items-center rounded border-2 ${checked ? 'border-ink bg-teal text-white' : 'border-line bg-white'}`}>{checked && <Check className="size-3" />}</span><DepartmentMark color={department.color} small /><span className="truncate">{department.name}</span></button> })}</div> : <div className="mt-2 rounded-xl border-2 border-line bg-paper-2 p-3 text-xs leading-5 text-muted">{emptyLabel}</div>}</fieldset> }

function ColorPicker({ value, onChange }: { value: DepartmentSummary['color']; onChange: (value: DepartmentSummary['color']) => void }) { return <fieldset><legend className="font-mono text-[10px] font-bold uppercase tracking-wider text-muted">Color</legend><div className="mt-2 flex gap-2">{DEPARTMENT_COLORS.map(color => <button key={color} type="button" aria-label={`${color} department color`} aria-pressed={value === color} onClick={() => onChange(color)} className={`grid size-9 place-items-center rounded-lg border-2 ${value === color ? 'border-ink shadow-[2px_2px_0_var(--color-shadow-strong)]' : 'border-line'}`}><DepartmentMark color={color} small /></button>)}</div></fieldset> }

function DepartmentMark({ color, small = false }: { color: DepartmentSummary['color']; small?: boolean }) { const tones: Record<DepartmentSummary['color'], string> = { orange: 'bg-orange', teal: 'bg-teal', blue: 'bg-blue-500', violet: 'bg-violet-500', rose: 'bg-rose-500', amber: 'bg-amber-400' }; return <span className={`${small ? 'size-3' : 'size-8'} shrink-0 rounded-lg border-2 border-ink ${tones[color]} ${small ? '' : 'shadow-[2px_2px_0_var(--color-shadow-strong)]'}`} /> }

function DepartmentPill({ department }: { department: Pick<DepartmentSummary, 'id' | 'name' | 'color'> }) { return <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-white px-2 py-1 text-[10px] font-semibold"><DepartmentMark color={department.color} small />{department.name}</span> }

function LoadingRows() { return <div className="space-y-3 p-6"><div className="h-16 animate-pulse rounded-xl bg-paper-2" /><div className="h-16 animate-pulse rounded-xl bg-paper-2" /><div className="h-16 animate-pulse rounded-xl bg-paper-2" /></div> }

function EmptyState({ icon: Icon, title, detail }: { icon: typeof Layers3; title: string; detail: string }) { return <div className="grid min-h-56 place-items-center p-8 text-center"><div><Icon className="mx-auto size-8 text-muted" /><h4 className="mt-4 text-lg font-bold">{title}</h4><p className="mt-2 text-sm text-muted">{detail}</p></div></div> }

function AdminRequired() { return <div className="mt-6 rounded-xl border-2 border-ink bg-paper-2 p-4"><LockKeyhole className="size-5 text-orange-dark" /><strong className="mt-3 block text-sm">Board or admin access required</strong><p className="mt-1 text-xs leading-5 text-muted">Only organization leadership can change people and structure.</p></div> }

function Modal({ children, onClose, title, eyebrow, icon: Icon }: { children: React.ReactNode; onClose: () => void; title: string; eyebrow: string; icon: typeof ArrowRightLeft }) { return <motion.div className="fixed inset-0 z-[100] grid place-items-center bg-ink/55 p-4 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={event => { if (event.currentTarget === event.target) onClose() }}><motion.div initial={{ opacity: 0, y: 16, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 10, scale: 0.98 }} className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl border-2 border-ink bg-white shadow-[8px_8px_0_var(--color-shadow-strong)]"><div className="sticky top-0 z-10 flex items-center justify-between border-b-2 border-ink bg-paper-2 p-5"><div className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl border-2 border-ink bg-orange text-white shadow-[2px_2px_0_var(--color-shadow-strong)]"><Icon className="size-4" /></span><div><p className="font-mono text-[9px] font-bold uppercase tracking-wider text-orange-dark">{eyebrow}</p><h3 className="mt-1 text-xl font-bold">{title}</h3></div></div><Button variant="subtle" size="icon" onClick={onClose} aria-label="Close"><X /></Button></div><div className="p-5 sm:p-6">{children}</div></motion.div></motion.div> }
