import React, { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { apiFetch } from '../lib/api'

const CATEGORY_OPTIONS = [
  { slug: 'dental', label: 'Dental' },
  { slug: 'aesthetics', label: 'Aesthetics' },
  { slug: 'opticians', label: 'Opticians' },
]

const STATUS_OPTIONS = ['active', 'inactive', 'coming soon']
const SERVICE_LABELS = {
  dentally: 'Dentally',
  carestack: 'CareStack',
  pabau: 'Pabau',
  cliniko: 'Cliniko',
  optix: 'Optix',
  ocuco: 'Ocuco',
  telnyx: 'Telnyx',
}

const SERVICE_DEFAULTS = {
  dentally: {
    slug: 'dentally',
    display_name: 'Dentally',
    category_slug: 'dental',
    short_description: 'Dental practice management integration for appointment, patient and recall context.',
    status: 'active',
    is_active: true,
    is_recommended: true,
    api_difficulty: 'easy API',
    docs_text: 'Tenant setup needs a Dentally API base URL and API key. Dentally should remain the appointment source of truth; VOXBULK reads appointment/customer context and writes recovery outcomes only where supported.',
    sort_order: 10,
  },
  carestack: {
    slug: 'carestack',
    display_name: 'CareStack',
    category_slug: 'dental',
    short_description: 'Dental practice management integration for larger dental groups.',
    status: 'coming soon',
    is_active: false,
    is_recommended: false,
    api_difficulty: 'beta',
    docs_text: 'Tenant setup will need the CareStack API base URL and API key. Extra location or group identifiers may be required for multi-site dental groups.',
    sort_order: 20,
  },
  pabau: {
    slug: 'pabau',
    display_name: 'Pabau',
    category_slug: 'aesthetics',
    short_description: 'Aesthetics and medspa practice software integration for appointments and client context.',
    status: 'coming soon',
    is_active: false,
    is_recommended: true,
    api_difficulty: 'beta',
    docs_text: 'Tenant setup will need Pabau API details. This will power consultation conversion, cancellation recovery and client recall workflows.',
    sort_order: 10,
  },
  cliniko: {
    slug: 'cliniko',
    display_name: 'Cliniko',
    category_slug: 'aesthetics',
    short_description: 'Clinic booking software integration for appointments and client context.',
    status: 'coming soon',
    is_active: false,
    is_recommended: false,
    api_difficulty: 'beta',
    docs_text: 'Tenant setup needs a Cliniko API base URL and API key. Some accounts may need business/practitioner scoping later.',
    sort_order: 20,
  },
  optix: {
    slug: 'optix',
    display_name: 'Optix',
    category_slug: 'opticians',
    short_description: 'Optician practice management integration for eye tests, contact lens checks and recall workflows.',
    status: 'coming soon',
    is_active: false,
    is_recommended: true,
    api_difficulty: 'beta',
    docs_text: 'Tenant setup will need Optix API access. Extra branch/store identifiers may be needed for multi-location opticians.',
    sort_order: 10,
  },
  ocuco: {
    slug: 'ocuco',
    display_name: 'Ocuco',
    category_slug: 'opticians',
    short_description: 'Optometry and optical retail software integration for appointments, recalls and customer context.',
    status: 'coming soon',
    is_active: false,
    is_recommended: false,
    api_difficulty: 'beta',
    docs_text: 'Tenant setup will need Ocuco API details. Additional store or practice identifiers may be required later.',
    sort_order: 20,
  },
  telnyx: {
    slug: 'telnyx',
    display_name: 'Telnyx',
    category_slug: 'voice-infrastructure',
    short_description: 'Voice infrastructure provider for outbound AI phone calls, call control, media streaming and Telnyx webhooks.',
    status: 'active',
    is_active: true,
    is_recommended: true,
    api_difficulty: 'voice infrastructure',
    docs_text: 'Platform-level Telnyx settings are stored securely in provider settings and reused by Vox Sales Demo Lab and outbound call workflows.',
    sort_order: 5,
  },
}

const REQUIRED_FIELDS = {
  dentally: [
    { key: 'base_url', label: 'Base URL', needed: true, secret: false, notes: 'Dentally API origin for this tenant.' },
    { key: 'api_key', label: 'API key', needed: true, secret: true, notes: 'Sensitive tenant API key, stored encrypted.' },
    { key: 'site_id', label: 'Site / practice ID', needed: false, secret: false, notes: 'Optional future field for multi-site setups.' },
  ],
  carestack: [
    { key: 'base_url', label: 'Base URL', needed: true, secret: false, notes: 'CareStack API origin.' },
    { key: 'api_key', label: 'API key', needed: true, secret: true, notes: 'Sensitive tenant API key, stored encrypted.' },
    { key: 'location_id', label: 'Location ID', needed: false, secret: false, notes: 'Optional placeholder for group/location scoping.' },
  ],
  pabau: [
    { key: 'base_url', label: 'Base URL', needed: true, secret: false, notes: 'Pabau API origin.' },
    { key: 'api_key', label: 'API key', needed: true, secret: true, notes: 'Sensitive tenant API key, stored encrypted.' },
    { key: 'clinic_id', label: 'Clinic ID', needed: false, secret: false, notes: 'Optional placeholder for multi-clinic accounts.' },
  ],
  cliniko: [
    { key: 'base_url', label: 'Base URL', needed: true, secret: false, notes: 'Cliniko API origin, e.g. region-specific API URL.' },
    { key: 'api_key', label: 'API key', needed: true, secret: true, notes: 'Sensitive tenant API key, stored encrypted.' },
    { key: 'business_id', label: 'Business ID', needed: false, secret: false, notes: 'Optional placeholder for account scoping.' },
  ],
  optix: [
    { key: 'base_url', label: 'Base URL', needed: true, secret: false, notes: 'Optix API origin.' },
    { key: 'api_key', label: 'API key', needed: true, secret: true, notes: 'Sensitive tenant API key, stored encrypted.' },
    { key: 'branch_id', label: 'Branch / store ID', needed: false, secret: false, notes: 'Optional placeholder for multi-branch opticians.' },
  ],
  ocuco: [
    { key: 'base_url', label: 'Base URL', needed: true, secret: false, notes: 'Ocuco API origin.' },
    { key: 'api_key', label: 'API key', needed: true, secret: true, notes: 'Sensitive tenant API key, stored encrypted.' },
    { key: 'store_id', label: 'Store / practice ID', needed: false, secret: false, notes: 'Optional placeholder for store scoping.' },
  ],
  telnyx: [
    { key: 'api_key', label: 'Telnyx API key', needed: true, secret: true, notes: 'Sensitive platform API key, stored encrypted in provider settings.' },
    { key: 'connection_id', label: 'Voice API application / connection ID', needed: true, secret: false, notes: 'Used by Telnyx Call Control outbound calls.' },
    { key: 'default_outbound_number', label: 'From phone number', needed: true, secret: false, notes: 'Default caller ID / from number for outbound test calls.' },
    { key: 'outbound_voice_profile_id', label: 'Outbound voice profile ID', needed: true, secret: false, notes: 'Used to verify the Telnyx voice profile.' },
    { key: 'voice_webhook_url', label: 'Webhook URL', needed: true, secret: false, notes: 'Set this in Telnyx portal for voice events.' },
    { key: 'status_callback_url', label: 'Status callback URL', needed: false, secret: false, notes: 'Receives call status updates.' },
    { key: 'media_stream_url', label: 'Media stream WebSocket URL', needed: false, secret: false, notes: 'Used for live media stream events.' },
  ],
}

const DEFAULT_WEBHOOK_BASE = 'https://localhost'

function slugify(s) {
  return String(s || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80)
}

function statusClass(status) {
  const s = String(status || '').toLowerCase()
  if (s === 'active') return 'p-green'
  if (s === 'inactive') return 'p-red'
  return 'p-amber'
}

function copyText(value) {
  const text = String(value || '')
  if (!text) return
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(text).catch(() => {})
}

function emptyDraft() {
  return {
    slug: '',
    display_name: '',
    category_slug: 'dental',
    short_description: '',
    status: 'active',
    is_active: true,
    is_recommended: false,
    api_difficulty: '',
    docs_text: '',
    sort_order: 100,
  }
}

export default function ServicesAPI() {
  const location = useLocation()
  const targetSlug = String(location.pathname || '').split('/').filter(Boolean)[1] || ''
  const [items, setItems] = useState(null)
  const [draft, setDraft] = useState(emptyDraft)
  const [editingSlug, setEditingSlug] = useState('')
  const [edit, setEdit] = useState(null)
  const [categories, setCategories] = useState([])
  const [categoryFilter, setCategoryFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [activeOnly, setActiveOnly] = useState(false)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [telnyxSettings, setTelnyxSettings] = useState(null)
  const [telnyxDraft, setTelnyxDraft] = useState({})
  const [telnyxSecret, setTelnyxSecret] = useState('')
  const [telnyxTestResult, setTelnyxTestResult] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams()
      if (!targetSlug && categoryFilter) params.set('category', categoryFilter)
      if (!targetSlug && statusFilter) params.set('status_filter', statusFilter)
      if (!targetSlug && activeOnly) params.set('active_only', 'true')
      const [rows, categoryRows] = await Promise.all([
        apiFetch(`/admin/services-api${params.toString() ? `?${params}` : ''}`),
        apiFetch('/admin/categories').catch(() => []),
      ])
      setItems(Array.isArray(rows) ? rows : [])
      setCategories(Array.isArray(categoryRows) ? categoryRows : [])
      if (targetSlug === 'telnyx') {
        const telnyx = await apiFetch('/admin/integrations/telnyx').catch(() => null)
        setTelnyxSettings(telnyx)
        setTelnyxDraft(telnyx?.config || {})
        setTelnyxSecret('')
      }
    } catch (e) {
      setItems([])
      setError(e?.message || 'Failed to load Services API entries')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categoryFilter, statusFilter, activeOnly, targetSlug])

  const stats = useMemo(() => {
    const rows = Array.isArray(items) ? items : []
    return {
      total: rows.length,
      active: rows.filter((x) => x.is_active).length,
      configured: rows.filter((x) => x.api_setup_exists).length,
    }
  }, [items])

  const categoryOptions = useMemo(() => {
    const seen = new Set()
    const fromAdmin = categories
      .map((category) => ({
        slug: String(category.slug || '').trim(),
        label: category.name || category.slug,
      }))
      .filter((category) => category.slug)
    return [...fromAdmin, ...CATEGORY_OPTIONS].filter((category) => {
      if (seen.has(category.slug)) return false
      seen.add(category.slug)
      return true
    })
  }, [categories])

  const categoryLabel = (slug) => categoryOptions.find((category) => category.slug === slug)?.label || slug || 'Unassigned'

  const telnyxWebhookUrl = telnyxDraft.voice_webhook_url || `${String(telnyxDraft.webhook_base_url || DEFAULT_WEBHOOK_BASE).replace(/\/+$/, '')}/telnyx/webhooks/voice`

  const setTelnyxField = (field, value) => {
    setTelnyxDraft((draft) => ({ ...draft, [field]: value }))
  }

  const saveTelnyxSettings = async () => {
    setSaving(true)
    setError('')
    setMessage('')
    setTelnyxTestResult('')
    try {
      const webhookBase = String(telnyxDraft.webhook_base_url || DEFAULT_WEBHOOK_BASE).replace(/\/+$/, '')
      const config = {
        ...telnyxDraft,
        webhook_base_url: webhookBase,
        voice_webhook_url: telnyxDraft.voice_webhook_url || `${webhookBase}/telnyx/webhooks/voice`,
        status_callback_url: telnyxDraft.status_callback_url || `${webhookBase}/telnyx/webhooks/status`,
        verified_number_webhook_url: telnyxDraft.verified_number_webhook_url || `${webhookBase}/telnyx/webhooks/verified-numbers`,
      }
      if (config.default_outbound_number && !config.from_phone_number) config.from_phone_number = config.default_outbound_number
      if (config.from_phone_number && !config.default_outbound_number) config.default_outbound_number = config.from_phone_number
      if (config.connection_id && !config.voice_api_application_id) config.voice_api_application_id = config.connection_id
      if (config.voice_api_application_id && !config.connection_id) config.connection_id = config.voice_api_application_id
      const outbound = String(config.default_outbound_number || config.from_phone_number || '').trim()
      if (outbound) {
        config.default_outbound_number = outbound
        config.from_phone_number = outbound
        config.fallback_caller_id = outbound
      }
      if (telnyxSecret.trim()) config.api_key = telnyxSecret.trim()
      const updated = await apiFetch('/admin/integrations/telnyx', {
        method: 'PUT',
        body: JSON.stringify({ is_enabled: true, config }),
      })
      setTelnyxSettings(updated)
      setTelnyxDraft(updated?.config || {})
      setTelnyxSecret('')
      setMessage('Telnyx settings saved.')
    } catch (e) {
      setError(e?.message || 'Could not save Telnyx settings')
    } finally {
      setSaving(false)
    }
  }

  const testTelnyxSettings = async () => {
    setSaving(true)
    setError('')
    setTelnyxTestResult('Testing Telnyx connection...')
    try {
      const result = await apiFetch('/admin/integrations/telnyx/test', { method: 'POST' })
      setTelnyxTestResult(result.message || 'Telnyx settings look complete.')
      await load()
    } catch (e) {
      setTelnyxTestResult('')
      setError(e?.message || 'Telnyx test failed')
    } finally {
      setSaving(false)
    }
  }

  const setDraftField = (key, value) => {
    setDraft((s) => ({ ...s, [key]: value }))
  }

  const create = async () => {
    const displayName = draft.display_name.trim()
    const slug = (draft.slug || slugify(displayName)).trim()
    if (!displayName || !slug) {
      window.alert('Integration name and slug are required.')
      return
    }
    setSaving(true)
    setError('')
    setMessage('')
    try {
      await apiFetch('/admin/services-api', {
        method: 'POST',
        body: JSON.stringify({
          ...draft,
          slug,
          display_name: displayName,
          short_description: draft.short_description.trim() || null,
          api_difficulty: draft.api_difficulty.trim() || null,
          docs_text: draft.docs_text.trim() || null,
          sort_order: Number(draft.sort_order) || 100,
        }),
      })
      setDraft(emptyDraft())
      setMessage('Service API entry created.')
      await load()
    } catch (e) {
      setError(e?.message || 'Create failed')
    } finally {
      setSaving(false)
    }
  }

  const beginEdit = (row) => {
    setEditingSlug(row.slug)
    setEdit({
      display_name: row.display_name || '',
      category_slug: row.category_slug || 'dental',
      short_description: row.short_description || '',
      status: row.status || 'active',
      is_active: Boolean(row.is_active),
      is_recommended: Boolean(row.is_recommended),
      api_difficulty: row.api_difficulty || '',
      docs_text: row.docs_text || '',
      sort_order: row.sort_order || 100,
    })
  }

  const saveEdit = async () => {
    if (!editingSlug || !edit) return
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const exists = rows.some((row) => row.slug === editingSlug)
      const payload = {
          ...edit,
          slug: editingSlug,
          short_description: edit.short_description.trim() || null,
          api_difficulty: edit.api_difficulty.trim() || null,
          docs_text: edit.docs_text.trim() || null,
          sort_order: Number(edit.sort_order) || 100,
        }
      await apiFetch(exists ? `/admin/services-api/${editingSlug}` : '/admin/services-api', {
        method: exists ? 'PATCH' : 'POST',
        body: JSON.stringify(payload),
      })
      setEditingSlug('')
      setEdit(null)
      setMessage('Service API entry updated.')
      await load()
    } catch (e) {
      setError(e?.message || 'Update failed')
    } finally {
      setSaving(false)
    }
  }

  const saveCategoryMapping = async (row, categorySlug) => {
    if (!row?.slug || !categorySlug) return
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const exists = rows.some((item) => item.slug === row.slug)
      const payload = {
        slug: row.slug,
        display_name: row.display_name,
        category_slug: categorySlug,
        short_description: row.short_description || null,
        status: row.status || 'active',
        is_active: Boolean(row.is_active),
        is_recommended: Boolean(row.is_recommended),
        api_difficulty: row.api_difficulty || null,
        docs_text: row.docs_text || null,
        sort_order: Number(row.sort_order) || 100,
      }
      await apiFetch(exists ? `/admin/services-api/${row.slug}` : '/admin/services-api', {
        method: exists ? 'PATCH' : 'POST',
        body: JSON.stringify(payload),
      })
      setMessage(`${row.display_name} now appears under ${categoryLabel(categorySlug)} in customer setup.`)
      await load()
    } catch (e) {
      setError(e?.message || 'Could not save category mapping')
    } finally {
      setSaving(false)
    }
  }

  const toggleEnabled = async (row) => {
    setSaving(true)
    setError('')
    setMessage('')
    try {
      await apiFetch(`/admin/services-api/${row.slug}/${row.is_active ? 'disable' : 'enable'}`, { method: 'POST' })
      setMessage(`${row.display_name} ${row.is_active ? 'disabled' : 'enabled'}.`)
      await load()
    } catch (e) {
      setError(e?.message || 'Could not update active state')
    } finally {
      setSaving(false)
    }
  }

  const rows = Array.isArray(items) ? items : []
  const target = targetSlug ? rows.find((row) => row.slug === targetSlug) : null
  const fallbackTarget = targetSlug ? { id: targetSlug, api_setup_exists: false, created_at: null, updated_at: null, ...SERVICE_DEFAULTS[targetSlug] } : null

  if (targetSlug) {
    const row = target || fallbackTarget
    const hasDbRow = Boolean(target)
    const editing = editingSlug === targetSlug && edit
    return (
      <>
        <div className='pageTop'>
          <div>
            <h1>Services API: {SERVICE_LABELS[targetSlug] || targetSlug}</h1>
            <p>Manage this booking/practice software definition used by tenant onboarding.</p>
          </div>
          <div className='actions'>
            <button className='btn' onClick={load} disabled={loading || saving}>{loading ? 'Refreshing…' : 'Refresh'}</button>
          </div>
        </div>

        {error && <div className='card' style={{ marginBottom: 16, borderColor: '#fecaca' }}><div className='cardBody' style={{ color: '#b91c1c', fontSize: 14 }}>{error}</div></div>}
        {message && <div className='card' style={{ marginBottom: 16, borderColor: '#bbf7d0' }}><div className='cardBody' style={{ color: '#166534', fontSize: 14 }}>{message}</div></div>}

        {!items ? (
          <div className='card'><div className='cardBody'>Loading…</div></div>
        ) : !row ? (
          <div className='card'><div className='cardBody'>No built-in metadata found for {targetSlug}.</div></div>
        ) : (
          <div className='grid-12'>
            <div className='card span-12'>
              <div className='cardHead'>
                <h3>Customer setup category mapping</h3>
                <span className='pill p-cyan'>Controls software list</span>
              </div>
              <div className='cardBody grid-12'>
                <div className='span-8'>
                  <label className='formField'>
                    <span className='label'>Show this software when customer selects</span>
                    <select
                      className='select'
                      value={row.category_slug || 'dental'}
                      onChange={(e) => saveCategoryMapping(row, e.target.value)}
                      disabled={saving}
                    >
                      {categoryOptions.map((c) => <option key={c.slug} value={c.slug}>{c.label}</option>)}
                    </select>
                    <div className='muted' style={{ fontSize: 12, lineHeight: 1.45 }}>
                      If a customer selects <strong>{categoryLabel(row.category_slug)}</strong> in dashboard setup, this software appears in the next step.
                    </div>
                  </label>
                </div>
                <div className='span-4'>
                  <div className='list-row'>
                    <strong>Current mapping</strong>
                    <p className='muted' style={{ marginBottom: 0 }}>{row.display_name} → {categoryLabel(row.category_slug)} software options</p>
                  </div>
                </div>
              </div>
            </div>
            <div className='card span-8'>
              <div className='cardHead'>
                <h3>{row.display_name}</h3>
                <span className={`pill ${statusClass(row.status)}`}>{row.status}</span>
              </div>
              <div className='cardBody stack' style={{ display: 'grid', gap: 14 }}>
                <div className='grid-12'>
                  <label className='formField span-6'>
                    <span className='label'>Integration name</span>
                    <input className='input' disabled={!editing} value={editing ? edit.display_name : row.display_name || ''} onChange={(e) => setEdit((s) => ({ ...s, display_name: e.target.value }))} />
                  </label>
                  <label className='formField span-6'>
                    <span className='label'>Category</span>
                    <select className='select' disabled={!editing} value={editing ? edit.category_slug : row.category_slug || 'dental'} onChange={(e) => setEdit((s) => ({ ...s, category_slug: e.target.value }))}>
                      {categoryOptions.map((c) => <option key={c.slug} value={c.slug}>{c.label}</option>)}
                    </select>
                    <div className='muted' style={{ fontSize: 12, lineHeight: 1.45 }}>
                      This connects {row.display_name} to a setup category. Dashboard software options are filtered by this category slug.
                    </div>
                  </label>
                  <label className='formField span-6'>
                    <span className='label'>Status</span>
                    <select className='select' disabled={!editing} value={editing ? edit.status : row.status || 'active'} onChange={(e) => setEdit((s) => ({ ...s, status: e.target.value }))}>
                      {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </label>
                  <label className='formField span-6'>
                    <span className='label'>Difficulty / label</span>
                    <input className='input' disabled={!editing} value={editing ? edit.api_difficulty : row.api_difficulty || ''} onChange={(e) => setEdit((s) => ({ ...s, api_difficulty: e.target.value }))} />
                  </label>
                  <label className='formField span-12'>
                    <span className='label'>Description</span>
                    <textarea className='input' rows={4} disabled={!editing} value={editing ? edit.short_description : row.short_description || ''} onChange={(e) => setEdit((s) => ({ ...s, short_description: e.target.value }))} />
                  </label>
                  <label className='formField span-12'>
                    <span className='label'>Docs / help text</span>
                    <textarea className='input' rows={4} disabled={!editing} value={editing ? edit.docs_text : row.docs_text || ''} onChange={(e) => setEdit((s) => ({ ...s, docs_text: e.target.value }))} />
                  </label>
                </div>
              </div>
            </div>
            <div className='card span-4'>
              <div className='cardHead'><h3>Controls</h3></div>
              <div className='cardBody stack' style={{ display: 'grid', gap: 12 }}>
                <div><span className={`pill ${row.is_active ? 'p-green' : 'p-red'}`}>{row.is_active ? 'active' : 'inactive'}</span></div>
                <div><span className={`pill ${hasDbRow ? 'p-green' : 'p-amber'}`}>{hasDbRow ? 'metadata saved' : 'default metadata only'}</span></div>
                <div><span className={`pill ${row.api_setup_exists ? 'p-green' : 'p-amber'}`}>API setup {row.api_setup_exists ? 'exists' : 'not set'}</span></div>
                {row.is_recommended ? <div><span className='pill p-cyan'>recommended</span></div> : null}
                {editing ? (
                  <div className='actions'>
                    <button className='btn primary' type='button' onClick={saveEdit} disabled={saving}>Save changes</button>
                    <button className='btn' type='button' onClick={() => { setEditingSlug(''); setEdit(null) }} disabled={saving}>Cancel</button>
                  </div>
                ) : (
                  <div className='actions'>
                    <button className='btn primary' type='button' onClick={() => beginEdit(row)} disabled={saving}>{hasDbRow ? 'Edit settings' : 'Create metadata'}</button>
                    <button className='btn soft' type='button' onClick={() => toggleEnabled(row)} disabled={saving || !hasDbRow}>{row.is_active ? 'Disable' : 'Enable'}</button>
                  </div>
                )}
              </div>
            </div>
            <div className='card span-12'>
              <div className='cardHead'><h3>Tenant setup field definitions</h3><span className='pill p-cyan'>API Settings</span></div>
              <div className='cardBody'>
                <div className='tableWrap'>
                  <table className='table'>
                    <thead>
                      <tr>
                        <th>Field</th>
                        <th>Required</th>
                        <th>Secret</th>
                        <th>Notes</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(REQUIRED_FIELDS[row.slug] || []).map((field) => (
                        <tr key={field.key}>
                          <td><strong>{field.label}</strong><div className='muted' style={{ fontSize: 12 }}>{field.key}</div></td>
                          <td><span className={`pill ${field.needed ? 'p-green' : 'p-amber'}`}>{field.needed ? 'yes' : 'optional'}</span></td>
                          <td><span className={`pill ${field.secret ? 'p-red' : 'p-cyan'}`}>{field.secret ? 'masked' : 'plain'}</span></td>
                          <td>{field.notes}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
            {row.slug === 'telnyx' ? (
              <div className='card span-12'>
                <div className='cardHead'>
                  <h3>Telnyx secure settings</h3>
                  <span className={`pill ${telnyxSettings?.configured ? 'p-green' : 'p-amber'}`}>{telnyxSettings?.configured ? 'Configured' : 'Incomplete'}</span>
                </div>
                <div className='cardBody grid-12'>
                  <label className='formField span-6'>
                    <span className='label'>Telnyx API key</span>
                    <input className='input' type='password' value={telnyxSecret} onChange={(e) => setTelnyxSecret(e.target.value)} placeholder={telnyxSettings?.secret_set?.api_key ? 'Leave blank to keep current key' : 'Paste Telnyx API key'} />
                  </label>
                  <label className='formField span-6'>
                    <span className='label'>Voice API application / connection ID</span>
                    <input className='input' value={telnyxDraft.connection_id || telnyxDraft.voice_api_application_id || ''} onChange={(e) => { setTelnyxField('connection_id', e.target.value); setTelnyxField('voice_api_application_id', e.target.value) }} />
                  </label>
                  <label className='formField span-6'>
                    <span className='label'>From phone number</span>
                    <input className='input' value={telnyxDraft.default_outbound_number || telnyxDraft.from_phone_number || ''} onChange={(e) => { setTelnyxField('default_outbound_number', e.target.value); setTelnyxField('from_phone_number', e.target.value) }} placeholder='+44...' />
                  </label>
                  <label className='formField span-6'>
                    <span className='label'>Outbound voice profile ID</span>
                    <input className='input' value={telnyxDraft.outbound_voice_profile_id || ''} onChange={(e) => setTelnyxField('outbound_voice_profile_id', e.target.value)} />
                  </label>
                  <label className='formField span-6'>
                    <span className='label'>Webhook base URL</span>
                    <input className='input' value={telnyxDraft.webhook_base_url || DEFAULT_WEBHOOK_BASE} onChange={(e) => setTelnyxField('webhook_base_url', e.target.value)} />
                  </label>
                  <label className='formField span-6'>
                    <span className='label'>Status callback URL</span>
                    <input className='input' value={telnyxDraft.status_callback_url || `${DEFAULT_WEBHOOK_BASE}/telnyx/webhooks/status`} onChange={(e) => setTelnyxField('status_callback_url', e.target.value)} />
                  </label>
                  <label className='formField span-12'>
                    <span className='label'>Webhook URL display/copy field</span>
                    <div className='actions'>
                      <input className='input' value={telnyxWebhookUrl} onChange={(e) => setTelnyxField('voice_webhook_url', e.target.value)} />
                      <button className='btn soft' type='button' onClick={() => copyText(telnyxWebhookUrl)}>Copy</button>
                    </div>
                  </label>
                  <label className='formField span-12'>
                    <span className='label'>Media stream WebSocket URL</span>
                    <input className='input' value={telnyxDraft.media_stream_url || ''} onChange={(e) => setTelnyxField('media_stream_url', e.target.value)} placeholder='wss://...' />
                  </label>
                  <div className='span-12 note'>
                    Missing: {(telnyxSettings?.missing_fields || []).join(', ') || 'none'}.
                  </div>
                  {telnyxTestResult ? <div className='span-12 note'>{telnyxTestResult}</div> : null}
                  <div className='span-12 actions'>
                    <button className='btn primary' type='button' disabled={saving} onClick={saveTelnyxSettings}>{saving ? 'Saving...' : 'Save Telnyx settings'}</button>
                    <button className='btn soft' type='button' disabled={saving || !telnyxSettings?.exists} onClick={testTelnyxSettings}>Test connection</button>
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        )}
      </>
    )
  }

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>Services API</h1>
          <p>Manage supported booking and practice software that organisations can select during onboarding.</p>
        </div>
        <div className='actions'>
          <button className='btn' onClick={load} disabled={loading || saving}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      {error && (
        <div className='card' style={{ marginBottom: 16, borderColor: '#fecaca' }}>
          <div className='cardBody' style={{ color: '#b91c1c', fontSize: 14 }}>
            {error}
          </div>
        </div>
      )}
      {message && (
        <div className='card' style={{ marginBottom: 16, borderColor: '#bbf7d0' }}>
          <div className='cardBody' style={{ color: '#166534', fontSize: 14 }}>
            {message}
          </div>
        </div>
      )}

      <div className='grid-12' style={{ marginBottom: 16 }}>
        <div className='card span-4'>
          <div className='cardBody'>
            <div className='statLabel'>Entries</div>
            <div className='statValue'>{stats.total}</div>
          </div>
        </div>
        <div className='card span-4'>
          <div className='cardBody'>
            <div className='statLabel'>Active</div>
            <div className='statValue'>{stats.active}</div>
          </div>
        </div>
        <div className='card span-4'>
          <div className='cardBody'>
            <div className='statLabel'>API setup exists</div>
            <div className='statValue'>{stats.configured}</div>
          </div>
        </div>
      </div>

      <div className='categoriesPageGrid'>
        <div className='stack'>
          <div className='card'>
            <div className='cardHead'>
              <h3>New service API</h3>
              <span className='pill p-cyan'>Platform</span>
            </div>
            <div className='cardBody stack' style={{ display: 'grid', gap: 12 }}>
              <label className='formField'>
                <span className='label'>Integration name</span>
                <input
                  className='input'
                  value={draft.display_name}
                  onChange={(e) => setDraftField('display_name', e.target.value)}
                  placeholder='e.g. Dentally'
                />
              </label>
              <label className='formField'>
                <span className='label'>Slug</span>
                <input
                  className='input'
                  value={draft.slug}
                  onChange={(e) => setDraftField('slug', slugify(e.target.value))}
                  placeholder='auto from name'
                />
              </label>
              <label className='formField'>
                <span className='label'>Category</span>
                <select className='select' value={draft.category_slug} onChange={(e) => setDraftField('category_slug', e.target.value)}>
                  {categoryOptions.map((c) => <option key={c.slug} value={c.slug}>{c.label}</option>)}
                </select>
                <div className='muted' style={{ fontSize: 12, lineHeight: 1.45 }}>
                  Add or edit categories under Organisations → Categories. The selected category controls where this software appears in dashboard setup.
                </div>
              </label>
              <label className='formField'>
                <span className='label'>Status</span>
                <select className='select' value={draft.status} onChange={(e) => setDraftField('status', e.target.value)}>
                  {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </label>
              <label className='formField'>
                <span className='label'>Short description</span>
                <textarea
                  className='input'
                  rows={3}
                  value={draft.short_description}
                  onChange={(e) => setDraftField('short_description', e.target.value)}
                  placeholder='What this integration supports…'
                />
              </label>
              <label className='formField'>
                <span className='label'>API difficulty / flag</span>
                <input
                  className='input'
                  value={draft.api_difficulty}
                  onChange={(e) => setDraftField('api_difficulty', e.target.value)}
                  placeholder='easy API, beta, recommended'
                />
              </label>
              <label className='checkbox-row' style={{ alignItems: 'center' }}>
                <input type='checkbox' checked={draft.is_active} onChange={(e) => setDraftField('is_active', e.target.checked)} />
                Active
              </label>
              <label className='checkbox-row' style={{ alignItems: 'center' }}>
                <input type='checkbox' checked={draft.is_recommended} onChange={(e) => setDraftField('is_recommended', e.target.checked)} />
                Recommended
              </label>
              <button type='button' className='btn primary' onClick={create} disabled={saving}>
                {saving ? 'Saving…' : 'Create service API'}
              </button>
            </div>
          </div>
        </div>

        <div className='stack' style={{ minWidth: 0 }}>
          <div className='card'>
            <div className='cardHead'>
              <h3>Supported integrations</h3>
              <span className='pill p-cyan'>{rows.length}</span>
            </div>
            <div className='cardBody'>
              <div className='actions' style={{ marginBottom: 12 }}>
                <select className='select' value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
                  <option value=''>All categories</option>
                  {categoryOptions.map((c) => <option key={c.slug} value={c.slug}>{c.label}</option>)}
                </select>
                <select className='select' value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                  <option value=''>All statuses</option>
                  {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
                <label className='checkbox-row' style={{ width: 'auto' }}>
                  <input type='checkbox' checked={activeOnly} onChange={(e) => setActiveOnly(e.target.checked)} />
                  Active only
                </label>
              </div>
              <div className='tableWrap'>
                <table className='table'>
                  <thead>
                    <tr>
                      <th>Integration</th>
                      <th>Category</th>
                      <th>Description</th>
                      <th>Status</th>
                      <th>Flags</th>
                      <th>API setup</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {!items && (
                      <tr>
                        <td colSpan={7}>Loading…</td>
                      </tr>
                    )}
                    {rows.map((row) => {
                      const editing = editingSlug === row.slug && edit
                      return (
                        <tr key={row.slug}>
                          <td>
                            {editing ? (
                              <input className='input' value={edit.display_name} onChange={(e) => setEdit((s) => ({ ...s, display_name: e.target.value }))} />
                            ) : (
                              <div>
                                <strong>{row.display_name}</strong>
                                <div className='muted' style={{ fontSize: 12 }}>{row.slug}</div>
                              </div>
                            )}
                          </td>
                          <td>
                            {editing ? (
                              <select className='select' value={edit.category_slug} onChange={(e) => setEdit((s) => ({ ...s, category_slug: e.target.value }))}>
                                {categoryOptions.map((c) => <option key={c.slug} value={c.slug}>{c.label}</option>)}
                              </select>
                            ) : (
                              <div>
                                <strong>{categoryLabel(row.category_slug)}</strong>
                                <div className='muted' style={{ fontSize: 12 }}>{row.category_slug}</div>
                              </div>
                            )}
                          </td>
                          <td>
                            {editing ? (
                              <textarea className='input' rows={2} value={edit.short_description} onChange={(e) => setEdit((s) => ({ ...s, short_description: e.target.value }))} />
                            ) : row.short_description || '—'}
                          </td>
                          <td>
                            {editing ? (
                              <select className='select' value={edit.status} onChange={(e) => setEdit((s) => ({ ...s, status: e.target.value }))}>
                                {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
                              </select>
                            ) : (
                              <span className={`pill ${statusClass(row.status)}`}>{row.status}</span>
                            )}
                            <div style={{ marginTop: 6 }}>
                              <span className={`pill ${row.is_active ? 'p-green' : 'p-red'}`}>{row.is_active ? 'active' : 'inactive'}</span>
                            </div>
                          </td>
                          <td>
                            {editing ? (
                              <div className='stack' style={{ gap: 8 }}>
                                <label className='checkbox-row'>
                                  <input type='checkbox' checked={edit.is_recommended} onChange={(e) => setEdit((s) => ({ ...s, is_recommended: e.target.checked }))} />
                                  Recommended
                                </label>
                                <input className='input' value={edit.api_difficulty} onChange={(e) => setEdit((s) => ({ ...s, api_difficulty: e.target.value }))} />
                              </div>
                            ) : (
                              <>
                                {row.is_recommended ? <span className='pill p-cyan'>recommended</span> : null}
                                {row.api_difficulty ? <span className='pill p-amber' style={{ marginLeft: row.is_recommended ? 6 : 0 }}>{row.api_difficulty}</span> : null}
                                {!row.is_recommended && !row.api_difficulty ? '—' : null}
                              </>
                            )}
                          </td>
                          <td>
                            <span className={`pill ${row.api_setup_exists ? 'p-green' : 'p-amber'}`}>
                              {row.api_setup_exists ? 'exists' : 'not set'}
                            </span>
                            <div className='muted' style={{ fontSize: 12, marginTop: 6 }}>
                              Fields: {(REQUIRED_FIELDS[row.slug] || []).map((field) => field.label).join(', ') || '—'}
                            </div>
                          </td>
                          <td>
                            <div className='actions'>
                              {editing ? (
                                <>
                                  <button className='btn primary' type='button' onClick={saveEdit} disabled={saving}>Save</button>
                                  <button className='btn' type='button' onClick={() => { setEditingSlug(''); setEdit(null) }} disabled={saving}>Cancel</button>
                                </>
                              ) : (
                                <>
                                  <button className='btn' type='button' onClick={() => beginEdit(row)} disabled={saving}>Edit</button>
                                  <button className='btn soft' type='button' onClick={() => toggleEnabled(row)} disabled={saving}>
                                    {row.is_active ? 'Disable' : 'Enable'}
                                  </button>
                                </>
                              )}
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                    {items && rows.length === 0 && (
                      <tr>
                        <td colSpan={7}>No service API entries match the filters.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

