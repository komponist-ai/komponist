'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { Database, Plus } from 'lucide-react'
import AppLayout from '../../components/AppLayout'
import StudioTopbar from '../../components/StudioTopbar'
import { Button } from '../../components/ui/button'
import { API_URL, apiFetch, getActiveOrgId } from '../../lib/api'

interface Source {
  id: string
  type: 'notion' | 'slack' | 'google' | 'local' | 'upload'
  name: string
  status: 'connected' | 'syncing' | 'error'
  lastSync: string | null
  itemCount: number
}

interface DisconnectModal {
  source: Source | null
  loading: boolean
}

export default function SourcesPage() {
  const [sources, setSources] = useState<Source[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [orgId, setOrgId] = useState('')
  const [syncing, setSyncing] = useState<string | null>(null)
  const [disconnectModal, setDisconnectModal] = useState<DisconnectModal>({ source: null, loading: false })

  useEffect(() => {
    setOrgId(getActiveOrgId())
  }, [])

  const fetchSources = async () => {
    try {
      const response = await apiFetch(`${API_URL}/sources?org_id=${orgId}`)
      if (response.ok) {
        const data = await response.json()
        setSources(data.sources || [])
      } else {
        setSources([])
      }
    } catch (err) {
      console.error('Failed to fetch sources:', err)
      setError('Could not connect to API')
      setSources([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (orgId) fetchSources()
  }, [orgId])

  const handleSync = async (sourceId: string) => {
    setSyncing(sourceId)
    setError(null)

    try {
      const response = await apiFetch(
        `${API_URL}/sources/${sourceId}/sync?org_id=${orgId}`,
        { method: 'POST' }
      )
      const data = await response.json()

      if (response.ok) {
        console.log('Sync result:', data)
        // Refresh sources to get updated status
        await fetchSources()
      } else {
        throw new Error(data.error || 'Sync failed')
      }
    } catch (err: any) {
      console.error('Sync error:', err)
      setError(err.message || 'Failed to sync source')
    } finally {
      setSyncing(null)
    }
  }

  const handleDisconnect = async (removeData: boolean) => {
    if (!disconnectModal.source) return

    setDisconnectModal(m => ({ ...m, loading: true }))
    setError(null)

    try {
      const sourceId = disconnectModal.source.id
      const url = `${API_URL}/sources/${sourceId}?org_id=${orgId}&remove_data=${removeData}`

      const response = await apiFetch(url, { method: 'DELETE' })
      const data = await response.json()

      if (response.ok) {
        console.log('Disconnect result:', data)
        setDisconnectModal({ source: null, loading: false })
        await fetchSources()
      } else {
        throw new Error(data.error || 'Failed to disconnect')
      }
    } catch (err: any) {
      console.error('Disconnect error:', err)
      setError(err.message || 'Failed to disconnect source')
      setDisconnectModal(m => ({ ...m, loading: false }))
    }
  }

  const getSourceIcon = (type: string) => {
    switch (type) {
      case 'notion': return 'NO'
      case 'slack': return 'SL'
      case 'google': return 'GD'
      case 'local': return '📁'
      case 'upload': return '↑'
      default: return '?'
    }
  }

  const getSourceClass = (type: string) => {
    switch (type) {
      case 'notion': return 'source-badge-notion'
      case 'slack': return 'source-badge-slack'
      case 'google': return 'source-badge-google'
      case 'local': return 'source-badge-manual'
      case 'upload': return 'source-badge-manual'
      default: return ''
    }
  }

  return (
    <AppLayout>
      <StudioTopbar
        section="Sources"
        title="Connected Sources"
        description={loading ? 'Loading source connections…' : `${sources.length} source${sources.length === 1 ? '' : 's'} connected`}
        icon={Database}
        actions={<Button asChild size="sm"><Link href="/onboard"><Plus /> Add source</Link></Button>}
      />

      <div className="page-body">
        {error && (
          <div className="card mb-6" style={{ background: 'var(--color-danger-soft)', borderColor: 'var(--color-danger)' }}>
            <p className="text-small" style={{ color: 'var(--color-danger)' }}>
              ⚠ {error}
            </p>
          </div>
        )}

        {!loading && sources.length === 0 ? (
          <div className="card">
            <div className="empty-state">
              <div className="empty-state-icon">↗</div>
              <h3 className="empty-state-title">No sources connected</h3>
              <p className="empty-state-description">
                Connect your first source to start building your company brain.
                We support Notion, Slack, Google Workspace, and local documents.
              </p>
              <Link href="/onboard" className="btn btn-primary">
                Add Your First Source →
              </Link>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-4xl">
            {sources.map((source) => (
              <div key={source.id} className="card">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <span className={`source-badge ${getSourceClass(source.type)}`}>
                      {getSourceIcon(source.type)}
                    </span>
                    <div>
                      <h3 className="text-h3">{source.name}</h3>
                      <p className="text-caption text-muted capitalize">{source.type}</p>
                    </div>
                  </div>
                  <span className={`badge ${source.status === 'connected' ? 'badge-teal' : source.status === 'syncing' ? 'badge-orange' : ''}`}>
                    {source.status}
                  </span>
                </div>

                <div className="flex justify-between text-small text-muted pt-3 border-t border-line">
                  <span>{source.itemCount} items synced</span>
                  <span>
                    {source.lastSync
                      ? `Last sync: ${new Date(source.lastSync).toLocaleDateString()}`
                      : 'Never synced'}
                  </span>
                </div>

                <div className="flex gap-2 mt-4">
                  {source.type !== 'upload' && <button
                      onClick={() => handleSync(source.id)}
                      className="btn btn-secondary btn-sm"
                      disabled={syncing === source.id}
                    >
                      {syncing === source.id ? 'Syncing...' : 'Sync Now'}
                    </button>}
                  <button
                    onClick={() => setDisconnectModal({ source, loading: false })}
                    className="btn btn-ghost btn-sm text-muted"
                  >
                    Disconnect
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Quick add cards when there are some sources */}
        {!loading && sources.length > 0 && sources.length < 4 && (
          <div className="mt-8 pt-6 border-t border-line">
            <p className="text-small text-muted mb-4">Add more sources:</p>
            <div className="flex flex-wrap gap-3">
              {!sources.find(s => s.type === 'notion') && (
                <Link href="/onboard" className="card hover:shadow-card transition-shadow p-4">
                  <div className="flex items-center gap-2">
                    <span className="source-badge source-badge-notion text-micro">NO</span>
                    <span className="text-small">Notion</span>
                  </div>
                </Link>
              )}
              {!sources.find(s => s.type === 'slack') && (
                <Link href="/onboard" className="card hover:shadow-card transition-shadow p-4">
                  <div className="flex items-center gap-2">
                    <span className="source-badge source-badge-slack text-micro">SL</span>
                    <span className="text-small">Slack</span>
                  </div>
                </Link>
              )}
              {!sources.find(s => s.type === 'google') && (
                <Link href="/onboard" className="card hover:shadow-card transition-shadow p-4">
                  <div className="flex items-center gap-2">
                    <span className="source-badge source-badge-google text-micro">GD</span>
                    <span className="text-small">Google</span>
                  </div>
                </Link>
              )}
              {!sources.find(s => s.type === 'local') && (
                <Link href="/onboard" className="card hover:shadow-card transition-shadow p-4">
                  <div className="flex items-center gap-2">
                    <span className="text-micro">📁</span>
                    <span className="text-small">Local Docs</span>
                  </div>
                </Link>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Disconnect Confirmation Modal */}
      {disconnectModal.source && (
        <div className="modal-overlay" onClick={() => !disconnectModal.loading && setDisconnectModal({ source: null, loading: false })}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h2 className="text-h2 mb-2">Disconnect {disconnectModal.source.name}?</h2>
            <p className="text-small text-muted mb-6">
              Choose what happens to the knowledge extracted from this source:
            </p>

            <div className="space-y-3 mb-6">
              <button
                onClick={() => handleDisconnect(false)}
                disabled={disconnectModal.loading}
                className="w-full text-left p-4 border border-line rounded-lg hover:border-teal hover:bg-paper-2 transition-colors"
              >
                <p className="text-small font-medium mb-1">Keep knowledge</p>
                <p className="text-caption text-muted">
                  Stop syncing but keep all extracted entities in your brain.
                  You can reconnect later without duplicating data.
                </p>
              </button>

              <button
                onClick={() => handleDisconnect(true)}
                disabled={disconnectModal.loading}
                className="w-full text-left p-4 border border-line rounded-lg hover:border-danger transition-colors"
                style={{ borderColor: 'var(--color-line)' }}
              >
                <p className="text-small font-medium mb-1" style={{ color: 'var(--color-danger)' }}>
                  Remove all data
                </p>
                <p className="text-caption text-muted">
                  Delete all entities and evidence that came from this source.
                  This cannot be undone.
                </p>
              </button>
            </div>

            <div className="flex justify-end gap-2">
              <button
                onClick={() => setDisconnectModal({ source: null, loading: false })}
                disabled={disconnectModal.loading}
                className="btn btn-ghost"
              >
                Cancel
              </button>
            </div>

            {disconnectModal.loading && (
              <div className="absolute inset-0 bg-paper/80 flex items-center justify-center rounded-lg">
                <p className="text-small text-muted">Disconnecting...</p>
              </div>
            )}
          </div>
        </div>
      )}

      <style jsx>{`
        .modal-overlay {
          position: fixed;
          inset: 0;
          background: rgba(0, 0, 0, 0.5);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 100;
        }
        .modal {
          position: relative;
          background: var(--color-paper);
          border-radius: 12px;
          padding: 24px;
          max-width: 480px;
          width: 90%;
          box-shadow: 0 20px 40px rgba(0, 0, 0, 0.2);
        }
      `}</style>
    </AppLayout>
  )
}
