type EvidenceChipProps = {
  source: string
  reference: string
  url?: string
  date?: string
}

const SOURCE_BADGES: Record<string, { abbr: string; className: string }> = {
  notion: { abbr: 'NO', className: 'bg-ink text-white' },
  slack: { abbr: 'SL', className: 'bg-[#4A154B] text-white' },
  google: { abbr: 'GD', className: 'bg-[#4285F4] text-white' },
  github: { abbr: 'GH', className: 'bg-[#24292f] text-white' },
  upload: { abbr: 'UP', className: 'bg-warning-soft text-orange-dark' },
  local: { abbr: 'LD', className: 'bg-info-soft text-info' },
  agent_report: { abbr: 'AI', className: 'bg-success-soft text-teal' },
  manual: { abbr: 'M', className: 'bg-paper-3 text-ink-2' },
}

export default function EvidenceChip({ source, reference, url, date }: EvidenceChipProps) {
  const sourceBadge = SOURCE_BADGES[source] || { abbr: source.substring(0, 2).toUpperCase(), className: '' }
  const uploadMatch = reference.match(/^upload:(.+):[a-f0-9]{8,}$/i)
  const displayReference = uploadMatch ? uploadMatch[1] : reference
  const canOpen = Boolean(url && /^https?:\/\//i.test(url))

  const content = (
    <>
      <span className={`grid size-5 shrink-0 place-items-center rounded border border-line font-mono text-[8px] font-bold ${sourceBadge.className}`}>
        {sourceBadge.abbr}
      </span>
      <span className="max-w-[240px] truncate text-ink-2">{displayReference}</span>
      {date && (
        <>
          <span className="text-faint">·</span>
          <span className="text-faint">{date}</span>
        </>
      )}
    </>
  )

  if (canOpen) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-line bg-paper px-2 py-1 font-mono text-[10px] no-underline hover:border-ink hover:bg-paper-2"
      >
        {content}
      </a>
    )
  }

  return <div className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-line bg-paper px-2 py-1 font-mono text-[10px]">{content}</div>
}
