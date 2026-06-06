import React, { useCallback, useEffect, useState } from 'react'
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

export default function WaSurveyIndustrySection({ onIndustriesChange }) {
  const [kpis, setKpis] = useState(null)
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [showInactive, setShowInactive] = useState(true)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [modal, setModal] = useState(null)
  const [deleteModal, setDeleteModal] = useState(null)
  const [deleteBusy, setDeleteBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch('/admin/wa-survey/overview')
      setKpis(data?.kpis || null)
      const list = Array.isArray(data?.industries) ? data.industries : []
      setRows(list)
      onIndustriesChange?.(list.filter((row) => row.is_active && !row.is_hidden))
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load WA Survey overview').message)
      setRows([])
      setKpis(null)
    } finally {
      setLoading(false)
    }
  }, [onIndustriesChange])

  useEffect(() => {
    void load()
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
      template_count: row.template_count || 0,
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

  const confirmDelete = (row) => {
    setDeleteModal(row)
  }

  const runDelete = async () => {
    const row = deleteModal
    if (!row) return
    setDeleteBusy(true)
    setError('')
    setMsg('')
    try {
      const result = await apiFetch(`/admin/wa-survey/industries/${encodeURIComponent(row.id)}`, {
        method: 'DELETE',
      })
      const warnings = Array.isArray(result?.warnings) ? result.warnings : []
      const telnyxNote =
        Number(result?.deleted_templates || 0) > 0
          ? ` Removed ${result.deleted_templates} template(s) from DB`
          : ''
      setMsg(
        warnings.length
          ? `Industry “${row.name}” deleted.${telnyxNote} Warnings: ${warnings.join(' ')}`
          : `Industry “${row.name}” deleted permanently.${telnyxNote}`,
      )
      setDeleteModal(null)
      if (modal?.id === row.id) setModal(null)
      await load()
    } catch (err) {
      setError(formatWaSurveyError(err, 'Could not delete industry').message)
    } finally {
      setDeleteBusy(false)
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
      <div className="agentsKpis waSurveyKpis">
        <div className="agentsKpi">
          <div className="agentsKpiLabel">Total industries</div>
          <div className="agentsKpiValue">{loading ? '…' : kpis?.total_industries ?? 0}</div>
        </div>
        <div className="agentsKpi">
          <div className="agentsKpiLabel">Total templates</div>
          <div className="agentsKpiValue">{loading ? '…' : kpis?.total_templates ?? 0}</div>
        </div>
        <div className="agentsKpi">
          <div className="agentsKpiLabel">Approved templates</div>
          <div className="agentsKpiValue waSurveyApprovedCount">
            {loading ? '…' : kpis?.approved_templates ?? 0}
          </div>
        </div>
        <div className="agentsKpi">
          <div className="agentsKpiLabel">Pending / not approved</div>
          <div className="agentsKpiValue">{loading ? '…' : kpis?.pending_templates ?? 0}</div>
        </div>
      </div>

      {error ? <div className="alert error" style={{ marginBottom: 16 }}><strong>{error}</strong></div> : null}
      {msg ? <div className="alert ok" style={{ marginBottom: 16 }}><strong>{msg}</strong></div> : null}

      <section className="card" id="wa-survey-industries" style={{ marginBottom: 16 }}>
        <div className="cardHead">
          <h2>Industries</h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <label className="muted" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, margin: 0 }}>
              <input
                type="checkbox"
                checked={showInactive}
                onChange={(e) => setShowInactive(e.target.checked)}
              />
              Show inactive
            </label>
            <span className="muted">{visibleRows.length} shown · {rows.length} total</span>
            <button type="button" className="btn sm primary" onClick={openCreate}>
              <i className="ti ti-plus" /> Add industry
            </button>
          </div>
        </div>
        <div className="cardBody">
          {loading ? (
            <p className="muted">Loading overview…</p>
          ) : (
            <div className="tableWrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Industry</th>
                    <th>Slug</th>
                    <th>Status</th>
                    <th>Survey types</th>
                    <th>Templates</th>
                    <th>Approved</th>
                    <th>Pending</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.length ? visibleRows.map((row) => (
                    <tr key={row.id} className={row.is_active ? '' : 'waIndustryRowMuted'}>
                      <td>
                        <strong>{row.name}</strong>
                        {row.is_hidden ? <span className="pill muted" style={{ marginLeft: 8 }}>System</span> : null}
                        {!row.is_active ? <span className="pill muted" style={{ marginLeft: 8 }}>Disabled</span> : null}
                        {row.template_count === 0 && row.survey_type_count === 0 && !row.is_hidden ? (
                          <span className="pill warn" style={{ marginLeft: 8 }}>Empty</span>
                        ) : null}
                      </td>
                      <td><code>{row.slug}</code></td>
                      <td>
                        <span className={`pill ${row.is_active ? 'ok' : 'muted'}`}>
                          {row.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td>{row.survey_type_count ?? 0}</td>
                      <td>{row.template_count ?? 0}</td>
                      <td><span className="waSurveyApprovedCount">{row.approved_template_count ?? 0}</span></td>
                      <td>{row.pending_template_count ?? 0}</td>
                      <td style={{ whiteSpace: 'nowrap' }}>
                        <button type="button" className="btn sm" onClick={() => openEdit(row)}>Edit</button>
                        {' '}
                        <button type="button" className="btn sm" onClick={() => void toggleActive(row)} disabled={row.is_hidden}>
                          {row.is_active ? 'Disable' : 'Enable'}
                        </button>
                        {!row.is_hidden ? (
                          <>
                            {' '}
                            <button
                              type="button"
                              className="btn sm danger"
                              onClick={() => confirmDelete(row)}
                            >
                              Delete
                            </button>
                          </>
                        ) : null}
                      </td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan={8} className="muted">No industries match this filter.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {modal ? (
        <div className="modalOverlay" role="presentation" onClick={() => setModal(null)}>
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
                  placeholder="Auto-generated from name if empty"
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
                  disabled={modal.is_hidden}
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
                  {modal.survey_type_count ?? 0} survey type(s) · {modal.template_count ?? 0} template(s) linked.
                </p>
              ) : null}
            </div>
            <div className="leadModalFoot" style={{ display: 'flex', gap: 8, justifyContent: 'space-between', flexWrap: 'wrap' }}>
              {modal.mode === 'edit' && !modal.is_hidden ? (
                <button type="button" className="btn danger" onClick={() => confirmDelete({
                  id: modal.id,
                  name: modal.name,
                  survey_type_count: modal.survey_type_count,
                  template_count: modal.template_count,
                  is_hidden: modal.is_hidden,
                })}
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

      {deleteModal ? (
        <div className="modalOverlay" role="presentation" onClick={() => !deleteBusy && setDeleteModal(null)}>
          <div
            className="leadModal"
            role="dialog"
            aria-modal="true"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="leadModalHead">
              <h3>Delete industry?</h3>
              <button type="button" className="btn soft" onClick={() => setDeleteModal(null)} aria-label="Close">×</button>
            </div>
            <div className="leadModalBody">
              <p style={{ marginTop: 0 }}>
                Delete <strong>{deleteModal.name}</strong> permanently?
              </p>
              <ul className="muted" style={{ marginBottom: 0, paddingLeft: 18 }}>
                <li>{deleteModal.survey_type_count ?? 0} survey type(s) will be removed</li>
                <li>{deleteModal.template_count ?? 0} WhatsApp template(s) will be removed from the database</li>
                <li>Synced templates will also be deleted from Telnyx where possible</li>
                <li>If Telnyx delete fails for any template, you will see a warning — local rows are still removed</li>
              </ul>
            </div>
            <div className="leadModalFoot" style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button type="button" className="btn ghost" onClick={() => setDeleteModal(null)} disabled={deleteBusy}>
                Cancel
              </button>
              <button type="button" className="btn danger" onClick={() => void runDelete()} disabled={deleteBusy}>
                {deleteBusy ? 'Deleting…' : 'Delete permanently'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}
