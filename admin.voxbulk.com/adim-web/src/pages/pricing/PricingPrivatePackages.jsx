import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../../lib/api'
import { CURRENCY_SYMBOLS } from '../../lib/billingAdminUtils'
import PricingPageFrame, { PricingLoadGate } from './PricingPageFrame'
import { penceToPounds, poundsToPence } from './pricingUtils'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

const CURRENCIES = ['GBP', 'EUR', 'USD', 'CAD', 'AUD']
const SERVICES = [
  { key: 'voxbulk', label: 'Core platform' },
  { key: 'customer_feedback', label: 'Customer Feedback' },
  { key: 'expo', label: 'Expo' },
  { key: 'smart_card', label: 'Smart Card QR' },
]

function defaultInterval(serviceKey) {
  if (serviceKey === 'expo') return 'one_time'
  if (serviceKey === 'smart_card') return 'yearly'
  return 'monthly'
}

function emptyMoneyMap() {
  const out = {}
  for (const c of CURRENCIES) out[c] = { monthly: '', yearly: '', perMin: '', extraPerMin: '' }
  return out
}

function emptyUnitMap() {
  const out = {}
  for (const c of CURRENCIES) {
    out[c] = { connection: '', interview: '', waPackage: '', waExtra: '', cvScan: '' }
  }
  return out
}

function defaultsToDraft(defaults) {
  const prices = emptyMoneyMap()
  const unitRates = emptyUnitMap()
  for (const c of CURRENCIES) {
    const p = defaults?.prices?.[c] || {}
    const u = defaults?.unit_rates?.[c] || {}
    prices[c] = {
      monthly: p.monthly_price_minor != null ? penceToPounds(p.monthly_price_minor) : '',
      yearly: p.yearly_price_minor != null ? penceToPounds(p.yearly_price_minor) : '',
      perMin: p.per_min_minor != null ? penceToPounds(p.per_min_minor) : '',
      extraPerMin: p.extra_per_min_minor != null ? penceToPounds(p.extra_per_min_minor) : '',
    }
    unitRates[c] = {
      connection: u.connection_fee_minor != null ? penceToPounds(u.connection_fee_minor) : '',
      interview: u.interview_per_min_minor != null ? penceToPounds(u.interview_per_min_minor) : '',
      waPackage: u.wa_package_fee_minor != null ? penceToPounds(u.wa_package_fee_minor) : '',
      waExtra: u.wa_extra_minor != null ? penceToPounds(u.wa_extra_minor) : '',
      cvScan: u.cv_scan_fee_minor != null ? penceToPounds(u.cv_scan_fee_minor) : '',
    }
  }
  return { prices, unitRates }
}

function packageToDraft(pkg) {
  const prices = emptyMoneyMap()
  const unitRates = emptyUnitMap()
  for (const c of CURRENCIES) {
    const p = pkg.prices?.[c] || {}
    const u = pkg.unit_rates?.[c] || {}
    prices[c] = {
      monthly: p.monthly_price_minor != null ? penceToPounds(p.monthly_price_minor) : '',
      yearly: p.yearly_price_minor != null ? penceToPounds(p.yearly_price_minor) : '',
      perMin: p.per_min_minor != null ? penceToPounds(p.per_min_minor) : '',
      extraPerMin: p.extra_per_min_minor != null ? penceToPounds(p.extra_per_min_minor) : '',
    }
    unitRates[c] = {
      connection: u.connection_fee_minor != null ? penceToPounds(u.connection_fee_minor) : '',
      interview: u.interview_per_min_minor != null ? penceToPounds(u.interview_per_min_minor) : '',
      waPackage: u.wa_package_fee_minor != null ? penceToPounds(u.wa_package_fee_minor) : '',
      waExtra: u.wa_extra_minor != null ? penceToPounds(u.wa_extra_minor) : '',
      cvScan: u.cv_scan_fee_minor != null ? penceToPounds(u.cv_scan_fee_minor) : '',
    }
  }
  return {
    ...pkg,
    interval: pkg.interval || defaultInterval(pkg.service_kind),
    org_ids: Array.isArray(pkg.org_ids) ? pkg.org_ids : (pkg.orgs || []).map((o) => o.org_id),
    prices,
    unitRates,
  }
}

function draftToPayload(draft) {
  const isExpo = draft.service_kind === 'expo'
  const isSmartCard = draft.service_kind === 'smart_card'
  const skipUnits = isExpo || isSmartCard
  const prices = {}
  const unit_rates = {}
  for (const c of CURRENCIES) {
    const p = draft.prices?.[c] || {}
    const u = draft.unitRates?.[c] || {}
    prices[c] = {
      monthly_price_minor: p.monthly === '' ? null : poundsToPence(p.monthly),
      yearly_price_minor: p.yearly === '' ? null : poundsToPence(p.yearly),
      per_min_minor: skipUnits ? 0 : poundsToPence(p.perMin || 0),
      extra_per_min_minor: skipUnits ? 0 : poundsToPence(p.extraPerMin || 0),
    }
    if (!skipUnits) {
      unit_rates[c] = {
        connection_fee_minor: u.connection === '' ? null : poundsToPence(u.connection),
        interview_per_min_minor: u.interview === '' ? null : poundsToPence(u.interview),
        wa_package_fee_minor: u.waPackage === '' ? null : poundsToPence(u.waPackage),
        wa_extra_minor: u.waExtra === '' ? null : poundsToPence(u.waExtra),
        cv_scan_fee_minor: u.cvScan === '' ? null : poundsToPence(u.cvScan),
      }
    }
  }
  const payload = {
    service_kind: draft.service_kind,
    name: draft.name,
    code: draft.code,
    interval: draft.interval || defaultInterval(draft.service_kind),
    is_active: Boolean(draft.is_active ?? true),
    calls_included: Number(draft.calls_included || 0),
    whatsapp_included: Number(draft.whatsapp_included || draft.wa_units_included || 0),
    cv_scans_included: Number(draft.cv_scans_included || 0),
    max_locations: Number(draft.max_locations || 1),
    wa_units_included: Number(draft.wa_units_included || draft.whatsapp_included || 0),
    web_units_included: Number(draft.web_units_included || 100),
    duration_days: Number(draft.duration_days || 1),
    tier: draft.tier || (isSmartCard ? 'seat' : undefined),
    monthly_unit_hint_usd_cents: isSmartCard ? Number(draft.monthly_unit_hint_usd_cents ?? 500) : undefined,
    org_ids: Array.isArray(draft.org_ids) ? draft.org_ids : [],
    prices,
  }
  if (!skipUnits) payload.unit_rates = unit_rates
  return payload
}

function formatMinor(minor, currency = 'GBP') {
  if (minor == null) return '—'
  const sym = CURRENCY_SYMBOLS[currency] || ''
  return `${sym}${(Number(minor) / 100).toFixed(2)}`
}

function MoneyInput({ value, onChange }) {
  return (
    <input
      className="input pricingInputSm pricingInputNum"
      type="number"
      step="0.01"
      min="0"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

export default function PricingPrivatePackages() {
  const [items, setItems] = useState([])
  const [orgs, setOrgs] = useState([])
  const [defaults, setDefaults] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [drawer, setDrawer] = useState(null)
  const [orgQuery, setOrgQuery] = useState('')

  const load = useCallback(async () => {
    setLoadError('')
    try {
      const [pkgBody, orgList, defs] = await Promise.all([
        apiFetch('/admin/pricing/private-packages?active_only=true'),
        apiFetch('/admin/organisations?limit=500'),
        apiFetch('/admin/pricing/private-packages/defaults'),
      ])
      setItems(Array.isArray(pkgBody?.items) ? pkgBody.items : [])
      setOrgs(Array.isArray(orgList) ? orgList : Array.isArray(orgList?.items) ? orgList.items : [])
      setDefaults(defs || null)
      return true
    } catch (e) {
      setLoadError(e?.message || 'Could not load private packages')
      return false
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      await load()
      if (!cancelled) setLoading(false)
    })()
    return () => { cancelled = true }
  }, [load])

  const filteredOrgs = useMemo(() => {
    const q = orgQuery.trim().toLowerCase()
    if (!q) return orgs
    return orgs.filter((o) => String(o.name || '').toLowerCase().includes(q) || String(o.id || '').includes(q))
  }, [orgs, orgQuery])

  const openCreate = (serviceKey) => {
    const { prices, unitRates } = defaultsToDraft(defaults)
    setDrawer({
      mode: 'create',
      draft: {
        service_kind: serviceKey,
        name: '',
        code: '',
        interval: defaultInterval(serviceKey),
        is_active: true,
        calls_included: 0,
        whatsapp_included: 0,
        cv_scans_included: 0,
        max_locations: 1,
        wa_units_included: 100,
        web_units_included: 100,
        duration_days: 1,
        tier: serviceKey === 'smart_card' ? 'seat' : undefined,
        monthly_unit_hint_usd_cents: serviceKey === 'smart_card' ? 500 : undefined,
        org_ids: [],
        prices,
        unitRates,
      },
      saving: false,
    })
  }

  const openEdit = (pkg) => setDrawer({ mode: 'edit', draft: packageToDraft(pkg), saving: false })
  const closeDrawer = () => setDrawer(null)

  const setDraftField = (key, value) => setDrawer((d) => (d ? { ...d, draft: { ...d.draft, [key]: value } } : d))
  const setPrice = (currency, field, value) => {
    setDrawer((d) => {
      if (!d) return d
      const prices = { ...d.draft.prices }
      prices[currency] = { ...(prices[currency] || {}), [field]: value }
      return { ...d, draft: { ...d.draft, prices } }
    })
  }
  const setUnit = (currency, field, value) => {
    setDrawer((d) => {
      if (!d) return d
      const unitRates = { ...d.draft.unitRates }
      unitRates[currency] = { ...(unitRates[currency] || {}), [field]: value }
      return { ...d, draft: { ...d.draft, unitRates } }
    })
  }

  const toggleOrg = (orgId) => {
    setDrawer((d) => {
      if (!d) return d
      const set = new Set(d.draft.org_ids || [])
      if (set.has(orgId)) set.delete(orgId)
      else set.add(orgId)
      return { ...d, draft: { ...d.draft, org_ids: Array.from(set) } }
    })
  }

  const saveDrawer = async () => {
    if (!drawer) return
    setDrawer((d) => (d ? { ...d, saving: true } : d))
    setError('')
    setMsg('')
    try {
      const payload = draftToPayload(drawer.draft)
      if (!payload.name) throw new Error('Name is required')
      if (drawer.mode === 'create') {
        await apiFetch('/admin/pricing/private-packages', { method: 'POST', body: JSON.stringify(payload) })
        setMsg('Private package created and orgs assigned.')
      } else {
        await apiFetch(`/admin/pricing/private-packages/${encodeURIComponent(drawer.draft.id)}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        })
        setMsg('Private package saved.')
      }
      setDrawer(null)
      await load()
    } catch (e) {
      setError(e?.message || 'Save failed')
      setDrawer((d) => (d ? { ...d, saving: false } : d))
    }
  }

  const deactivate = async (pkg) => {
    if (!window.confirm(`Deactivate private package “${pkg.name}”?`)) return
    try {
      await apiFetch(`/admin/pricing/private-packages/${encodeURIComponent(pkg.id)}`, { method: 'DELETE' })
      setMsg('Private package deactivated.')
      await load()
    } catch (e) {
      setError(e?.message || 'Could not deactivate')
    }
  }

  const byService = useMemo(() => {
    const map = { voxbulk: [], customer_feedback: [], expo: [], smart_card: [] }
    for (const item of items) {
      const k = item.service_kind || 'voxbulk'
      if (!map[k]) map[k] = []
      map[k].push(item)
    }
    return map
  }, [items])

  const isExpo = drawer?.draft?.service_kind === 'expo'
  const isSmartCard = drawer?.draft?.service_kind === 'smart_card'
  const isFeedback = drawer?.draft?.service_kind === 'customer_feedback'
  const pricePrimaryLabel = isExpo
    ? (drawer?.draft?.interval === 'yearly' ? 'Yearly' : 'Price')
    : isSmartCard
      ? 'Yearly'
      : 'Monthly'

  return (
    <PricingLoadGate
      loading={loading}
      error={loadError}
      title="Private packages"
      description="Org-only packages — hidden from public pricing. Assign to one or many organisations."
      onRetry={load}
    >
      <PricingPageFrame
        title="Private packages"
        description="Create a private Core / Feedback / Expo package, set prices (defaults prefilled), and assign multiple orgs. Billing and overage use these rates for assigned orgs only. Create as many yearly packages as you need."
        error={error}
        msg={msg}
      >
        <div className="pricingPackagesStack">
          {SERVICES.map((svc) => (
            <section key={svc.key} className={`pricingPkgTableCard tint-${svc.key === 'voxbulk' ? 'core' : svc.key === 'expo' ? 'expo' : 'feedback'}`}>
              <div className="pricingPkgTableHead">
                <div>
                  <h3 className="pricingPkgTableTitle">{svc.label}</h3>
                  <p className="muted pricingPkgTableBlurb">
                    {svc.key === 'smart_card'
                      ? '$5/seat/month billed annually — edit yearly unit price. Private deals only.'
                      : 'Private deals for this product — not shown on public pricing.'}
                  </p>
                </div>
                <Button variant="outline" size="sm" className="h-8" type="button" onClick={() => openCreate(svc.key)}>+ Create private package</Button>
              </div>
              <div className="tableWrap">
                <table className="pricingPkgTable">
                  <thead>
                    <tr>
                      <th>Package</th>
                      <th>Code</th>
                      <th>Billing</th>
                      <th>Orgs</th>
                      <th>Monthly / price (GBP)</th>
                      <th>Yearly (GBP)</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {(byService[svc.key] || []).length === 0 ? (
                      <tr><td colSpan={7} className="muted">No private packages yet.</td></tr>
                    ) : (
                      (byService[svc.key] || []).map((pkg) => {
                        const gbp = pkg.prices?.GBP || {}
                        const orgNames = (pkg.orgs || []).map((o) => o.org_name).filter(Boolean)
                        const interval = String(pkg.interval || defaultInterval(svc.key)).replace(/_/g, ' ')
                        return (
                          <tr key={pkg.id}>
                            <td>
                              <strong>{pkg.name}</strong>
                              {svc.key === 'expo' && pkg.duration_days != null ? (
                                <div className="muted" style={{ fontSize: 12 }}>{pkg.duration_days} day{pkg.duration_days === 1 ? '' : 's'}</div>
                              ) : null}
                            </td>
                            <td className="muted">{pkg.code}</td>
                            <td className="muted" style={{ textTransform: 'capitalize' }}>{interval}</td>
                            <td>{orgNames.length ? orgNames.join(', ') : <span className="muted">None</span>}</td>
                            <td>{svc.key === 'smart_card' ? '—' : formatMinor(gbp.monthly_price_minor)}</td>
                            <td>
                              {svc.key === 'smart_card' ? (
                                <strong>{formatMinor(gbp.yearly_price_minor)}</strong>
                              ) : (
                                formatMinor(gbp.yearly_price_minor)
                              )}
                            </td>
                            <td className="pricingPkgActions">
                              <Button variant="outline" size="sm" className="h-7 text-xs" type="button" onClick={() => openEdit(pkg)}>Edit</Button>
                              <Button variant="ghost" size="sm" className="h-7 text-xs" type="button" onClick={() => void deactivate(pkg)}>Off</Button>
                            </td>
                          </tr>
                        )
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          ))}
        </div>

        <div className={`pricingPkgOverlay${drawer ? ' open' : ''}`} onClick={closeDrawer} />
        <div className={`pricingPkgDrawer${drawer ? ' open' : ''}`}>
          {drawer ? (
            <div className="pricingPkgDrawerInner">
              <div className="pricingPkgDrawerHeader">
                <div>
                  <div className="pricingPkgDrawerTitle">{drawer.mode === 'create' ? 'Create private package' : 'Edit private package'}</div>
                  <div className="muted">{SERVICES.find((s) => s.key === drawer.draft.service_kind)?.label}</div>
                </div>
                <button className="close-x" type="button" onClick={closeDrawer}>✕</button>
              </div>
              <div className="pricingPkgDrawerBody">
                <div className="pricingPkgField">
                  <label>Name</label>
                  <input className="input" value={drawer.draft.name || ''} onChange={(e) => setDraftField('name', e.target.value)} />
                </div>
                <div className="pricingPkgField">
                  <label>Code</label>
                  <input className="input" value={drawer.draft.code || ''} onChange={(e) => setDraftField('code', e.target.value)} disabled={drawer.mode === 'edit'} placeholder="auto if blank" />
                </div>

                <div className="pricingPkgField">
                  <label>Billing</label>
                  {isExpo ? (
                    <select className="input" value={drawer.draft.interval || 'one_time'} onChange={(e) => setDraftField('interval', e.target.value)}>
                      <option value="one_time">One-time</option>
                      <option value="yearly">Yearly</option>
                    </select>
                  ) : isSmartCard ? (
                    <select className="input" value={drawer.draft.interval || 'yearly'} onChange={(e) => setDraftField('interval', e.target.value)}>
                      <option value="yearly">Yearly</option>
                    </select>
                  ) : (
                    <select className="input" value={drawer.draft.interval || 'monthly'} onChange={(e) => setDraftField('interval', e.target.value)}>
                      <option value="monthly">Monthly</option>
                      <option value="yearly">Yearly</option>
                    </select>
                  )}
                </div>

                {isFeedback ? (
                  <div className="pricingPkgFieldGrid">
                    <div className="pricingPkgField">
                      <label>Locations</label>
                      <input className="input" type="number" value={drawer.draft.max_locations ?? 1} onChange={(e) => setDraftField('max_locations', e.target.value)} />
                    </div>
                    <div className="pricingPkgField">
                      <label>WA units</label>
                      <input className="input" type="number" value={drawer.draft.wa_units_included ?? 100} onChange={(e) => setDraftField('wa_units_included', e.target.value)} />
                    </div>
                    <div className="pricingPkgField">
                      <label>Web units</label>
                      <input className="input" type="number" value={drawer.draft.web_units_included ?? 100} onChange={(e) => setDraftField('web_units_included', e.target.value)} />
                    </div>
                  </div>
                ) : null}

                {isExpo ? (
                  <div className="pricingPkgField">
                    <label>Duration days</label>
                    <input className="input" type="number" min="1" value={drawer.draft.duration_days ?? 1} onChange={(e) => setDraftField('duration_days', e.target.value)} />
                  </div>
                ) : null}

                {isSmartCard ? (
                  <div className="pricingPkgFieldGrid">
                    <div className="pricingPkgField">
                      <label>Tier</label>
                      <input className="input" value={drawer.draft.tier || 'seat'} onChange={(e) => setDraftField('tier', e.target.value)} />
                    </div>
                    <div className="pricingPkgField">
                      <label>Monthly unit hint (USD cents)</label>
                      <input
                        className="input"
                        type="number"
                        min="0"
                        value={drawer.draft.monthly_unit_hint_usd_cents ?? 500}
                        onChange={(e) => setDraftField('monthly_unit_hint_usd_cents', e.target.value)}
                      />
                    </div>
                  </div>
                ) : null}

                <h4 className="pricingPkgPricesTitle">Assign organisations</h4>
                <Input className="mb-2 h-8" placeholder="Search orgs…" value={orgQuery} onChange={(e) => setOrgQuery(e.target.value)} />
                <div className="pricingPrivateOrgList">
                  {filteredOrgs.slice(0, 80).map((o) => {
                    const on = (drawer.draft.org_ids || []).includes(o.id)
                    return (
                      <label key={o.id} className={`pricingPrivateOrgRow${on ? ' on' : ''}`}>
                        <input type="checkbox" checked={on} onChange={() => toggleOrg(o.id)} />
                        <span>{o.name}</span>
                      </label>
                    )
                  })}
                </div>
                <p className="muted" style={{ fontSize: 12 }}>{(drawer.draft.org_ids || []).length} org(s) selected</p>

                <h4 className="pricingPkgPricesTitle">
                  {isSmartCard ? 'Yearly seat prices (billed annually)' : 'Package prices'}
                </h4>
                <table className="pricingPlanPriceTable">
                  <thead>
                    <tr>
                      <th>Currency</th>
                      {isSmartCard ? null : (
                        <th>{isExpo ? (drawer.draft.interval === 'yearly' ? 'Yearly' : 'Price') : pricePrimaryLabel}</th>
                      )}
                      {isSmartCard || (!isExpo || drawer.draft.interval !== 'yearly') ? (
                        <th>Yearly{isExpo && !isSmartCard ? ' (optional)' : isSmartCard ? ' (per seat)' : ''}</th>
                      ) : null}
                      {!isExpo && !isSmartCard ? (
                        <>
                          <th>Per min</th>
                          <th>Extra / min</th>
                        </>
                      ) : null}
                    </tr>
                  </thead>
                  <tbody>
                    {CURRENCIES.map((c) => {
                      const row = drawer.draft.prices?.[c] || {}
                      const showYearlyCol = isSmartCard || !isExpo || drawer.draft.interval !== 'yearly'
                      const yearlyOnly = isSmartCard || (isExpo && drawer.draft.interval === 'yearly')
                      return (
                        <tr key={c}>
                          <td><strong>{CURRENCY_SYMBOLS[c] || c} {c}</strong></td>
                          {isSmartCard ? null : (
                            <td>
                              <MoneyInput
                                value={yearlyOnly ? (row.yearly ?? '') : (row.monthly ?? '')}
                                onChange={(v) => setPrice(c, yearlyOnly ? 'yearly' : 'monthly', v)}
                              />
                            </td>
                          )}
                          {showYearlyCol ? (
                            <td><MoneyInput value={row.yearly ?? ''} onChange={(v) => setPrice(c, 'yearly', v)} /></td>
                          ) : null}
                          {!isExpo && !isSmartCard ? (
                            <>
                              <td><MoneyInput value={row.perMin ?? ''} onChange={(v) => setPrice(c, 'perMin', v)} /></td>
                              <td><MoneyInput value={row.extraPerMin ?? ''} onChange={(v) => setPrice(c, 'extraPerMin', v)} /></td>
                            </>
                          ) : null}
                        </tr>
                      )
                    })}
                  </tbody>
                </table>

                {!isExpo && !isSmartCard ? (
                  <>
                    <h4 className="pricingPkgPricesTitle">Unit rates (blank = platform default)</h4>
                    <table className="pricingPlanPriceTable">
                      <thead>
                        <tr>
                          <th>Currency</th>
                          <th>Connection</th>
                          <th>Interview / min</th>
                          <th>WA package</th>
                          <th>WA extra</th>
                          <th>CV scan</th>
                        </tr>
                      </thead>
                      <tbody>
                        {CURRENCIES.map((c) => {
                          const row = drawer.draft.unitRates?.[c] || {}
                          return (
                            <tr key={c}>
                              <td><strong>{c}</strong></td>
                              <td><MoneyInput value={row.connection ?? ''} onChange={(v) => setUnit(c, 'connection', v)} /></td>
                              <td><MoneyInput value={row.interview ?? ''} onChange={(v) => setUnit(c, 'interview', v)} /></td>
                              <td><MoneyInput value={row.waPackage ?? ''} onChange={(v) => setUnit(c, 'waPackage', v)} /></td>
                              <td><MoneyInput value={row.waExtra ?? ''} onChange={(v) => setUnit(c, 'waExtra', v)} /></td>
                              <td><MoneyInput value={row.cvScan ?? ''} onChange={(v) => setUnit(c, 'cvScan', v)} /></td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </>
                ) : null}
              </div>
              <div className="pricingPkgDrawerFooter">
                <Button variant="ghost" size="sm" className="h-8" type="button" onClick={closeDrawer}>Cancel</Button>
                <Button size="sm" className="h-8" type="button" disabled={drawer.saving} onClick={() => void saveDrawer()}>
                  {drawer.saving ? 'Saving…' : 'Save & assign'}
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      </PricingPageFrame>
    </PricingLoadGate>
  )
}
