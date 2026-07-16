type EvidenceChipProps = {
  source: string
  reference: string
  url?: string
  date?: string
}

const SOURCE_BADGES: Record<string, { abbr: string; className: string }> = {
  notion: { abbr: 'NO', className: 'source-badge-notion' },
  slack: { abbr: 'SL', className: 'source-badge-slack' },
  google: { abbr: 'GD', className: 'source-badge-google' },
  github: { abbr: 'GH', className: 'source-badge-github' },
  local: { abbr: 'L', className: 'source-badge-manual' },
  agent_report: { abbr: 'AI', className: '' },
  manual: { abbr: 'M', className: '' },
}

export default function EvidenceChip({ source, reference, url, date }: EvidenceChipProps) {
  const sourceBadge = SOURCE_BADGES[source] || { abbr: source.substring(0, 2).toUpperCase(), className: '' }

  const content = (
    <>
      <span className={`source-badge ${sourceBadge.className}`} style={{ width: '20px', height: '20px', fontSize: '9px' }}>
        {sourceBadge.abbr}
      </span>
      <span className="text-ink-secondary">{reference}</span>
      {date && (
        <>
          <span className="text-ink-muted">·</span>
          <span className="text-ink-muted">{date}</span>
        </>
      )}
    </>
  )

  if (url) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="evidence-chip"
      >
        {content}
      </a>
    )
  }

  return <div className="evidence-chip">{content}</div>
}
