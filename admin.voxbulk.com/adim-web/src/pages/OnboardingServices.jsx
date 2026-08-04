import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Switch } from '@/components/ui/Switch'
import { Pill } from '@/components/ui/Badge'
import {
  StripeTable,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table'

const SERVICE_ROWS = [
  { key: 'interview', label: 'Interviews', desc: 'AI phone screening campaigns', icon: 'ti-phone' },
  { key: 'survey', label: 'Surveys', desc: 'AI phone & WhatsApp questionnaires', icon: 'ti-clipboard' },
  { key: 'customer_feedback', label: 'Customer feedback', desc: 'WhatsApp QR feedback by location', icon: 'ti-message-circle' },
  { key: 'feedback_campaigns', label: 'Add-on · Send campaign', desc: 'Promo WhatsApp Send campaign + Campaign dashboard', icon: 'ti-send' },
  { key: 'expo', label: 'VoxBulk Expo', desc: 'Exhibition WhatsApp lead capture (QR + product PDFs)', icon: 'ti-qrcode' },
  { key: 'smart_card', label: 'Smart Card QR', desc: 'Representative QR cards, catalogue, WhatsApp/web leads', icon: 'ti-id-badge' },
  { key: 'appointments', label: 'Appointments', desc: 'CRM booking confirmation via WhatsApp + AI calls', icon: 'ti-calendar' },
  { key: 'recovery', label: 'Recovery', desc: 'Missed-appointment & recall outreach', icon: 'ti-heart' },
  { key: 'follow_up', label: 'Follow up', desc: 'WhatsApp appointment reminders', icon: 'ti-bell' },
  { key: 'campaigns', label: 'Broadcast campaigns', desc: 'WhatsApp template broadcasts (preview)', icon: 'ti-megaphone' },
]

const EMPTY_SERVICES = {
  interview: true,
  survey: true,
  customer_feedback: false,
  feedback_campaigns: false,
  expo: false,
  smart_card: false,
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
    feedback_campaigns: Boolean(raw?.feedback_campaigns),
    expo: Boolean(raw?.expo),
    smart_card: Boolean(raw?.smart_card),
    appointments: Boolean(raw?.appointments),
    recovery: Boolean(raw?.recovery),
    follow_up: Boolean(raw?.follow_up),
    campaigns: Boolean(raw?.campaigns),
  }
}

function ServiceModuleRows({ services, onToggle, enabledCount, disabled }) {
  const ordered = [...SERVICE_ROWS].sort(
    (a, b) => Number(Boolean(services[b.key])) - Number(Boolean(services[a.key])),
  )
  return (
    <div className='flex flex-col gap-2'>
      {ordered.map((row) => {
        const on = Boolean(services[row.key])
        const lockOff = on && enabledCount <= 1
        return (
          <div
            key={row.key}
            className='flex items-center justify-between gap-3 rounded-lg border border-border bg-card px-3 py-2.5'
          >
            <div className='flex min-w-0 items-center gap-3'>
              <span
                className={[
                  'grid size-9 shrink-0 place-items-center rounded-lg text-[16px]',
                  on
                    ? 'bg-success-soft text-success ring-1 ring-inset ring-success/40'
                    : 'bg-secondary text-secondary-foreground',
                ].join(' ')}
                aria-hidden
              >
                <i className={`ti ${row.icon}`} />
              </span>
              <div className='min-w-0'>
                <strong className='block text-[13px] font-semibold text-foreground'>{row.label}</strong>
                <span className='block text-[11px] text-muted-foreground'>{row.desc}</span>
              </div>
            </div>
            <div className='flex shrink-0 items-center gap-2'>
              <span className='min-w-[3.25rem] text-right text-[11px] text-muted-foreground'>
                {on ? 'Granted' : 'Off'}
              </span>
              <Switch
                checked={on}
                disabled={disabled || lockOff}
                aria-label={`Grant ${row.label}`}
                onCheckedChange={(value) => onToggle(row.key, value)}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function CustomerPreview({ breakdown, orgName }) {
  if (!breakdown?.length) return null
  const ordered = [...breakdown].sort((a, b) => {
    const score = (row) => (row.enabled ? 2 : 0) + (row.allowed ? 1 : 0)
    return score(b) - score(a)
  })
  return (
    <div className='mt-3.5 space-y-2'>
      <p className='m-0 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground'>
        What {orgName || 'this customer'} sees today
      </p>
      <StripeTable>
        <TableHeader>
          <TableRow>
            <TableHead>Module</TableHead>
            <TableHead>Admin granted</TableHead>
            <TableHead>Customer enabled</TableHead>
            <TableHead>In sidebar</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {ordered.map((row) => (
            <TableRow key={row.key}>
              <TableCell>
                <span className='inline-flex items-center gap-2'>
                  {row.enabled ? (
                    <span className='inline-block size-2 shrink-0 rounded-full bg-success' aria-hidden />
                  ) : null}
                  {row.label}
                </span>
              </TableCell>
              <TableCell>{row.allowed ? 'Yes' : 'No'}</TableCell>
              <TableCell>{row.allowed ? (row.enabled ? 'Yes' : 'No') : '—'}</TableCell>
              <TableCell className={row.allowed && !row.visible ? 'text-warning' : ''}>
                {row.visible ? 'Yes' : row.allowed ? 'No' : 'Hidden'}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </StripeTable>
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
    <div className='ds-scope space-y-4'>
      <div className='pageTop'>
        <div>
          <h1>Dashboard modules</h1>
          <p>
            <strong>Off</strong> = customer cannot see or enable the module. <strong>On</strong> = it appears in their
            Settings → Services so they can turn it on for their sidebar.
          </p>
        </div>
      </div>

      <div className='rounded-lg border border-border bg-surface-muted px-4 py-3.5 text-[13px] leading-relaxed text-muted-foreground'>
        <ol className='m-0 list-decimal space-y-1.5 pl-5'>
          <li>
            Grant modules <strong className='text-foreground'>on</strong> here to make them available to organisations.
          </li>
          <li>
            Customers choose visibility in <strong className='text-foreground'>Settings → Services</strong> — you do not
            control their sidebar directly.
          </li>
          <li>
            Use <strong className='text-foreground'>organisation overrides</strong> when specific customers need different
            grants than platform defaults.
          </li>
        </ol>
      </div>

      {error ? (
        <div className='rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive'>
          {error}
        </div>
      ) : null}
      {success ? (
        <div className='rounded-md border border-success/40 bg-success-soft px-3 py-2 text-sm text-success'>
          {success}
        </div>
      ) : null}

      <Panel
        title='Platform defaults'
        subtitle='Default grants for new organisations and any org without a custom override.'
        action={loadingPlatform ? <Pill tone='info'>Loading…</Pill> : null}
        bodyClassName='space-y-3'
      >
        <ServiceModuleRows
          services={platformServices}
          onToggle={onPlatformToggle}
          enabledCount={platformEnabledCount}
          disabled={loadingPlatform || savingPlatform}
        />
        <label className='flex items-center gap-2 text-[13px] text-foreground'>
          <input
            type='checkbox'
            className='size-3.5 accent-primary'
            checked={resetAllOnPlatformSave}
            onChange={(e) => setResetAllOnPlatformSave(e.target.checked)}
          />
          Also reset <strong>all</strong> organisations to inherit these defaults
        </label>
        <div className='flex flex-wrap gap-2'>
          <Button
            type='button'
            size='sm'
            className='h-8'
            onClick={() => void onSavePlatform()}
            disabled={loadingPlatform || savingPlatform}
          >
            {savingPlatform ? 'Saving…' : 'Save platform defaults'}
          </Button>
        </div>
      </Panel>

      <Panel
        title='Organisation overrides'
        subtitle='Apply custom module grants to one, many, or all organisations.'
        action={loadingOrgs ? <Pill tone='info'>Loading…</Pill> : null}
        bodyClassName='space-y-3'
      >
        <div className='inline-flex h-8 items-center rounded-lg bg-muted p-0.5 text-muted-foreground'>
          <button
            type='button'
            className={[
              'inline-flex items-center justify-center rounded-md px-3 py-1 text-xs font-medium transition-all',
              orgMode === 'selected' ? 'bg-background text-foreground shadow' : 'hover:text-foreground',
            ].join(' ')}
            onClick={() => setOrgMode('selected')}
          >
            Selected organisations
          </button>
          <button
            type='button'
            className={[
              'inline-flex items-center justify-center rounded-md px-3 py-1 text-xs font-medium transition-all',
              orgMode === 'all' ? 'bg-background text-foreground shadow' : 'hover:text-foreground',
            ].join(' ')}
            onClick={() => {
              setOrgMode('all')
              setSelectedOrgIds([])
            }}
          >
            All organisations
          </button>
        </div>

        <div className='grid gap-4 lg:grid-cols-[minmax(240px,34%)_minmax(0,1fr)] lg:items-start'>
          {!applyToAll ? (
            <div className='rounded-lg border border-border bg-surface-muted p-3'>
              <Input
                type='search'
                placeholder='Search organisations…'
                value={orgSearch}
                onChange={(e) => setOrgSearch(e.target.value)}
                className='mb-2.5 h-8'
              />
              <div className='mb-2 flex flex-wrap items-center gap-2 text-[12px]'>
                <Pill tone='info'>{selectedOrgIds.length} selected</Pill>
                <Button type='button' variant='link' size='sm' className='h-auto p-0 text-[12px]' onClick={selectAllFiltered}>
                  Select all shown
                </Button>
                <Button type='button' variant='link' size='sm' className='h-auto p-0 text-[12px]' onClick={clearOrgSelection}>
                  Clear
                </Button>
              </div>
              <div className='flex max-h-[280px] flex-col gap-0.5 overflow-y-auto'>
                {filteredOrgs.map((o) => {
                  const selected = selectedOrgIds.includes(o.id)
                  return (
                    <label
                      key={o.id}
                      className={[
                        'flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 text-[13px]',
                        selected ? 'bg-primary/10 font-semibold text-foreground' : 'text-foreground hover:bg-muted/60',
                      ].join(' ')}
                    >
                      <input
                        type='checkbox'
                        className='size-3.5 shrink-0 accent-primary'
                        checked={selected}
                        onChange={() => toggleOrgSelection(o.id)}
                      />
                      <span className='min-w-0 truncate'>{o.name}</span>
                    </label>
                  )
                })}
              </div>
            </div>
          ) : (
            <div className='rounded-lg border border-border bg-surface-muted p-3'>
              <p className='m-0 text-[13px] text-muted-foreground'>
                Module grants below apply to <strong className='text-foreground'>every organisation</strong> when you
                save.
              </p>
            </div>
          )}

          <div className='min-w-0 space-y-2.5'>
            {!applyToAll && singleOrgId ? (
              <Pill tone={usesPlatformDefault ? 'info' : 'warning'}>
                {usesPlatformDefault ? 'Inherits platform defaults' : 'Custom override active'}
              </Pill>
            ) : null}

            {!applyToAll && selectedOrgIds.length > 1 ? (
              <p className='rounded-md border border-border bg-surface-muted px-2.5 py-2 text-[12px] text-muted-foreground'>
                Same module grants will apply to <strong className='text-foreground'>{selectedOrgIds.length} organisations</strong>{' '}
                when you save. Select only one org to preview what that customer sees.
              </p>
            ) : null}

            <p className='m-0 text-[12px] text-muted-foreground'>
              Toggle <strong className='text-foreground'>Granted</strong> to control what the customer may use. Revoked
              modules disappear from their dashboard and Settings → Services.
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

            <div className='flex flex-wrap gap-2 pt-1'>
              <Button
                type='button'
                size='sm'
                className='h-8'
                onClick={() => void onSaveSelectedOrgs()}
                disabled={orgSectionDisabled}
              >
                {savingOrgs
                  ? 'Saving…'
                  : applyToAll
                    ? 'Apply grants to all organisations'
                    : `Save grants for ${selectedOrgIds.length} organisation(s)`}
              </Button>
              <Button
                type='button'
                variant='outline'
                size='sm'
                className='h-8'
                onClick={() => void onResetSelectedToPlatform()}
                disabled={savingOrgs || (!applyToAll && selectedOrgIds.length === 0)}
              >
                Reset to platform defaults
              </Button>
            </div>
          </div>
        </div>
      </Panel>
    </div>
  )
}
