'use client'

import { useState } from 'react'
import EvidenceChip from './EvidenceChip'

type FactCardProps = {
  id: string
  type: string
  statement: string
  detail?: string
  confidence: string
  evidence: Array<{
    id: string
    source: string
    reference: string
    url?: string
    source_date: string
  }>
  relatedTo?: Array<{ id: string; statement: string; score: number }>
  onConfirm: (id: string, statement: string) => void
  onReject: (id: string) => void
  onMerge: (id: string, targetId: string) => void
}

export default function FactCard({
  id,
  type,
  statement: initialStatement,
  detail,
  confidence,
  evidence,
  relatedTo,
  onConfirm,
  onReject,
  onMerge,
}: FactCardProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [statement, setStatement] = useState(initialStatement)
  const [showMerge, setShowMerge] = useState(false)

  const handleConfirm = () => {
    onConfirm(id, statement)
  }

  const handleEdit = () => {
    setIsEditing(true)
  }

  const handleSave = () => {
    setIsEditing(false)
    onConfirm(id, statement)
  }

  const typeClass = `type-${type.toLowerCase()}`

  return (
    <div className="card card-interactive">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <span className={`badge ${typeClass}`}>{type}</span>
        <span className="text-caption text-ink-muted font-mono">
          Confidence: {confidence}
        </span>
      </div>

      {/* Statement */}
      {isEditing ? (
        <textarea
          value={statement}
          onChange={(e) => setStatement(e.target.value)}
          className="input mb-4"
          rows={3}
          autoFocus
        />
      ) : (
        <p className="text-lead mb-3 leading-relaxed">{statement}</p>
      )}

      {/* Detail */}
      {detail && (
        <p className="text-ink-secondary text-small mb-4 leading-relaxed">
          {detail}
        </p>
      )}

      {/* Evidence */}
      {evidence.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-4">
          {evidence.map((e) => (
            <EvidenceChip
              key={e.id}
              source={e.source}
              reference={e.reference}
              url={e.url}
              date={new Date(e.source_date).toLocaleDateString()}
            />
          ))}
        </div>
      )}

      {/* Duplicate warning */}
      {relatedTo && relatedTo.length > 0 && (
        <div className="bg-warning-soft border border-warning rounded-md p-4 mb-4">
          <p className="text-small text-warning font-medium mb-2">
            ⚠️ Possible duplicate
          </p>
          {relatedTo.map((related) => (
            <div key={related.id} className="text-caption text-ink-secondary mb-1">
              {related.statement}{' '}
              <span className="text-ink-muted">
                (similarity: {(related.score * 100).toFixed(0)}%)
              </span>
            </div>
          ))}
          <button
            onClick={() => setShowMerge(!showMerge)}
            className="text-caption text-warning hover:underline mt-2"
          >
            {showMerge ? 'Cancel merge' : 'Merge into existing →'}
          </button>
        </div>
      )}

      {/* Merge selector */}
      {showMerge && relatedTo && (
        <div className="mb-4 p-3 bg-surface-subtle rounded-md border border-line">
          <p className="text-small font-medium mb-2">Merge into:</p>
          {relatedTo.map((related) => (
            <button
              key={related.id}
              onClick={() => onMerge(id, related.id)}
              className="block w-full text-left text-small p-2 hover:bg-surface rounded mb-1 transition-colors"
            >
              {related.statement}
            </button>
          ))}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-3 pt-4 border-t border-line">
        {isEditing ? (
          <>
            <button onClick={handleSave} className="btn btn-primary">
              Save & Confirm
            </button>
            <button onClick={() => setIsEditing(false)} className="btn btn-secondary">
              Cancel
            </button>
          </>
        ) : (
          <>
            <button onClick={handleConfirm} className="btn btn-primary">
              Confirm
              <kbd className="kbd-hint ml-2">C</kbd>
            </button>
            <button onClick={handleEdit} className="btn btn-secondary">
              Edit
              <kbd className="kbd-hint ml-2">E</kbd>
            </button>
            <button onClick={() => onReject(id)} className="btn btn-danger">
              Reject
              <kbd className="kbd-hint ml-2">R</kbd>
            </button>
            {relatedTo && relatedTo.length > 0 && (
              <button onClick={() => setShowMerge(!showMerge)} className="btn btn-secondary">
                Merge
                <kbd className="kbd-hint ml-2">M</kbd>
              </button>
            )}
          </>
        )}
      </div>
    </div>
  )
}
