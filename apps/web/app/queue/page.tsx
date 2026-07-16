'use client'

import { useState, useEffect } from 'react'
import useSWR, { mutate } from 'swr'
import AppLayout from '../../components/AppLayout'
import FactCard from '../../components/FactCard'
import { fetchQueue, confirmEntity, rejectEntity, mergeEntity } from '../../lib/api'

export default function QueuePage() {
  const { data, error, isLoading } = useSWR('/queue', fetchQueue, {
    refreshInterval: 5000,
  })

  const [filter, setFilter] = useState<string>('all')

  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return
      }
      // TODO: Implement global keyboard shortcuts for first card
    }

    window.addEventListener('keydown', handleKeyPress)
    return () => window.removeEventListener('keydown', handleKeyPress)
  }, [])

  const handleConfirm = async (id: string, statement: string) => {
    try {
      await confirmEntity(id, statement)
      mutate('/queue')
    } catch (error) {
      console.error('Failed to confirm:', error)
      alert('Failed to confirm entity')
    }
  }

  const handleReject = async (id: string) => {
    try {
      await rejectEntity(id)
      mutate('/queue')
    } catch (error) {
      console.error('Failed to reject:', error)
      alert('Failed to reject entity')
    }
  }

  const handleMerge = async (id: string, targetId: string) => {
    try {
      await mergeEntity(id, targetId)
      mutate('/queue')
    } catch (error) {
      console.error('Failed to merge:', error)
      alert('Failed to merge entity')
    }
  }

  const items = data?.items || []

  const filteredItems = filter === 'all'
    ? items
    : items.filter((item: any) => item.entity_type === filter)

  const groupedByType = filteredItems.reduce((acc: any, item: any) => {
    const type = item.entity_type
    if (!acc[type]) acc[type] = []
    acc[type].push(item)
    return acc
  }, {})

  const typeOrder = ['Fact', 'Decision', 'Goal', 'Constraint', 'Instruction', 'Note', 'CustomerRequest', 'Project']

  return (
    <AppLayout>
      <div className="page-header">
        <div>
          <h1 className="page-title">Review Queue</h1>
          <p className="text-small text-muted">
            {isLoading
              ? 'Loading...'
              : items.length === 0
              ? 'Nothing to review'
              : `${items.length} fact${items.length === 1 ? '' : 's'} pending`}
          </p>
        </div>
      </div>

      <div className="page-body">
        {error && (
          <div className="card mb-6" style={{ background: 'var(--color-danger-soft)', borderColor: 'var(--color-danger)' }}>
            <p className="text-small" style={{ color: 'var(--color-danger)' }}>
              ⚠ Failed to load queue. Is the API running?
            </p>
          </div>
        )}

        {/* Filters */}
        {items.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-6">
            <button
              onClick={() => setFilter('all')}
              className={`badge ${filter === 'all' ? 'badge-orange' : ''}`}
            >
              All ({items.length})
            </button>
            {typeOrder.map((type) => {
              const count = items.filter((i: any) => i.entity_type === type).length
              if (count === 0) return null
              return (
                <button
                  key={type}
                  onClick={() => setFilter(type)}
                  className={`badge ${filter === type ? 'badge-teal' : ''}`}
                >
                  {type} ({count})
                </button>
              )
            })}
          </div>
        )}

        {/* Empty state */}
        {!isLoading && items.length === 0 && (
          <div className="card">
            <div className="empty-state">
              <div className="empty-state-icon">✓</div>
              <h3 className="empty-state-title">Queue is empty</h3>
              <p className="empty-state-description">
                No facts waiting for review. New facts will appear here when sources are synced.
              </p>
            </div>
          </div>
        )}

        {/* Queue items grouped by type */}
        <div className="max-w-3xl">
          {typeOrder.map((type) => {
            const typeItems = groupedByType[type]
            if (!typeItems || typeItems.length === 0) return null

            return (
              <div key={type} className="mb-8">
                <h2 className="text-h3 text-muted mb-4 pb-2 border-b border-line">
                  {type}s
                </h2>
                <div className="space-y-4">
                  {typeItems.map((item: any) => (
                    <FactCard
                      key={item.id}
                      id={item.id}
                      type={item.entity_type}
                      statement={item.statement}
                      detail={item.detail}
                      confidence={item.confidence}
                      evidence={item.evidence || []}
                      relatedTo={item.related_to}
                      onConfirm={handleConfirm}
                      onReject={handleReject}
                      onMerge={handleMerge}
                    />
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </AppLayout>
  )
}
