import React, { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { apiFetch } from '../../lib/api'

const DEFAULT_BUTTONS = [
  { id: 'great', label: 'Great' },
  { id: 'ok', label: 'OK' },
  { id: 'poor', label: 'Poor' },
]

function syncPillClass(status) {
  const s = String(status || 'draft').toLowerCase()
  if (['approved', 'synced', 'live'].includes(s)) return 'leadPill leadPillAdvance'
  if (s === 'submitted') return 'leadPill leadPillNeutral'
  return 'leadPill leadPillNeutral'
}

export default function FeedbackSurveyTypeEdit() {
  const { typeId } = useParams()
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [item, setItem] = useState(null)
  const [editing, setEditing] = useState(null)

  const load = useCallback(async () => {
    setError('')
    setLoading(true)
    try {
      const data = await apiFetch(`/admin/customer-feedback/survey-types/${typeId}`)
      setItem(data?.item || null)
    } catch (e) {
      setError(e?.message || 'Could not load survey type')
    } finally {
      setLoading(false)
    }
  }, [typeId])

  useEffect(() => {
    load()
  }, [load])

  const saveSurveyType = async () => {
    if (!item) return
    setBusy('save-type')
    setError('')
    try {
      await apiFetch('/admin/customer-feedback/survey-types', {
        method: 'POST',
        body: JSON.stringify({
          id: item.id,
          industry_id: item.industry_id,
          name: item.name,
          slug: item.slug,
          description: item.description,
          sort_order: item.sort_order,
          is_active: item.is_active,
        }),
      })
      setMsg('Survey type saved.')
      await load()
    } catch (e) {
      setError(e?.message || 'Could not save survey type')
    } finally {
      setBusy('')
    }
  }

  const syncTelnyx = async () => {
    setBusy('sync')
    setError('')
    try {
      const data = await apiFetch(`/admin/customer-feedback/survey-types/${typeId}/sync-telnyx`, { method: 'POST' })
      setMsg(`Submitted ${data?.submitted || 0} template(s) to Telnyx.`)
      await load()
    } catch (e) {
      setError(e?.message || 'Sync failed')
    } finally {
      setBusy('')
    }
  }

  const openTemplate = (tpl) => {
    setEditing({
      ...tpl,
      buttons: Array.isArray(tpl.buttons) && tpl.buttons.length ? tpl.buttons : DEFAULT_BUTTONS,
    })
  }

  const saveTemplate = async () => {
    if (!editing) return
    setBusy(`tpl-${editing.id || 'new'}`)
    setError('')
    try {
      await apiFetch('/admin/customer-feedback/wa-templates', {
        method: 'POST',
        body: JSON.stringify({
          id: editing.id,
          industry_id: item.industry_id,
          survey_type_id: item.id,
          step_order: editing.step_order,
          template_key: editing.template_key,
          body_text: editing.body_text,
          step_role: editing.step_role,
          language: editing.language,
          meta_category: editing.meta_category,
          buttons: editing.buttons,
          is_active: editing.is_active,
        }),
      })
      setMsg('Template saved.')
      setEditing(null)
      await load()
    } catch (e) {
      setError(e?.message || 'Could not save template')
    } finally {
      setBusy('')
    }
  }

  const createTemplate = async () => {
    setBusy('create')
    setError('')
    try {
      const nextOrder = (item?.templates?.length || 0) + 1
      const data = await apiFetch('/admin/customer-feedback/wa-templates', {
        method: 'POST',
        body: JSON.stringify({
          industry_id: item.industry_id,
          survey_type_id: item.id,
          step_order: nextOrder,
          template_key: 'rating',
          step_role: 'rating',
          body_text: `How was your experience with ${item.name}?`,
          language: 'en_GB',
          meta_category: 'utility',
          buttons: DEFAULT_BUTTONS,
          is_active: true,
        }),
      })
      openTemplate(data?.item || {})
      await load()
    } catch (e) {
      setError(e?.message || 'Could not create template')
    } finally {
      setBusy('')
    }
  }

  if (loading) {
    return <div className="pageWrap"><div className="card"><div className="cardBody muted">Loading…</div></div></div>
  }

  if (!item) {
    return <div className="pageWrap"><div className="alert error">{error || 'Survey type not found'}</div></div>
  }

  return (
    <div className="pageWrap">
      <div className="breadcrumb muted" style={{ marginBottom: 12 }}>
        <Link to="/customer-feedback/industries">Industries</Link>
        {' / '}
        <Link to={`/customer-feedback/industries/${item.industry_id}`}>{item.industry_name || 'Industry'}</Link>
        {' / '}
        {item.name}
      </div>

      <div className="pageHead">
        <div>
          <h1>{item.name}</h1>
          <p className="muted">
            English topic template for Customer Feedback WhatsApp surveys.
            {' '}
            {item.template_count ?? 0} template(s) · {item.approved_count ?? 0} approved
          </p>
        </div>
        <div className="pageHeadActions">
          <button type="button" className="btn soft bsm" disabled={Boolean(busy)} onClick={syncTelnyx}>
            {busy === 'sync' ? 'Syncing…' : 'Sync to Telnyx'}
          </button>
          <button type="button" className="btn primary bsm" disabled={busy === 'save-type'} onClick={saveSurveyType}>
            Save type
          </button>
        </div>
      </div>

      {error ? <div className="alert error">{error}</div> : null}
      {msg ? <div className="alert ok">{msg}</div> : null}

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="cardHead"><h3>Survey type details</h3></div>
        <div className="cardBody runningSurveyEditGrid">
          <label>Name<input className="input" value={item.name || ''} onChange={(e) => setItem((f) => ({ ...f, name: e.target.value }))} /></label>
          <label>Slug<input className="input" value={item.slug || ''} onChange={(e) => setItem((f) => ({ ...f, slug: e.target.value }))} /></label>
          <label>Sort order<input className="input" type="number" value={item.sort_order ?? 100} onChange={(e) => setItem((f) => ({ ...f, sort_order: Number(e.target.value) }))} /></label>
          <label>Description<textarea className="input" rows={2} value={item.description || ''} onChange={(e) => setItem((f) => ({ ...f, description: e.target.value }))} /></label>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input type="checkbox" checked={Boolean(item.is_active)} onChange={(e) => setItem((f) => ({ ...f, is_active: e.target.checked }))} />
            Active
          </label>
        </div>
      </div>

      <div className="card">
        <div className="cardHead">
          <h3>WhatsApp templates</h3>
          <button type="button" className="btn soft bsm" disabled={Boolean(busy)} onClick={createTemplate}>
            Add English template
          </button>
        </div>
        <div className="tableWrap">
          <table className="table runningSurveyTable">
            <thead>
              <tr>
                <th>Key</th>
                <th>Role</th>
                <th>Language</th>
                <th>Category</th>
                <th>Telnyx</th>
                <th>Active</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(item.templates || []).map((tpl) => (
                <tr key={tpl.id}>
                  <td><strong>{tpl.template_key}</strong></td>
                  <td>{tpl.step_role || '—'}</td>
                  <td>{tpl.language}</td>
                  <td>{tpl.meta_category}</td>
                  <td><span className={syncPillClass(tpl.telnyx_sync_status)}>{tpl.telnyx_sync_status || 'draft'}</span></td>
                  <td>{tpl.is_active ? 'Yes' : 'No'}</td>
                  <td>
                    <button type="button" className="btn soft bsm" onClick={() => openTemplate(tpl)}>Edit</button>
                  </td>
                </tr>
              ))}
              {!item.templates?.length ? (
                <tr><td colSpan={7} className="muted">No templates yet. Import from MD on Industries or add one here.</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      {editing ? (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="cardHead">
            <h3>Edit template — {editing.template_key}</h3>
            <button type="button" className="btn soft bsm" onClick={() => setEditing(null)}>Close</button>
          </div>
          <div className="cardBody runningSurveyEditGrid">
            <label>Template key<input className="input" value={editing.template_key || ''} onChange={(e) => setEditing((f) => ({ ...f, template_key: e.target.value }))} /></label>
            <label>Step role<input className="input" value={editing.step_role || ''} onChange={(e) => setEditing((f) => ({ ...f, step_role: e.target.value }))} /></label>
            <label>Step order<input className="input" type="number" value={editing.step_order ?? 1} onChange={(e) => setEditing((f) => ({ ...f, step_order: Number(e.target.value) }))} /></label>
            <label>Language<input className="input" value={editing.language || 'en_GB'} onChange={(e) => setEditing((f) => ({ ...f, language: e.target.value }))} /></label>
            <label>Meta category
              <select className="input" value={editing.meta_category || 'utility'} onChange={(e) => setEditing((f) => ({ ...f, meta_category: e.target.value }))}>
                <option value="utility">Utility</option>
                <option value="marketing">Marketing</option>
              </select>
            </label>
            <label style={{ gridColumn: '1 / -1' }}>Body text
              <textarea className="input" rows={4} value={editing.body_text || ''} onChange={(e) => setEditing((f) => ({ ...f, body_text: e.target.value }))} />
            </label>
            <label style={{ gridColumn: '1 / -1' }}>Quick-reply buttons (JSON)
              <textarea
                className="input"
                rows={4}
                value={JSON.stringify(editing.buttons || [], null, 2)}
                onChange={(e) => {
                  try {
                    const parsed = JSON.parse(e.target.value)
                    if (Array.isArray(parsed)) setEditing((f) => ({ ...f, buttons: parsed }))
                  } catch {
                    /* allow invalid JSON while typing */
                  }
                }}
              />
            </label>
            <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input type="checkbox" checked={Boolean(editing.is_active)} onChange={(e) => setEditing((f) => ({ ...f, is_active: e.target.checked }))} />
              Active
            </label>
            <div style={{ gridColumn: '1 / -1' }}>
              <button type="button" className="btn primary bsm" disabled={Boolean(busy)} onClick={saveTemplate}>
                {busy.startsWith('tpl-') ? 'Saving…' : 'Save template'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
