'use client'

import { motion } from 'framer-motion'
import { AlertTriangle, CheckCircle2, Info } from 'lucide-react'

export type SettingsMessage = {
  type: 'success' | 'error' | 'info'
  text: string
}

export default function SettingsNotice({ message }: { message: SettingsMessage }) {
  const Icon = message.type === 'success' ? CheckCircle2 : message.type === 'error' ? AlertTriangle : Info
  const tone = message.type === 'success'
    ? 'border-teal bg-success-soft text-teal'
    : message.type === 'error'
      ? 'border-danger bg-danger-soft text-danger'
      : 'border-ink bg-paper-2 text-ink'

  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      className={`flex items-start gap-3 rounded-xl border-2 px-4 py-3 text-sm font-semibold ${tone}`}
      role={message.type === 'error' ? 'alert' : 'status'}
    >
      <Icon className="mt-0.5 size-4 shrink-0" />
      <span>{message.text}</span>
    </motion.div>
  )
}
