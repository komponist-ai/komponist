'use client'

import { useState } from 'react'
import useSWR from 'swr'
import AppLayout from '../../components/AppLayout'
import EvidenceChip from '../../components/EvidenceChip'
import { fetchEntities } from '../../lib/api'

export default function EntitiesPage() {
  const [filter, setFilter] = useState<string>('all')
  const [statusFilter, setStatusFilter] = useState<string>('confirmed')

  // Fetch with current status filter
  const { data, error, isLoading } = useSWR(
    ['entities', statusFilter],
    () => fetchEntities(statusFilter)
  )

  const entities = data?.entities || []

  const filtered = entities
    .filter((e: any) => filter === 'all' || e.entity_type === filter)

  const typeOrder = ['Fact', 'Decision', 'Goal', 'Constraint', 'Instruction', 'Note', 'CustomerRequest', 'Project']

  return (
    <AppLayout>
      <div className="page-header">
        <div>
          <h1 className="page-title">Brain</h1>
          <p className="text-small text-muted">
            {isLoading ? 'Loading...' : `${entities.length} confirmed facts`}
          </p>
        </div>
      </div>

      <div className="page-body">
        {error && (
          <div className="card mb-6" style={{ background: 'var(--color-danger-soft)', borderColor: 'var(--color-danger)' }}>
            <p className="text-small" style={{ color: 'var(--color-danger)' }}>
              ⚠ Failed to load entities. Is the API running?
            </p>
          </div>
        )}

        {/* Filters */}
        <div className="flex flex-wrap gap-6 mb-6 pb-4 border-b border-line">
          {/* Status filters */}
          <div>
            <p className="text-caption text-muted mb-2 uppercase tracking-wide">Status</p>
            <div className="flex gap-2">
              <button
                onClick={() => setStatusFilter('confirmed')}
                className={`badge ${statusFilter === 'confirmed' ? 'badge-teal' : ''}`}
              >
                Confirmed
              </button>
              <button
                onClick={() => setStatusFilter('proposed')}
                className={`badge ${statusFilter === 'proposed' ? 'badge-orange' : ''}`}
              >
                Proposed
              </button>
              <button
                onClick={() => setStatusFilter('all')}
                className={`badge ${statusFilter === 'all' ? 'badge-teal' : ''}`}
              >
                All
              </button>
            </div>
          </div>

          {/* Type filters */}
          <div>
            <p className="text-caption text-muted mb-2 uppercase tracking-wide">Type</p>
            <div className="flex gap-2">
              <button
                onClick={() => setFilter('all')}
                className={`badge ${filter === 'all' ? 'badge-teal' : ''}`}
              >
                All Types
              </button>
              {typeOrder.map((type) => (
                <button
                  key={type}
                  onClick={() => setFilter(type)}
                  className={`badge ${filter === type ? 'badge-orange' : ''}`}
                >
                  {type}s
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Entity list */}
        {!isLoading && filtered.length === 0 ? (
          <div className="card">
            <div className="empty-state">
              <div className="empty-state-icon">∅</div>
              <h3 className="empty-state-title">No entities found</h3>
              <p className="empty-state-description">
                {entities.length === 0
                  ? 'Your brain is empty. Connect a source and review some facts.'
                  : 'No entities match your filters. Try adjusting the filters above.'}
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-4 max-w-4xl">
            {filtered.map((entity: any) => (
              <div key={entity.id} className="card">
                <div className="flex items-start justify-between mb-3">
                  <span className="badge badge-orange">
                    {entity.entity_type}
                  </span>
                  <span className="text-caption text-muted font-mono">
                    {entity.confirmed_at
                      ? new Date(entity.confirmed_at).toLocaleDateString()
                      : 'Proposed'}
                  </span>
                </div>

                <p className="text-lead mb-2">{entity.statement}</p>

                {entity.detail && (
                  <p className="text-small text-muted mb-4">
                    {entity.detail}
                  </p>
                )}

                {entity.evidence && entity.evidence.length > 0 && (
                  <div className="flex flex-wrap gap-2 pt-3 border-t border-line">
                    {entity.evidence.map((e: any) => (
                      <EvidenceChip
                        key={e.id}
                        source={e.source}
                        reference={e.reference}
                        url={e.url}
                      />
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Summary stats */}
        {entities.length > 0 && (
          <div className="mt-8 pt-6 border-t border-line">
            <p className="text-caption text-muted uppercase tracking-wide mb-4">By Type</p>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              {typeOrder.map((type) => {
                const count = entities.filter((e: any) => e.entity_type === type && e.status === 'confirmed').length
                return (
                  <div key={type} className="stat-card">
                    <div className="stat-value">{count}</div>
                    <div className="stat-label">{type}s</div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  )
}
