'use client'

import { useState, useEffect, useRef } from 'react'
import AppLayout from '../components/AppLayout'
import ChatMessage from '../components/ChatMessage'
import ChatInput from '../components/ChatInput'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: any[]
}

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
  }, [messages])

  const handleSendMessage = async (messageText: string) => {
    const orgId = typeof window !== 'undefined'
      ? localStorage.getItem('komponist_org_id') || 'default-org'
      : 'default-org'

    // Add user message
    const userMessage: Message = { role: 'user', content: messageText }
    setMessages((prev) => [...prev, userMessage])
    setIsLoading(true)
    setError(null)
    let assistantAdded = false

    try {
      // Call chat API with streaming
      const response = await fetch(`${API_URL}/chat`, {
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
      <div className="page-header">
        <h1 className="page-title">Company Brain</h1>
        <div className="text-small text-muted">
          Ask questions about your knowledge graph
        </div>
      </div>

      <div className="page-body" style={{ height: 'calc(100vh - 180px)', display: 'flex', flexDirection: 'column', padding: 0 }}>
        {error && (
          <div className="card mb-4 mx-4 mt-4" style={{ background: 'var(--color-danger-soft)', borderColor: 'var(--color-danger)' }}>
            <p className="text-small" style={{ color: 'var(--color-danger)' }}>
              ⚠ {error}
            </p>
          </div>
        )}

        <div className="chat-container">
          {messages.length === 0 ? (
            <div className="chat-empty-state">
              <div className="empty-state-icon">🧠</div>
              <h3 className="empty-state-title">Ask your company brain anything</h3>
              <p className="empty-state-description">
                Try questions like:
              </p>
              <div className="chat-example-queries">
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => handleSendMessage("Who worked on the DAAD application?")}
                  disabled={isLoading}
                >
                  Who worked on the DAAD application?
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => handleSendMessage("What are our active decisions?")}
                  disabled={isLoading}
                >
                  What are our active decisions?
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => handleSendMessage("Show me all current goals")}
                  disabled={isLoading}
                >
                  Show me all current goals
                </button>
              </div>
            </div>
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
          placeholder="Ask about decisions, goals, people, projects..."
        />
      </div>
    </AppLayout>
  )
}
