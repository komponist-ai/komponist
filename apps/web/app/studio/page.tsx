'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import Link from 'next/link'
import { motion } from 'framer-motion'
import {
  ArrowUpRight, CircleDot, FileKey2, FlaskConical, MessageSquareText,
  History, LoaderCircle, Plus, ShieldCheck, Sparkles,
} from 'lucide-react'
import AppLayout from '../../components/AppLayout'
import StudioTopbar from '../../components/StudioTopbar'
import ChatMessage from '../../components/ChatMessage'
import ChatInput from '../../components/ChatInput'
import ChatHistory, { type ChatConversation } from '../../components/ChatHistory'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { API_URL, apiFetch, getActiveOrgId } from '../../lib/api'

interface Message {
  id?: string
  role: 'user' | 'assistant'
  content: string
  sources?: any[]
}

interface SuggestedQuestion {
  id: string
  category: string
  title: string
  prompt: string
  entity_type: string
  reference: string
}

const SUGGESTION_ICONS: Record<string, typeof Sparkles> = {
  Decision: Sparkles,
  Constraint: FileKey2,
  Project: FlaskConical,
  Goal: ShieldCheck,
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [suggestions, setSuggestions] = useState<SuggestedQuestion[]>([])
  const [suggestionsLoading, setSuggestionsLoading] = useState(true)
  const [conversations, setConversations] = useState<ChatConversation[]>([])
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  const [historyLoading, setHistoryLoading] = useState(true)
  const [historyLoadingMore, setHistoryLoadingMore] = useState(false)
  const [historyOffset, setHistoryOffset] = useState(0)
  const [historyHasMore, setHistoryHasMore] = useState(false)
  const [messageHistoryLoading, setMessageHistoryLoading] = useState(false)
  const [messageHistoryHasMore, setMessageHistoryHasMore] = useState(false)
  const [messageHistoryCursor, setMessageHistoryCursor] = useState<string | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const latestMessageContent = messages[messages.length - 1]?.content

  useEffect(() => {
    scrollToBottom()
  }, [isLoading, latestMessageContent, messages.length])

  const loadConversations = useCallback(async (
    showLoader = false,
    offset = 0,
    append = false,
  ) => {
    if (showLoader) setHistoryLoading(true)
    if (append) setHistoryLoadingMore(true)
    try {
      const orgId = getActiveOrgId()
      const response = await apiFetch(
        `${API_URL}/chat/conversations?org_id=${encodeURIComponent(orgId)}&limit=30&offset=${offset}`,
      )
      if (!response.ok) throw new Error('Could not load chat history')
      const payload = await response.json()
      setConversations(current => append
        ? [...current, ...(payload.conversations || [])]
        : (payload.conversations || []))
      setHistoryOffset(offset)
      setHistoryHasMore(Boolean(payload.has_more))
    } catch (loadError: any) {
      setError(loadError.message || 'Could not load chat history')
    } finally {
      setHistoryLoading(false)
      setHistoryLoadingMore(false)
    }
  }, [])

  useEffect(() => {
    void loadConversations(true)
  }, [loadConversations])

  useEffect(() => {
    let cancelled = false
    const loadSuggestions = async () => {
      setSuggestionsLoading(true)
      try {
        const orgId = getActiveOrgId()
        const response = await apiFetch(`${API_URL}/chat/suggestions?org_id=${encodeURIComponent(orgId)}&limit=4`)
        if (!response.ok) throw new Error('Could not load suggested questions')
        const payload = await response.json()
        if (!cancelled) setSuggestions(payload.suggestions || [])
      } catch {
        if (!cancelled) setSuggestions([])
      } finally {
        if (!cancelled) setSuggestionsLoading(false)
      }
    }
    loadSuggestions()
    return () => { cancelled = true }
  }, [])

  const handleNewConversation = () => {
    if (isLoading) return
    setActiveConversationId(null)
    setMessages([])
    setMessageHistoryHasMore(false)
    setMessageHistoryCursor(null)
    setError(null)
  }

  const handleSelectConversation = async (conversationId: string) => {
    if (isLoading || conversationId === activeConversationId) return
    setError(null)
    try {
      const orgId = getActiveOrgId()
      const response = await apiFetch(`${API_URL}/chat/conversations/${conversationId}?org_id=${encodeURIComponent(orgId)}&limit=100`)
      if (!response.ok) throw new Error('Could not open this conversation')
      const payload = await response.json()
      setActiveConversationId(conversationId)
      setMessages((payload.messages || []).map((message: Message) => ({
        id: message.id,
        role: message.role,
        content: message.content,
        sources: message.sources || [],
      })))
      setMessageHistoryHasMore(Boolean(payload.has_more))
      setMessageHistoryCursor(payload.next_before || null)
    } catch (openError: any) {
      setError(openError.message || 'Could not open this conversation')
    }
  }

  const loadOlderMessages = async () => {
    if (!activeConversationId || !messageHistoryCursor || messageHistoryLoading) return
    setMessageHistoryLoading(true)
    try {
      const orgId = getActiveOrgId()
      const response = await apiFetch(
        `${API_URL}/chat/conversations/${activeConversationId}?org_id=${encodeURIComponent(orgId)}&limit=100&before=${encodeURIComponent(messageHistoryCursor)}`,
      )
      if (!response.ok) throw new Error('Could not load older messages')
      const payload = await response.json()
      const older = (payload.messages || []).map((message: Message) => ({
        id: message.id,
        role: message.role,
        content: message.content,
        sources: message.sources || [],
      }))
      setMessages(current => [...older, ...current])
      setMessageHistoryHasMore(Boolean(payload.has_more))
      setMessageHistoryCursor(payload.next_before || null)
    } catch (historyError: any) {
      setError(historyError.message || 'Could not load older messages')
    } finally {
      setMessageHistoryLoading(false)
    }
  }

  const handleRenameConversation = async (conversationId: string, title: string) => {
    const orgId = getActiveOrgId()
    const response = await apiFetch(`${API_URL}/chat/conversations/${conversationId}?org_id=${encodeURIComponent(orgId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    })
    if (!response.ok) throw new Error('Could not rename this conversation')
    const updated = await response.json()
    setConversations((previous) => previous.map((item) => item.id === conversationId ? { ...item, ...updated } : item))
  }

  const handleDeleteConversation = async (conversationId: string) => {
    const orgId = getActiveOrgId()
    const response = await apiFetch(`${API_URL}/chat/conversations/${conversationId}?org_id=${encodeURIComponent(orgId)}`, {
      method: 'DELETE',
    })
    if (!response.ok) throw new Error('Could not delete this conversation')
    setConversations((previous) => previous.filter((item) => item.id !== conversationId))
    if (conversationId === activeConversationId) handleNewConversation()
  }

  const handleSendMessage = async (messageText: string) => {
    const orgId = getActiveOrgId()

    // Add the user turn and the assistant placeholder immediately so the
    // retrieval/generation state is visible before the server starts streaming.
    const userMessage: Message = { role: 'user', content: messageText }
    setMessages((prev) => [
      ...prev,
      userMessage,
      { role: 'assistant', content: '', sources: [] },
    ])
    setIsLoading(true)
    setError(null)
    const assistantAdded = true

    try {
      // Call chat API with streaming
      const response = await apiFetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: messageText,
          org_id: orgId,
          conversation_id: activeConversationId,
          stream: true
        })
      })

      if (!response.ok) {
        const failure = await response.json().catch(() => null)
        throw new Error(failure?.detail || 'Failed to get response')
      }

      // Handle streaming response
      const reader = response.body?.getReader()
      if (!reader) throw new Error('The response stream could not be opened')
      const decoder = new TextDecoder()

      let assistantMessage = ''
      let sources: any[] = []

      let buffer = ''

      const processLine = (rawLine: string) => {
        const line = rawLine.replace(/\r$/, '')
        if (!line.startsWith('data: ')) return

        const payload = line.slice(6)
        if (!payload) return

        const data = JSON.parse(payload)
        if (data.error) throw new Error(data.error)
        if (data.conversation_id) {
          const now = new Date().toISOString()
          setActiveConversationId(data.conversation_id)
          setConversations((previous) => {
            const existing = previous.find((item) => item.id === data.conversation_id)
            const optimistic: ChatConversation = {
              id: data.conversation_id,
              title: data.title || messageText,
              preview: messageText,
              message_count: existing?.message_count || 1,
              created_at: existing?.created_at || now,
              updated_at: now,
            }
            return [optimistic, ...previous.filter((item) => item.id !== data.conversation_id)]
          })
        }
        if (data.content) assistantMessage += data.content
        if (data.sources) sources = data.sources

        setMessages((prev) => {
          const updated = [...prev]
          updated[updated.length - 1] = {
            role: 'assistant',
            content: assistantMessage,
            sources
          }
          return updated
        })
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          processLine(line)
        }
      }
      buffer += decoder.decode()
      if (buffer) processLine(buffer)

      // Final update with sources
      setMessages((prev) => {
        const updated = [...prev]
        updated[updated.length - 1] = {
          role: 'assistant',
          content: assistantMessage,
          sources: sources
        }
        return updated
      })

    } catch (err: any) {
      setError(err.message || 'Failed to send message')
      if (assistantAdded) {
        setMessages((prev) => prev.slice(0, -1))
      }
    } finally {
      setIsLoading(false)
      void loadConversations()
    }
  }

  return (
    <AppLayout>
      <div className="studio-chat-shell flex h-screen min-h-[680px] flex-col overflow-hidden bg-paper text-ink">
        <StudioTopbar
          section="Company brain"
          title="Ask Komponist"
          description="Grounded answers from confirmed company context"
          icon={MessageSquareText}
          actions={
            <>
            <Badge variant={isLoading ? 'orange' : 'teal'} className="hidden sm:inline-flex" title="Chat searches confirmed entities only">
              {isLoading ? <LoaderCircle className="size-3 animate-spin" /> : <span className="size-1.5 rounded-full bg-teal" />}
              {isLoading ? 'Thinking' : 'Confirmed only'}
            </Badge>
            <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setHistoryOpen(true)} aria-label="Open chat history">
              <History />
            </Button>
            {messages.length > 0 && (
              <Button variant="outline" size="sm" onClick={handleNewConversation} disabled={isLoading}>
                <Plus /> New thread
              </Button>
            )}
            </>
          }
        />

        <div className="relative flex min-h-0 flex-1">
          <ChatHistory
            conversations={conversations}
            activeId={activeConversationId}
            loading={historyLoading}
            disabled={isLoading}
            mobileOpen={historyOpen}
            hasMore={historyHasMore}
            loadingMore={historyLoadingMore}
            onMobileClose={() => setHistoryOpen(false)}
            onNew={handleNewConversation}
            onSelect={(conversationId) => { void handleSelectConversation(conversationId) }}
            onRename={handleRenameConversation}
            onDelete={handleDeleteConversation}
            onLoadMore={() => void loadConversations(false, historyOffset + 30, true)}
          />
          <div className="flex min-w-0 flex-1 flex-col">
          {error && (
            <div className="mx-auto mt-4 flex w-[calc(100%-2rem)] max-w-[880px] items-center gap-3 rounded-lg border-2 border-danger bg-danger-soft px-4 py-3 text-sm text-danger" role="alert">
              <CircleDot className="size-5 shrink-0" />
              <div><strong>Komponist could not answer.</strong> {error}</div>
            </div>
          )}

          <div className="min-h-0 flex-1 overflow-y-auto">
            {messages.length === 0 ? (
              <section className="mx-auto grid min-h-full w-[calc(100%-2rem)] max-w-[1040px] content-center gap-10 py-12 lg:grid-cols-[0.72fr_1.28fr] lg:items-center">
                <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.45 }}>
                  <Badge variant="orange">Questions from your live graph</Badge>
                  <h2 className="studio-empty-title mt-5 font-display text-[clamp(3rem,6vw,5.7rem)] font-bold leading-[0.88] tracking-[-0.06em]">
                    Ask the brain.<span className="mt-2 block text-orange">It has receipts.</span>
                  </h2>
                  <p className="mt-6 max-w-xl text-lg leading-8 text-ink-2">
                    Ask for a direct answer across your confirmed company knowledge. Suggested questions adapt to the graph and documents in this workspace.
                  </p>
                  <div className="mt-7 flex items-center gap-3 rounded-lg border-2 border-ink bg-warning-soft p-3 text-sm font-semibold shadow-[4px_4px_0_#201c15] lg:max-w-sm">
                    <ShieldCheck className="size-5 shrink-0" />
                    Proposed facts stay out until you review them.
                  </div>
                </motion.div>

                <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.08 }} className="overflow-hidden rounded-xl border-2 border-ink bg-white shadow-[7px_7px_0_#e8641b]">
                  <div className="flex items-center justify-between border-b-2 border-ink bg-ink px-4 py-3 text-white">
                    <span className="font-mono text-[10px] uppercase tracking-wider text-white/65">starter-queries.json</span>
                    <span className="flex items-center gap-2 font-mono text-[10px] text-teal-light"><span className="size-1.5 rounded-full bg-teal-light" /> live graph</span>
                  </div>
                  <div className="grid gap-px bg-line sm:grid-cols-2">
                  {suggestionsLoading ? Array.from({ length: 4 }).map((_, index) => (
                    <div className="min-h-[190px] animate-pulse bg-white p-5" key={index}>
                      <div className="size-10 rounded-md bg-paper-3" />
                      <div className="mt-7 h-2 w-24 rounded bg-paper-3" />
                      <div className="mt-3 h-4 w-32 rounded bg-paper-3" />
                      <div className="mt-3 h-3 w-full rounded bg-paper-2" />
                      <div className="mt-2 h-3 w-3/4 rounded bg-paper-2" />
                    </div>
                  )) : suggestions.length > 0 ? suggestions.map((question, index) => {
                    const Icon = SUGGESTION_ICONS[question.entity_type] || Sparkles
                    return (
                    <motion.button
                      key={question.id}
                      whileHover={{ y: -2 }}
                      whileTap={{ scale: 0.985 }}
                      className="group min-h-[190px] bg-white p-5 text-left transition-colors hover:bg-warning-soft disabled:opacity-50"
                      onClick={() => handleSendMessage(question.prompt)}
                      disabled={isLoading}
                    >
                      <div className="flex items-start justify-between">
                        <span className="grid size-10 place-items-center rounded-md border-2 border-ink bg-paper shadow-[2px_2px_0_#201c15]"><Icon className="size-4" /></span>
                        <span className="font-mono text-[10px] text-muted">{String(index + 1).padStart(2, '0')}</span>
                      </div>
                      <div className="mt-6 font-mono text-[9px] font-semibold uppercase tracking-wider text-orange-dark">{question.category}</div>
                      <strong className="mt-1 block text-base">{question.title}</strong>
                      <p className="mt-2 text-sm leading-5 text-ink-2">{question.prompt}</p>
                      <ArrowUpRight className="mt-4 size-4 text-faint transition-transform group-hover:translate-x-1 group-hover:-translate-y-1 group-hover:text-orange" />
                    </motion.button>
                    )
                  }) : (
                    <div className="bg-white p-7 sm:col-span-2">
                      <strong className="block text-lg">No confirmed questions yet.</strong>
                      <p className="mt-2 text-sm leading-6 text-muted">Upload a document and confirm its extracted facts. Komponist will generate useful starter questions from that context.</p>
                      <Button asChild className="mt-5" size="sm"><Link href="/onboard">Upload a source <ArrowUpRight /></Link></Button>
                    </div>
                  )}
                  </div>
                  <div className="border-t-2 border-ink bg-paper-2 px-4 py-3 text-center font-mono text-[10px] text-muted">
                    Need more context? <Link href="/onboard" className="font-bold text-orange-dark underline">Upload another source</Link>
                  </div>
                </motion.div>
              </section>
            ) : (
              <div className="mx-auto flex w-[calc(100%-2rem)] max-w-[880px] flex-col gap-8 py-10 pb-20">
                {messageHistoryHasMore && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="self-center"
                    disabled={messageHistoryLoading}
                    onClick={() => void loadOlderMessages()}
                  >
                    {messageHistoryLoading ? <LoaderCircle className="animate-spin" /> : <History />}
                    Load older messages
                  </Button>
                )}
                {messages.map((msg, idx) => (
                  <ChatMessage
                    key={msg.id ?? idx}
                    role={msg.role}
                    content={msg.content}
                    sources={msg.sources}
                    isStreaming={idx === messages.length - 1 && isLoading}
                  />
                ))}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          <ChatInput
            onSend={handleSendMessage}
            disabled={isLoading}
            placeholder={isLoading ? 'Komponist is thinking…' : 'Ask a question about your company knowledge…'}
          />
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
