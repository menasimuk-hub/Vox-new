import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { formatActionSuccess, formatWaSurveyError } from '../lib/waSurveyFeedback'
import { resolveTelnyxSyncLabel, telnyxSyncPillClass } from '../lib/waSurveyTelnyxSync'
import WaInterviewTemplateModal from '../components/WaInterviewTemplateModal'

function formatWhen(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

export default function WaInterviewTemplates() {
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState('')
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [templates, setTemplates] = useState([])
  const [editId, setEditId] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch('/admin/wa-interview/templates')
      setTemplates(Array.isArray(data?.templates) ? data.templates : [])
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load interview templates').message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const syncAll = async () => {
    setWorking('sync')
    setError('')
    setMsg('')
    try {
      const result = await apiFetch('/admin/wa-interview/sync', { method: 'POST', body: '{}' })
      if (result?.ok === false) {
        throw Object.assign(new Error(result.message || 'Telnyx sync failed'), { data: { detail: result } })
      }
      setMsg(formatActionSuccess(result, 'Synced from Telnyx').message)
      await load()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Telnyx sync failed').detailText)
    } finally {
      setWorking('')
    }
  }

  const toggleHidden = async (tpl) => {
    setWorking(`hide-${tpl.id}`)
    try {
      await apiFetch(`/admin/wa-interview/templates/${tpl.id}/set-active`, {
        method: 'POST',
        body: JSON.stringify({ active_for_interview: tpl.active_for_interview === false }),
      })
      await load()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not update visibility').message)
    } finally {
      setWorking('')
    }
  }

  const deleteTemplate = async (tpl) => {
    if (!window.confirm(`Delete “${tpl.display_name || tpl.name}”? This removes it from Telnyx when synced.`)) return
    setWorking(`delete-${tpl.id}`)
    try {
      const result = await apiFetch(`/admin/wa-interview/templates/${tpl.id}`, { method: 'DELETE' })
      setMsg(formatActionSuccess(result, 'Template deleted').message)
      await load()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not delete template').message)
    } finally {
      setWorking('')
    }
  }

  const pushTemplate = async (tpl) => {
    setWorking(`push-${tpl.id}`)
    try {
      const result = await apiFetch(`/admin/wa-interview/templates/${tpl.id}/push`, { method: 'POST', body: '{}' })
      setMsg(formatActionSuccess(result, 'Synced to Telnyx').message)
      await load()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Telnyx push failed').detailText)
    } finally {
      setWorking('')
    }
  }

  return (
    <div className="pageShell">
      <div className="pageTop">
        <div>
          <p className="muted" style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>Platform Settings</p>
          <h1>WA Interview templates</h1>
          <p className="muted">
            Manage WhatsApp templates used by the AI Interview flow — launch email notice, booking confirmation, cancel, and job closed.
          </p>
        </div>
        <div className="actions">
          <Link className="btn" to="/settings/email">Email settings</Link>
          <button type="button" className="btn primary" disabled={working === 'sync'} onClick={() => void syncAll()}>
            {working === 'sync' ? 'Syncing…' : 'Sync from Telnyx'}
          </button>
        </div>
      </div>

      {error ? <div className="alert err">{error}</div> : null}
      {msg ? <div className="alert ok">{msg}</div> : null}

      {loading ? (
        <p className="muted">Loading templates…</p>
      ) : (
        <div className="card">
          <div className="tableWrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Template</th>
                  <th>Telnyx name</th>
                  <th>Status</th>
                  <th>Visibility</th>
                  <th>Updated</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {templates.map((tpl) => (
                  <tr key={tpl.id}>
                    <td>
                      <strong>{tpl.display_name || tpl.name}</strong>
                      <div className="muted" style={{ fontSize: '11.5px', marginTop: '3px' }}>{tpl.description || tpl.sales_template_key}</div>
                    </td>
                    <td><code>{tpl.name}</code></td>
                    <td>
                      <span className={telnyxSyncPillClass(resolveTelnyxSyncLabel(tpl))}>
                        {resolveTelnyxSyncLabel(tpl)}
                      </span>
                    </td>
                    <td>{tpl.active_for_interview === false ? 'Hidden' : 'Active'}</td>
                    <td>{formatWhen(tpl.updated_at || tpl.last_pushed_at)}</td>
                    <td>
                      <div style={{ display: 'flex', gap: '6px', flexWrap: 'nowrap' }}>
                        <button type="button" className="btn soft sm" onClick={() => setEditId(tpl.id)}>
                          Edit
                        </button>
                        <button
                          type="button"
                          className="btn soft sm"
                          disabled={!!working}
                          onClick={() => void toggleHidden(tpl)}
                        >
                          {tpl.active_for_interview === false ? 'Show' : 'Hide'}
                        </button>
                        <button
                          type="button"
                          className="btn soft sm"
                          disabled={!!working}
                          onClick={() => void pushTemplate(tpl)}
                        >
                          Sync
                        </button>
                        <button
                          type="button"
                          className="btn sm danger"
                          disabled={!!working}
                          onClick={() => void deleteTemplate(tpl)}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <WaInterviewTemplateModal
        templateId={editId}
        open={Boolean(editId)}
        onClose={() => setEditId(null)}
        onSaved={() => void load()}
      />
    </div>
  )
}
