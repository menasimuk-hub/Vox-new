import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'

function statusTone(label) {
  if (label === 'Ready') return 'ok'
  if (label === 'Pending approval') return 'warn'
  return 'muted'
}

export default function WaSurveyTypes() {
  const [types, setTypes] = useState([])
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [creating, setCreating] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch('/admin/wa-survey/types')
      setTypes(Array.isArray(data?.types) ? data.types : [])
    } catch (e) {
      setError(e?.message || 'Could not load survey types')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const syncAll = async () => {
    setSyncing(true)
    setMsg('')
    setError('')
    try {
      const summary = await apiFetch('/admin/wa-survey/sync', { method: 'POST', body: '{}' })
      setMsg(
        `Sync complete — imported ${summary.imported || 0}, updated ${summary.updated || 0}, skipped ${summary.skipped || 0}, failed ${summary.failed || 0}. Only Telnyx templates whose names contain “survey” are imported and linked when possible.`
      )
      await load()
    } catch (e) {
      setError(e?.message || 'Sync failed')
    } finally {
      setSyncing(false)
    }
  }

  const createType = async (e) => {
    e.preventDefault()
    if (!newName.trim()) return
    setCreating(true)
    setError('')
    setMsg('')
    try {
      await apiFetch('/admin/wa-survey/types', {
        method: 'POST',
        body: JSON.stringify({ name: newName.trim(), description: newDescription.trim() || undefined }),
      })
      setShowCreate(false)
      setNewName('')
      setNewDescription('')
      setMsg('Survey type created. Add a standard template draft on the edit page, then push to Telnyx.')
      await load()
    } catch (err) {
      setError(err?.message || 'Could not create survey type')
    } finally {
      setCreating(false)
    }
  }

  return (
    <>
      <div className="pageTop">
        <div>
          <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
            Platform Settings
          </div>
          <h1>WA Survey</h1>
          <p className="pageLead">
            Manage reusable survey types and their approved WhatsApp templates. Push drafts to Telnyx, sync approval status, and preview the first template message plus simulated survey flow.
          </p>
        </div>
        <div className="pageTopActions">
          <button type="button" className="btn" onClick={() => setShowCreate((v) => !v)}>
            <i className="ti ti-plus" /> Create survey type
          </button>
          <button type="button" className="btn" onClick={syncAll} disabled={syncing} title="Pull WhatsApp templates from Telnyx whose names contain “survey”, update approval status, and link them to survey types when the name matches.">
            <i className="ti ti-refresh" /> {syncing ? 'Syncing…' : 'Sync from Telnyx'}
          </button>
        </div>
      </div>

      <div className="note" style={{ marginBottom: 16 }}>
        <strong>Sync from Telnyx</strong> fetches remote WhatsApp templates from Telnyx/Meta, updates approval status locally, and imports templates whose names contain “survey”. It does not push your drafts — use <em>Push to Telnyx</em> on each template after editing.
      </div>

      {showCreate ? (
        <form className="card" style={{ marginBottom: 16 }} onSubmit={createType}>
          <div className="cardHead"><h2>New survey type</h2></div>
          <div className="cardBody grid2">
            <label className="field">
              <span>Name</span>
              <input className="input" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="e.g. Post-visit feedback" required />
            </label>
            <label className="field">
              <span>Description</span>
              <input className="input" value={newDescription} onChange={(e) => setNewDescription(e.target.value)} placeholder="Optional" />
            </label>
            <div className="formActions">
              <button type="submit" className="btn primary" disabled={creating}>{creating ? 'Creating…' : 'Save survey type'}</button>
              <button type="button" className="btn ghost" onClick={() => setShowCreate(false)}>Cancel</button>
            </div>
          </div>
        </form>
      ) : null}

      {error ? <div className="alert error">{error}</div> : null}
      {msg ? <div className="alert ok">{msg}</div> : null}

      <div className="card">
        <div className="cardHead">
          <h2>Survey types</h2>
          <span className="muted">{types.length} types</span>
        </div>
        <div className="cardBody">
          {loading ? (
            <p className="muted">Loading…</p>
          ) : (
            <div className="tableWrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Survey type</th>
                    <th>Active</th>
                    <th>Standard</th>
                    <th>Anonymous</th>
                    <th>Last synced</th>
                    <th>Status</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {types.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <strong>{row.name}</strong>
                        <div className="muted">{row.description}</div>
                      </td>
                      <td>{row.is_active ? 'Yes' : 'No'}</td>
                      <td>{row.standard_template_count || 0}</td>
                      <td>{row.anonymous_template_count || 0}</td>
                      <td>{row.last_synced_at ? new Date(row.last_synced_at).toLocaleString() : '—'}</td>
                      <td>
                        <span className={`pill ${statusTone(row.status_label)}`}>{row.status_label || '—'}</span>
                      </td>
                      <td>
                        <Link className="btn sm" to={`/settings/wa-survey/${row.id}`}>
                          Edit
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
