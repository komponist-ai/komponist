'use client'

import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Check, History, LoaderCircle, MessageSquareText, Pencil,
  Plus, Trash2, X,
} from 'lucide-react'
import { Button } from './ui/button'
import { cn } from '../lib/utils'

export interface ChatConversation {
  id: string
  title: string
  preview: string
  message_count: number
  created_at: string
  updated_at: string
}

type ChatHistoryProps = {
  conversations: ChatConversation[]
  activeId: string | null
  loading: boolean
  disabled: boolean
  mobileOpen: boolean
  hasMore: boolean
  loadingMore: boolean
  onLoadMore: () => void
  onMobileClose: () => void
  onNew: () => void
  onSelect: (id: string) => void
  onRename: (id: string, title: string) => Promise<void>
  onDelete: (id: string) => Promise<void>
}

function relativeDate(value: string) {
  const date = new Date(value)
  const today = new Date()
  if (date.toDateString() === today.toDateString()) return 'Today'
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  if (date.toDateString() === yesterday.toDateString()) return 'Yesterday'
  return new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric' }).format(date)
}

function HistoryContent({
  conversations, activeId, loading, disabled, onNew, onSelect,
  onRename, onDelete, onMobileClose, hasMore, loadingMore, onLoadMore,
}: Omit<ChatHistoryProps, 'mobileOpen'>) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const [pendingId, setPendingId] = useState<string | null>(null)

  useEffect(() => {
    if (editingId && !conversations.some((item) => item.id === editingId)) {
      setEditingId(null)
    }
  }, [conversations, editingId])

  const startRename = (conversation: ChatConversation) => {
    setDeleteId(null)
    setEditingId(conversation.id)
    setTitle(conversation.title)
  }

  const saveRename = async (id: string) => {
    const nextTitle = title.trim()
    if (!nextTitle) return
    setPendingId(id)
    try {
      await onRename(id, nextTitle)
      setEditingId(null)
    } finally {
      setPendingId(null)
    }
  }

  const confirmDelete = async (id: string) => {
    setPendingId(id)
    try {
      await onDelete(id)
      setDeleteId(null)
    } finally {
      setPendingId(null)
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-paper-2">
      <div className="border-b-2 border-ink p-4">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <div className="font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-orange-dark">Workspace memory</div>
            <h2 className="mt-0.5 flex items-center gap-2 text-base font-bold"><History className="size-4" /> Chat history</h2>
          </div>
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={onMobileClose} aria-label="Close chat history">
            <X />
          </Button>
        </div>
        <Button
          variant="dark"
          size="sm"
          className="w-full"
          disabled={disabled}
          onClick={() => { onNew(); onMobileClose() }}
        >
          <Plus /> New chat
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-10 text-xs font-semibold text-muted">
            <LoaderCircle className="size-4 animate-spin" /> Loading chats
          </div>
        ) : conversations.length === 0 ? (
          <div className="m-2 rounded-lg border-2 border-dashed border-line bg-white p-4 text-center">
            <MessageSquareText className="mx-auto size-5 text-faint" />
            <p className="mt-2 text-xs font-semibold">Your conversations will appear here.</p>
          </div>
        ) : (
          <div className="space-y-1.5">
            {conversations.map((conversation) => {
              const active = activeId === conversation.id
              const editing = editingId === conversation.id
              const deleting = deleteId === conversation.id
              const pending = pendingId === conversation.id
              return (
                <motion.div
                  layout
                  key={conversation.id}
                  className={cn(
                    'group relative overflow-hidden rounded-lg border-2 transition-colors',
                    active ? 'border-ink bg-white shadow-[3px_3px_0_#e8641b]' : 'border-transparent hover:border-line hover:bg-white',
                  )}
                >
                  {editing ? (
                    <form
                      className="p-2"
                      onSubmit={(event) => { event.preventDefault(); void saveRename(conversation.id) }}
                    >
                      <input
                        autoFocus
                        value={title}
                        maxLength={120}
                        disabled={pending}
                        onChange={(event) => setTitle(event.target.value)}
                        className="h-8 w-full rounded border-2 border-ink bg-white px-2 text-xs font-semibold outline-none focus:ring-2 focus:ring-teal"
                        aria-label="Conversation title"
                      />
                      <div className="mt-2 flex justify-end gap-1">
                        <button type="button" className="grid size-7 place-items-center rounded hover:bg-paper-2" onClick={() => setEditingId(null)} aria-label="Cancel rename"><X className="size-3.5" /></button>
                        <button type="submit" className="grid size-7 place-items-center rounded bg-ink text-white disabled:opacity-50" disabled={!title.trim() || pending} aria-label="Save title">
                          {pending ? <LoaderCircle className="size-3.5 animate-spin" /> : <Check className="size-3.5" />}
                        </button>
                      </div>
                    </form>
                  ) : (
                    <>
                      <button
                        className="w-full p-3 pr-16 text-left disabled:cursor-not-allowed"
                        disabled={disabled}
                        onClick={() => { onSelect(conversation.id); onMobileClose() }}
                      >
                        <span className="block truncate text-xs font-bold">{conversation.title}</span>
                        <span className="mt-1.5 line-clamp-2 block text-[11px] leading-4 text-muted">{conversation.preview || 'No answer yet'}</span>
                        <span className="mt-2 flex items-center gap-2 font-mono text-[9px] uppercase tracking-wide text-faint">
                          {relativeDate(conversation.updated_at)}
                          <span className="size-1 rounded-full bg-line" />
                          {conversation.message_count} messages
                        </span>
                      </button>
                      <div className={cn('absolute right-2 top-2 flex gap-0.5 transition-opacity', active || deleting ? 'opacity-100' : 'opacity-0 group-hover:opacity-100')}>
                        <button
                          className="grid size-7 place-items-center rounded border border-transparent bg-white/90 text-muted hover:border-line hover:text-ink"
                          disabled={disabled}
                          onClick={() => startRename(conversation)}
                          aria-label={`Rename ${conversation.title}`}
                        ><Pencil className="size-3.5" /></button>
                        <button
                          className={cn('grid h-7 place-items-center rounded border text-[10px] font-bold transition-all', deleting ? 'w-[62px] border-danger bg-danger text-white' : 'w-7 border-transparent bg-white/90 text-muted hover:border-danger hover:text-danger')}
                          disabled={disabled || pending}
                          onClick={() => deleting ? void confirmDelete(conversation.id) : setDeleteId(conversation.id)}
                          aria-label={deleting ? `Confirm delete ${conversation.title}` : `Delete ${conversation.title}`}
                        >
                          {pending ? <LoaderCircle className="size-3.5 animate-spin" /> : deleting ? 'Delete?' : <Trash2 className="size-3.5" />}
                        </button>
                      </div>
                    </>
                  )}
                </motion.div>
              )
            })}
            {hasMore && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="w-full"
                disabled={loadingMore || disabled}
                onClick={onLoadMore}
              >
                {loadingMore ? <LoaderCircle className="animate-spin" /> : <History />}
                Load older chats
              </Button>
            )}
          </div>
        )}
      </div>
      <div className="border-t border-line px-4 py-3 font-mono text-[9px] uppercase tracking-wider text-faint">
        Private to your account
      </div>
    </div>
  )
}

export default function ChatHistory(props: ChatHistoryProps) {
  const contentProps = { ...props }
  return (
    <>
      <aside className="hidden h-full w-[260px] shrink-0 border-r-2 border-ink lg:block">
        <HistoryContent {...contentProps} />
      </aside>
      <AnimatePresence>
        {props.mobileOpen && (
          <>
            <motion.button
              aria-label="Close chat history"
              className="fixed inset-0 z-40 bg-ink/40 backdrop-blur-[2px] lg:hidden"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              onClick={props.onMobileClose}
            />
            <motion.aside
              className="fixed inset-y-0 left-0 z-50 w-[min(86vw,320px)] border-r-2 border-ink shadow-2xl lg:hidden"
              initial={{ x: '-100%' }} animate={{ x: 0 }} exit={{ x: '-100%' }}
              transition={{ type: 'spring', damping: 28, stiffness: 280 }}
            >
              <HistoryContent {...contentProps} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  )
}
