import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Copy,
  Info,
  ListChecks,
  MessageCircle,
  Pencil,
  Phone,
  Plug,
  Plus,
  RefreshCw,
  Trash2,
  X,
} from 'lucide-react'
import { apiFetch } from '../lib/api'
import '../styles/connection-profiles-hub.css'

const SERVICE_LABELS = {
  ai_interview: 'AI Interview',
  survey: 'Survey',
  customer_feedback: 'Customer Feedback',
  booking: 'Booking',
  marketing: 'Marketing',
}

const DEFAULT_SERVICE_CODES = ['ai_interview', 'survey', 'customer_feedback']
const PAGE_SIZE = 50

function providerDisplay(provider) {
  return String(provider || '').toLowerCase() === 'meta' ? 'Meta' : 'Telnyx'
}

function defaultServices(codes) {
  const out = {}
  ;(codes || []).forEach((code) => {
    out[code] = DEFAULT_SERVICE_CODES.includes(code)
  })
  return out
}

function allServicesOn(codes) {
  const out = {}
  ;(codes || []).forEach((code) => {
    out[code] = true
  })
  return out
}

function allServicesOff(codes) {
  const out = {}
  ;(codes || []).forEach((code) => {
    out[code] = false
  })
  return out
}

function normalizeOrgIds(orgIds) {
  return (orgIds || []).map((id) => String(id).trim()).filter(Boolean)
}

function enabledServiceCodes(services, serviceCodes) {
  return (serviceCodes || []).filter((code) => services?.[code])
}

function findServiceConflicts({ profiles, channel, editingId, isDefault, orgIds, services, serviceCodes }) {
  const enabled = enabledServiceCodes(services, serviceCodes)
  const conflicts = []
  const others = (profiles || []).filter(
    (p) => p.channel === channel && p.id !== editingId && p.is_active,
  )
  const myOrgs = normalizeOrgIds(orgIds)

  for (const code of enabled) {
    for (const other of others) {
      if (!other.services?.[code]) continue
      const label = SERVICE_LABELS[code] || code
      if (!isDefault && !other.is_default) {
        const overlap = myOrgs.filter((id) => (other.org_ids || []).includes(id))
        if (overlap.length) {
          conflicts.push({ service: label, profileName: other.name, orgIds: overlap })
        }
      }
    }
  }
  return conflicts
}

function buildProfileGuidance({ isDefault, isActive, orgIds, serviceCodes, services, conflicts, channelLabel }) {
  const orgLines = []
  const serviceLines = []

  if (isDefault) {
    orgLines.push(`${channelLabel} default profile applies to all organizations automatically.`)
    serviceLines.push('Toggle ON only the services this default line should handle.')
  } else if (isActive) {
    orgLines.push('Dedicated profile: use the picker below to assign one or more organizations.')
    orgLines.push('Only assigned organizations use this profile instead of the default Telnyx line.')
    if (!normalizeOrgIds(orgIds).length) {
      orgLines.push('⚠ Assign at least one organization — this profile is ignored until you do.')
    }
    const enabled = enabledServiceCodes(services, serviceCodes)
    if (enabled.length) {
      serviceLines.push(
        `Assigned organizations will use this line for: ${enabled.map((c) => SERVICE_LABELS[c] || c).join(', ')}.`,
      )
    }
  } else {
    orgLines.push('Profile is inactive — turn Active ON, then assign organizations if not default.')
  }

  return { orgLines, serviceLines, conflicts }
}

function OrgMultiSelect({ orgOptions, selectedOrgIds, onChange, inputId, tagsId, disabled = false, placeholder }) {
  const [query, setQuery] = useState('')
  const [showSuggestions, setShowSuggestions] = useState(false)

  const selectedNames = selectedOrgIds
    .map((id) => orgOptions.find((o) => o.id === id))
    .filter(Boolean)

  const availableOrgs = useMemo(
    () => orgOptions.filter((o) => !selectedOrgIds.includes(o.id)),
    [orgOptions, selectedOrgIds],
  )

  const suggestions = useMemo(() => {
    const q = query.toLowerCase().trim()
    const pool = q
      ? availableOrgs.filter((o) => String(o.name || '').toLowerCase().includes(q))
      : availableOrgs
    return pool.slice(0, 50)
  }, [availableOrgs, query])

  const addOrg = (org) => {
    if (!org || selectedOrgIds.includes(org.id)) return
    onChange([...selectedOrgIds, org.id])
    setQuery('')
    setShowSuggestions(false)
  }

  const removeOrg = (orgId) => {
    onChange(selectedOrgIds.filter((id) => id !== orgId))
  }

  return (
    <div className={`org-picker${disabled ? ' org-picker-disabled' : ''}`}>
      <div className={`multi-select${disabled ? ' multi-select-disabled' : ''}`}>
        <div id={tagsId} style={{ display: 'flex', flexWrap: 'wrap', gap: '0.2rem', alignItems: 'center' }}>
          {selectedNames.length ? (
            selectedNames.map((org) => (
              <span key={org.id} className='tag'>
                {org.name}
                {!disabled ? (
                  <button type='button' className='remove-tag' onClick={() => removeOrg(org.id)}>
                    ×
                  </button>
                ) : null}
              </span>
            ))
          ) : (
            <span className='org-picker-empty'>No organizations selected</span>
          )}
        </div>
        <input
          id={inputId}
          type='text'
          value={query}
          placeholder={placeholder || 'Type to search organizations…'}
          autoComplete='off'
          disabled={disabled}
          onChange={(e) => {
            setQuery(e.target.value)
            setShowSuggestions(true)
          }}
          onFocus={() => !disabled && setShowSuggestions(true)}
          onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && suggestions[0]) {
              e.preventDefault()
              addOrg(suggestions[0])
            }
          }}
        />
        <div className={`org-suggestions${showSuggestions && suggestions.length ? ' show' : ''}`}>
          {suggestions.map((org) => (
            <div
              key={org.id}
              className='suggestion-item'
              role='button'
              tabIndex={0}
              onMouseDown={() => addOrg(org)}
            >
              {org.name}
            </div>
          ))}
        </div>
      </div>
      {!disabled ? (
        <div className='org-picker-menu'>
          <label className='org-picker-menu-label' htmlFor={`${inputId}-select`}>
            Add organization
          </label>
          <select
            id={`${inputId}-select`}
            className='org-picker-select'
            value=''
            onChange={(e) => {
              const org = orgOptions.find((o) => o.id === e.target.value)
              if (org) addOrg(org)
            }}
          >
            <option value=''>— Choose organization —</option>
            {availableOrgs.map((org) => (
              <option key={org.id} value={org.id}>
                {org.name}
              </option>
            ))}
          </select>
          <span className='org-picker-count'>
            {selectedOrgIds.length} selected · {availableOrgs.length} available
          </span>
        </div>
      ) : null}
    </div>
  )
}

function ServiceGrid({ serviceCodes, services, onChange }) {
  return (
    <div className='service-grid'>
      {serviceCodes.map((code) => (
        <div key={code} className='service-item'>
          <label className='toggle-switch service-toggle'>
            <input
              type='checkbox'
              checked={!!services[code]}
              onChange={() => onChange({ ...services, [code]: !services[code] })}
            />
            <span className='toggle-slider' />
          </label>
          <span className='service-label'>{SERVICE_LABELS[code] || code}</span>
        </div>
      ))}
    </div>
  )
}

function ProfileServicesInfo({ lines, conflicts, orgNameById, variant = 'info' }) {
  if (!lines.length && !conflicts.length) return null
  return (
    <div className={`info-box${variant === 'warn' ? ' info-box-warn' : ''}`}>
      <Info />
      <span>
        {lines.map((line, idx) => (
          <span key={idx}>
            {idx > 0 ? ' ' : null}
            {line}
          </span>
        ))}
        {conflicts.length ? (
          <>
            {' '}
            <strong>Conflict:</strong>{' '}
            {conflicts
              .map((c) => {
                const orgNames = c.orgIds.map((id) => orgNameById[id] || id).join(', ')
                return `${c.service} already enabled on “${c.profileName}” for ${orgNames}`
              })
              .join('; ')}
            .
          </>
        ) : null}
      </span>
    </div>
  )
}

function MaskField({ value, onChange, placeholder, savedHint }) {
  const [visible, setVisible] = useState(false)
  const inputId = React.useId()
  return (
    <div className='mask-wrapper'>
      <input
        id={inputId}
        type={visible ? 'text' : 'password'}
        value={value}
        placeholder={savedHint || placeholder}
        autoComplete='new-password'
        onChange={(e) => onChange(e.target.value)}
      />
      <button type='button' className='toggle-btn' onClick={() => setVisible((v) => !v)}>
        {visible ? 'hide' : 'show'}
      </button>
    </div>
  )
}

function CopyField({ value }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className='inline-flex' style={{ width: '100%' }}>
      <input type='text' readOnly value={value} />
      <button
        type='button'
        className='copy-btn'
        onClick={() => {
          navigator.clipboard?.writeText(value).catch(() => {})
          setCopied(true)
          setTimeout(() => setCopied(false), 1200)
        }}
      >
        {copied ? (
          <>
            <Check /> copied
          </>
        ) : (
          <>
            <Copy /> copy
          </>
        )}
      </button>
    </div>
  )
}

const emptyWaForm = (serviceCodes) => ({
  name: '',
  provider: 'telnyx',
  is_default: false,
  is_active: true,
  telnyx_api_key: '',
  telnyx_messaging_profile_id: '',
  telnyx_number: '',
  meta_waba_id: '',
  meta_phone_number_id: '',
  meta_business_id: '',
  meta_access_token: '',
  meta_app_secret: '',
  meta_webhook_verify_token: '',
  meta_whatsapp_from: '',
  org_ids: [],
  services: defaultServices(serviceCodes),
  has_telnyx_api_key: false,
  has_meta_access_token: false,
  has_meta_app_secret: false,
  has_meta_webhook_verify_token: false,
})

const emptyCallingForm = (serviceCodes) => ({
  name: '',
  is_default: false,
  is_active: true,
  calling_number: '',
  org_ids: [],
  services: defaultServices(serviceCodes),
})

export default function ConnectionProfiles() {
  const [tab, setTab] = useState('whatsapp')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [profiles, setProfiles] = useState([])
  const [webhookUrls, setWebhookUrls] = useState({})
  const [serviceCodes, setServiceCodes] = useState([])
  const [orgOptions, setOrgOptions] = useState([])

  const [waFormOpen, setWaFormOpen] = useState(false)
  const [callingFormOpen, setCallingFormOpen] = useState(false)
  const [editingWaId, setEditingWaId] = useState('')
  const [editingCallingId, setEditingCallingId] = useState('')
  const [waForm, setWaForm] = useState(emptyWaForm([]))
  const [callingForm, setCallingForm] = useState(emptyCallingForm([]))
  const [waTestResult, setWaTestResult] = useState({ text: '', kind: '' })
  const [callingTestResult, setCallingTestResult] = useState({ text: '', kind: '' })
  const [defaultNote, setDefaultNote] = useState('only one default per channel')

  const waGuidance = useMemo(
    () =>
      buildProfileGuidance({
        isDefault: !!waForm.is_default,
        isActive: !!waForm.is_active,
        orgIds: waForm.org_ids,
        serviceCodes,
        services: waForm.services,
        conflicts: findServiceConflicts({
          profiles,
          channel: 'whatsapp',
          editingId: editingWaId,
          isDefault: !!waForm.is_default,
          orgIds: waForm.org_ids,
          services: waForm.services,
          serviceCodes,
        }),
        channelLabel: 'WhatsApp',
      }),
    [waForm.is_default, waForm.is_active, waForm.org_ids, waForm.services, profiles, editingWaId, serviceCodes],
  )

  const callingGuidance = useMemo(
    () =>
      buildProfileGuidance({
        isDefault: !!callingForm.is_default,
        isActive: !!callingForm.is_active,
        orgIds: callingForm.org_ids,
        serviceCodes,
        services: callingForm.services,
        conflicts: findServiceConflicts({
          profiles,
          channel: 'calling',
          editingId: editingCallingId,
          isDefault: !!callingForm.is_default,
          orgIds: callingForm.org_ids,
          services: callingForm.services,
          serviceCodes,
        }),
        channelLabel: 'Calling',
      }),
    [
      callingForm.is_default,
      callingForm.is_active,
      callingForm.org_ids,
      callingForm.services,
      profiles,
      editingCallingId,
      serviceCodes,
    ],
  )

  const [sortKey, setSortKey] = useState('name')
  const [sortAsc, setSortAsc] = useState(true)
  const [currentPage, setCurrentPage] = useState(1)

  const waProfiles = useMemo(() => profiles.filter((p) => p.channel === 'whatsapp'), [profiles])
  const callingProfiles = useMemo(() => profiles.filter((p) => p.channel === 'calling'), [profiles])

  const orgNameById = useMemo(() => {
    const map = {}
    orgOptions.forEach((o) => {
      map[o.id] = o.name
    })
    return map
  }, [orgOptions])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [data, orgs] = await Promise.all([
        apiFetch('/admin/connection-profiles'),
        apiFetch('/admin/organisations?limit=500').catch(() => []),
      ])
      const codes = Array.isArray(data?.service_codes) ? data.service_codes : Object.keys(SERVICE_LABELS)
      setProfiles(Array.isArray(data?.profiles) ? data.profiles : [])
      setWebhookUrls(data?.webhook_urls || {})
      setServiceCodes(codes)
      const embedded = Array.isArray(data?.org_options) ? data.org_options : []
      const orgRows = embedded.length
        ? embedded
        : Array.isArray(orgs?.items)
          ? orgs.items
          : Array.isArray(orgs)
            ? orgs
            : []
      setOrgOptions(orgRows.map((o) => ({ id: o.id, name: o.name || o.trading_name || o.id })))
    } catch (e) {
      window.alert(e?.message || 'Failed to load connection profiles')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (serviceCodes.length) {
      setWaForm((prev) => ({ ...prev, services: { ...defaultServices(serviceCodes), ...prev.services } }))
      setCallingForm((prev) => ({ ...prev, services: { ...defaultServices(serviceCodes), ...prev.services } }))
    }
  }, [serviceCodes])

  const sortedWaProfiles = useMemo(() => {
    const sorted = [...waProfiles].sort((a, b) => {
      let va = a[sortKey] ?? ''
      let vb = b[sortKey] ?? ''
      if (sortKey === 'provider') {
        va = providerDisplay(va)
        vb = providerDisplay(vb)
      }
      if (typeof va === 'string') va = va.toLowerCase()
      if (typeof vb === 'string') vb = vb.toLowerCase()
      if (va < vb) return sortAsc ? -1 : 1
      if (va > vb) return sortAsc ? 1 : -1
      return 0
    })
    return sorted
  }, [waProfiles, sortAsc, sortKey])

  const totalPages = Math.max(1, Math.ceil(sortedWaProfiles.length / PAGE_SIZE))
  const pageItems = sortedWaProfiles.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  const toggleSort = (key) => {
    if (sortKey === key) setSortAsc((v) => !v)
    else {
      setSortKey(key)
      setSortAsc(true)
    }
  }

  const clearWaForm = () => {
    setEditingWaId('')
    setWaForm(emptyWaForm(serviceCodes))
    setWaTestResult({ text: '', kind: '' })
    setDefaultNote('only one default per channel')
  }

  const clearCallingForm = () => {
    setEditingCallingId('')
    setCallingForm(emptyCallingForm(serviceCodes))
    setCallingTestResult({ text: '', kind: '' })
  }

  const loadWaProfile = (profile) => {
    setEditingWaId(profile.id)
    setWaForm({
      ...emptyWaForm(serviceCodes),
      ...profile,
      telnyx_api_key: '',
      meta_access_token: '',
      meta_app_secret: '',
      meta_webhook_verify_token: '',
      services: { ...defaultServices(serviceCodes), ...(profile.services || {}) },
      org_ids: [...(profile.org_ids || [])],
    })
    setDefaultNote(profile.is_default ? 'replaces current default' : 'only one default per channel')
    setWaTestResult(
      profile.last_test_detail
        ? {
            text: profile.last_test_status === 'ok' ? `✓ ${profile.last_test_detail}` : `✗ ${profile.last_test_detail}`,
            kind: profile.last_test_status === 'ok' ? 'success' : 'fail',
          }
        : { text: '', kind: '' },
    )
    setWaFormOpen(true)
  }

  const loadCallingProfile = (profile) => {
    setEditingCallingId(profile.id)
    setCallingForm({
      ...emptyCallingForm(serviceCodes),
      ...profile,
      services: { ...defaultServices(serviceCodes), ...(profile.services || {}) },
      org_ids: [...(profile.org_ids || [])],
    })
    setCallingTestResult({ text: '', kind: '' })
    setCallingFormOpen(true)
  }

  const saveWaProfile = async () => {
    const name = String(waForm.name || '').trim()
    const provider = String(waForm.provider || 'telnyx').toLowerCase()
    if (!name) {
      window.alert('Name and Provider are required.')
      return
    }
    if (provider === 'meta') {
      const phoneNumberId = String(waForm.meta_phone_number_id || '').trim()
      if (phoneNumberId.startsWith('+') || /\s/.test(phoneNumberId)) {
        window.alert(
          'Phone Number ID must be the Meta Cloud API numeric ID (e.g. 1307579342430096), not the +44 display number.',
        )
        return
      }
      if (
        !String(waForm.meta_waba_id || '').trim() ||
        !String(waForm.meta_phone_number_id || '').trim() ||
        !String(waForm.meta_business_id || '').trim() ||
        (!String(waForm.meta_access_token || '').trim() && !waForm.has_meta_access_token) ||
        (!String(waForm.meta_webhook_verify_token || '').trim() && !waForm.has_meta_webhook_verify_token) ||
        (!String(waForm.meta_app_secret || '').trim() && !waForm.has_meta_app_secret)
      ) {
        window.alert('All Meta fields are required.')
        return
      }
    } else if (!String(waForm.telnyx_messaging_profile_id || '').trim() || !String(waForm.telnyx_number || '').trim()) {
      window.alert('Messaging Profile ID and Phone Number are required for Telnyx.')
      return
    }

    if (waForm.is_active && !waForm.is_default && !normalizeOrgIds(waForm.org_ids).length) {
      window.alert('Assign at least one organization — active non-default profiles are only used for assigned orgs.')
      return
    }
    if (waGuidance.conflicts.length) {
      const msg = waGuidance.conflicts
        .map((c) => `${c.service} on “${c.profileName}”`)
        .join('; ')
      if (!window.confirm(`Service conflict for the same organization(s): ${msg}. Save anyway?`)) return
    }

    setSaving(true)
    try {
      const payload = {
        ...waForm,
        channel: 'whatsapp',
        provider,
        org_ids: waForm.is_default ? [] : normalizeOrgIds(waForm.org_ids),
      }
      const saved = editingWaId
        ? await apiFetch(`/admin/connection-profiles/${encodeURIComponent(editingWaId)}`, {
            method: 'PUT',
            body: JSON.stringify(payload),
          })
        : await apiFetch('/admin/connection-profiles', { method: 'POST', body: JSON.stringify(payload) })
      await load()
      clearWaForm()
      setWaFormOpen(false)
      if (saved?.id) setEditingWaId(saved.id)
    } catch (e) {
      window.alert(e?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const saveCallingProfile = async () => {
    const name = String(callingForm.name || '').trim()
    const phone = String(callingForm.calling_number || '').trim()
    if (!name || !phone) {
      window.alert('Name and Phone Number are required.')
      return
    }
    if (callingForm.is_active && !callingForm.is_default && !normalizeOrgIds(callingForm.org_ids).length) {
      window.alert('Assign at least one organization — active non-default profiles are only used for assigned orgs.')
      return
    }
    if (callingGuidance.conflicts.length) {
      const msg = callingGuidance.conflicts
        .map((c) => `${c.service} on “${c.profileName}”`)
        .join('; ')
      if (!window.confirm(`Service conflict for the same organization(s): ${msg}. Save anyway?`)) return
    }

    setSaving(true)
    try {
      const payload = {
        ...callingForm,
        channel: 'calling',
        provider: 'telnyx',
        calling_number: phone,
        org_ids: callingForm.is_default ? [] : normalizeOrgIds(callingForm.org_ids),
      }
      if (editingCallingId) {
        await apiFetch(`/admin/connection-profiles/${encodeURIComponent(editingCallingId)}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        })
      } else {
        await apiFetch('/admin/connection-profiles', { method: 'POST', body: JSON.stringify(payload) })
      }
      await load()
      clearCallingForm()
      setCallingFormOpen(false)
    } catch (e) {
      window.alert(e?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const testWaProfile = async () => {
    if (!editingWaId) {
      setWaTestResult({ text: 'Save profile first', kind: 'fail' })
      return
    }
    setTesting(true)
    setWaTestResult({ text: 'testing...', kind: '' })
    try {
      const result = await apiFetch(`/admin/connection-profiles/${encodeURIComponent(editingWaId)}/test`, {
        method: 'POST',
        body: JSON.stringify({}),
      })
      setWaTestResult({
        text: result?.ok ? '✓ connected' : `✗ ${String(result?.detail || 'failed').trim()}`,
        kind: result?.ok ? 'success' : 'fail',
      })
      await load()
    } catch (e) {
      setWaTestResult({ text: `✗ ${e?.message || 'failed'}`, kind: 'fail' })
    } finally {
      setTesting(false)
    }
  }

  const testCallingProfile = async () => {
    if (!editingCallingId) {
      setCallingTestResult({ text: 'Save profile first', kind: 'fail' })
      return
    }
    setTesting(true)
    setCallingTestResult({ text: 'testing...', kind: '' })
    try {
      const result = await apiFetch(`/admin/connection-profiles/${encodeURIComponent(editingCallingId)}/test`, {
        method: 'POST',
        body: JSON.stringify({}),
      })
      setCallingTestResult({
        text: result?.ok ? '✓ connected' : `✗ ${String(result?.detail || 'failed').trim()}`,
        kind: result?.ok ? 'success' : 'fail',
      })
      await load()
    } catch (e) {
      setCallingTestResult({ text: `✗ ${e?.message || 'failed'}`, kind: 'fail' })
    } finally {
      setTesting(false)
    }
  }

  const deleteProfile = async (id) => {
    if (!window.confirm('Delete this profile?')) return
    try {
      await apiFetch(`/admin/connection-profiles/${encodeURIComponent(id)}`, { method: 'DELETE' })
      if (editingWaId === id) {
        clearWaForm()
        setWaFormOpen(false)
      }
      if (editingCallingId === id) {
        clearCallingForm()
        setCallingFormOpen(false)
      }
      await load()
    } catch (e) {
      window.alert(e?.message || 'Delete failed')
    }
  }

  const renderServiceBadges = (services) => {
    const active = serviceCodes.filter((c) => services?.[c])
    if (!active.length) {
      return DEFAULT_SERVICE_CODES.map((c) => (
        <span key={c} className='badge badge-service'>
          {SERVICE_LABELS[c]}
        </span>
      ))
    }
    return active.map((c) => (
      <span key={c} className='badge badge-service'>
        {SERVICE_LABELS[c] || c}
      </span>
    ))
  }

  const renderOrgBadges = (orgIds) => {
    if (!orgIds?.length) return '—'
    return orgIds.map((id) => (
      <span key={id} className='badge badge-org'>
        {orgNameById[id] || id}
      </span>
    ))
  }

  const telnyxWebhook = webhookUrls.telnyx_whatsapp || 'https://api.voxbulk.com/telnyx/webhooks/messages'
  const metaWebhook = webhookUrls.meta_whatsapp || 'https://api.voxbulk.com/webhooks/meta/whatsapp'
  const isMeta = String(waForm.provider || '').toLowerCase() === 'meta'

  return (
    <div className='pageShell connectionProfilesPageShell'>
      <div className='connectionProfilesHub'>
        <div className='page' id='app'>
      <div className='tabs'>
        <button type='button' className={`tab-btn${tab === 'whatsapp' ? ' active' : ''}`} onClick={() => setTab('whatsapp')}>
          <MessageCircle /> WhatsApp
        </button>
        <button type='button' className={`tab-btn${tab === 'calling' ? ' active' : ''}`} onClick={() => setTab('calling')}>
          <Phone /> Calling
        </button>
      </div>

      {/* WHATSAPP TAB */}
      <div id='tab-whatsapp' className={`tab-content${tab === 'whatsapp' ? ' active' : ''}`}>
        <div className='create-btn-wrap'>
          <button
            type='button'
            className='btn btn-primary btn-sm'
            onClick={() => {
              if (waFormOpen) {
                setWaFormOpen(false)
                clearWaForm()
              } else {
                clearWaForm()
                setWaFormOpen(true)
              }
            }}
          >
            <Plus /> New WhatsApp
          </button>
        </div>

        <div className={`form-container${waFormOpen ? ' open' : ''}`} id='whatsappFormContainer'>
          <div className='section'>
            <div className='section-title'>
              <MessageCircle />
              <span>{editingWaId ? 'Edit WhatsApp profile' : 'Create WhatsApp profile'}</span>
            </div>
            <form autoComplete='off' onSubmit={(e) => e.preventDefault()}>
              <div className='form-grid'>
                <div className='field-group'>
                  <label>
                    Name <span className='required'>*</span>
                  </label>
                  <input
                    type='text'
                    value={waForm.name}
                    placeholder='e.g. Default Shared Pool'
                    required
                    onChange={(e) => setWaForm((f) => ({ ...f, name: e.target.value }))}
                  />
                </div>
                <div className='field-group'>
                  <label>
                    Provider <span className='required'>*</span>
                  </label>
                  <select
                    value={isMeta ? 'Meta' : 'Telnyx'}
                    onChange={(e) =>
                      setWaForm((f) => ({ ...f, provider: e.target.value === 'Meta' ? 'meta' : 'telnyx' }))
                    }
                  >
                    <option value='Telnyx'>Telnyx</option>
                    <option value='Meta'>Meta</option>
                  </select>
                </div>
                <div className='field-group'>
                  <div className='toggle-wrap' style={{ marginTop: '0.25rem' }}>
                    <span className='toggle-label'>Default</span>
                    <label className='toggle-switch'>
                      <input
                        type='checkbox'
                        checked={!!waForm.is_default}
                        onChange={(e) => {
                          const checked = e.target.checked
                          setWaForm((f) => ({
                            ...f,
                            is_default: checked,
                            org_ids: checked ? [] : f.org_ids,
                          }))
                          setDefaultNote(checked ? 'replaces current default' : 'only one default per channel')
                        }}
                      />
                      <span className='toggle-slider' />
                    </label>
                    <span className='toggle-label'>Active</span>
                    <label className='toggle-switch'>
                      <input
                        type='checkbox'
                        checked={!!waForm.is_active}
                        onChange={(e) => setWaForm((f) => ({ ...f, is_active: e.target.checked }))}
                      />
                      <span className='toggle-slider' />
                    </label>
                    <span className='inline-note'>{defaultNote}</span>
                  </div>
                </div>
              </div>

              <div className='form-grid' style={{ marginTop: '0.8rem' }}>
                <div className='field-group full-width'>
                  <label>
                    Services{' '}
                    <span style={{ fontWeight: 400, textTransform: 'none' }}>(toggle which services this number supports)</span>
                  </label>
                  <ServiceGrid
                    serviceCodes={serviceCodes}
                    services={waForm.services}
                    onChange={(services) => setWaForm((f) => ({ ...f, services }))}
                  />
                  <div className='service-actions'>
                    <button
                      type='button'
                      className='btn btn-sm btn-secondary'
                      onClick={() => setWaForm((f) => ({ ...f, services: allServicesOn(serviceCodes) }))}
                    >
                      <ListChecks /> All ON
                    </button>
                    <button
                      type='button'
                      className='btn btn-sm btn-secondary'
                      onClick={() => setWaForm((f) => ({ ...f, services: allServicesOff(serviceCodes) }))}
                    >
                      <X /> All OFF
                    </button>
                    <button
                      type='button'
                      className='btn btn-sm btn-secondary'
                      onClick={() => setWaForm((f) => ({ ...f, services: defaultServices(serviceCodes) }))}
                    >
                      <RefreshCw /> Default
                    </button>
                  </div>
                  <ProfileServicesInfo
                    lines={waGuidance.serviceLines}
                    conflicts={[]}
                    orgNameById={orgNameById}
                  />
                </div>
              </div>

              {!isMeta ? (
                <div id='telnyxFields' className='form-grid' style={{ marginTop: '0.6rem' }}>
                  <div className='field-group'>
                    <label>
                      API Key <span style={{ fontWeight: 400, textTransform: 'none' }}>(optional)</span>
                    </label>
                    <MaskField
                      value={waForm.telnyx_api_key}
                      onChange={(v) => setWaForm((f) => ({ ...f, telnyx_api_key: v }))}
                      placeholder='leave blank = master key'
                      savedHint={waForm.has_telnyx_api_key ? 'leave blank = master key' : undefined}
                    />
                  </div>
                  <div className='field-group'>
                    <label>Profile ID</label>
                    <input
                      type='text'
                      value={waForm.telnyx_messaging_profile_id || ''}
                      placeholder='mp_123...'
                      onChange={(e) => setWaForm((f) => ({ ...f, telnyx_messaging_profile_id: e.target.value }))}
                    />
                  </div>
                  <div className='field-group'>
                    <label>Phone Number (E.164)</label>
                    <input
                      type='text'
                      value={waForm.telnyx_number || ''}
                      placeholder='+447...'
                      onChange={(e) => setWaForm((f) => ({ ...f, telnyx_number: e.target.value }))}
                    />
                  </div>
                  <div className='field-group full-width'>
                    <label>Webhook URL</label>
                    <CopyField value={telnyxWebhook} />
                  </div>
                </div>
              ) : (
                <div id='metaFields' className='form-grid' style={{ marginTop: '0.6rem' }}>
                  <div className='field-group'>
                    <label>WABA ID</label>
                    <input
                      type='text'
                      value={waForm.meta_waba_id || ''}
                      placeholder='WhatsApp Business Account ID'
                      onChange={(e) => setWaForm((f) => ({ ...f, meta_waba_id: e.target.value }))}
                    />
                  </div>
                  <div className='field-group'>
                    <label>Phone Number ID</label>
                    <input
                      type='text'
                      value={waForm.meta_phone_number_id || ''}
                      placeholder='1307579342430096 (numeric Cloud API ID)'
                      onChange={(e) => setWaForm((f) => ({ ...f, meta_phone_number_id: e.target.value }))}
                    />
                  </div>
                  <div className='field-group'>
                    <label>Business ID</label>
                    <input
                      type='text'
                      value={waForm.meta_business_id || ''}
                      placeholder='Meta Business Manager ID'
                      onChange={(e) => setWaForm((f) => ({ ...f, meta_business_id: e.target.value }))}
                    />
                  </div>
                  <div className='field-group'>
                    <label>Access Token</label>
                    <MaskField
                      value={waForm.meta_access_token}
                      onChange={(v) => setWaForm((f) => ({ ...f, meta_access_token: v }))}
                      savedHint={waForm.has_meta_access_token ? '(saved)' : undefined}
                    />
                  </div>
                  <div className='field-group'>
                    <label>Verify Token</label>
                    <input
                      type='text'
                      value={waForm.meta_webhook_verify_token || ''}
                      placeholder='verify token'
                      onChange={(e) => setWaForm((f) => ({ ...f, meta_webhook_verify_token: e.target.value }))}
                    />
                  </div>
                  <div className='field-group'>
                    <label>App Secret</label>
                    <MaskField
                      value={waForm.meta_app_secret}
                      onChange={(v) => setWaForm((f) => ({ ...f, meta_app_secret: v }))}
                      savedHint={waForm.has_meta_app_secret ? '(saved)' : undefined}
                    />
                  </div>
                  <div className='field-group full-width'>
                    <label>Webhook URL</label>
                    <CopyField value={metaWebhook} />
                  </div>
                  <div className='field-group'>
                    <label>Phone Number (display)</label>
                    <input
                      type='text'
                      value={waForm.meta_whatsapp_from || ''}
                      placeholder='+447... (reference)'
                      onChange={(e) => setWaForm((f) => ({ ...f, meta_whatsapp_from: e.target.value }))}
                    />
                  </div>
                </div>
              )}

              <div className='assignment-section'>
                <div className='assignment-section-title'>Assign organizations to this profile</div>
                <ProfileServicesInfo
                  lines={waGuidance.orgLines}
                  conflicts={waGuidance.conflicts}
                  orgNameById={orgNameById}
                  variant={!waForm.is_default && waForm.is_active && !normalizeOrgIds(waForm.org_ids).length ? 'warn' : 'info'}
                />
                {!waForm.is_default && !orgOptions.length ? (
                  <div className='field-hint field-hint-warn'>No organizations loaded — refresh the page. If this persists, contact support.</div>
                ) : null}
                <div className='field-group full-width'>
                  <label>
                    Assigned Organizations
                    {waForm.is_default ? (
                      <span style={{ fontWeight: 400, textTransform: 'none' }}> — disabled while Default is ON</span>
                    ) : null}
                  </label>
                  <OrgMultiSelect
                    orgOptions={orgOptions}
                    selectedOrgIds={waForm.org_ids}
                    onChange={(org_ids) => setWaForm((f) => ({ ...f, org_ids }))}
                    inputId='orgInput'
                    tagsId='orgTags'
                    disabled={!!waForm.is_default}
                    placeholder={waForm.is_default ? 'Default = all organizations' : 'Search or choose from the dropdown below…'}
                  />
                </div>
              </div>

              <div className='action-bar'>
                <button type='button' className='btn btn-primary' disabled={saving} onClick={saveWaProfile}>
                  <Check /> {saving ? 'Saving…' : 'Save'}
                </button>
                <button
                  type='button'
                  className='btn btn-secondary'
                  onClick={() => {
                    clearWaForm()
                    setWaFormOpen(false)
                  }}
                >
                  <X /> Cancel
                </button>
                <button type='button' className='btn btn-secondary' disabled={testing} onClick={testWaProfile}>
                  <Plug /> Test
                </button>
                {waTestResult.text ? (
                  <span className={`test-result${waTestResult.kind ? ` ${waTestResult.kind}` : ''}`}>{waTestResult.text}</span>
                ) : null}
              </div>
            </form>
          </div>
        </div>

        <div className='section'>
          <div className='section-title'>
            <MessageCircle /> WhatsApp Profiles
          </div>
          <div className='table-wrap'>
            <table>
              <thead>
                <tr>
                  <th onClick={() => toggleSort('name')}>Name ↕</th>
                  <th onClick={() => toggleSort('provider')}>Provider ↕</th>
                  <th>Number / Phone ID</th>
                  <th>Services</th>
                  <th>Organizations</th>
                  <th>Default</th>
                  <th>Active</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr className='empty-row'>
                    <td colSpan={8}>Loading…</td>
                  </tr>
                ) : null}
                {!loading && pageItems.length === 0 ? (
                  <tr className='empty-row'>
                    <td colSpan={8}>No WhatsApp profiles yet.</td>
                  </tr>
                ) : null}
                {!loading
                  ? pageItems.map((p) => {
                      const numberDisplay =
                        String(p.provider).toLowerCase() === 'meta'
                          ? p.meta_phone_number_id || '—'
                          : p.telnyx_number || '—'
                      return (
                        <tr key={p.id}>
                          <td>
                            <strong>{p.name}</strong>
                          </td>
                          <td>{providerDisplay(p.provider)}</td>
                          <td>{numberDisplay}</td>
                          <td>{renderServiceBadges(p.services)}</td>
                          <td>{renderOrgBadges(p.org_ids)}</td>
                          <td>{p.is_default ? <span className='badge badge-default'>default</span> : null}</td>
                          <td>
                            {p.is_active ? (
                              <span className='badge badge-active'>active</span>
                            ) : (
                              <span className='badge badge-inactive'>inactive</span>
                            )}
                          </td>
                          <td className='actions-cell'>
                            <button type='button' className='btn' onClick={() => loadWaProfile(p)}>
                              <Pencil />
                            </button>
                            <button type='button' className='btn btn-danger' onClick={() => deleteProfile(p.id)}>
                              <Trash2 />
                            </button>
                          </td>
                        </tr>
                      )
                    })
                  : null}
              </tbody>
            </table>
          </div>
          <div className='pagination'>
            <span>
              {sortedWaProfiles.length === 0 ? '0 / 0' : `${currentPage} / ${totalPages}`}
            </span>
            <button
              type='button'
              className='btn'
              disabled={currentPage <= 1}
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            >
              <ChevronLeft />
            </button>
            <button
              type='button'
              className='btn'
              disabled={currentPage >= totalPages}
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            >
              <ChevronRight />
            </button>
          </div>
        </div>
      </div>

      {/* CALLING TAB */}
      <div id='tab-calling' className={`tab-content${tab === 'calling' ? ' active' : ''}`}>
        <div className='create-btn-wrap'>
          <button
            type='button'
            className='btn btn-primary btn-sm'
            onClick={() => {
              if (callingFormOpen) {
                setCallingFormOpen(false)
                clearCallingForm()
              } else {
                clearCallingForm()
                setCallingFormOpen(true)
              }
            }}
          >
            <Plus /> New Calling
          </button>
        </div>

        <div className={`form-container${callingFormOpen ? ' open' : ''}`} id='callingFormContainer'>
          <div className='section'>
            <div className='section-title'>
              <Phone /> {editingCallingId ? 'Edit Calling profile (Telnyx)' : 'Create Calling profile (Telnyx)'}
            </div>
            <div className='form-grid'>
              <div className='field-group'>
                <label>
                  Name <span className='required'>*</span>
                </label>
                <input
                  type='text'
                  value={callingForm.name}
                  placeholder='e.g. Sales Line'
                  required
                  onChange={(e) => setCallingForm((f) => ({ ...f, name: e.target.value }))}
                />
              </div>
              <div className='field-group'>
                <label>
                  Phone Number (E.164) <span className='required'>*</span>
                </label>
                <input
                  type='text'
                  value={callingForm.calling_number || ''}
                  placeholder='+447...'
                  onChange={(e) => setCallingForm((f) => ({ ...f, calling_number: e.target.value }))}
                />
              </div>
              <div className='field-group'>
                <div className='toggle-wrap' style={{ marginTop: '0.25rem' }}>
                  <span className='toggle-label'>Default</span>
                  <label className='toggle-switch'>
                    <input
                      type='checkbox'
                      checked={!!callingForm.is_default}
                      onChange={(e) => {
                        const checked = e.target.checked
                        setCallingForm((f) => ({
                          ...f,
                          is_default: checked,
                          org_ids: checked ? [] : f.org_ids,
                        }))
                      }}
                    />
                    <span className='toggle-slider' />
                  </label>
                  <span className='toggle-label'>Active</span>
                  <label className='toggle-switch'>
                    <input
                      type='checkbox'
                      checked={!!callingForm.is_active}
                      onChange={(e) => setCallingForm((f) => ({ ...f, is_active: e.target.checked }))}
                    />
                    <span className='toggle-slider' />
                  </label>
                </div>
              </div>
            </div>

            <div className='form-grid' style={{ marginTop: '0.8rem' }}>
              <div className='field-group full-width'>
                <label>
                  Services{' '}
                  <span style={{ fontWeight: 400, textTransform: 'none' }}>(toggle which services this number supports)</span>
                </label>
                <ServiceGrid
                  serviceCodes={serviceCodes}
                  services={callingForm.services}
                  onChange={(services) => setCallingForm((f) => ({ ...f, services }))}
                />
                <div className='service-actions'>
                  <button
                    type='button'
                    className='btn btn-sm btn-secondary'
                    onClick={() => setCallingForm((f) => ({ ...f, services: allServicesOn(serviceCodes) }))}
                  >
                    <ListChecks /> All ON
                  </button>
                  <button
                    type='button'
                    className='btn btn-sm btn-secondary'
                    onClick={() => setCallingForm((f) => ({ ...f, services: allServicesOff(serviceCodes) }))}
                  >
                    <X /> All OFF
                  </button>
                  <button
                    type='button'
                    className='btn btn-sm btn-secondary'
                    onClick={() => setCallingForm((f) => ({ ...f, services: defaultServices(serviceCodes) }))}
                  >
                    <RefreshCw /> Default
                  </button>
                </div>
                <ProfileServicesInfo
                  lines={callingGuidance.serviceLines}
                  conflicts={[]}
                  orgNameById={orgNameById}
                />
              </div>
            </div>

            <div className='assignment-section'>
              <div className='assignment-section-title'>Assign organizations to this profile</div>
              <ProfileServicesInfo
                lines={callingGuidance.orgLines}
                conflicts={callingGuidance.conflicts}
                orgNameById={orgNameById}
                variant={
                  !callingForm.is_default && callingForm.is_active && !normalizeOrgIds(callingForm.org_ids).length
                    ? 'warn'
                    : 'info'
                }
              />
              <div className='field-group full-width'>
                <label>
                  Assigned Organizations
                  {callingForm.is_default ? (
                    <span style={{ fontWeight: 400, textTransform: 'none' }}> — disabled while Default is ON</span>
                  ) : null}
                </label>
                <OrgMultiSelect
                  orgOptions={orgOptions}
                  selectedOrgIds={callingForm.org_ids}
                  onChange={(org_ids) => setCallingForm((f) => ({ ...f, org_ids }))}
                  inputId='callingOrgInput'
                  tagsId='callingOrgTags'
                  disabled={!!callingForm.is_default}
                  placeholder={callingForm.is_default ? 'Default = all organizations' : 'Search or choose from the dropdown below…'}
                />
              </div>
            </div>

            <div className='action-bar'>
              <button type='button' className='btn btn-primary' disabled={saving} onClick={saveCallingProfile}>
                <Check /> {saving ? 'Saving…' : 'Save'}
              </button>
              <button
                type='button'
                className='btn btn-secondary'
                onClick={() => {
                  clearCallingForm()
                  setCallingFormOpen(false)
                }}
              >
                <X /> Cancel
              </button>
              <button type='button' className='btn btn-secondary' disabled={testing} onClick={testCallingProfile}>
                <Plug /> Test
              </button>
              {callingTestResult.text ? (
                <span className={`test-result${callingTestResult.kind ? ` ${callingTestResult.kind}` : ''}`}>
                  {callingTestResult.text}
                </span>
              ) : null}
            </div>
          </div>
        </div>

        <div className='section'>
          <div className='section-title'>
            <Phone /> Calling Number Profiles (Telnyx)
          </div>
          <div className='table-wrap'>
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Phone Number</th>
                  <th>Services</th>
                  <th>Organizations</th>
                  <th>Default</th>
                  <th>Active</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr className='empty-row'>
                    <td colSpan={7}>Loading…</td>
                  </tr>
                ) : null}
                {!loading && callingProfiles.length === 0 ? (
                  <tr className='empty-row'>
                    <td colSpan={7}>No Telnyx calling profiles found.</td>
                  </tr>
                ) : null}
                {!loading
                  ? callingProfiles.map((p) => (
                      <tr key={p.id}>
                        <td>
                          <strong>{p.name}</strong>
                        </td>
                        <td>{p.calling_number || '—'}</td>
                        <td>{renderServiceBadges(p.services)}</td>
                        <td>{renderOrgBadges(p.org_ids)}</td>
                        <td>{p.is_default ? <span className='badge badge-default'>default</span> : null}</td>
                        <td>
                          {p.is_active ? (
                            <span className='badge badge-active'>active</span>
                          ) : (
                            <span className='badge badge-inactive'>inactive</span>
                          )}
                        </td>
                        <td className='actions-cell'>
                          <button type='button' className='btn' onClick={() => loadCallingProfile(p)}>
                            <Pencil />
                          </button>
                          <button type='button' className='btn btn-danger' onClick={() => deleteProfile(p.id)}>
                            <Trash2 />
                          </button>
                        </td>
                      </tr>
                    ))
                  : null}
              </tbody>
            </table>
          </div>
        </div>
      </div>
        </div>
      </div>
    </div>
  )
}
