'use client'

import EvidenceChip from './EvidenceChip'

interface Source {
  id: string
  entity_id: string
  type: string
  statement: string
  source: string
  reference: string
  url?: string
  excerpt?: string
  source_date?: string
}

interface ChatMessageProps {
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
  isStreaming?: boolean
}

export default function ChatMessage({ role, content, sources, isStreaming }: ChatMessageProps) {
  const isUser = role === 'user'

  return (
    <div className={`chat-message ${isUser ? 'chat-message-user' : 'chat-message-assistant'}`}>
      <div className="chat-message-avatar">
        {isUser ? '👤' : '🧠'}
      </div>
      <div className="chat-message-content">
        <div className="chat-message-text">
          {content}
          {isStreaming && <span className="chat-cursor">▊</span>}
        </div>
        {sources && sources.length > 0 && (
          <div className="chat-message-sources">
            <div className="text-caption text-muted mb-2">Sources:</div>
            <div className="flex flex-wrap gap-2">
              {sources.map((source) => (
                <EvidenceChip
                  key={source.id}
                  source={source.source}
                  reference={source.reference}
                  url={source.url}
                  date={source.source_date?.slice(0, 10)}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
