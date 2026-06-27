import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { formatWaSurveyError } from '../lib/waSurveyFeedback'
import '../styles/admin-industries.css'

export default function WaSurveyIndustrySection() {
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
  const [duplicateModal, setDuplicateModal] = useState(null)
  const [orgs, setOrgs] = useState([])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const data = await apiFetch('/admin/organisations?limit=500')
        if (!cancelled) setOrgs(Array.isArray(data) ? data : [])
      } catch {
        if (!cancelled) setOrgs([])
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch('/admin/wa-survey/overview')
      setKpis(data?.kpis || null)
      const list = Array.isArray(data?.industries) ? data.industries : []
      setRows(list)
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load WA Survey overview').message)
      setRows([])
      setKpis(null)
    } finally {
      setLoading(false)
    }
  }, [])

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
      visibility_mode: 'all',
      selectedOrgIds: [],
    })
  }

  const toggleCreateOrg = (orgId) => {
    setModal((prev) => {
      if (!prev) return prev
      const set = new Set(prev.selectedOrgIds || [])
      if (set.has(orgId)) set.delete(orgId)
      else set.add(orgId)
      return { ...prev, selectedOrgIds: [...set] }
    })
  }

  const saveModal = async (e) => {
    e.preventDefault()
    if (!modal) return
    setSaving(true)
    setError('')
    setMsg('')
    const orgIds = modal.visibility_mode === 'restricted' ? (modal.selectedOrgIds || []) : []
    const body = {
      name: modal.name.trim(),
      slug: modal.slug.trim() || undefined,
      description: modal.description.trim() || undefined,
      sort_order: Number(modal.sort_order) || 100,
      is_active: Boolean(modal.is_active),
      visibility_mode: modal.visibility_mode === 'restricted' ? 'restricted' : 'all',
      org_ids: orgIds,
    }
    try {
      await apiFetch('/admin/wa-survey/industries', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      setMsg('Industry created.')
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
      await load()
    } catch (err) {
      setError(formatWaSurveyError(err, 'Could not delete industry').message)
    } finally {
      setDeleteBusy(false)
    }
  }

  const openDuplicate = (row) => {
    setDuplicateModal({
      source: row,
      name: `${row.name} (copy)`,
      slug: `${row.slug}_copy`,
      org_ids: '',
    })
  }

  const saveDuplicate = async (e) => {
    e.preventDefault()
    if (!duplicateModal?.source) return
    setSaving(true)
    setError('')
    setMsg('')
    const orgIds = String(duplicateModal.org_ids || '')
      .split(/[\n,;]+/)
      .map((s) => s.trim())
      .filter(Boolean)
    try {
      await apiFetch(`/admin/wa-survey/industries/${encodeURIComponent(duplicateModal.source.id)}/duplicate`, {
        method: 'POST',
        body: JSON.stringify({
          name: duplicateModal.name.trim(),
          slug: duplicateModal.slug.trim() || undefined,
          org_ids: orgIds,
          visibility_mode: orgIds.length ? 'restricted' : 'all',
        }),
      })
      setMsg(`Industry duplicated as “${duplicateModal.name.trim()}” (inactive until you enable it).`)
      setDuplicateModal(null)
      await load()
    } catch (err) {
      setError(formatWaSurveyError(err, 'Could not duplicate industry').message)
    } finally {
      setSaving(false)
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
    <div className="indHub">
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
                        <Link className="btn sm" to={`/settings/wa-survey/industries/${row.id}`}>Edit</Link>
                        {' '}
                        <button type="button" className="btn sm" onClick={() => void toggleActive(row)} disabled={row.is_hidden}>
                          {row.is_active ? 'Disable' : 'Enable'}
                        </button>
                        {!row.is_hidden ? (
                          <>
                            {' '}
                            <button type="button" className="btn sm" onClick={() => openDuplicate(row)}>
                              Duplicate
                            </button>
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
              <h3 id="waIndustryModalTitle">Add industry</h3>
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
              <div className="field" style={{ gridColumn: '1 / -1' }}>
                <span>Customer visibility</span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 8 }}>
                  <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <input
                      type="radio"
                      name="create_visibility"
                      checked={modal.visibility_mode !== 'restricted'}
                      onChange={() => setModal({ ...modal, visibility_mode: 'all', selectedOrgIds: [] })}
                    />
                    <span>Visible to all customers (default)</span>
                  </label>
                  <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <input
                      type="radio"
                      name="create_visibility"
                      checked={modal.visibility_mode === 'restricted'}
                      onChange={() => setModal({ ...modal, visibility_mode: 'restricted' })}
                    />
                    <span>Visible to selected customers only</span>
                  </label>
                </div>
              </div>
              {modal.visibility_mode === 'restricted' ? (
                <div className="field" style={{ gridColumn: '1 / -1', maxHeight: 220, overflow: 'auto', border: '1px solid var(--line)', borderRadius: 8, padding: 12 }}>
                  <span>Select customers</span>
                  {orgs.length ? orgs.map((org) => (
                    <label key={org.id} style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 8, fontSize: 13 }}>
                      <input
                        type="checkbox"
                        checked={(modal.selectedOrgIds || []).includes(org.id)}
                        onChange={() => toggleCreateOrg(org.id)}
                      />
                      <span>{org.name || org.id}</span>
                    </label>
                  )) : (
                    <p className="muted" style={{ margin: '8px 0 0' }}>No organisations loaded.</p>
                  )}
                </div>
              ) : null}
            </div>
            <div className="leadModalFoot" style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button type="button" className="btn ghost" onClick={() => setModal(null)}>Cancel</button>
              <button type="submit" className="btn primary" disabled={saving}>
                {saving ? 'Saving…' : 'Create industry'}
              </button>
            </div>
          </form>
        </div>
      ) : null}

      {duplicateModal ? (
        <div className="modalOverlay" role="presentation" onClick={() => !saving && setDuplicateModal(null)}>
          <form
            className="leadModal"
            role="dialog"
            aria-modal="true"
            onSubmit={saveDuplicate}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="leadModalHead">
              <h3>Duplicate industry</h3>
              <button type="button" className="btn soft" onClick={() => setDuplicateModal(null)} aria-label="Close">×</button>
            </div>
            <div className="leadModalBody grid2">
              <p className="muted" style={{ gridColumn: '1 / -1', marginTop: 0 }}>
                Copies all survey types and templates from <strong>{duplicateModal.source?.name}</strong>.
                The copy is <strong>inactive</strong> until you enable it. Push templates to Telnyx after activation.
              </p>
              <label className="field">
                <span>New name</span>
                <input className="input" value={duplicateModal.name} onChange={(e) => setDuplicateModal({ ...duplicateModal, name: e.target.value })} required />
              </label>
              <label className="field">
                <span>Slug</span>
                <input className="input" value={duplicateModal.slug} onChange={(e) => setDuplicateModal({ ...duplicateModal, slug: e.target.value })} />
              </label>
              <label className="field" style={{ gridColumn: '1 / -1' }}>
                <span>Organisation IDs (optional — comma or newline separated)</span>
                <textarea
                  className="input"
                  rows={3}
                  value={duplicateModal.org_ids}
                  onChange={(e) => setDuplicateModal({ ...duplicateModal, org_ids: e.target.value })}
                  placeholder="Leave empty = all customers when active"
                />
              </label>
            </div>
            <div className="leadModalFoot" style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button type="button" className="btn ghost" onClick={() => setDuplicateModal(null)} disabled={saving}>Cancel</button>
              <button type="submit" className="btn primary" disabled={saving}>{saving ? 'Duplicating…' : 'Duplicate industry'}</button>
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
    </div>
  )
}
