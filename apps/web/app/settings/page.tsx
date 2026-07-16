'use client'

import { useState, useEffect } from 'react'
import AppLayout from '../../components/AppLayout'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface OrgSettings {
  auto_confirm: boolean
  parallel_batch_size: number
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<OrgSettings>({
    auto_confirm: true,
    parallel_batch_size: 5
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null)

  // Get org ID from localStorage
  const getOrgId = () => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('komponist_org_id') || 'default-org'
    }
    return 'default-org'
  }

  useEffect(() => {
    fetchSettings()
  }, [])

  const fetchSettings = async () => {
    setLoading(true)
    try {
      const orgId = getOrgId()
      const res = await fetch(`${API_URL}/settings?org_id=${orgId}`)
      if (res.ok) {
        const data = await res.json()
        setSettings(data)
      }
    } catch (err) {
      console.error('Failed to fetch settings:', err)
    } finally {
      setLoading(false)
    }
  }

  const saveSettings = async () => {
    setSaving(true)
    setMessage(null)
    try {
      const orgId = getOrgId()
      const res = await fetch(`${API_URL}/settings?org_id=${orgId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
      })
      if (res.ok) {
        setMessage({ type: 'success', text: 'Settings saved successfully!' })
      } else {
        throw new Error('Failed to save')
      }
    } catch (err) {
      setMessage({ type: 'error', text: 'Failed to save settings' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <AppLayout>
      <div className="page-header">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="text-small text-muted">
            Configure how your company brain works
          </p>
        </div>
      </div>

      <div className="page-body max-w-2xl">
        {message && (
          <div
            className="card mb-6"
            style={{
              background: message.type === 'success' ? 'var(--color-success-soft)' : 'var(--color-danger-soft)',
              borderColor: message.type === 'success' ? 'var(--color-success)' : 'var(--color-danger)'
            }}
          >
            <p className="text-small" style={{ color: message.type === 'success' ? 'var(--color-success)' : 'var(--color-danger)' }}>
              {message.type === 'success' ? '✓' : '⚠'} {message.text}
            </p>
          </div>
        )}

        {/* Extraction Settings */}
        <div className="card mb-6">
          <h2 className="text-h2 mb-4">Extraction Settings</h2>

          <div className="space-y-6">
            {/* Auto-confirm toggle */}
            <div className="flex items-start justify-between">
              <div>
                <p className="text-small font-medium mb-1">Auto-accept extracted entities</p>
                <p className="text-caption text-muted">
                  When enabled, new entities are automatically confirmed.
                  When disabled, they go to the review queue for manual approval.
                </p>
              </div>
              <button
                onClick={() => setSettings(s => ({ ...s, auto_confirm: !s.auto_confirm }))}
                className={`toggle ${settings.auto_confirm ? 'toggle-on' : 'toggle-off'}`}
                disabled={loading}
              >
                <span className="toggle-handle" />
              </button>
            </div>

            {/* Batch size */}
            <div>
              <p className="text-small font-medium mb-1">Parallel processing batch size</p>
              <p className="text-caption text-muted mb-3">
                Number of pages to process simultaneously during sync. Higher values are faster but use more resources.
              </p>
              <div className="flex items-center gap-4">
                <input
                  type="range"
                  min="1"
                  max="10"
                  value={settings.parallel_batch_size}
                  onChange={(e) => setSettings(s => ({ ...s, parallel_batch_size: parseInt(e.target.value) }))}
                  className="flex-1"
                  disabled={loading}
                />
                <span className="text-small font-mono w-8">{settings.parallel_batch_size}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Organization Settings */}
        <div className="card mb-6">
          <h2 className="text-h2 mb-4">Organization</h2>

          <div className="space-y-4">
            <div>
              <p className="text-small font-medium mb-1">Organization ID</p>
              <p className="text-caption text-muted mb-2">
                Used to isolate your data. Change this to work with a different organization.
              </p>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={typeof window !== 'undefined' ? localStorage.getItem('komponist_org_id') || 'default-org' : 'default-org'}
                  onChange={(e) => {
                    if (typeof window !== 'undefined') {
                      localStorage.setItem('komponist_org_id', e.target.value)
                    }
                  }}
                  className="input flex-1"
                  placeholder="my-company"
                />
              </div>
              <p className="text-caption text-muted mt-1">
                Note: Changing this requires a page refresh to take effect.
              </p>
            </div>
          </div>
        </div>

        {/* Save button */}
        <div className="flex justify-end">
          <button
            onClick={saveSettings}
            disabled={saving || loading}
            className="btn btn-primary"
          >
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>

        {/* Info card */}
        <div className="card mt-8 bg-paper-2">
          <h3 className="text-h3 mb-2">About Review Mode</h3>
          <p className="text-small text-muted mb-3">
            When auto-accept is <strong>enabled</strong> (default), extracted entities are immediately
            added to your knowledge graph. This is faster but means you trust the AI extraction.
          </p>
          <p className="text-small text-muted">
            When auto-accept is <strong>disabled</strong>, all new entities go to the Review Queue
            where you can confirm, edit, or reject them before they become part of your brain.
          </p>
        </div>
      </div>

      <style jsx>{`
        .toggle {
          position: relative;
          width: 48px;
          height: 24px;
          border-radius: 12px;
          border: none;
          cursor: pointer;
          transition: background-color 0.2s;
        }
        .toggle-on {
          background-color: var(--color-teal);
        }
        .toggle-off {
          background-color: var(--color-line);
        }
        .toggle-handle {
          position: absolute;
          top: 2px;
          left: 2px;
          width: 20px;
          height: 20px;
          border-radius: 10px;
          background: white;
          transition: transform 0.2s;
        }
        .toggle-on .toggle-handle {
          transform: translateX(24px);
        }
        .input {
          padding: 8px 12px;
          border: 1px solid var(--color-line);
          border-radius: 6px;
          font-size: 14px;
          background: var(--color-paper);
        }
        .input:focus {
          outline: none;
          border-color: var(--color-teal);
        }
      `}</style>
    </AppLayout>
  )
}
