import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'
import './onboarding-services.css'

const SERVICE_ROWS = [
  { key: 'interview', label: 'Interviews', desc: 'AI phone screening campaigns', icon: 'ti-phone' },
  { key: 'survey', label: 'Surveys', desc: 'AI phone & WhatsApp questionnaires', icon: 'ti-clipboard' },
  { key: 'customer_feedback', label: 'Customer feedback', desc: 'WhatsApp QR feedback by location', icon: 'ti-message-circle' },
  { key: 'appointments', label: 'Appointments', desc: 'CRM booking confirmation via WhatsApp + AI calls', icon: 'ti-calendar' },
  { key: 'recovery', label: 'Recovery', desc: 'Missed-appointment & recall outreach', icon: 'ti-heart' },
  { key: 'follow_up', label: 'Follow up', desc: 'WhatsApp appointment reminders', icon: 'ti-bell' },
  { key: 'campaigns', label: 'Broadcast campaigns', desc: 'WhatsApp template broadcasts (preview)', icon: 'ti-megaphone' },
]

const EMPTY_SERVICES = {
  interview: true,
  survey: true,
  customer_feedback: false,
  appointments: false,
  recovery: false,
  follow_up: false,
  campaigns: false,
}

function servicesFromApi(raw) {
  return {
    interview: raw?.interview !== false,
    survey: raw?.survey !== false,
    customer_feedback: Boolean(raw?.customer_feedback),
    appointments: Boolean(raw?.appointments),
    recovery: Boolean(raw?.recovery),
    follow_up: Boolean(raw?.follow_up),
    campaigns: Boolean(raw?.campaigns),
  }
}

function ToggleSwitch({ checked, disabled, onChange, label }) {
  return (
    <div className='os-toggle-wrap'>
      <span className='os-toggle-label'>{checked ? 'Granted' : 'Off'}</span>
      <button
        type='button'
        role='switch'
        aria-checked={checked}
        aria-label={label}
        className={`os-toggle${checked ? ' on' : ''}`}
        disabled={disabled}
        onClick={() => !disabled && onChange(!checked)}
      />
    </div>
  )
}

function ServiceModuleRows({ services, onToggle, enabledCount, disabled }) {
  return (
    <div className='os-module-list'>
      {SERVICE_ROWS.map((row) => {
        const on = Boolean(services[row.key])
        const lockOff = on && enabledCount <= 1
        return (
          <div key={row.key} className='os-module-row'>
            <div className='os-module-main'>
              <span className={`os-icon-chip ${row.key}`} aria-hidden>
                <i className={`ti ${row.icon}`} />
              </span>
              <div className='os-module-text'>
                <strong>{row.label}</strong>
                <span>{row.desc}</span>
              </div>
            </div>
            <ToggleSwitch
              checked={on}
              disabled={disabled || lockOff}
              label={`Grant ${row.label}`}
              onChange={(value) => onToggle(row.key, value)}
            />
          </div>
        )
      })}
    </div>
  )
}

function CustomerPreview({ breakdown, orgName }) {
  if (!breakdown?.length) return null
  return (
    <div className='os-preview'>
      <div className='os-preview-head'>What {orgName || 'this customer'} sees today</div>
      <table>
        <thead>
          <tr>
            <th>Module</th>
            <th>Admin granted</th>
            <th>Customer enabled</th>
            <th>In sidebar</th>
          </tr>
        </thead>
        <tbody>
          {breakdown.map((row) => (
            <tr key={row.key}>
              <td>{row.label}</td>
              <td>{row.allowed ? 'Yes' : 'No'}</td>
              <td>{row.allowed ? (row.enabled ? 'Yes' : 'No') : '—'}</td>
              <td className={row.allowed && !row.visible ? 'hint' : ''}>
                {row.visible ? 'Yes' : row.allowed ? 'No' : 'Hidden'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function OnboardingServices() {
  const [orgs, setOrgs] = useState(null)
  const [platformServices, setPlatformServices] = useState({ ...EMPTY_SERVICES })
  const [orgServices, setOrgServices] = useState({ ...EMPTY_SERVICES })
  const [selectedOrgIds, setSelectedOrgIds] = useState([])
  const [orgMode, setOrgMode] = useState('selected')
  const [orgSearch, setOrgSearch] = useState('')
  const [usesPlatformDefault, setUsesPlatformDefault] = useState(true)
  const [serviceBreakdown, setServiceBreakdown] = useState([])
  const [selectedOrgName, setSelectedOrgName] = useState('')
  const [loadingPlatform, setLoadingPlatform] = useState(false)
  const [loadingOrgs, setLoadingOrgs] = useState(false)
  const [savingPlatform, setSavingPlatform] = useState(false)
  const [savingOrgs, setSavingOrgs] = useState(false)
  const [resetAllOnPlatformSave, setResetAllOnPlatformSave] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const applyToAll = orgMode === 'all'
  const singleOrgId = selectedOrgIds.length === 1 ? selectedOrgIds[0] : ''

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const data = await apiFetch('/admin/organisations?limit=500')
        if (cancelled) return
        setOrgs(Array.isArray(data) ? data : [])
      } catch (e) {
        if (!cancelled) {
          setOrgs([])
          setError(e?.message || 'Could not load organisations')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoadingPlatform(true)
    ;(async () => {
      try {
        const data = await apiFetch('/admin/platform/default-allowed-services')
        if (cancelled) return
        setPlatformServices(servicesFromApi(data?.default_allowed_services || {}))
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load platform defaults')
      } finally {
        if (!cancelled) setLoadingPlatform(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const loadOrgDetail = useCallback(async (orgId) => {
    if (!orgId) {
      setServiceBreakdown([])
      setSelectedOrgName('')
      return
    }
    setLoadingOrgs(true)
    setError('')
    try {
      const data = await apiFetch(`/admin/organisations/${encodeURIComponent(orgId)}/allowed-services`)
      setUsesPlatformDefault(Boolean(data?.uses_platform_default_allowed))
      setOrgServices(servicesFromApi(data?.allowed_services || {}))
      setServiceBreakdown(Array.isArray(data?.service_breakdown) ? data.service_breakdown : [])
      setSelectedOrgName(data?.org_name || '')
    } catch (e) {
      setError(e?.message || 'Could not load organisation services')
    } finally {
      setLoadingOrgs(false)
    }
  }, [])

  useEffect(() => {
    if (applyToAll) {
      setOrgServices({ ...platformServices })
      setUsesPlatformDefault(true)
      setServiceBreakdown([])
      setSelectedOrgName('')
      return
    }
    if (singleOrgId) {
      void loadOrgDetail(singleOrgId)
      return
    }
    setServiceBreakdown([])
    setSelectedOrgName('')
    if (selectedOrgIds.length > 1) {
      setUsesPlatformDefault(false)
    }
  }, [singleOrgId, selectedOrgIds.length, applyToAll, platformServices, loadOrgDetail])

  const filteredOrgs = useMemo(() => {
    const list = orgs || []
    const q = orgSearch.trim().toLowerCase()
    if (!q) return list
    return list.filter((o) => String(o.name || '').toLowerCase().includes(q))
  }, [orgs, orgSearch])

  const filteredOrgIds = useMemo(() => filteredOrgs.map((o) => o.id), [filteredOrgs])

  const platformEnabledCount = useMemo(
    () => SERVICE_ROWS.filter((row) => platformServices[row.key]).length,
    [platformServices],
  )
  const orgEnabledCount = useMemo(
    () => SERVICE_ROWS.filter((row) => orgServices[row.key]).length,
    [orgServices],
  )

  const toggleOrgSelection = (orgId) => {
    setOrgMode('selected')
    setSelectedOrgIds((prev) => (prev.includes(orgId) ? prev.filter((id) => id !== orgId) : [...prev, orgId]))
  }

  const selectAllFiltered = () => {
    setOrgMode('selected')
    setSelectedOrgIds((prev) => Array.from(new Set([...prev, ...filteredOrgIds])))
  }

  const clearOrgSelection = () => {
    setOrgMode('selected')
    setSelectedOrgIds([])
  }

  const onPlatformToggle = (key, value) => {
    if (!value && platformEnabledCount <= 1) {
      setError('At least one dashboard module must stay granted in platform defaults.')
      return
    }
    setError('')
    setSuccess('')
    setPlatformServices((prev) => ({ ...prev, [key]: value }))
  }

  const onOrgToggle = (key, value) => {
    if (!value && orgEnabledCount <= 1) {
      setError('At least one dashboard module must stay granted.')
      return
    }
    setError('')
    setSuccess('')
    setOrgServices((prev) => ({ ...prev, [key]: value }))
  }

  const onSavePlatform = async () => {
    setSavingPlatform(true)
    setError('')
    setSuccess('')
    try {
      const data = await apiFetch('/admin/platform/default-allowed-services', {
        method: 'PATCH',
        body: JSON.stringify({
          services: platformServices,
          reset_all_orgs_to_platform_default: resetAllOnPlatformSave,
        }),
      })
      const msg = resetAllOnPlatformSave
        ? `Platform defaults saved. ${data?.orgs_reset_to_platform_default ?? 0} organisation(s) reset to inherit them.`
        : 'Platform defaults saved. Orgs without a custom override inherit these grants.'
      setSuccess(msg)
    } catch (e) {
      setError(e?.message || 'Could not save platform defaults')
    } finally {
      setSavingPlatform(false)
    }
  }

  const onSaveSelectedOrgs = async () => {
    if (!applyToAll && selectedOrgIds.length === 0) {
      setError('Select one or more organisations, or switch to All organisations.')
      return
    }
    setSavingOrgs(true)
    setError('')
    setSuccess('')
    try {
      const data = await apiFetch('/admin/organisations/bulk-allowed-services', {
        method: 'PATCH',
        body: JSON.stringify({
          apply_to_all: applyToAll,
          org_ids: applyToAll ? undefined : selectedOrgIds,
          services: orgServices,
        }),
      })
      setSuccess(
        `Module grants saved for ${data?.updated_count ?? 0} organisation(s). Off = hidden from customer Settings and sidebar. Ask them to refresh the dashboard.`,
      )
      if (singleOrgId) await loadOrgDetail(singleOrgId)
    } catch (e) {
      setError(e?.message || 'Could not save organisation overrides')
    } finally {
      setSavingOrgs(false)
    }
  }

  const onResetSelectedToPlatform = async () => {
    if (!applyToAll && selectedOrgIds.length === 0) {
      setError('Select one or more organisations, or switch to All organisations.')
      return
    }
    if (!window.confirm('Reset selected organisations to inherit platform defaults?')) return
    setSavingOrgs(true)
    setError('')
    setSuccess('')
    try {
      const data = await apiFetch('/admin/organisations/bulk-allowed-services', {
        method: 'PATCH',
        body: JSON.stringify({
          apply_to_all: applyToAll,
          org_ids: applyToAll ? undefined : selectedOrgIds,
          reset_to_platform_default: true,
        }),
      })
      setSuccess(`${data?.updated_count ?? 0} organisation(s) now inherit platform defaults.`)
      if (singleOrgId) await loadOrgDetail(singleOrgId)
      else setUsesPlatformDefault(true)
    } catch (e) {
      setError(e?.message || 'Could not reset organisations')
    } finally {
      setSavingOrgs(false)
    }
  }

  const orgSectionDisabled = loadingOrgs || savingOrgs || (!applyToAll && selectedOrgIds.length === 0)

  return (
    <div className='onboarding-services-page'>
      <div className='pageTop'>
        <div>
          <h1>Dashboard modules</h1>
          <p>
            <strong>Off</strong> = customer cannot see or enable the module. <strong>On</strong> = it appears in their
            Settings → Services so they can turn it on for their sidebar.
          </p>
        </div>
      </div>

      <div className='os-steps'>
        <ol>
          <li>Grant modules <strong>on</strong> here to make them available to organisations.</li>
          <li>Customers choose visibility in <strong>Settings → Services</strong> — you do not control their sidebar directly.</li>
          <li>Use <strong>organisation overrides</strong> when specific customers need different grants than platform defaults.</li>
        </ol>
      </div>

      {error ? <div className='os-banner error'>{error}</div> : null}
      {success ? <div className='os-banner success'>{success}</div> : null}

      <div className='card' style={{ marginBottom: 16 }}>
        <div className='cardHead'>
          <h3>Platform defaults</h3>
          {loadingPlatform ? <span className='pill'>Loading…</span> : null}
        </div>
        <div className='cardBody'>
          <p className='muted' style={{ fontSize: 13, marginBottom: 12 }}>
            Default grants for new organisations and any org without a custom override.
          </p>
          <ServiceModuleRows
            services={platformServices}
            onToggle={onPlatformToggle}
            enabledCount={platformEnabledCount}
            disabled={loadingPlatform || savingPlatform}
          />
          <label className='os-reset-row'>
            <input
              type='checkbox'
              checked={resetAllOnPlatformSave}
              onChange={(e) => setResetAllOnPlatformSave(e.target.checked)}
            />
            Also reset <strong>all</strong> organisations to inherit these defaults
          </label>
          <div className='os-actions'>
            <button
              type='button'
              className='btn primary'
              onClick={() => void onSavePlatform()}
              disabled={loadingPlatform || savingPlatform}
            >
              {savingPlatform ? 'Saving…' : 'Save platform defaults'}
            </button>
          </div>
        </div>
      </div>

      <div className='card'>
        <div className='cardHead'>
          <h3>Organisation overrides</h3>
          {loadingOrgs ? <span className='pill'>Loading…</span> : null}
        </div>
        <div className='cardBody'>
          <div className='os-segment'>
            <button
              type='button'
              className={orgMode === 'selected' ? 'active' : ''}
              onClick={() => setOrgMode('selected')}
            >
              Selected organisations
            </button>
            <button
              type='button'
              className={orgMode === 'all' ? 'active' : ''}
              onClick={() => {
                setOrgMode('all')
                setSelectedOrgIds([])
              }}
            >
              All organisations
            </button>
          </div>

          <div className='os-grid org-section'>
            {!applyToAll ? (
              <div className='os-org-panel'>
                <input
                  className='os-search'
                  type='search'
                  placeholder='Search organisations…'
                  value={orgSearch}
                  onChange={(e) => setOrgSearch(e.target.value)}
                />
                <div className='os-org-toolbar'>
                  <span className='pill'>{selectedOrgIds.length} selected</span>
                  <button type='button' onClick={selectAllFiltered}>Select all shown</button>
                  <button type='button' onClick={clearOrgSelection}>Clear</button>
                </div>
                <div className='os-org-list'>
                  {filteredOrgs.map((o) => (
                    <label
                      key={o.id}
                      className={`os-org-item${selectedOrgIds.includes(o.id) ? ' selected' : ''}`}
                    >
                      <input
                        type='checkbox'
                        checked={selectedOrgIds.includes(o.id)}
                        onChange={() => toggleOrgSelection(o.id)}
                      />
                      <span>{o.name}</span>
                    </label>
                  ))}
                </div>
              </div>
            ) : (
              <div className='os-org-panel'>
                <p className='muted' style={{ fontSize: 13, margin: 0 }}>
                  Module grants below apply to <strong>every organisation</strong> when you save.
                </p>
              </div>
            )}

            <div>
              {!applyToAll && singleOrgId ? (
                <span className={`os-status-pill${usesPlatformDefault ? '' : ' custom'}`}>
                  {usesPlatformDefault ? 'Inherits platform defaults' : 'Custom override active'}
                </span>
              ) : null}

              {!applyToAll && selectedOrgIds.length > 1 ? (
                <p className='os-multi-hint'>
                  Same module grants will apply to <strong>{selectedOrgIds.length} organisations</strong> when you save.
                  Select only one org to preview what that customer sees.
                </p>
              ) : null}

              <p className='os-grant-hint'>
                Toggle <strong>Granted</strong> to control what the customer may use. Revoked modules disappear from their
                dashboard and Settings → Services.
              </p>

              <ServiceModuleRows
                services={orgServices}
                onToggle={onOrgToggle}
                enabledCount={orgEnabledCount}
                disabled={orgSectionDisabled}
              />

              {!applyToAll && singleOrgId ? (
                <CustomerPreview breakdown={serviceBreakdown} orgName={selectedOrgName} />
              ) : null}

              <div className='os-actions'>
                <button
                  type='button'
                  className='btn primary'
                  onClick={() => void onSaveSelectedOrgs()}
                  disabled={orgSectionDisabled}
                >
                  {savingOrgs
                    ? 'Saving…'
                    : applyToAll
                      ? 'Apply grants to all organisations'
                      : `Save grants for ${selectedOrgIds.length} organisation(s)`}
                </button>
                <button
                  type='button'
                  className='btn soft'
                  onClick={() => void onResetSelectedToPlatform()}
                  disabled={savingOrgs || (!applyToAll && selectedOrgIds.length === 0)}
                >
                  Reset to platform defaults
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
