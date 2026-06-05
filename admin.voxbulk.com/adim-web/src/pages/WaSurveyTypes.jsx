import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { formatSyncSummary, formatWaSurveyError } from '../lib/waSurveyFeedback'

function statusTone(label) {
  if (label === 'Ready') return 'ok'
  if (label === 'Pending approval') return 'warn'
  return 'muted'
}

export default function WaSurveyTypes() {
  const [industries, setIndustries] = useState([])
  const [industryFilter, setIndustryFilter] = useState('')
  const [newIndustryId, setNewIndustryId] = useState('')
  const [types, setTypes] = useState([])
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [creating, setCreating] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [msg, setMsg] = useState('')
  const [msgDetail, setMsgDetail] = useState('')
  const [feedbackTone, setFeedbackTone] = useState('ok')
  const [error, setError] = useState('')
  const [errorDetail, setErrorDetail] = useState('')
  const [pickerEnabled, setPickerEnabled] = useState(true)
  const [pickerLoading, setPickerLoading] = useState(true)
  const [pickerSaving, setPickerSaving] = useState(false)

  const clearFeedback = () => {
    setMsg('')
    setMsgDetail('')
    setError('')
    setErrorDetail('')
    setFeedbackTone('ok')
  }

  const showSuccess = (summary) => {
    const formatted = formatSyncSummary(summary)
    setError('')
    setErrorDetail('')
    setFeedbackTone(formatted.severity === 'error' ? 'error' : formatted.severity === 'warn' ? 'warn' : 'ok')
    if (formatted.severity === 'error') {
      setError(formatted.message)
      setErrorDetail(formatted.detailText !== formatted.message ? formatted.detailText : '')
      setMsg('')
      setMsgDetail('')
      return
    }
    setMsg(formatted.message)
    setMsgDetail(formatted.detailText !== formatted.message ? formatted.detailText : '')
  }

  const showError = (err, fallback = 'Request failed') => {
    const formatted = formatWaSurveyError(err, fallback)
    setMsg('')
    setMsgDetail('')
    setFeedbackTone('error')
    setError(formatted.message)
    setErrorDetail(formatted.detailText !== formatted.message ? formatted.detailText : '')
  }

  const loadIndustries = useCallback(async () => {
    try {
      const data = await apiFetch('/admin/wa-survey/industries')
      const list = Array.isArray(data?.industries) ? data.industries : []
      setIndustries(list)
      setIndustryFilter((prev) => (prev && list.some((row) => String(row.id) === String(prev)) ? prev : ''))
      setNewIndustryId((prev) => {
        if (prev && list.some((row) => String(row.id) === String(prev))) return prev
        return String(list[0]?.id || '')
      })
    } catch (e) {
      showError(e, 'Could not load industries')
    }
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    clearFeedback()
    try {
      const qs = industryFilter ? `?industry_id=${encodeURIComponent(industryFilter)}` : ''
      const data = await apiFetch(`/admin/wa-survey/types${qs}`)
      setTypes(Array.isArray(data?.types) ? data.types : [])
    } catch (e) {
      showError(e, 'Could not load survey types')
    } finally {
      setLoading(false)
    }
  }, [industryFilter])

  const loadPickerSettings = useCallback(async () => {
    setPickerLoading(true)
    try {
      const data = await apiFetch('/admin/wa-survey/picker-settings')
      setPickerEnabled(Boolean(data?.ai_picker_enabled))
    } catch {
      setPickerEnabled(true)
    } finally {
      setPickerLoading(false)
    }
  }, [])

  const savePickerSettings = async () => {
    setPickerSaving(true)
    clearFeedback()
    try {
      await apiFetch('/admin/wa-survey/picker-settings', {
        method: 'PUT',
        body: JSON.stringify({ ai_picker_enabled: pickerEnabled }),
      })
      setFeedbackTone('ok')
      setMsg('AI picker platform setting saved.')
      setMsgDetail('Orders still need flow_engine=graph and per-order ai_picker_enabled. Env WA_SURVEY_AI_PICKER_ENABLED can override off.')
    } catch (e) {
      showError(e, 'Could not save picker setting')
    } finally {
      setPickerSaving(false)
    }
  }

  useEffect(() => {
    loadIndustries()
    loadPickerSettings()
  }, [loadIndustries, loadPickerSettings])

  useEffect(() => {
    const refreshIndustries = () => {
      if (document.visibilityState === 'visible') void loadIndustries()
    }
    window.addEventListener('focus', refreshIndustries)
    document.addEventListener('visibilitychange', refreshIndustries)
    return () => {
      window.removeEventListener('focus', refreshIndustries)
      document.removeEventListener('visibilitychange', refreshIndustries)
    }
  }, [loadIndustries])

  useEffect(() => {
    load()
  }, [load])

  const syncAll = async () => {
    setSyncing(true)
    clearFeedback()
    try {
      const summary = await apiFetch('/admin/wa-survey/sync', { method: 'POST', body: '{}' })
      showSuccess(summary)
      await load()
    } catch (e) {
      showError(e, 'Sync from Telnyx failed')
    } finally {
      setSyncing(false)
    }
  }

  const createType = async (e) => {
    e.preventDefault()
    if (!newName.trim()) return
    setCreating(true)
    clearFeedback()
    try {
      if (!newIndustryId) {
        showError(new Error('Select an industry first'), 'Industry is required')
        setCreating(false)
        return
      }
      await apiFetch('/admin/wa-survey/types', {
        method: 'POST',
        body: JSON.stringify({
          name: newName.trim(),
          description: newDescription.trim() || undefined,
          industry_id: newIndustryId,
        }),
      })
      setShowCreate(false)
      setNewName('')
      setNewDescription('')
      setFeedbackTone('ok')
      setMsg('Survey type created. Add a standard template draft on the edit page, then push to Telnyx.')
      setMsgDetail('')
      await load()
    } catch (err) {
      showError(err, 'Could not create survey type')
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
          <Link className="btn" to="/settings/wa-survey/industries">
            <i className="ti ti-building" /> Manage industries
          </Link>
          <Link className="btn" to="/settings/wa-survey/simulator">
            <i className="ti ti-flask" /> Flow simulator
          </Link>
          <button type="button" className="btn" onClick={() => setShowCreate((v) => !v)}>
            <i className="ti ti-plus" /> Create survey type
          </button>
          <button type="button" className="btn" onClick={syncAll} disabled={syncing} title="Pull WhatsApp templates from Telnyx whose names contain “survey”, update approval status, and link them to survey types when the name matches.">
            <i className="ti ti-refresh" /> {syncing ? 'Syncing…' : 'Sync from Telnyx'}
          </button>
        </div>
      </div>

      <section className="card" style={{ marginBottom: 16 }}>
        <div className="cardHead"><h2>Launch &amp; safety</h2></div>
        <div className="cardBody">
          <p className="muted" style={{ marginBottom: 12 }}>
            Linear flow remains the safe default. Graph + AI picker only run when explicitly enabled on an order.
          </p>
          <label className="checkRow" style={{ marginBottom: 12 }}>
            <input
              type="checkbox"
              checked={pickerEnabled}
              disabled={pickerLoading || pickerSaving}
              onChange={(e) => setPickerEnabled(e.target.checked)}
            />
            Platform AI picker enabled (kill switch)
          </label>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button type="button" className="btn sm primary" onClick={savePickerSettings} disabled={pickerSaving || pickerLoading}>
              {pickerSaving ? 'Saving…' : 'Save picker setting'}
            </button>
            <Link className="btn sm" to="/settings/wa-survey/simulator">
              Open flow simulator (port 5174)
            </Link>
          </div>
        </div>
      </section>

      <div className="note" style={{ marginBottom: 16 }}>
        <strong>Sync from Telnyx</strong> fetches remote WhatsApp templates from Telnyx/Meta, updates approval status locally, and imports templates whose names contain “survey”. It does not push your drafts — use <em>Push to Telnyx</em> on each template after editing.
      </div>

      {showCreate ? (
        <form className="card" style={{ marginBottom: 16 }} onSubmit={createType}>
          <div className="cardHead"><h2>New survey type</h2></div>
          <div className="cardBody grid2">
            <label className="field">
              <span>Industry</span>
              <select className="input" value={newIndustryId} onChange={(e) => setNewIndustryId(e.target.value)} required>
                <option value="">Select industry…</option>
                {industries.map((ind) => (
                  <option key={ind.id} value={ind.id}>{ind.name}</option>
                ))}
              </select>
            </label>
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

      {error ? (
        <div className="alert error">
          <strong>{error}</strong>
          {errorDetail ? <pre className="waSurveyFeedbackDetail">{errorDetail}</pre> : null}
        </div>
      ) : null}
      {msg ? (
        <div className={`alert ${feedbackTone === 'warn' ? 'warn' : 'ok'}`}>
          <strong>{msg}</strong>
          {msgDetail ? <pre className="waSurveyFeedbackDetail">{msgDetail}</pre> : null}
        </div>
      ) : null}

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="cardBody" style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <label className="field" style={{ margin: 0, minWidth: 220 }}>
            <span>Filter by industry</span>
            <select className="input" value={industryFilter} onChange={(e) => setIndustryFilter(e.target.value)}>
              <option value="">All industries</option>
              {industries.map((ind) => (
                <option key={ind.id} value={ind.id}>{ind.name}</option>
              ))}
            </select>
          </label>
        </div>
      </div>

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
                    <th>Industry</th>
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
                      <td>{row.industry_name || row.industry_slug || '—'}</td>
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
