import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'
import PlanPickerSelect from '../components/billing/PlanPickerSelect'
import '../styles/custom-org.css'

/**
 * Custom Org — per-customer WhatsApp workspace ("WA Profiles").
 * Layout is a 1:1 port of Custom-org.html (design source of truth); behaviour is
 * wired to real admin APIs (connection profiles, orgs, plans, industries, templates).
 */

const STATUS_BADGE = { active: 'active', paused: 'paused', setup: 'setup' }
const REGIONS = ['United Kingdom', 'United States', 'Canada', 'Australia']

function statusLabel(s) {
  const v = String(s || 'setup').toLowerCase()
  return v.charAt(0).toUpperCase() + v.slice(1)
}

function approvalBadgeClass(status) {
  const s = String(status || '').toUpperCase()
  if (s === 'APPROVED') return 'approved'
  if (s === 'LOCAL_DRAFT' || s === 'DRAFT') return 'local'
  return 'pending'
}

function approvalLabel(status) {
  const s = String(status || '').toUpperCase()
  if (s === 'APPROVED') return 'Approved'
  if (s === 'LOCAL_DRAFT' || s === 'DRAFT') return 'Local draft'
  if (s === 'PENDING' || s === 'IN_APPEAL' || s === 'PENDING_DELETION') return 'Pending on Meta'
  if (s === 'REJECTED') return 'Rejected'
  return s ? s.charAt(0) + s.slice(1).toLowerCase() : 'Draft'
}

/** Swap {{1}},{{2}}… in a body with sample values for the phone preview. */
function fillSamples(body, samples) {
  let out = String(body || '')
  ;(samples || []).forEach((val, idx) => {
    if (!val) return
    out = out.replaceAll(`{{${idx + 1}}}`, val)
  })
  return out
}

export default function CustomOrg() {
  const [view, setView] = useState('list')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [profiles, setProfiles] = useState([])
  const [options, setOptions] = useState({ wa_profiles: [], calling_profiles: [], orgs: [], plans: [] })
  const [search, setSearch] = useState('')

  const [detail, setDetail] = useState(null) // serialized custom-org profile
  const [form, setForm] = useState(null) // editable copy
  const [openAcc, setOpenAcc] = useState({ general: true, wa: false, templates: false })
  const [industryTemplates, setIndustryTemplates] = useState({}) // industry_id -> templates[]
  const [syncProfileId, setSyncProfileId] = useState('')
  const [syncBoth, setSyncBoth] = useState(false)
  const [busy, setBusy] = useState('')
  const [toast, setToast] = useState('')

  const [drawer, setDrawer] = useState(null) // { templateId, draft, saving }

  const loadList = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch('/admin/custom-org-profiles')
      setProfiles(data?.profiles || [])
      setOptions(data?.options || { wa_profiles: [], calling_profiles: [], orgs: [], plans: [] })
    } catch (e) {
      setError(e?.message || 'Failed to load profiles')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadList()
  }, [loadList])

  const flash = useCallback((msg) => {
    setToast(msg)
    window.setTimeout(() => setToast(''), 2600)
  }, [])

  const openDetail = useCallback(
    async (profileId) => {
      setError('')
      if (!profileId) {
        // New profile — create a blank row first so save/edit have an id.
        try {
          const data = await apiFetch('/admin/custom-org-profiles', {
            method: 'POST',
            body: JSON.stringify({ name: 'New profile' }),
          })
          const p = data?.profile
          setDetail(p)
          setForm({ ...p })
          setIndustryTemplates({})
          setView('detail')
          window.scrollTo(0, 0)
          loadList()
        } catch (e) {
          setError(e?.message || 'Could not create profile')
        }
        return
      }
      try {
        const data = await apiFetch(`/admin/custom-org-profiles/${profileId}`)
        const p = data?.profile
        setDetail(p)
        setForm({ ...p })
        setOptions(data?.options || options)
        setSyncProfileId(p?.wa_profile_id || '')
        setView('detail')
        window.scrollTo(0, 0)
        // Load templates for each dedicated industry.
        const map = {}
        for (const ind of p?.industries || []) {
          try {
            const t = await apiFetch(`/admin/wa-survey/industries/${ind.id}/templates`)
            map[ind.id] = t?.templates || []
          } catch {
            map[ind.id] = []
          }
        }
        setIndustryTemplates(map)
      } catch (e) {
        setError(e?.message || 'Could not open profile')
      }
    },
    [loadList, options]
  )

  const closeDetail = useCallback(() => {
    setView('list')
    setDetail(null)
    setForm(null)
    loadList()
  }, [loadList])

  const deleteProfile = useCallback(async () => {
    if (!form?.id) return
    const label = form.name || 'Untitled'
    const ok = window.confirm(
      `Delete WA profile "${label}"?\n\nThis removes the admin workspace only. The customer Organisation record is kept. Linked industries and templates are not deleted — use ✕ on each industry block to remove those.`,
    )
    if (!ok) return
    setBusy('delete')
    setError('')
    try {
      await apiFetch(`/admin/custom-org-profiles/${form.id}`, { method: 'DELETE' })
      flash('Profile deleted')
      closeDetail()
    } catch (e) {
      setError(e?.message || 'Could not delete profile')
    } finally {
      setBusy('')
    }
  }, [form, closeDetail, flash])

  const setField = (key, value) => setForm((f) => ({ ...f, [key]: value }))

  const saveDetail = useCallback(async () => {
    if (!form?.id) return
    setBusy('save')
    setError('')
    try {
      const body = {
        name: form.name,
        status: form.status,
        org_id: form.org_id || null,
        wa_profile_id: form.wa_profile_id || null,
        calling_profile_id: form.calling_profile_id || null,
        plan_id: form.plan_id || null,
        contact_name: form.contact_name || null,
        contact_email: form.contact_email || null,
        contact_phone: form.contact_phone || null,
        region: form.region || null,
        notes: form.notes || null,
      }
      const data = await apiFetch(`/admin/custom-org-profiles/${form.id}`, {
        method: 'PUT',
        body: JSON.stringify(body),
      })
      const p = data?.profile
      setDetail(p)
      setForm({ ...p })
      const map = {}
      for (const ind of p?.industries || []) {
        try {
          const t = await apiFetch(`/admin/wa-survey/industries/${ind.id}/templates`)
          map[ind.id] = t?.templates || []
        } catch {
          map[ind.id] = []
        }
      }
      setIndustryTemplates(map)
      flash('Changes saved')
    } catch (e) {
      setError(e?.message || 'Save failed')
    } finally {
      setBusy('')
    }
  }, [form, flash])

  const waProfileMeta = useMemo(
    () => (options.wa_profiles || []).find((p) => p.id === form?.wa_profile_id) || null,
    [options.wa_profiles, form?.wa_profile_id]
  )

  const reloadIndustryTemplates = useCallback(async (industryId) => {
    try {
      const t = await apiFetch(`/admin/wa-survey/industries/${industryId}/templates`)
      setIndustryTemplates((m) => ({ ...m, [industryId]: t?.templates || [] }))
    } catch {
      /* ignore */
    }
  }, [])

  const addIndustry = useCallback(async () => {
    const name = window.prompt('New industry name for this customer (dedicated to this org)')
    if (!name || !name.trim()) return
    if (!form?.org_id) {
      setError('Assign a User / Organisation in General first, then Save — the industry is dedicated to that customer.')
      return
    }
    setBusy('add-industry')
    setError('')
    try {
      await apiFetch('/admin/wa-survey/industries', {
        method: 'POST',
        body: JSON.stringify({
          name: name.trim(),
          visibility_mode: 'restricted',
          org_ids: [form.org_id],
        }),
      })
      await openDetail(form.id)
      flash('Industry created')
    } catch (e) {
      setError(e?.message || 'Could not create industry')
    } finally {
      setBusy('')
    }
  }, [form, openDetail, flash])

  const linkExistingIndustry = useCallback(async () => {
    if (!form?.org_id) {
      setError('Assign a User / Organisation in General first, then Save — industries are linked to that customer org.')
      return
    }
    setBusy('link-industry')
    setError('')
    try {
      const data = await apiFetch('/admin/wa-survey/industries?include_inactive=true')
      const all = Array.isArray(data?.industries) ? data.industries : []
      const linkedIds = new Set((form.industries || []).map((i) => i.id))
      const candidates = all.filter((i) => i?.id && !linkedIds.has(i.id))
      if (!candidates.length) {
        setError('No other survey industries available to link. Create a new one instead.')
        return
      }
      const lines = candidates.slice(0, 30).map((i, idx) => `${idx + 1}. ${i.name}${i.visibility_mode === 'restricted' ? ' (restricted)' : ''}`)
      const pick = window.prompt(
        `Link an existing survey industry to this customer org.\n\n${lines.join('\n')}\n\nEnter the number (1–${Math.min(candidates.length, 30)}):`,
      )
      const n = Number.parseInt(String(pick || '').trim(), 10)
      if (!Number.isFinite(n) || n < 1 || n > Math.min(candidates.length, 30)) return
      const chosen = candidates[n - 1]
      const orgIds = Array.from(new Set([...(chosen.org_ids || []), form.org_id]))
      await apiFetch(`/admin/wa-survey/industries/${chosen.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          visibility_mode: 'restricted',
          org_ids: orgIds,
        }),
      })
      await openDetail(form.id)
      flash(`Linked “${chosen.name}” to this profile`)
    } catch (e) {
      setError(e?.message || 'Could not link industry')
    } finally {
      setBusy('')
    }
  }, [form, openDetail, flash])

  const deleteIndustry = useCallback(
    async (industryId, industryName) => {
      if (!industryId) return
      const ok = window.confirm(
        `Delete industry “${industryName || 'Untitled'}” and ALL its templates from the local DB (and Meta/Telnyx if pushed)?\n\nThis cannot be undone.`,
      )
      if (!ok) return
      setBusy(`del-ind-${industryId}`)
      setError('')
      try {
        const result = await apiFetch(`/admin/wa-survey/industries/${industryId}`, {
          method: 'DELETE',
          timeoutMs: 180000,
        })
        flash(`Deleted industry (${result?.deleted_templates ?? 0} template(s) removed)`)
        await openDetail(form.id)
      } catch (e) {
        setError(e?.message || 'Could not delete industry')
      } finally {
        setBusy('')
      }
    },
    [form, openDetail, flash],
  )

  const syncTargets = useMemo(() => {
    const ids = []
    if (syncProfileId) ids.push(syncProfileId)
    if (syncBoth) {
      for (const p of options.wa_profiles || []) {
        if (p.id !== syncProfileId) ids.push(p.id)
      }
    }
    return ids
  }, [syncProfileId, syncBoth, options.wa_profiles])

  const syncIndustry = useCallback(
    async (industryId) => {
      if (!syncProfileId) {
        setError('Pick a target profile (Meta / Telnyx / dedicated) in the Service Templates header first.')
        return
      }
      setBusy(`sync-${industryId}`)
      setError('')
      try {
        for (const pid of syncTargets) {
          await apiFetch(`/admin/wa-survey/industries/${industryId}/templates/push-all`, {
            method: 'POST',
            body: JSON.stringify({ connection_profile_id: pid }),
          })
        }
        await reloadIndustryTemplates(industryId)
        flash(syncBoth ? 'Synced to both profiles' : 'Synced')
      } catch (e) {
        setError(e?.message || 'Sync failed')
      } finally {
        setBusy('')
      }
    },
    [syncProfileId, syncTargets, syncBoth, reloadIndustryTemplates, flash]
  )

  const syncAll = useCallback(async () => {
    for (const ind of form?.industries || []) {
      // eslint-disable-next-line no-await-in-loop
      await syncIndustry(ind.id)
    }
  }, [form, syncIndustry])

  const syncTemplate = useCallback(
    async (templateId, industryId) => {
      if (!syncProfileId) {
        setError('Pick a target profile in the Service Templates header first.')
        return
      }
      setBusy(`tpl-${templateId}`)
      setError('')
      try {
        for (const pid of syncTargets) {
          await apiFetch(`/admin/wa-survey/templates/${templateId}/push`, {
            method: 'POST',
            body: JSON.stringify({ connection_profile_id: pid }),
          })
        }
        await reloadIndustryTemplates(industryId)
        flash('Template synced')
      } catch (e) {
        setError(e?.message || 'Template sync failed')
      } finally {
        setBusy('')
      }
    },
    [syncProfileId, syncTargets, reloadIndustryTemplates, flash]
  )

  const toggleTemplateActive = useCallback(
    async (tpl, industryId) => {
      setBusy(`tpl-toggle-${tpl.id}`)
      setError('')
      try {
        await apiFetch(`/admin/wa-survey/templates/${tpl.id}`, {
          method: 'PUT',
          body: JSON.stringify({ active_for_survey: !tpl.active_for_survey }),
        })
        await reloadIndustryTemplates(industryId)
      } catch (e) {
        setError(e?.message || 'Could not toggle template')
      } finally {
        setBusy('')
      }
    },
    [reloadIndustryTemplates]
  )

  // ---- drawer ----
  const openDrawer = useCallback(async (tpl) => {
    if (!tpl?.id) return
    const samples = (tpl.example_values || []).map((v) => (typeof v === 'string' ? v : v?.value || ''))
    setDrawer({
      templateId: tpl.id,
      industryId: tpl.__industryId,
      saving: false,
      draft: {
        name: tpl.display_name || tpl.name || '',
        category: (tpl.category || 'UTILITY').toUpperCase() === 'MARKETING' ? 'Marketing' : 'Utility',
        language: tpl.language || 'en_GB',
        body: tpl.body_preview || '',
        active: !!tpl.active_for_survey,
        buttonLabel: (tpl.buttons || [])[0]?.text || '',
        variables: samples,
      },
    })
  }, [])

  const closeDrawer = useCallback(() => setDrawer(null), [])

  const setDraft = (key, value) => setDrawer((d) => (d ? { ...d, draft: { ...d.draft, [key]: value } } : d))

  const saveTemplate = useCallback(async () => {
    if (!drawer?.templateId) return
    setDrawer((d) => ({ ...d, saving: true }))
    setError('')
    try {
      // Preserve existing components (buttons/header/footer); only swap BODY text.
      const detailData = await apiFetch(`/admin/wa-survey/templates/${drawer.templateId}`)
      const tpl = detailData?.template || {}
      const existing = tpl.draft_components || tpl.remote_components || tpl.components || []
      let components = Array.isArray(existing) ? JSON.parse(JSON.stringify(existing)) : []
      let hasBody = false
      components = components.map((c) => {
        if (c && String(c.type || '').toUpperCase() === 'BODY') {
          hasBody = true
          return { ...c, text: drawer.draft.body }
        }
        return c
      })
      if (!hasBody) components.unshift({ type: 'BODY', text: drawer.draft.body })
      const category = drawer.draft.category === 'Marketing' ? 'MARKETING' : 'UTILITY'
      await apiFetch(`/admin/wa-survey/templates/${drawer.templateId}`, {
        method: 'PUT',
        body: JSON.stringify({
          display_name: drawer.draft.name,
          category,
          language: drawer.draft.language || 'en_GB',
          active_for_survey: drawer.draft.active,
          components,
          example_values: drawer.draft.variables,
        }),
      })
      if (drawer.industryId) await reloadIndustryTemplates(drawer.industryId)
      flash('Template saved')
      setDrawer(null)
    } catch (e) {
      setError(e?.message || 'Could not save template')
      setDrawer((d) => (d ? { ...d, saving: false } : d))
    }
  }, [drawer, reloadIndustryTemplates, flash])

  const filteredProfiles = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return profiles
    return profiles.filter((p) =>
      [p.name, p.org_name, p.wa_number, (p.industries || []).map((i) => i.name).join(' ')]
        .filter(Boolean)
        .some((s) => String(s).toLowerCase().includes(q))
    )
  }, [profiles, search])

  const previewBody = drawer ? fillSamples(drawer.draft.body, drawer.draft.variables) : ''

  return (
    <div className="custom-org-page">
      <h1>WA Profiles</h1>
      <div className="sub">Manage isolated WhatsApp profiles, service templates and topics per customer organisation.</div>

      {error ? (
        <div className="card" style={{ padding: '10px 14px', borderColor: 'var(--warn)', color: 'var(--warn)' }}>{error}</div>
      ) : null}
      {toast ? (
        <div className="card" style={{ padding: '10px 14px', borderColor: 'var(--ok)', color: 'var(--ok)' }}>{toast}</div>
      ) : null}

      {view === 'list' ? (
        <div id="view-list">
          <div className="card" style={{ padding: '14px' }}>
            <div className="list-toolbar">
              <input
                className="search"
                placeholder="Search by org name, WA number, industry…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <button className="btn" onClick={() => openDetail(null)}>+ New Profile</button>
            </div>
            <table>
              <thead>
                <tr><th>Org</th><th>Industry</th><th>WA Number</th><th>Templates</th><th>Status</th></tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={5} className="empty">Loading…</td></tr>
                ) : filteredProfiles.length === 0 ? (
                  <tr><td colSpan={5} className="empty">No profiles yet. Click “+ New Profile”.</td></tr>
                ) : (
                  filteredProfiles.map((p) => (
                    <tr className="clickable" key={p.id} onClick={() => openDetail(p.id)}>
                      <td><strong>{p.name}</strong>{p.org_name ? <div className="muted" style={{ fontSize: '10.5px' }}>{p.org_name}</div> : null}</td>
                      <td>{(p.industries || []).map((i) => i.name).join(', ') || '—'}</td>
                      <td>{p.wa_number || '— not registered —'}</td>
                      <td>{p.industry_count || 0}</td>
                      <td><span className={`badge ${STATUS_BADGE[p.status] || 'setup'}`}>{statusLabel(p.status)}</span></td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {view === 'detail' && form ? (
        <div id="view-detail" style={{ display: 'block' }}>
          <div className="back-link" onClick={closeDetail}>&larr; All profiles</div>

          <div className="detail-header">
            <div>
              <div className="org-name">{form.name || 'Untitled'}</div>
              <div className="org-meta">
                {form.internal_ref || 'WAP-—'} &nbsp;·&nbsp; {(form.industries || []).map((i) => i.name).join(', ') || 'No industry'}
                {form.plan_service ? (
                  <> &nbsp;·&nbsp; {form.plan_service}{form.plan_name ? ` · ${form.plan_name}` : ''}{form.plan_currency ? ` (${form.plan_currency})` : ''}</>
                ) : null}
                &nbsp;·&nbsp;{' '}
                <span className={`badge ${STATUS_BADGE[form.status] || 'setup'}`}>{statusLabel(form.status)}</span>
              </div>
            </div>
            <div className="detail-header-actions">
              <button className="btn ghost danger" onClick={deleteProfile} disabled={!!busy}>
                {busy === 'delete' ? 'Deleting…' : 'Delete profile'}
              </button>
              <button className="btn" onClick={saveDetail} disabled={busy === 'save'}>{busy === 'save' ? 'Saving…' : 'Save changes'}</button>
            </div>
          </div>

          {/* GENERAL */}
          <div className={`card${openAcc.general ? ' open' : ''}`}>
            <div className="acc-header" onClick={() => setOpenAcc((a) => ({ ...a, general: !a.general }))}>
              <div className="acc-title">General</div>
              <div className="acc-chevron">▾</div>
            </div>
            <div className="acc-body">
              <table className="kv-table">
                <tbody>
                  <tr>
                    <td className="k">Profile / Org name</td>
                    <td className="v"><input type="text" value={form.name || ''} onChange={(e) => setField('name', e.target.value)} /></td>
                    <td className="k">Internal reference</td>
                    <td className="v"><input type="text" value={form.internal_ref || ''} disabled /></td>
                  </tr>
                  <tr>
                    <td className="k">User / Organisation</td>
                    <td className="v">
                      <select value={form.org_id || ''} onChange={(e) => setField('org_id', e.target.value)}>
                        <option value="">— select customer —</option>
                        {(options.orgs || []).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                      </select>
                    </td>
                    <td className="k">Billing plan</td>
                    <td className="v" colSpan={1}>
                      <PlanPickerSelect
                        value={form.plan_id || ''}
                        onChange={(id) => setField('plan_id', id || null)}
                        valueKey="id"
                        grouped
                        placeholder="— select plan —"
                        className="custom-org-plan-picker-input"
                      />
                      <div className="muted" style={{ fontSize: '11px', marginTop: 4 }}>
                        Grouped by service. Shows package, region, and currency. Overrides org billing when this WA profile is active.
                      </div>
                    </td>
                  </tr>
                  <tr>
                    <td className="k">Primary contact name</td>
                    <td className="v"><input type="text" value={form.contact_name || ''} onChange={(e) => setField('contact_name', e.target.value)} /></td>
                    <td className="k">Primary contact email</td>
                    <td className="v"><input type="text" value={form.contact_email || ''} onChange={(e) => setField('contact_email', e.target.value)} /></td>
                  </tr>
                  <tr>
                    <td className="k">Contact phone</td>
                    <td className="v"><input type="text" value={form.contact_phone || ''} onChange={(e) => setField('contact_phone', e.target.value)} /></td>
                    <td className="k">Market / region</td>
                    <td className="v">
                      <select value={form.region || ''} onChange={(e) => setField('region', e.target.value)}>
                        <option value="">—</option>
                        {REGIONS.map((r) => <option key={r} value={r}>{r}</option>)}
                      </select>
                    </td>
                  </tr>
                  <tr>
                    <td className="k">Status</td>
                    <td className="v">
                      <select value={form.status || 'setup'} onChange={(e) => setField('status', e.target.value)}>
                        <option value="setup">Setup</option>
                        <option value="active">Active</option>
                        <option value="paused">Paused</option>
                      </select>
                    </td>
                    <td className="k" />
                    <td className="v" />
                  </tr>
                  <tr>
                    <td className="k">Admin notes</td>
                    <td className="v" colSpan={3}><textarea style={{ minHeight: '44px' }} value={form.notes || ''} onChange={(e) => setField('notes', e.target.value)} /></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* WA SETUP - CONNECTION */}
          <div className={`card${openAcc.wa ? ' open' : ''}`}>
            <div className="acc-header" onClick={() => setOpenAcc((a) => ({ ...a, wa: !a.wa }))}>
              <div className="acc-title">WA Setup — connection</div>
              <div className="acc-chevron">▾</div>
            </div>
            <div className="acc-body">
              <table className="kv-table">
                <tbody>
                  <tr>
                    <td className="k">WhatsApp profile</td>
                    <td className="v">
                      <select value={form.wa_profile_id || ''} onChange={(e) => setField('wa_profile_id', e.target.value)}>
                        <option value="">— our shared number (Meta 99 / Telnyx 55) —</option>
                        {(options.wa_profiles || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                      </select>
                    </td>
                    <td className="k">Calling line</td>
                    <td className="v">
                      <select value={form.calling_profile_id || ''} onChange={(e) => setField('calling_profile_id', e.target.value)}>
                        <option value="">— none —</option>
                        {(options.calling_profiles || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                      </select>
                    </td>
                  </tr>
                  <tr>
                    <td className="k">Sending provider</td>
                    <td className="v"><input type="text" value={waProfileMeta?.provider ? (waProfileMeta.provider === 'telnyx' ? 'Telnyx' : 'Meta Cloud API') : '—'} disabled /></td>
                    <td className="k">WhatsApp number</td>
                    <td className="v"><input type="text" value={waProfileMeta?.wa_number || '—'} disabled /></td>
                  </tr>
                </tbody>
              </table>
              <div className="muted" style={{ fontSize: '11px', padding: '4px 8px' }}>
                WABA credentials live on the Connection Profiles page. Select the customer’s dedicated profile here to route their surveys and templates to their own number.
              </div>
            </div>
          </div>

          {/* SERVICE TEMPLATES */}
          <div className={`card${openAcc.templates ? ' open' : ''}`}>
            <div className="acc-header" onClick={() => setOpenAcc((a) => ({ ...a, templates: !a.templates }))}>
              <div className="acc-title">Service Templates</div>
              <div className="acc-actions" onClick={(e) => e.stopPropagation()}>
                <div className="profile-switch">
                  <span className="muted" style={{ fontSize: '11px' }}>Profile</span>
                  <select value={syncProfileId} onChange={(e) => setSyncProfileId(e.target.value)}>
                    <option value="">— select —</option>
                    {(options.wa_profiles || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                  <label className="muted" style={{ fontSize: '11px', display: 'flex', alignItems: 'center', gap: 4 }}>
                    <input type="checkbox" style={{ width: 'auto' }} checked={syncBoth} onChange={(e) => setSyncBoth(e.target.checked)} />
                    sync both
                  </label>
                </div>
                <button className="btn ghost small" onClick={syncAll} disabled={!!busy}>⟲ Sync all industries</button>
                <div className="acc-chevron" onClick={() => setOpenAcc((a) => ({ ...a, templates: !a.templates }))}>▾</div>
              </div>
            </div>
            <div className="acc-body">
              {(form.industries || []).length === 0 ? (
                <div className="empty">
                  No dedicated industries yet. In <strong>General</strong>, assign a customer org and click <strong>Save</strong>, then use
                  <strong> + Add industry</strong> or <strong>Link existing</strong> below.
                </div>
              ) : (
                (form.industries || []).map((ind) => {
                  const tpls = industryTemplates[ind.id] || []
                  return (
                    <div className="industry-block" key={ind.id}>
                      <div className="industry-block-head">
                        <div className="name">{ind.name}</div>
                        <div className="industry-block-actions">
                          <button className="icon-btn" title="Sync this industry" onClick={() => syncIndustry(ind.id)} disabled={!!busy}>⟲</button>
                          <button
                            className="icon-btn danger"
                            title="Delete this industry and all its templates"
                            onClick={() => deleteIndustry(ind.id, ind.name)}
                            disabled={!!busy}
                          >
                            ✕
                          </button>
                        </div>
                      </div>
                      <table>
                        <thead>
                          <tr><th>Topic / Template</th><th>Message</th><th>Status</th><th style={{ width: '150px' }}>Actions</th></tr>
                        </thead>
                        <tbody>
                          {tpls.length === 0 ? (
                            <tr><td colSpan={4} className="empty">No templates.</td></tr>
                          ) : (
                            tpls.map((t) => (
                              <tr key={t.id}>
                                <td>{t.display_name || t.name}</td>
                                <td style={{ color: 'var(--ink-soft)' }}>{t.body_preview || '—'}</td>
                                <td><span className={`badge ${approvalBadgeClass(t.approval_status)}`}>{approvalLabel(t.approval_status)}</span></td>
                                <td>
                                  <button className="icon-btn" title="Edit" onClick={() => openDrawer({ ...t, __industryId: ind.id })}>✎</button>
                                  <button
                                    className={`icon-btn${t.active_for_survey ? ' on-state' : ''}`}
                                    title={t.active_for_survey ? 'Enabled — click to disable' : 'Disabled — click to enable'}
                                    onClick={() => toggleTemplateActive(t, ind.id)}
                                    disabled={busy === `tpl-toggle-${t.id}`}
                                  >⏻</button>
                                  <button className="icon-btn" title="Sync" onClick={() => syncTemplate(t.id, ind.id)} disabled={busy === `tpl-${t.id}`}>⟲</button>
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>
                  )
                })
              )}

              <div className="industry-block-foot">
                <button className="btn ghost small" onClick={addIndustry} disabled={!!busy}>+ Add industry</button>
                <button className="btn ghost small" onClick={linkExistingIndustry} disabled={!!busy}>Link existing</button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {/* TEMPLATE EDIT DRAWER */}
      <div className={`overlay${drawer ? ' open' : ''}`} onClick={closeDrawer} />
      <div className={`drawer${drawer ? ' open' : ''}`}>
        {drawer ? (
          <div className="drawer-inner">
            <div className="drawer-form">
              <div className="drawer-header">
                <div className="title">Edit WA template</div>
                <button className="close-x" onClick={closeDrawer}>✕</button>
              </div>

              <div className="status-row">
                <div className="lbl">Template enabled</div>
                <button className={`toggle${drawer.draft.active ? ' on' : ''}`} onClick={() => setDraft('active', !drawer.draft.active)}><span /></button>
              </div>

              <div className="field">
                <label>Template name</label>
                <input type="text" value={drawer.draft.name} onChange={(e) => setDraft('name', e.target.value)} />
                <div className="hint">Lowercase, underscores only — must match Meta's approved name.</div>
              </div>

              <div className="field">
                <label>Category</label>
                <select value={drawer.draft.category} onChange={(e) => setDraft('category', e.target.value)}>
                  <option>Utility</option><option>Marketing</option><option>Authentication</option>
                </select>
              </div>

              <div className="field">
                <label>Language</label>
                <select value={drawer.draft.language} onChange={(e) => setDraft('language', e.target.value)}>
                  <option value="en_GB">en_GB</option><option value="en_US">en_US</option><option value="ar">ar</option>
                </select>
              </div>

              <div className="field">
                <label>Body text</label>
                <textarea value={drawer.draft.body} onChange={(e) => setDraft('body', e.target.value)} />
                <div className="hint">Use {'{{1}}'}, {'{{2}}'}… for variables.</div>
              </div>

              <div className="field">
                <label>Buttons</label>
                <div className="btn-row">
                  <input type="text" value="Quick Reply" disabled />
                  <input type="text" value={drawer.draft.buttonLabel} onChange={(e) => setDraft('buttonLabel', e.target.value)} />
                  <span />
                </div>
              </div>

              <div className="form-actions">
                <button className="btn ghost" onClick={closeDrawer}>Cancel</button>
                <button className="btn" onClick={saveTemplate} disabled={drawer.saving}>{drawer.saving ? 'Saving…' : 'Save template'}</button>
              </div>
            </div>

            <div className="drawer-preview">
              <div className="iphone-label">iPhone 17 Pro Max preview</div>
              <div className="phone">
                <div className="phone-screen">
                  <div className="notch" />
                  <div className="wa-header">
                    <div className="avatar" />
                    <div>{form?.name || 'WhatsApp Business'}<br /><span style={{ fontWeight: 400, fontSize: '9.5px', opacity: 0.8 }}>WhatsApp Business</span></div>
                  </div>
                  <div className="wa-body">
                    <div className="wa-bubble">
                      <div className="tname">{drawer.draft.name || 'template_name'}</div>
                      <div>{previewBody || '—'}</div>
                      {drawer.draft.buttonLabel ? <div className="btns"><div className="wbtn">{drawer.draft.buttonLabel}</div></div> : null}
                      <div className="wa-time">09:41</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
