import React, { useCallback, useEffect, useMemo, useState } from 'react'

import { Link, useNavigate, useParams } from 'react-router-dom'

import { apiFetch } from '../lib/api'

import { formatWaSurveyError } from '../lib/waSurveyFeedback'
import { Switch } from '@/components/ui/Switch'



function statusTone(label) {

  if (label === 'Ready') return 'ok'

  if (label === 'Pending approval') return 'warn'

  return 'muted'

}



function formatWhen(iso) {

  if (!iso) return '—'

  try {

    return new Date(iso).toLocaleString()

  } catch {

    return iso

  }

}



export default function WaSurveyIndustryEdit() {

  const { industryId } = useParams()

  const navigate = useNavigate()

  const [loading, setLoading] = useState(true)

  const [saving, setSaving] = useState(false)

  const [error, setError] = useState('')

  const [msg, setMsg] = useState('')

  const [industry, setIndustry] = useState(null)

  const [surveyTypes, setSurveyTypes] = useState([])

  const [typesLoading, setTypesLoading] = useState(false)

  const [newTypeName, setNewTypeName] = useState('')

  const [newTypeDescription, setNewTypeDescription] = useState('')

  const [creatingType, setCreatingType] = useState(false)

  const [deleteModal, setDeleteModal] = useState(false)

  const [deleteBusy, setDeleteBusy] = useState(false)

  const [selectedTypeIds, setSelectedTypeIds] = useState(() => new Set())

  const [typeDeleteModal, setTypeDeleteModal] = useState(null)

  const [typeDeleteBusy, setTypeDeleteBusy] = useState(false)

  const [syncBusy, setSyncBusy] = useState(false)
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

  const loadSurveyTypes = useCallback(async (id) => {

    setTypesLoading(true)

    try {

      const data = await apiFetch(`/admin/wa-survey/types?industry_id=${encodeURIComponent(id)}`)

      setSurveyTypes(Array.isArray(data?.types) ? data.types : [])

      setSelectedTypeIds(new Set())

    } catch (e) {

      setError(formatWaSurveyError(e, 'Could not load survey types').message)

      setSurveyTypes([])

      setSelectedTypeIds(new Set())

    } finally {

      setTypesLoading(false)

    }

  }, [])



  const load = useCallback(async () => {

    setLoading(true)

    setError('')

    try {

      const data = await apiFetch(`/admin/wa-survey/industries/${encodeURIComponent(industryId)}`)

      const row = data?.industry

      if (!row) throw new Error('Industry not found')

      setIndustry({

        id: row.id,

        name: row.name || '',

        slug: row.slug || '',

        description: row.description || '',

        sort_order: row.sort_order ?? 100,

        is_active: Boolean(row.is_active),

        is_hidden: Boolean(row.is_hidden),

        visibility_mode: row.visibility_mode === 'restricted' ? 'restricted' : 'all',

        selectedOrgIds: Array.isArray(row.org_ids) ? row.org_ids : [],

        survey_type_count: row.survey_type_count || 0,

        template_count: row.template_count || 0,

      })

      await loadSurveyTypes(row.id)

    } catch (e) {

      setError(formatWaSurveyError(e, 'Could not load industry').message)

      setIndustry(null)

    } finally {

      setLoading(false)

    }

  }, [industryId, loadSurveyTypes])



  useEffect(() => {

    void load()

  }, [load])



  const selectableTypeIds = useMemo(

    () => surveyTypes.map((type) => String(type.id)),

    [surveyTypes],

  )



  const allSelected = selectableTypeIds.length > 0 && selectableTypeIds.every((id) => selectedTypeIds.has(id))

  const someSelected = selectedTypeIds.size > 0



  const toggleTypeSelection = (typeId) => {

    const key = String(typeId)

    setSelectedTypeIds((prev) => {

      const next = new Set(prev)

      if (next.has(key)) next.delete(key)

      else next.add(key)

      return next

    })

  }



  const toggleSelectAll = () => {

    if (allSelected) {

      setSelectedTypeIds(new Set())

      return

    }

    setSelectedTypeIds(new Set(selectableTypeIds))

  }



  const saveIndustry = async (e) => {

    e.preventDefault()

    if (!industry) return

    setSaving(true)

    setError('')

    setMsg('')

    try {

      const orgIds = industry.visibility_mode === 'restricted' ? (industry.selectedOrgIds || []) : []

      await apiFetch(`/admin/wa-survey/industries/${encodeURIComponent(industry.id)}`, {

        method: 'PUT',

        body: JSON.stringify({

          name: industry.name.trim(),

          slug: industry.slug.trim() || undefined,

          description: industry.description.trim() || undefined,

          sort_order: Number(industry.sort_order) || 100,

          is_active: Boolean(industry.is_active),

          visibility_mode: industry.visibility_mode === 'restricted' ? 'restricted' : 'all',

          org_ids: orgIds,

        }),

      })

      setMsg('Industry updated.')

      await load()

    } catch (err) {

      setError(formatWaSurveyError(err, 'Could not save industry').message)

    } finally {

      setSaving(false)

    }

  }



  const createSurveyType = async (e) => {

    e.preventDefault()

    if (!industry?.id || !newTypeName.trim()) return

    setCreatingType(true)

    setError('')

    try {

      await apiFetch('/admin/wa-survey/types', {

        method: 'POST',

        body: JSON.stringify({

          name: newTypeName.trim(),

          description: newTypeDescription.trim() || undefined,

          industry_id: industry.id,

        }),

      })

      setNewTypeName('')

      setNewTypeDescription('')

      setMsg('Survey type created.')

      await loadSurveyTypes(industry.id)

    } catch (err) {

      setError(formatWaSurveyError(err, 'Could not create survey type').message)

    } finally {

      setCreatingType(false)

    }

  }



  const deleteSurveyTypes = async (typeIds) => {

    if (!industry?.id || !typeIds.length) return

    setTypeDeleteBusy(true)

    setError('')

    try {

      const result = typeIds.length === 1

        ? await apiFetch(`/admin/wa-survey/types/${encodeURIComponent(typeIds[0])}`, { method: 'DELETE' })

        : await apiFetch('/admin/wa-survey/types/bulk-delete', {

          method: 'POST',

          body: JSON.stringify({ type_ids: typeIds }),

        })



      const warnings = Array.isArray(result?.warnings) ? result.warnings : []

      const deletedCount = typeIds.length === 1 ? 1 : Number(result?.deleted_count || typeIds.length)

      setMsg(

        warnings.length

          ? `Deleted ${deletedCount} survey type(s). Warnings: ${warnings.join(' ')}`

          : `Deleted ${deletedCount} survey type(s) and linked Telnyx templates.`,

      )

      setTypeDeleteModal(null)

      setSelectedTypeIds(new Set())

      await load()

    } catch (err) {

      setError(formatWaSurveyError(err, 'Could not delete survey type(s)').message)

      setTypeDeleteModal(null)

    } finally {

      setTypeDeleteBusy(false)

    }

  }



  const pushAllIndustryToTelnyx = async () => {

    if (!industry?.id) return

    setSyncBusy(true)

    setError('')

    setMsg('')

    const PUSH_BATCH = 5

    const acc = { pushed: 0, error_count: 0, errors: [] }

    try {

      let offset = 0

      for (;;) {

        const summary = await apiFetch(

          `/admin/wa-survey/industries/${encodeURIComponent(industry.id)}/templates/push-all`,

          { method: 'POST', body: JSON.stringify({ offset, limit: PUSH_BATCH }), timeoutMs: 280000, quietNetworkHint: true },

        )

        acc.pushed += Number(summary.pushed || 0)

        acc.error_count += Number(summary.error_count || 0)

        acc.errors.push(...(summary.errors || []))

        if (!summary.has_more) break

        offset = Number(summary.next_offset ?? offset + PUSH_BATCH)

      }

      if (acc.error_count) {

        setMsg(`Pushed ${acc.pushed} template(s)`)

        setError(

          acc.errors

            .map((item) => `${item.template_name || item.template_id}: ${item.error}`)

            .join('\n'),

        )

      } else {

        setMsg(`Pushed ${acc.pushed} template(s) to Meta.`)

      }

      await load()

    } catch (err) {

      setError(formatWaSurveyError(err, 'Sync all survey types to Telnyx failed').message)

    } finally {

      setSyncBusy(false)

    }

  }



  const runDelete = async () => {

    if (!industry) return

    setDeleteBusy(true)

    setError('')

    try {

      const result = await apiFetch(`/admin/wa-survey/industries/${encodeURIComponent(industry.id)}`, {

        method: 'DELETE',

      })

      const warnings = Array.isArray(result?.warnings) ? result.warnings : []

      navigate('/settings/wa-survey', {

        replace: true,

        state: {

          waSurveyMsg: warnings.length

            ? `Industry deleted. Warnings: ${warnings.join(' ')}`

            : 'Industry deleted permanently.',

        },

      })

    } catch (err) {

      setError(formatWaSurveyError(err, 'Could not delete industry').message)

      setDeleteModal(false)

    } finally {

      setDeleteBusy(false)

    }

  }



  if (loading) {

    return <p className="muted">Loading industry…</p>

  }



  if (!industry) {

    return (

      <>

        <div className="alert error"><strong>{error || 'Industry not found.'}</strong></div>

        <Link className="btn" to="/settings/wa-survey">Back to WA Survey</Link>

      </>

    )

  }



  const typeDeleteTargets = typeDeleteModal?.typeIds || []

  const typeDeleteLabel = typeDeleteModal?.label || ''



  return (

    <>

      <div className="pageTop">

        <div>

          <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>

            <Link to="/settings/wa-survey" style={{ color: 'var(--grn)' }}>WA Survey</Link>

            {' / '}

            <span>{industry.name}</span>

          </div>

          <h1>{industry.name}</h1>

          <p className="pageLead">

            Manage this industry, its survey types, and linked WhatsApp templates.

            {industry.is_hidden ? <span className="pill muted" style={{ marginLeft: 8 }}>System industry</span> : null}

          </p>

        </div>

        <div className="pageTopActions">

          <button

            type="button"

            className="btn primary"

            onClick={() => void pushAllIndustryToTelnyx()}

            disabled={syncBusy || !surveyTypes.length}

            title="Push every linked template for all survey types in this industry"

          >

            {syncBusy ? 'Syncing all…' : 'Sync all survey types to Telnyx'}

          </button>

          <Link className="btn" to="/settings/wa-survey">Back to overview</Link>

        </div>

      </div>



      {error ? <div className="alert error" style={{ marginBottom: 16 }}><strong>{error}</strong></div> : null}

      {msg ? <div className="alert ok" style={{ marginBottom: 16 }}><strong>{msg}</strong></div> : null}



      <form className="card waIndustrySettingsCard" style={{ marginBottom: 16 }} onSubmit={saveIndustry}>

        <div className="cardHead"><h2>Industry settings</h2></div>

        <div className="cardBody grid-3">

          <label className="field">

            <span>Name</span>

            <input className="input" value={industry.name} onChange={(e) => setIndustry({ ...industry, name: e.target.value })} required />

          </label>

          <label className="field">

            <span>Slug</span>

            <input className="input" value={industry.slug} onChange={(e) => setIndustry({ ...industry, slug: e.target.value })} />

          </label>

          <label className="field">

            <span>Sort order</span>

            <input className="input" type="number" min={0} max={9999} value={industry.sort_order} onChange={(e) => setIndustry({ ...industry, sort_order: e.target.value })} />

          </label>

          <label className="field">

            <span>Status</span>

            <select

              className="input"

              value={industry.is_active ? 'active' : 'inactive'}

              onChange={(e) => setIndustry({ ...industry, is_active: e.target.value === 'active' })}

              disabled={industry.is_hidden}

            >

              <option value="active">Active</option>

              <option value="inactive">Inactive</option>

            </select>

          </label>

          <label className="field span-2">

            <span>Description</span>

            <input className="input" value={industry.description} onChange={(e) => setIndustry({ ...industry, description: e.target.value })} placeholder="Optional" />

          </label>

          {!industry.is_hidden ? (
            <>
              <div className="field span-2">
                <span>Customer visibility</span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 8 }}>
                  <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <input
                      type="radio"
                      name="edit_visibility"
                      checked={industry.visibility_mode !== 'restricted'}
                      onChange={() => setIndustry({ ...industry, visibility_mode: 'all', selectedOrgIds: [] })}
                    />
                    <span>Visible to all customers (default)</span>
                  </label>
                  <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <input
                      type="radio"
                      name="edit_visibility"
                      checked={industry.visibility_mode === 'restricted'}
                      onChange={() => setIndustry({ ...industry, visibility_mode: 'restricted' })}
                    />
                    <span>Visible to selected customers only</span>
                  </label>
                </div>
              </div>
              {industry.visibility_mode === 'restricted' ? (
                <div className="field span-2" style={{ maxHeight: 220, overflow: 'auto', border: '1px solid var(--line)', borderRadius: 8, padding: 12 }}>
                  <span>Select customers</span>
                  {orgs.length ? orgs.map((org) => (
                    <div key={org.id} style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 8, fontSize: 13 }}>
                      <Switch
                        checked={(industry.selectedOrgIds || []).includes(org.id)}
                        onCheckedChange={() => {
                          const set = new Set(industry.selectedOrgIds || [])
                          if (set.has(org.id)) set.delete(org.id)
                          else set.add(org.id)
                          setIndustry({ ...industry, selectedOrgIds: [...set] })
                        }}
                      />
                      <span>{org.name || org.id}</span>
                    </div>
                  )) : (
                    <p className="muted" style={{ margin: '8px 0 0' }}>No organisations loaded.</p>
                  )}
                </div>
              ) : null}
            </>
          ) : null}

        </div>

        <div className="cardBody" style={{ borderTop: '1px solid var(--line)', paddingTop: 16, display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'space-between' }}>

          {!industry.is_hidden ? (

            <button type="button" className="btn danger" onClick={() => setDeleteModal(true)}>Delete industry</button>

          ) : (

            <span />

          )}

          <button type="submit" className="btn primary" disabled={saving}>{saving ? 'Saving…' : 'Save industry'}</button>

        </div>

      </form>



      <section className="card" style={{ marginBottom: 16 }}>

        <div className="cardHead">

          <h2>Survey types</h2>

          <span className="muted">{typesLoading ? 'Loading…' : `${surveyTypes.length} type(s)`}</span>

        </div>

        <div className="cardBody">

          {!industry.is_hidden && someSelected ? (

            <div className="waIndustryTypesBulkBar">

              <span className="muted">{selectedTypeIds.size} selected</span>

              <button

                type="button"

                className="btn sm danger"

                disabled={typeDeleteBusy}

                onClick={() => setTypeDeleteModal({

                  typeIds: [...selectedTypeIds],

                  label: `${selectedTypeIds.size} survey type(s)`,

                })}

              >

                Delete selected

              </button>

              <button type="button" className="btn sm ghost" onClick={() => setSelectedTypeIds(new Set())}>Clear selection</button>

            </div>

          ) : null}



          <div className="tableWrap">

            <table className="table waIndustryTypesTable">

              <thead>

                <tr>

                  {!industry.is_hidden ? (

                    <th className="waIndustryTypesCheckCol">

                      <Switch

                        aria-label="Select all survey types"

                        checked={allSelected}

                        onCheckedChange={() => toggleSelectAll()}

                        disabled={typesLoading || !selectableTypeIds.length}

                      />

                    </th>

                  ) : null}

                  <th>Survey type</th>

                  <th>Active</th>

                  <th>Std</th>

                  <th>Anon</th>

                  <th>Synced</th>

                  <th>Status</th>

                  <th />

                </tr>

              </thead>

              <tbody>

                {typesLoading ? (

                  <tr><td colSpan={industry.is_hidden ? 7 : 8} className="muted">Loading survey types…</td></tr>

                ) : surveyTypes.length ? surveyTypes.map((type) => {

                  const typeId = String(type.id)

                  const checked = selectedTypeIds.has(typeId)

                  return (

                    <tr key={type.id}>

                      {!industry.is_hidden ? (

                        <td className="waIndustryTypesCheckCol">

                          <Switch

                            aria-label={`Select ${type.name}`}

                            checked={checked}

                            onCheckedChange={() => toggleTypeSelection(typeId)}

                          />

                        </td>

                      ) : null}

                      <td>

                        <strong>{type.name}</strong>

                        <div className="muted waIndustryTypeSlug"><code>{type.slug}</code></div>

                      </td>

                      <td>{type.is_active ? 'Yes' : 'No'}</td>

                      <td>{type.standard_template_count || 0}</td>

                      <td>{type.anonymous_template_count || 0}</td>

                      <td>{formatWhen(type.last_synced_at)}</td>

                      <td>

                        <span className={`pill ${statusTone(type.status_label)}`}>{type.status_label || '—'}</span>

                      </td>

                      <td className="waIndustryTypesActions">

                        <Link className="btn sm primary" to={`/settings/wa-survey/${type.id}`}>Open</Link>

                        {!industry.is_hidden ? (

                          <button

                            type="button"

                            className="btn sm danger"

                            disabled={typeDeleteBusy}

                            onClick={() => setTypeDeleteModal({

                              typeIds: [typeId],

                              label: type.name,

                            })}

                          >

                            Delete

                          </button>

                        ) : null}

                      </td>

                    </tr>

                  )

                }) : (

                  <tr><td colSpan={industry.is_hidden ? 7 : 8} className="muted">No survey types in this industry yet.</td></tr>

                )}

              </tbody>

            </table>

          </div>



          {!industry.is_hidden ? (

            <form className="waIndustryAddTypeForm" onSubmit={createSurveyType} style={{ marginTop: 16 }}>

              <label className="field">

                <span>Name</span>

                <input className="input" value={newTypeName} onChange={(e) => setNewTypeName(e.target.value)} placeholder="Post-visit feedback" />

              </label>

              <label className="field">

                <span>Description</span>

                <input className="input" value={newTypeDescription} onChange={(e) => setNewTypeDescription(e.target.value)} placeholder="Optional" />

              </label>

              <button type="submit" className="btn sm primary" disabled={creatingType || !newTypeName.trim()}>

                {creatingType ? 'Adding…' : 'Add type'}

              </button>

            </form>

          ) : null}

        </div>

      </section>



      {typeDeleteModal ? (

        <div className="modalOverlay" role="presentation" onClick={() => !typeDeleteBusy && setTypeDeleteModal(null)}>

          <div className="leadModal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>

            <div className="leadModalHead">

              <h3>Delete survey type{typeDeleteTargets.length > 1 ? 's' : ''}?</h3>

              <button type="button" className="btn soft" onClick={() => setTypeDeleteModal(null)} aria-label="Close">×</button>

            </div>

            <div className="leadModalBody">

              <p style={{ marginTop: 0 }}>

                Delete <strong>{typeDeleteLabel}</strong> permanently?

              </p>

              <ul className="muted" style={{ marginBottom: 0, paddingLeft: 18 }}>

                <li>Linked WhatsApp templates will be removed from the database</li>

                <li>Synced templates will also be deleted from Telnyx where possible</li>

              </ul>

            </div>

            <div className="leadModalFoot" style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>

              <button type="button" className="btn ghost" onClick={() => setTypeDeleteModal(null)} disabled={typeDeleteBusy}>Cancel</button>

              <button

                type="button"

                className="btn danger"

                onClick={() => void deleteSurveyTypes(typeDeleteTargets)}

                disabled={typeDeleteBusy}

              >

                {typeDeleteBusy ? 'Deleting…' : 'Delete permanently'}

              </button>

            </div>

          </div>

        </div>

      ) : null}



      {deleteModal ? (

        <div className="modalOverlay" role="presentation" onClick={() => !deleteBusy && setDeleteModal(false)}>

          <div className="leadModal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>

            <div className="leadModalHead">

              <h3>Delete industry?</h3>

              <button type="button" className="btn soft" onClick={() => setDeleteModal(false)} aria-label="Close">×</button>

            </div>

            <div className="leadModalBody">

              <p style={{ marginTop: 0 }}>Delete <strong>{industry.name}</strong> permanently?</p>

              <ul className="muted" style={{ marginBottom: 0, paddingLeft: 18 }}>

                <li>{industry.survey_type_count ?? surveyTypes.length} survey type(s) will be removed</li>

                <li>{industry.template_count ?? 0} WhatsApp template(s) will be removed from the database</li>

                <li>Synced templates will also be deleted from Telnyx where possible</li>

              </ul>

            </div>

            <div className="leadModalFoot" style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>

              <button type="button" className="btn ghost" onClick={() => setDeleteModal(false)} disabled={deleteBusy}>Cancel</button>

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

