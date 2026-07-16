'use client'

import EvidenceChip from './EvidenceChip'

interface Source {
  id: string
  type: string
  statement: string
  score?: number
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
                  source={source.type.toLowerCase()}
                  reference={source.statement}
                  url={`/entities/${source.id}`}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
