import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { formatWaSurveyError } from '../lib/waSurveyFeedback'

function formatWhen(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

export default function WaSurveyIndustries() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [showInactive, setShowInactive] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [modal, setModal] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch('/admin/wa-survey/industries?include_inactive=true')
      setRows(Array.isArray(data?.industries) ? data.industries : [])
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load industries').message)
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const openCreate = () => {
    setModal({
      mode: 'create',
      name: '',
      slug: '',
      description: '',
      sort_order: 100,
      is_active: true,
    })
  }

  const openEdit = (row) => {
    setModal({
      mode: 'edit',
      id: row.id,
      name: row.name || '',
      slug: row.slug || '',
      description: row.description || '',
      sort_order: row.sort_order ?? 100,
      is_active: Boolean(row.is_active),
      is_hidden: Boolean(row.is_hidden),
      survey_type_count: row.survey_type_count || 0,
    })
  }

  const saveModal = async (e) => {
    e.preventDefault()
    if (!modal) return
    setSaving(true)
    setError('')
    setMsg('')
    const body = {
      name: modal.name.trim(),
      slug: modal.slug.trim() || undefined,
      description: modal.description.trim() || undefined,
      sort_order: Number(modal.sort_order) || 100,
      is_active: Boolean(modal.is_active),
    }
    try {
      if (modal.mode === 'create') {
        await apiFetch('/admin/wa-survey/industries', {
          method: 'POST',
          body: JSON.stringify(body),
        })
        setMsg('Industry created.')
      } else {
        await apiFetch(`/admin/wa-survey/industries/${encodeURIComponent(modal.id)}`, {
          method: 'PUT',
          body: JSON.stringify(body),
        })
        setMsg('Industry updated.')
      }
      setModal(null)
      await load()
    } catch (err) {
      setError(formatWaSurveyError(err, 'Could not save industry').message)
    } finally {
      setSaving(false)
    }
  }

  const deleteIndustry = async (row) => {
    if (row.is_hidden) return
    const typeCount = Number(row.survey_type_count || 0)
    const lines = [
      `Delete industry “${row.name}”?`,
      '',
      typeCount > 0
        ? `This permanently removes ${typeCount} survey type(s), linked WhatsApp templates, template packs, and mappings under this industry.`
        : 'This permanently removes the industry and any linked records under it.',
      'This cannot be undone.',
    ]
    if (row.is_active) {
      lines.splice(2, 0, 'Active industries are removed immediately, including linked survey types and templates.')
    }
    if (!window.confirm(lines.join('\n'))) return
    setError('')
    setMsg('')
    try {
      const result = await apiFetch(`/admin/wa-survey/industries/${encodeURIComponent(row.id)}`, { method: 'DELETE' })
      const warnings = Array.isArray(result?.warnings) ? result.warnings : []
      setRows((prev) => prev.filter((item) => item.id !== row.id))
      setMsg(
        warnings.length
          ? `Industry “${row.name}” deleted. ${warnings.join(' ')}`
          : `Industry “${row.name}” deleted permanently.`,
      )
      if (modal?.id === row.id) setModal(null)
      await load()
    } catch (err) {
      setError(formatWaSurveyError(err, 'Could not delete industry').message)
    }
  }

  const toggleActive = async (row) => {
    setError('')
    setMsg('')
    try {
      await apiFetch(`/admin/wa-survey/industries/${encodeURIComponent(row.id)}/status`, {
        method: 'POST',
        body: JSON.stringify({ is_active: !row.is_active }),
      })
      setMsg(row.is_active ? 'Industry disabled.' : 'Industry enabled.')
      await load()
    } catch (err) {
      setError(formatWaSurveyError(err, 'Could not update industry status').message)
    }
  }

  const visibleRows = showInactive ? rows : rows.filter((row) => row.is_active)

  return (
    <>
      <div className="pageTop">
        <div>
          <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
            <Link to="/settings/wa-survey" style={{ color: 'var(--grn)' }}>WA Survey</Link>
            {' '}/ Industries
          </div>
          <h1>Industries</h1>
          <p className="pageLead">
            Manage industry dimensions for survey types, template banks, and Create Survey dropdowns.
            <strong> Disable</strong> hides an industry from customers but keeps it in this list.
            <strong> Delete</strong> removes it permanently, including linked survey types and templates.
            The system industry cannot be deleted.
          </p>
        </div>
        <div className="pageTopActions">
          <button type="button" className="btn primary" onClick={openCreate}>
            <i className="ti ti-plus" /> Add industry
          </button>
        </div>
      </div>

      {error ? <div className="alert error"><strong>{error}</strong></div> : null}
      {msg ? <div className="alert ok"><strong>{msg}</strong></div> : null}

      <div className="card">
        <div className="cardHead">
          <h2>All industries</h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <label className="muted" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, margin: 0 }}>
              <input
                type="checkbox"
                checked={showInactive}
                onChange={(e) => setShowInactive(e.target.checked)}
              />
              Show inactive
            </label>
            <span className="muted">{visibleRows.length} shown · {rows.length} total</span>
          </div>
        </div>
        <div className="cardBody">
          {loading ? (
            <p className="muted">Loading…</p>
          ) : (
            <div className="tableWrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Slug</th>
                    <th>Status</th>
                    <th>Sort</th>
                    <th>Survey types</th>
                    <th>Created</th>
                    <th>Updated</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map((row) => (
                    <tr key={row.id} className={row.is_active ? '' : 'waIndustryRowMuted'}>
                      <td><strong>{row.name}</strong>{row.is_hidden ? <span className="pill muted" style={{ marginLeft: 8 }}>System</span> : null}</td>
                      <td><code>{row.slug}</code></td>
                      <td>
                        <span className={`pill ${row.is_active ? 'ok' : 'muted'}`}>
                          {row.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td>{row.sort_order}</td>
                      <td>{row.survey_type_count ?? 0}</td>
                      <td>{formatWhen(row.created_at)}</td>
                      <td>{formatWhen(row.updated_at)}</td>
                      <td style={{ whiteSpace: 'nowrap' }}>
                        <button type="button" className="btn sm" onClick={() => openEdit(row)}>Edit</button>
                        {' '}
                        <button type="button" className="btn sm" onClick={() => toggleActive(row)} disabled={row.is_hidden}>
                          {row.is_active ? 'Disable' : 'Enable'}
                        </button>
                        {!row.is_hidden ? (
                          <>
                            {' '}
                            <button
                              type="button"
                              className="btn sm danger"
                              onClick={() => void deleteIndustry(row)}
                              title="Delete industry and linked survey types/templates"
                            >
                              Delete
                            </button>
                          </>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {modal ? (
        <div
          className="modalOverlay"
          role="presentation"
          onClick={() => setModal(null)}
        >
          <form
            className="leadModal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="waIndustryModalTitle"
            onSubmit={saveModal}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="leadModalHead">
              <h3 id="waIndustryModalTitle">{modal.mode === 'create' ? 'Add industry' : 'Edit industry'}</h3>
              <button type="button" className="btn soft" onClick={() => setModal(null)} aria-label="Close">×</button>
            </div>
            <div className="leadModalBody grid2">
              <label className="field">
                <span>Name</span>
                <input className="input" value={modal.name} onChange={(e) => setModal({ ...modal, name: e.target.value })} required />
              </label>
              <label className="field">
                <span>Slug</span>
                <input
                  className="input"
                  value={modal.slug}
                  onChange={(e) => setModal({ ...modal, slug: e.target.value })}
                  placeholder="e.g. healthcare (auto-generated from name if empty)"
                />
              </label>
              <label className="field">
                <span>Sort order</span>
                <input
                  className="input"
                  type="number"
                  min={0}
                  max={9999}
                  value={modal.sort_order}
                  onChange={(e) => setModal({ ...modal, sort_order: e.target.value })}
                />
              </label>
              <label className="field">
                <span>Status</span>
                <select
                  className="input"
                  value={modal.is_active ? 'active' : 'inactive'}
                  onChange={(e) => setModal({ ...modal, is_active: e.target.value === 'active' })}
                >
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </select>
              </label>
              <label className="field" style={{ gridColumn: '1 / -1' }}>
                <span>Description</span>
                <input
                  className="input"
                  value={modal.description}
                  onChange={(e) => setModal({ ...modal, description: e.target.value })}
                  placeholder="Optional"
                />
              </label>
              {modal.mode === 'edit' ? (
                <p className="muted" style={{ gridColumn: '1 / -1', margin: 0 }}>
                  Industry ID: <code>{modal.id}</code>
                  {modal.survey_type_count ? ` · ${modal.survey_type_count} survey type(s) under this industry.` : ' · No survey types yet.'}
                </p>
              ) : null}
              {modal.mode === 'edit' && (modal.survey_type_count || 0) > 0 ? (
                <p className="muted" style={{ gridColumn: '1 / -1', margin: 0 }}>
                  {modal.survey_type_count} survey type(s) under this industry. Deleting the industry removes them and linked templates.
                </p>
              ) : null}
            </div>
            <div className="leadModalFoot" style={{ display: 'flex', gap: 8, justifyContent: 'space-between', flexWrap: 'wrap' }}>
              {modal.mode === 'edit' && !modal.is_hidden ? (
                <button
                  type="button"
                  className="btn danger"
                  onClick={() => void deleteIndustry({
                    id: modal.id,
                    name: modal.name,
                    is_active: modal.is_active,
                    is_hidden: modal.is_hidden,
                    survey_type_count: modal.survey_type_count,
                  })}
                >
                  Delete industry
                </button>
              ) : (
                <span />
              )}
              <div style={{ display: 'flex', gap: 8, marginLeft: 'auto' }}>
              <button type="button" className="btn ghost" onClick={() => setModal(null)}>Cancel</button>
              <button type="submit" className="btn primary" disabled={saving}>
                {saving ? 'Saving…' : 'Save'}
              </button>
              </div>
            </div>
          </form>
        </div>
      ) : null}
    </>
  )
}
