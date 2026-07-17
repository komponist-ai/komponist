import Image from 'next/image'
import { FileUp, FolderOpen, PlugZap } from 'lucide-react'
import { cn } from '../lib/utils'

type SourceLogoProps = {
  type: string
  className?: string
}

export default function SourceLogo({ type, className }: SourceLogoProps) {
  const frame = cn('grid size-11 shrink-0 place-items-center rounded-xl border-2 border-ink bg-white shadow-[2px_2px_0_#201c15]', className)

  if (type === 'notion') {
    return (
      <span className={frame} aria-label="Notion">
        <Image src="https://www.notion.so/images/logo-ios.png" width={28} height={28} alt="" aria-hidden="true" className="size-7 object-contain" />
      </span>
    )
  }

  if (type === 'slack') {
    return (
      <span className={frame} aria-label="Slack">
        <Image src="https://a.slack-edge.com/80588/marketing/img/meta/slack_hash_256.png" width={28} height={28} alt="" aria-hidden="true" className="size-7 object-contain" />
      </span>
    )
  }

  if (type === 'google') {
    return (
      <span className={frame} aria-label="Google Drive">
        <Image src="https://www.gstatic.com/images/branding/productlogos/drive_2026/v2/web-64dp/logo_drive_2026_color_2x_web_64dp.png" width={28} height={28} alt="" aria-hidden="true" className="size-7 object-contain" />
      </span>
    )
  }

  if (type === 'upload') {
    return <span className={cn(frame, 'bg-warning-soft text-orange-dark')} aria-label="Document upload"><FileUp className="size-5" /></span>
  }

  if (type === 'local') {
    return <span className={cn(frame, 'bg-info-soft text-info')} aria-label="Local documents"><FolderOpen className="size-5" /></span>
  }

  return <span className={frame} aria-label="Source"><PlugZap className="size-5" /></span>
}
