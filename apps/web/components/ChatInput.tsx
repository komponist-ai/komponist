'use client'

import { useEffect, useRef, useState, KeyboardEvent } from 'react'

interface ChatInputProps {
  onSend: (message: string) => void
  disabled?: boolean
  placeholder?: string
}

export default function ChatInput({ onSend, disabled, placeholder }: ChatInputProps) {
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 144)}px`
  }, [input])

  const handleSend = () => {
    if (input.trim() && !disabled) {
      onSend(input.trim())
      setInput('')
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="chat-composer-wrap">
      <div className="chat-input-container">
        <div className="chat-composer-mark" aria-hidden="true">K</div>
        <textarea
          ref={textareaRef}
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || "Ask anything about your company brain..."}
          disabled={disabled}
          rows={1}
          aria-label="Ask Komponist"
        />
        <button
          className="chat-send-button"
          onClick={handleSend}
          disabled={disabled || !input.trim()}
          aria-label="Send message"
        >
          {disabled ? <span className="chat-send-loader" /> : <span aria-hidden="true">↑</span>}
        </button>
      </div>
      <div className="chat-composer-meta">
        <span>Answers use confirmed graph knowledge</span>
        <span><kbd>Enter</kbd> send · <kbd>Shift</kbd> + <kbd>Enter</kbd> new line</span>
      </div>
    </div>
  )
}
