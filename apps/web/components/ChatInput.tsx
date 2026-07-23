'use client'

import { useEffect, useRef, useState, KeyboardEvent } from 'react'
import { LoaderCircle, SendHorizontal, ShieldCheck, Sparkles } from 'lucide-react'
import { Button } from './ui/button'

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
    <div className="chat-input-shell relative z-10 shrink-0 border-t border-line bg-paper/90 px-4 pb-4 pt-3 backdrop-blur-xl">
      <div className="mx-auto max-w-[880px]">
        <div className="chat-input-frame flex items-end gap-3 rounded-xl border-2 border-ink bg-white p-2.5 shadow-[5px_5px_0_#201c15] transition-shadow focus-within:shadow-[7px_7px_0_#e8641b]">
          <div className={`chat-input-mark grid size-10 shrink-0 place-items-center rounded-md border border-line bg-warning-soft text-orange-dark ${disabled ? 'animate-pulse' : ''}`}>
            <Sparkles className="size-4" />
          </div>
          <textarea
            ref={textareaRef}
            className="max-h-36 min-h-10 min-w-0 flex-1 resize-none overflow-y-auto border-0 bg-transparent px-1 py-2 text-base leading-6 text-ink outline-none placeholder:text-faint"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder || "Ask anything about your company brain..."}
            disabled={disabled}
            rows={1}
            aria-label="Ask Komponist"
          />
          <Button
            size="icon"
            onClick={handleSend}
            disabled={disabled || !input.trim()}
            aria-label="Send message"
            className="shrink-0 shadow-[2px_2px_0_#201c15]"
          >
            {disabled ? <LoaderCircle className="animate-spin" /> : <SendHorizontal />}
          </Button>
        </div>
        <div className="chat-input-meta flex items-center justify-between gap-4 px-2 pt-2 font-mono text-[9px] text-faint sm:text-[10px]">
          <span className="flex items-center gap-1.5">
            {disabled ? <LoaderCircle className="size-3 animate-spin text-orange" /> : <ShieldCheck className="size-3 text-teal" />}
            {disabled ? 'Komponist is working on your answer' : 'confirmed graph only'}
          </span>
          <span><kbd>Enter</kbd> send · <kbd>Shift</kbd> + <kbd>Enter</kbd> new line</span>
        </div>
      </div>
    </div>
  )
}
