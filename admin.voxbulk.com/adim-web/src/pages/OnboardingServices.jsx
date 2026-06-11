import React, { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'

const SERVICE_ROWS = [
  { key: 'interview', label: 'Interviews', desc: 'AI phone screening campaigns' },
  { key: 'survey', label: 'Surveys', desc: 'AI phone & WhatsApp questionnaires' },
  { key: 'customer_feedback', label: 'Customer feedback', desc: 'WhatsApp QR feedback by location' },
  { key: 'recovery', label: 'Recovery', desc: 'Missed-appointment & recall outreach' },
  { key: 'follow_up', label: 'Follow up', desc: 'WhatsApp appointment reminders' },
]

const EMPTY_SERVICES = {
  interview: true,
  survey: true,
  customer_feedback: false,
  recovery: false,
  follow_up: false,
}

function ServiceToggleRows({ services, onToggle, enabledCount, disabled }) {
  return (
    <div style={{ display: 'grid', gap: 12 }}>
      {SERVICE_ROWS.map((row) => (
        <div
          key={row.key}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 16,
            padding: '12px 14px',
            border: '1px solid var(--border, #e5e7eb)',
            borderRadius: 10,
          }}
        >
          <div>
            <strong>{row.label}</strong>
            <div className='muted' style={{ fontSize: 13 }}>{row.desc}</div>
          </div>
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              cursor: services[row.key] && enabledCount <= 1 ? 'not-allowed' : disabled ? 'wait' : 'pointer',
            }}
          >
            <span className='muted' style={{ fontSize: 12 }}>{services[row.key] ? 'On' : 'Off'}</span>
            <input
              type='checkbox'
              checked={Boolean(services[row.key])}
              disabled={disabled || (Boolean(services[row.key]) && enabledCount <= 1)}
              onChange={(e) => onToggle(row.key, e.target.checked)}
            />
          </label>
        </div>
      ))}
    </div>
  )
}

export default function OnboardingServices() {
  const [orgs, setOrgs] = useState(null)
  const [platformServices, setPlatformServices] = useState({ ...EMPTY_SERVICES })
  const [orgServices, setOrgServices] = useState({ ...EMPTY_SERVICES })
  const [selectedOrgIds, setSelectedOrgIds] = useState([])
  const [applyToAll, setApplyToAll] = useState(false)
  const [usesPlatformDefault, setUsesPlatformDefault] = useState(true)
  const [loadingPlatform, setLoadingPlatform] = useState(false)
  const [loadingOrgs, setLoadingOrgs] = useState(false)
  const [savingPlatform, setSavingPlatform] = useState(false)
  const [savingOrgs, setSavingOrgs] = useState(false)
  const [resetAllOnPlatformSave, setResetAllOnPlatformSave] = useState(false)
  const [error, setError] = useState('')

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
        const raw = data?.default_allowed_services || {}
        setPlatformServices({
          interview: raw.interview !== false,
          survey: raw.survey !== false,
          customer_feedback: Boolean(raw.customer_feedback),
          recovery: Boolean(raw.recovery),
          follow_up: Boolean(raw.follow_up),
        })
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

  useEffect(() => {
    if (applyToAll || selectedOrgIds.length !== 1) {
      if (applyToAll) {
        setOrgServices({ ...platformServices })
        setUsesPlatformDefault(true)
      }
      return
    }
    let cancelled = false
    setLoadingOrgs(true)
    setError('')
    ;(async () => {
      try {
        const orgId = selectedOrgIds[0]
        const data = await apiFetch(`/admin/organisations/${encodeURIComponent(orgId)}/allowed-services`)
        if (cancelled) return
        setUsesPlatformDefault(Boolean(data?.uses_platform_default_allowed))
        setOrgServices({
          interview: data?.allowed_services?.interview !== false,
          survey: data?.allowed_services?.survey !== false,
          customer_feedback: Boolean(data?.allowed_services?.customer_feedback),
          recovery: Boolean(data?.allowed_services?.recovery),
          follow_up: Boolean(data?.allowed_services?.follow_up),
        })
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load organisation services')
      } finally {
        if (!cancelled) setLoadingOrgs(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [selectedOrgIds, applyToAll, platformServices])

  const platformEnabledCount = useMemo(
    () => SERVICE_ROWS.filter((row) => platformServices[row.key]).length,
    [platformServices],
  )
  const orgEnabledCount = useMemo(
    () => SERVICE_ROWS.filter((row) => orgServices[row.key]).length,
    [orgServices],
  )

  const onPlatformToggle = (key, value) => {
    if (!value && platformEnabledCount <= 1) {
      setError('At least one dashboard service must stay enabled in platform defaults.')
      return
    }
    setError('')
    setPlatformServices((prev) => ({ ...prev, [key]: value }))
  }

  const onOrgToggle = (key, value) => {
    if (!value && orgEnabledCount <= 1) {
      setError('At least one dashboard service must stay enabled.')
      return
    }
    setError('')
    setOrgServices((prev) => ({ ...prev, [key]: value }))
  }

  const toggleOrgSelection = (orgId) => {
    setApplyToAll(false)
    setSelectedOrgIds((prev) => (prev.includes(orgId) ? prev.filter((id) => id !== orgId) : [...prev, orgId]))
  }

  const onSelectAllOrgs = () => {
    setApplyToAll(true)
    setSelectedOrgIds([])
  }

  const onClearOrgSelection = () => {
    setApplyToAll(false)
    setSelectedOrgIds([])
  }

  const onSavePlatform = async () => {
    setSavingPlatform(true)
    setError('')
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
        : 'Platform defaults saved. Organisations without a custom override will use these automatically.'
      window.alert(msg)
    } catch (e) {
      setError(e?.message || 'Could not save platform defaults')
    } finally {
      setSavingPlatform(false)
    }
  }

  const onSaveSelectedOrgs = async () => {
    if (!applyToAll && selectedOrgIds.length === 0) {
      setError('Select at least one organisation, or choose “All organisations”.')
      return
    }
    setSavingOrgs(true)
    setError('')
    try {
      const data = await apiFetch('/admin/organisations/bulk-allowed-services', {
        method: 'PATCH',
        body: JSON.stringify({
          apply_to_all: applyToAll,
          org_ids: applyToAll ? undefined : selectedOrgIds,
          services: orgServices,
        }),
      })
      window.alert(`Dashboard services updated for ${data?.updated_count ?? 0} organisation(s).`)
    } catch (e) {
      setError(e?.message || 'Could not save organisation overrides')
    } finally {
      setSavingOrgs(false)
    }
  }

  const onResetSelectedToPlatform = async () => {
    if (!applyToAll && selectedOrgIds.length === 0) {
      setError('Select organisations to reset, or choose “All organisations”.')
      return
    }
    if (!window.confirm('Reset selected organisations to inherit VoxBulk platform defaults?')) return
    setSavingOrgs(true)
    setError('')
    try {
      const data = await apiFetch('/admin/organisations/bulk-allowed-services', {
        method: 'PATCH',
        body: JSON.stringify({
          apply_to_all: applyToAll,
          org_ids: applyToAll ? undefined : selectedOrgIds,
          reset_to_platform_default: true,
        }),
      })
      window.alert(`${data?.updated_count ?? 0} organisation(s) now inherit platform defaults.`)
      if (selectedOrgIds.length === 1) setUsesPlatformDefault(true)
    } catch (e) {
      setError(e?.message || 'Could not reset organisations')
    } finally {
      setSavingOrgs(false)
    }
  }

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>Customer services</h1>
          <p>
            Set <strong>VoxBulk platform defaults</strong> for every organisation, or apply custom overrides to one or
            more selected organisations. Customers can still hide allowed modules in Settings → Services.
          </p>
        </div>
      </div>

      {error ? (
        <div className='card' style={{ marginBottom: 16, borderColor: '#fecaca' }}>
          <div className='cardBody' style={{ color: '#b91c1c', fontSize: 14 }}>{error}</div>
        </div>
      ) : null}

      <div className='card' style={{ marginBottom: 16 }}>
        <div className='cardHead'>
          <h3>VoxBulk defaults (all organisations)</h3>
          {loadingPlatform ? <span className='pill'>Loading…</span> : null}
        </div>
        <div className='cardBody'>
          <p className='muted' style={{ fontSize: 13, marginBottom: 12 }}>
            New organisations and any org without a custom override inherit these modules automatically. Turn on
            Customer feedback here to make it available platform-wide.
          </p>
          <ServiceToggleRows
            services={platformServices}
            onToggle={onPlatformToggle}
            enabledCount={platformEnabledCount}
            disabled={loadingPlatform || savingPlatform}
          />
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 16, fontSize: 13 }}>
            <input
              type='checkbox'
              checked={resetAllOnPlatformSave}
              onChange={(e) => setResetAllOnPlatformSave(e.target.checked)}
            />
            Also reset <strong>all</strong> organisations to inherit these defaults (clears custom overrides)
          </label>
          <div className='actions' style={{ marginTop: 16 }}>
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
          <h3>Organisation overrides (optional)</h3>
          {loadingOrgs ? <span className='pill'>Loading…</span> : null}
        </div>
        <div className='cardBody'>
          <p className='muted' style={{ fontSize: 13, marginBottom: 12 }}>
            Use this when a module should apply only to specific customers. Select one or more organisations, or apply to
            everyone at once.
          </p>

          <div className='actions' style={{ marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
            <button type='button' className={`btn soft${applyToAll ? ' primary' : ''}`} onClick={onSelectAllOrgs}>
              All organisations
            </button>
            <button type='button' className='btn soft' onClick={onClearOrgSelection}>
              Clear selection
            </button>
            {applyToAll ? (
              <span className='pill p-cyan'>Targeting all organisations</span>
            ) : (
              <span className='pill'>{selectedOrgIds.length} selected</span>
            )}
          </div>

          {!applyToAll ? (
            <div
              style={{
                maxHeight: 220,
                overflowY: 'auto',
                border: '1px solid var(--border, #e5e7eb)',
                borderRadius: 10,
                padding: 8,
                marginBottom: 16,
              }}
            >
              {(orgs || []).map((o) => (
                <label
                  key={o.id}
                  style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', cursor: 'pointer' }}
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
          ) : null}

          {selectedOrgIds.length === 1 && !applyToAll ? (
            <p className='muted' style={{ fontSize: 13, marginBottom: 12 }}>
              {usesPlatformDefault
                ? 'This organisation currently inherits VoxBulk platform defaults.'
                : 'This organisation has a custom override. Saving below replaces it.'}
            </p>
          ) : null}

          <ServiceToggleRows
            services={orgServices}
            onToggle={onOrgToggle}
            enabledCount={orgEnabledCount}
            disabled={loadingOrgs || savingOrgs || (!applyToAll && selectedOrgIds.length === 0)}
          />

          <div className='actions' style={{ marginTop: 16, flexWrap: 'wrap', gap: 8 }}>
            <button
              type='button'
              className='btn primary'
              onClick={() => void onSaveSelectedOrgs()}
              disabled={savingOrgs || loadingOrgs || (!applyToAll && selectedOrgIds.length === 0)}
            >
              {savingOrgs ? 'Saving…' : applyToAll ? 'Apply to all organisations' : 'Apply to selected'}
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
    </>
  )
}
