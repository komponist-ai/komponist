'use client'

import { useState, useEffect, useRef } from 'react'
import Link from 'next/link'
import { motion } from 'framer-motion'
import {
  ArrowUpRight, CircleDot, FileKey2, FlaskConical, MessageSquareText,
  Plus, ShieldCheck, Sparkles,
} from 'lucide-react'
import AppLayout from '../../components/AppLayout'
import ChatMessage from '../../components/ChatMessage'
import ChatInput from '../../components/ChatInput'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { API_URL, apiFetch, getActiveOrgId } from '../../lib/api'

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: any[]
}

const STARTER_QUESTIONS = [
  {
    category: 'Product strategy',
    number: '01',
    icon: Sparkles,
    title: 'MVP scope',
    prompt: 'What does the MVP extract, and which features does it postpone?',
  },
  {
    category: 'Security policy',
    number: '02',
    icon: FileKey2,
    title: 'Security constraints',
    prompt: 'Which security constraints apply to OpenAI credentials and uploaded documents?',
  },
  {
    category: 'Customer interview',
    number: '03',
    icon: FlaskConical,
    title: 'Northstar pilot',
    prompt: 'What are the goals and scope of the Northstar Labs pilot?',
  },
  {
    category: 'Readiness',
    number: '04',
    icon: ShieldCheck,
    title: 'Design partner gate',
    prompt: 'What must happen before we invite the first external design partner?',
  },
]

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages.length])

  const handleSendMessage = async (messageText: string) => {
    const orgId = getActiveOrgId()

    // Add user message
    const userMessage: Message = { role: 'user', content: messageText }
    setMessages((prev) => [...prev, userMessage])
    setIsLoading(true)
    setError(null)
    let assistantAdded = false

    try {
      // Call chat API with streaming
      const response = await apiFetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: messageText,
          org_id: orgId,
          conversation_history: messages,
          stream: true
        })
      })

      if (!response.ok) throw new Error('Failed to get response')

      // Handle streaming response
      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      let assistantMessage = ''
      let sources: any[] = []

      // Add empty assistant message for streaming
      setMessages((prev) => [...prev, { role: 'assistant', content: '', sources: [] }])
      assistantAdded = true

      let buffer = ''

      const processLine = (rawLine: string) => {
        const line = rawLine.replace(/\r$/, '')
        if (!line.startsWith('data: ')) return

        const payload = line.slice(6)
        if (!payload) return

        const data = JSON.parse(payload)
        if (data.error) throw new Error(data.error)
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
        const { done, value } = await reader!.read()
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
    }
  }

  return (
    <AppLayout>
      <div className="flex h-screen min-h-[680px] flex-col overflow-hidden bg-paper text-ink">
        <header className="flex min-h-[72px] items-center justify-between gap-4 border-b border-line bg-white px-5 sm:px-8">
          <div className="flex items-center gap-3">
            <div className="grid size-10 place-items-center rounded-lg border-2 border-ink bg-orange text-white shadow-[2px_2px_0_#201c15]">
              <MessageSquareText className="size-5" />
            </div>
            <div>
              <div className="font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">Studio / Company brain</div>
              <h1 className="mt-0.5 text-xl font-bold tracking-tight sm:text-2xl">Ask Komponist</h1>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Badge variant="teal" className="hidden sm:inline-flex" title="Chat searches confirmed entities only">
              <span className="size-1.5 rounded-full bg-teal" /> Confirmed only
            </Badge>
            {messages.length > 0 && (
              <Button variant="outline" size="sm" onClick={() => setMessages([])}>
                <Plus /> New thread
              </Button>
            )}
          </div>
        </header>

        <div className="flex min-h-0 flex-1 flex-col">
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
                  <Badge variant="orange">Example upload is ready</Badge>
                  <h2 className="mt-5 font-display text-[clamp(3rem,6vw,5.7rem)] font-bold leading-[0.88] tracking-[-0.06em]">
                    Ask the brain.<span className="mt-2 block text-orange">It has receipts.</span>
                  </h2>
                  <p className="mt-6 max-w-xl text-lg leading-8 text-ink-2">
                    Query product strategy, security policy, and the Northstar interview. Every answer stays attached to confirmed graph facts.
                  </p>
                  <div className="mt-7 flex items-center gap-3 rounded-lg border-2 border-ink bg-[#f4d06f] p-3 text-sm font-semibold shadow-[4px_4px_0_#201c15] lg:max-w-sm">
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
                  {STARTER_QUESTIONS.map((question, index) => {
                    const Icon = question.icon
                    return (
                    <motion.button
                      key={question.prompt}
                      whileHover={{ y: -2 }}
                      whileTap={{ scale: 0.985 }}
                      className="group min-h-[190px] bg-white p-5 text-left transition-colors hover:bg-warning-soft disabled:opacity-50"
                      onClick={() => handleSendMessage(question.prompt)}
                      disabled={isLoading}
                    >
                      <div className="flex items-start justify-between">
                        <span className="grid size-10 place-items-center rounded-md border-2 border-ink bg-paper shadow-[2px_2px_0_#201c15]"><Icon className="size-4" /></span>
                        <span className="font-mono text-[10px] text-muted">{question.number}</span>
                      </div>
                      <div className="mt-6 font-mono text-[9px] font-semibold uppercase tracking-wider text-orange-dark">{question.category}</div>
                      <strong className="mt-1 block text-base">{question.title}</strong>
                      <p className="mt-2 text-sm leading-5 text-ink-2">{question.prompt}</p>
                      <ArrowUpRight className="mt-4 size-4 text-faint transition-transform group-hover:translate-x-1 group-hover:-translate-y-1 group-hover:text-orange" />
                    </motion.button>
                    )
                  })}
                  </div>
                  <div className="border-t-2 border-ink bg-paper-2 px-4 py-3 text-center font-mono text-[10px] text-muted">
                    Need more context? <Link href="/onboard" className="font-bold text-orange-dark underline">Upload another source</Link>
                  </div>
                </motion.div>
              </section>
            ) : (
              <div className="mx-auto flex w-[calc(100%-2rem)] max-w-[880px] flex-col gap-8 py-10 pb-20">
                {messages.map((msg, idx) => (
                  <ChatMessage
                    key={idx}
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
            placeholder="Ask a question about your company knowledge…"
          />
        </div>
      </div>
    </AppLayout>
  )
}
