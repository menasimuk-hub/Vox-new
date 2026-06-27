import React, { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { apiFetch } from '../../lib/api'
import '../../styles/admin-industries.css'

function statusPill(label) {
  if (label === 'live') return 'badge-active'
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
      const approved = data?.approved ?? data?.refresh?.approved ?? 0
      const pending = data?.pending ?? data?.refresh?.pending ?? 0
      const pushed = data?.pushed ?? data?.push?.pushed ?? 0
      const linked = data?.linked ?? data?.push?.linked ?? 0
      const failed = data?.failed ?? data?.push?.failed ?? 0
      const parts = []
      if (pushed) parts.push(`${pushed} pushed${linked ? ` (${linked} already on Meta)` : ''}`)
      if (approved) parts.push(`${approved} approved in DB`)
      if (pending) parts.push(`${pending} pending Meta review`)
      if (failed) parts.push(`${failed} failed`)
      setMsg(parts.length ? parts.join(' · ') : (data?.message || 'Templates synced with Telnyx.'))
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
    return <div className="pageWrap indHub"><div className="card"><div className="cardBody muted">Loading…</div></div></div>
  }

  if (!item) {
    return <div className="pageWrap indHub"><div className="alert error">{error || 'Industry not found'}</div></div>
  }

  return (
    <div className="pageWrap indHub">
      <Link to="/customer-feedback/industries" className="ind-breadcrumb">← <span>Industries</span></Link>

      {error ? <div className="alert error">{error}</div> : null}
      {msg ? <div className="alert ok">{msg}</div> : null}

      <div className="ind-strip">
        <div className="ind-strip-head">
          <div className="ind-strip-head-title">Industry details</div>
          <div className="ind-strip-actions">
            <button type="button" className="btn soft bsm" disabled={busy} onClick={syncTelnyx}>Sync all templates (Telnyx)</button>
            <button type="button" className="btn primary bsm" disabled={busy} onClick={save}>Save changes</button>
          </div>
        </div>
        <div className="ind-fields">
          <div className="fg">
            <label>Name</label>
            <input className="input" value={item.name || ''} onChange={(e) => setItem((f) => ({ ...f, name: e.target.value }))} />
          </div>
          <div className="fg">
            <label>Slug</label>
            <input className="input" value={item.slug || ''} onChange={(e) => setItem((f) => ({ ...f, slug: e.target.value }))} />
          </div>
          <div className="fg">
            <label>Sort order</label>
            <input className="input" type="number" value={item.sort_order ?? 100} onChange={(e) => setItem((f) => ({ ...f, sort_order: Number(e.target.value) }))} />
          </div>
          <div className="fg">
            <label>Description</label>
            <input className="input" value={item.description || ''} onChange={(e) => setItem((f) => ({ ...f, description: e.target.value }))} placeholder="Optional…" />
          </div>
          <div className="toggle-row">
            <label className="ind-toggle">
              <input type="checkbox" checked={Boolean(item.is_active)} onChange={(e) => setItem((f) => ({ ...f, is_active: e.target.checked }))} />
              <span className="ind-toggle-track" aria-hidden />
            </label>
            <span>{item.is_active ? 'Active' : 'Inactive'}</span>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="section-title">
          <span>Survey types</span>
          <button type="button" className="btn primary bsm" onClick={addType}>+ Add type</button>
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
