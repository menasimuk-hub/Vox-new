import React, { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { apiFetch } from '../../lib/api'

function statusPill(label) {
  if (label === 'live') return 'leadPill leadPillAdvance'
  return 'leadPill leadPillNeutral'
}

export default function FeedbackIndustryEdit() {
  const { industryId } = useParams()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [item, setItem] = useState(null)

  const load = useCallback(async () => {
    setError('')
    setLoading(true)
    try {
      const data = await apiFetch(`/admin/customer-feedback/industries/${industryId}`)
      setItem(data?.item || null)
    } catch (e) {
      setError(e?.message || 'Could not load industry')
    } finally {
      setLoading(false)
    }
  }, [industryId])

  useEffect(() => {
    load()
  }, [load])

  const save = async () => {
    if (!item) return
    setBusy(true)
    setError('')
    try {
      await apiFetch('/admin/customer-feedback/industries', {
        method: 'POST',
        body: JSON.stringify(item),
      })
      setMsg('Saved.')
      await load()
    } catch (e) {
      setError(e?.message || 'Could not save')
    } finally {
      setBusy(false)
    }
  }

  const syncTelnyx = async () => {
    setBusy(true)
    setError('')
    try {
      const data = await apiFetch(`/admin/customer-feedback/industries/${industryId}/sync-telnyx`, { method: 'POST' })
      setMsg(`Submitted ${data?.submitted || 0} templates to Telnyx.`)
      await load()
    } catch (e) {
      setError(e?.message || 'Sync failed')
    } finally {
      setBusy(false)
    }
  }

  const addType = async () => {
    const name = window.prompt('Survey type name')
    if (!name?.trim()) return
    setBusy(true)
    try {
      await apiFetch('/admin/customer-feedback/survey-types', {
        method: 'POST',
        body: JSON.stringify({ industry_id: industryId, name: name.trim() }),
      })
      await load()
    } catch (e) {
      setError(e?.message || 'Could not add survey type')
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return <div className="pageWrap"><div className="card"><div className="cardBody muted">Loading…</div></div></div>
  }

  if (!item) {
    return <div className="pageWrap"><div className="alert error">{error || 'Industry not found'}</div></div>
  }

  return (
    <div className="pageWrap">
      <div className="breadcrumb muted" style={{ marginBottom: 12 }}>
        <Link to="/customer-feedback/industries">Industries</Link> / {item.name}
      </div>

      <div className="pageHead">
        <div>
          <h1>{item.name}</h1>
          <p className="muted">Edit industry details and linked survey types.</p>
        </div>
        <div className="pageHeadActions">
          <button type="button" className="btn soft bsm" disabled={busy} onClick={syncTelnyx}>Sync all to Telnyx</button>
          <button type="button" className="btn primary bsm" disabled={busy} onClick={save}>Save changes</button>
        </div>
      </div>

      {error ? <div className="alert error">{error}</div> : null}
      {msg ? <div className="alert ok">{msg}</div> : null}

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="cardHead"><h3>Industry details</h3></div>
        <div className="cardBody runningSurveyEditGrid">
          <label>Name<input className="input" value={item.name || ''} onChange={(e) => setItem((f) => ({ ...f, name: e.target.value }))} /></label>
          <label>Slug<input className="input" value={item.slug || ''} onChange={(e) => setItem((f) => ({ ...f, slug: e.target.value }))} /></label>
          <label>Sort order<input className="input" type="number" value={item.sort_order ?? 100} onChange={(e) => setItem((f) => ({ ...f, sort_order: Number(e.target.value) }))} /></label>
          <label>Description<textarea className="input" rows={3} value={item.description || ''} onChange={(e) => setItem((f) => ({ ...f, description: e.target.value }))} /></label>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input type="checkbox" checked={Boolean(item.is_active)} onChange={(e) => setItem((f) => ({ ...f, is_active: e.target.checked }))} />
            Active
          </label>
        </div>
      </div>

      <div className="card">
        <div className="cardHead">
          <h3>Survey types</h3>
          <button type="button" className="btn soft bsm" onClick={addType}>Add type</button>
        </div>
        <div className="tableWrap">
          <table className="table runningSurveyTable">
            <thead>
              <tr>
                <th>Survey type</th>
                <th>Templates</th>
                <th>Approved</th>
                <th>Pending</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(item.survey_types || []).map((row) => (
                <tr key={row.id}>
                  <td><strong>{row.name}</strong></td>
                  <td>{row.template_count ?? 0}</td>
                  <td>{row.approved_count ?? 0}</td>
                  <td>{row.pending_count ?? 0}</td>
                  <td><span className={statusPill(row.status)}>{row.status || 'draft'}</span></td>
                  <td>
                    <button type="button" className="btn soft bsm" onClick={() => navigate(`/customer-feedback/survey-types/${row.id}`)}>
                      Open
                    </button>
                  </td>
                </tr>
              ))}
              {!item.survey_types?.length ? <tr><td colSpan={6} className="muted">No survey types yet.</td></tr> : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
