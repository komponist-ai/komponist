'use client'

import { useState, useEffect, useRef } from 'react'
import AppLayout from '../components/AppLayout'
import ChatMessage from '../components/ChatMessage'
import ChatInput from '../components/ChatInput'
import { API_URL, apiFetch, getActiveOrgId } from '../lib/api'

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: any[]
}

const STARTER_QUESTIONS = [
  {
    category: 'Product strategy',
    number: '01',
    title: 'MVP scope',
    prompt: 'What does the MVP extract, and which features does it postpone?',
  },
  {
    category: 'Security policy',
    number: '02',
    title: 'Security constraints',
    prompt: 'Which security constraints apply to OpenAI credentials and uploaded documents?',
  },
  {
    category: 'Customer interview',
    number: '03',
    title: 'Northstar pilot',
    prompt: 'What are the goals and scope of the Northstar Labs pilot?',
  },
  {
    category: 'Readiness',
    number: '04',
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
      <div className="chat-page">
        <header className="chat-page-header">
          <div>
            <div className="chat-page-eyebrow">Company brain</div>
            <h1>Ask Komponist</h1>
          </div>
          <div className="chat-trust-badge" title="Chat searches confirmed entities only">
            <span className="chat-trust-dot" aria-hidden="true" />
            Confirmed knowledge only
          </div>
        </header>

        <div className="chat-workspace">
          {error && (
            <div className="chat-error" role="alert">
              <span aria-hidden="true">!</span>
              <div>
                <strong>Komponist could not answer</strong>
                <p>{error}</p>
              </div>
            </div>
          )}

          <div className="chat-container">
            {messages.length === 0 ? (
              <section className="chat-welcome">
                <div className="chat-mark" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </div>
                <div className="chat-welcome-copy">
                  <div className="eyebrow">Explore the example upload</div>
                  <h2>Your documents,<br />ready to answer.</h2>
                  <p>
                    Ask across the product strategy, security policy, and customer
                    interview. Every answer stays grounded in confirmed graph facts.
                  </p>
                </div>

                <div className="chat-starter-grid">
                  {STARTER_QUESTIONS.map((question) => (
                    <button
                      key={question.prompt}
                      className="chat-starter-card"
                      onClick={() => handleSendMessage(question.prompt)}
                      disabled={isLoading}
                    >
                      <span className="chat-starter-number">{question.number}</span>
                      <span className="chat-starter-copy">
                        <span className="chat-starter-category">{question.category}</span>
                        <strong>{question.title}</strong>
                        <span>{question.prompt}</span>
                      </span>
                      <span className="chat-starter-arrow" aria-hidden="true">↗</span>
                    </button>
                  ))}
                </div>

                <div className="chat-grounding-note">
                  <span className="chat-grounding-icon" aria-hidden="true">✓</span>
                  <span>
                    Only confirmed facts are used. Review proposed facts in the{' '}
                    <a href="/queue">Review Queue</a> before asking about them.
                  </span>
                </div>
              </section>
            ) : (
              <div className="chat-messages">
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
