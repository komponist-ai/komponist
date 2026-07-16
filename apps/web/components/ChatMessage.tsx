'use client'

import { useState } from 'react'
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
  const [showAllSources, setShowAllSources] = useState(false)
  const visibleSources = showAllSources ? sources : sources?.slice(0, 3)

  const renderedContent = content.split(/(\[\d+\])/g).map((part, index) =>
    /^\[\d+\]$/.test(part) ? (
      <span className="chat-citation" key={`${part}-${index}`}>{part.slice(1, -1)}</span>
    ) : part
  )

  return (
    <div className={`chat-message ${isUser ? 'chat-message-user' : 'chat-message-assistant'}`}>
      <div className="chat-message-avatar">
        {isUser ? 'Y' : 'K'}
      </div>
      <div className="chat-message-content">
        <div className="chat-message-author">{isUser ? 'You' : 'Komponist'}</div>
        <div className="chat-message-text">
          {renderedContent}
          {isStreaming && <span className="chat-cursor">▊</span>}
        </div>
        {sources && sources.length > 0 && (
          <div className="chat-message-sources">
            <div className="chat-sources-heading">
              <span>Evidence</span>
              <span>{sources.length} {sources.length === 1 ? 'source' : 'sources'}</span>
            </div>
            <div className="chat-source-list">
              {visibleSources?.map((source, index) => (
                <div className="chat-source-item" key={source.id}>
                  <span className="chat-source-index">{index + 1}</span>
                  <div className="chat-source-body">
                    <div className="chat-source-meta">
                      <span className={`badge type-${source.type.toLowerCase()}`}>{source.type}</span>
                      <EvidenceChip
                        source={source.source}
                        reference={source.reference}
                        url={source.url}
                        date={source.source_date?.slice(0, 10)}
                      />
                    </div>
                    <p>{source.statement}</p>
                    {source.excerpt && <blockquote>“{source.excerpt}”</blockquote>}
                  </div>
                </div>
              ))}
            </div>
            {sources.length > 3 && (
              <button
                className="chat-sources-toggle"
                onClick={() => setShowAllSources((current) => !current)}
              >
                {showAllSources
                  ? 'Show fewer sources'
                  : `Show ${sources.length - 3} more ${sources.length - 3 === 1 ? 'source' : 'sources'}`}
                <span aria-hidden="true">{showAllSources ? '↑' : '↓'}</span>
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
