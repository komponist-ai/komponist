import { FileUp, FolderOpen, PlugZap } from 'lucide-react'
import { cn } from '../lib/utils'

type SourceLogoProps = {
  type: string
  className?: string
}

export default function SourceLogo({ type, className }: SourceLogoProps) {
  const frame = cn('relative size-11 shrink-0 overflow-hidden rounded-xl border-2 border-ink shadow-[2px_2px_0_var(--color-shadow-strong)]', className)

  if (type === 'notion') {
    return (
      <span className={frame} aria-label="Notion">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="https://www.notion.so/images/logo-ios.png" alt="" aria-hidden="true" className="size-full object-cover" />
      </span>
    )
  }

  if (type === 'slack') {
    return (
      <span className={frame} aria-label="Slack">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="https://a.slack-edge.com/80588/marketing/img/meta/slack_hash_256.png" alt="" aria-hidden="true" className="size-full object-cover" />
      </span>
    )
  }

  if (type === 'google') {
    return (
      <span className={cn(frame, 'bg-white')} aria-label="Google Drive">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="https://www.gstatic.com/images/branding/productlogos/drive_2026/v2/web-64dp/logo_drive_2026_color_2x_web_64dp.png" alt="" aria-hidden="true" className="size-full object-cover" />
      </span>
    )
  }

  if (type === 'upload') {
    return <span className={cn(frame, 'grid place-items-center bg-warning-soft text-orange-dark')} aria-label="Document upload"><FileUp className="size-5" /></span>
  }

  if (type === 'local') {
    return <span className={cn(frame, 'grid place-items-center bg-info-soft text-info')} aria-label="Local documents"><FolderOpen className="size-5" /></span>
  }

  return <span className={cn(frame, 'grid place-items-center bg-white')} aria-label="Source"><PlugZap className="size-5" /></span>
}
