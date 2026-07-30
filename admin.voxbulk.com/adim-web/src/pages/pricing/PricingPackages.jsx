import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { apiFetch } from '../../lib/api'
import { CURRENCY_SYMBOLS } from '../../lib/billingAdminUtils'
import PricingPageFrame, { PricingLoadGate } from './PricingPageFrame'
import { penceToPounds, poundsToPence } from './pricingUtils'

const CURRENCIES = ['GBP', 'EUR', 'USD', 'CAD', 'AUD']

const SERVICES = [
  {
    key: 'voxbulk',
    title: 'Core platform',
    blurb: 'Interview, WA Surveys & ATS — billed monthly or annually.',
    tint: 'core',
    priceMode: 'subscription',
  },
  {
    key: 'customer_feedback',
    title: 'Customer Feedback',
    blurb: 'Location packages — monthly and annual subscription prices.',
    tint: 'feedback',
    priceMode: 'subscription',
  },
  {
    key: 'expo',
    title: 'VoxBulk Expo',
    blurb: 'Per-exhibition packages — one-time payment, optional annual if a company wants to subscribe.',
    tint: 'expo',
    priceMode: 'expo',
  },
  {
    key: 'smart_card',
    title: 'Smart Card QR',
    blurb: '$5/seat/month billed annually — edit yearly unit price',
    tint: 'feedback',
    priceMode: 'subscription',
  },
]

function emptyPriceDraft() {
  const out = {}
  for (const c of CURRENCIES) {
    out[c] = { monthly: '', yearly: '', perMin: '', extraPerMin: '' }
  }
  return out
}

function pricesToDraft(prices) {
  const out = emptyPriceDraft()
  for (const c of CURRENCIES) {
    const row = prices?.[c] || {}
    out[c] = {
      monthly: row.monthly_price_minor != null ? penceToPounds(row.monthly_price_minor) : '',
      yearly: row.yearly_price_minor != null ? penceToPounds(row.yearly_price_minor) : '',
      perMin: row.per_min_minor != null ? penceToPounds(row.per_min_minor) : '',
      extraPerMin: row.extra_per_min_minor != null ? penceToPounds(row.extra_per_min_minor) : '',
    }
  }
  return out
}

function draftToPricesPayload(draft, priceMode) {
  const prices = {}
  for (const c of CURRENCIES) {
    const row = draft?.[c] || {}
    const payload = {
      monthly_price_minor: row.monthly === '' ? null : poundsToPence(row.monthly),
      yearly_price_minor: row.yearly === '' ? null : poundsToPence(row.yearly),
    }
    if (priceMode === 'subscription' || priceMode === 'core') {
      payload.per_min_minor = poundsToPence(row.perMin || 0)
      payload.extra_per_min_minor = poundsToPence(row.extraPerMin || 0)
    } else {
      payload.per_min_minor = 0
      payload.extra_per_min_minor = 0
    }
    prices[c] = payload
  }
  return prices
}

function formatMinor(minor, currency) {
  if (minor == null || minor === '') return '—'
  const sym = CURRENCY_SYMBOLS[currency] || currency
  return `${sym}${(Number(minor) / 100).toFixed(2)}`
}

function MoneyInput({ value, onChange, placeholder }) {
  return (
    <input
      className="input pricingInputSm pricingInputNum"
      type="number"
      step="0.01"
      min="0"
      value={value}
      placeholder={placeholder || '0.00'}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

function newDraftFor(serviceKey) {
  if (serviceKey === 'expo') {
    return {
      service_kind: 'expo',
      name: '',
      code: '',
      duration_days: 1,
      tier: 'day1',
      max_booths: 1,
      max_assets: 5,
      lead_scoring_enabled: true,
      is_active: true,
      is_featured: false,
      sort_order: 100,
      features: [],
      prices: emptyPriceDraft(),
    }
  }
  if (serviceKey === 'smart_card') {
    return {
      service_kind: 'smart_card',
      name: '',
      code: '',
      tier: 'seat',
      monthly_unit_hint_usd_cents: 500,
      interval: 'yearly',
      is_active: true,
      is_featured: false,
      sort_order: 100,
      features: [],
      prices: emptyPriceDraft(),
    }
  }
  if (serviceKey === 'customer_feedback') {
    return {
      service_kind: 'customer_feedback',
      name: '',
      code: '',
      max_locations: 1,
      wa_units_included: 100,
      web_units_included: 100,
      promo_message_cost_minor: 5,
      is_active: true,
      is_featured: false,
      sort_order: 100,
      prices: emptyPriceDraft(),
    }
  }
  return {
    service_kind: 'voxbulk',
    name: '',
    code: '',
    interval: 'monthly',
    calls_included: 0,
    whatsapp_included: 0,
    cv_scans_included: 0,
    per_min_pence: 0,
    extra_per_min_pence: 0,
    is_active: true,
    is_featured: false,
    is_enterprise: false,
    sort_order: 100,
    prices: emptyPriceDraft(),
  }
}

function packageToDraft(pkg) {
  return {
    ...pkg,
    prices: pricesToDraft(pkg.prices),
    featuresText: Array.isArray(pkg.features) ? pkg.features.join('\n') : '',
  }
}

export default function PricingPackages() {
  const [searchParams] = useSearchParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [drawer, setDrawer] = useState(null) // { mode: 'create'|'edit', serviceKey, draft, saving }

  const load = useCallback(async () => {
    setError('')
    try {
      const body = await apiFetch('/admin/pricing/packages?active_only=true')
      setData(body)
      return true
    } catch (e) {
      setError(e?.message || 'Could not load packages')
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

  useEffect(() => {
    const focus = searchParams.get('service') || searchParams.get('tab')
    const planCode = searchParams.get('plan')
    if ((!focus && !planCode) || !data) return
    const map = {
      core: 'voxbulk',
      voxbulk: 'voxbulk',
      feedback: 'customer_feedback',
      customer_feedback: 'customer_feedback',
      expo: 'expo',
      smart_card: 'smart_card',
      'smart-card': 'smart_card',
    }
    const key = map[String(focus || '').toLowerCase()]
    const t = window.setTimeout(() => {
      if (key) document.getElementById(`pricing-pkg-${key}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      if (planCode) {
        document.getElementById(`pricing-pkg-row-${planCode}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
    }, 150)
    return () => window.clearTimeout(t)
  }, [searchParams, data])

  const packagesByKind = useMemo(() => data?.packages || {}, [data])

  const openCreate = (serviceKey) => {
    setDrawer({ mode: 'create', serviceKey, draft: newDraftFor(serviceKey), saving: false })
  }

  const openEdit = (serviceKey, pkg) => {
    setDrawer({ mode: 'edit', serviceKey, draft: packageToDraft(pkg), saving: false })
  }

  const closeDrawer = () => setDrawer(null)

  const setDraftField = (key, value) => {
    setDrawer((d) => (d ? { ...d, draft: { ...d.draft, [key]: value } } : d))
  }

  const setPriceField = (currency, field, value) => {
    setDrawer((d) => {
      if (!d) return d
      const prices = { ...(d.draft.prices || emptyPriceDraft()) }
      prices[currency] = { ...(prices[currency] || {}), [field]: value }
      return { ...d, draft: { ...d.draft, prices } }
    })
  }

  const saveDrawer = async () => {
    if (!drawer) return
    const { mode, serviceKey, draft } = drawer
    const svc = SERVICES.find((s) => s.key === serviceKey)
    setDrawer((d) => (d ? { ...d, saving: true } : d))
    setError('')
    setMsg('')
    try {
      const features = String(draft.featuresText || '')
        .split('\n')
        .map((x) => x.trim())
        .filter(Boolean)
      const prices = draftToPricesPayload(draft.prices, svc?.priceMode || 'subscription')
      const payload = {
        service_kind: serviceKey,
        name: draft.name,
        code: draft.code,
        is_active: Boolean(draft.is_active),
        is_featured: Boolean(draft.is_featured),
        is_enterprise: Boolean(draft.is_enterprise),
        sort_order: Number(draft.sort_order || 100),
        description: draft.description || undefined,
        features,
        prices,
      }
      if (serviceKey === 'voxbulk') {
        Object.assign(payload, {
          interval: draft.interval || 'monthly',
          calls_included: Number(draft.calls_included || 0),
          whatsapp_included: Number(draft.whatsapp_included || 0),
          cv_scans_included: Number(draft.cv_scans_included || 0),
        })
      }
      if (serviceKey === 'customer_feedback') {
        Object.assign(payload, {
          max_locations: Number(draft.max_locations || 1),
          wa_units_included: Number(draft.wa_units_included || 0),
          web_units_included: Number(draft.web_units_included || 0),
          promo_message_cost_minor: Number(draft.promo_message_cost_minor || 5),
        })
      }
      if (serviceKey === 'expo') {
        Object.assign(payload, {
          duration_days: Number(draft.duration_days || 1),
          tier: draft.tier || `day${draft.duration_days || 1}`,
          max_booths: Number(draft.max_booths || 1),
          max_assets: Number(draft.max_assets || 5),
          lead_scoring_enabled: Boolean(draft.lead_scoring_enabled),
          post_show_followup_enabled: Boolean(draft.post_show_followup_enabled),
          post_event_survey_enabled: Boolean(draft.post_event_survey_enabled),
          ai_summary_report_enabled: Boolean(draft.ai_summary_report_enabled),
        })
      }
      if (serviceKey === 'smart_card') {
        Object.assign(payload, {
          interval: draft.interval || 'yearly',
          tier: draft.tier || 'seat',
          monthly_unit_hint_usd_cents: Number(draft.monthly_unit_hint_usd_cents ?? 500),
        })
      }

      if (mode === 'create') {
        await apiFetch('/admin/pricing/packages', { method: 'POST', body: JSON.stringify(payload) })
        setMsg('Package created.')
      } else {
        await apiFetch(`/admin/pricing/packages/${encodeURIComponent(draft.id)}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        })
        setMsg('Package saved.')
      }
      setDrawer(null)
      await load()
    } catch (e) {
      setError(e?.message || 'Save failed')
      setDrawer((d) => (d ? { ...d, saving: false } : d))
    }
  }

  const deactivate = async (pkg) => {
    if (!window.confirm(`Deactivate “${pkg.name}”? It will disappear from this list.`)) return
    setError('')
    try {
      await apiFetch(`/admin/pricing/packages/${encodeURIComponent(pkg.id)}`, { method: 'DELETE' })
      setMsg('Package deactivated.')
      await load()
    } catch (e) {
      setError(e?.message || 'Could not deactivate')
    }
  }

  return (
    <PricingLoadGate
      loading={loading}
      error={!data ? error : ''}
      title="Packages"
      description="Active packages by service — open a row to edit multi-currency prices."
      onRetry={load}
    >
      {data ? (
        <PricingPageFrame
          title="Packages"
          description="One table per product. Inactive packages are hidden. Open a package to edit prices in the drawer."
          error={error}
          msg={msg}
        >
          <div className="pricingPackagesStack">
            {SERVICES.map((svc) => {
              const rows = packagesByKind[svc.key] || []
              return (
                <section
                  key={svc.key}
                  id={`pricing-pkg-${svc.key}`}
                  className={`pricingPkgTableCard tint-${svc.tint}`}
                >
                  <div className="pricingPkgTableHead">
                    <div>
                      <h3 className="pricingPkgTableTitle">{svc.title}</h3>
                      <p className="muted pricingPkgTableBlurb">{svc.blurb}</p>
                    </div>
                    <button className="btn soft" type="button" onClick={() => openCreate(svc.key)}>
                      + Create package
                    </button>
                  </div>
                  <div className="tableWrap">
                    <table className="pricingPkgTable">
                      <thead>
                        <tr>
                          <th>Package</th>
                          <th>Code</th>
                          {svc.priceMode === 'expo' ? (
                            <>
                              <th>Days</th>
                              <th>One-time (GBP)</th>
                              <th>Annual (GBP)</th>
                            </>
                          ) : svc.key === 'smart_card' ? (
                            <>
                              <th>Tier</th>
                              <th>Yearly (GBP)</th>
                              <th>Monthly hint (USD¢)</th>
                            </>
                          ) : (
                            <>
                              <th>Monthly (GBP)</th>
                              <th>Yearly (GBP)</th>
                            </>
                          )}
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {rows.length === 0 ? (
                          <tr>
                            <td colSpan={6} className="muted">No active packages yet.</td>
                          </tr>
                        ) : (
                          rows.map((pkg) => {
                            const gbp = pkg.prices?.GBP || {}
                            return (
                              <tr key={pkg.id} id={`pricing-pkg-row-${pkg.code}`} className="pricingPkgRow">
                                <td>
                                  <strong>{pkg.name}</strong>
                                  {pkg.is_featured ? <span className="pill p-cyan" style={{ marginLeft: 8 }}>Featured</span> : null}
                                  {pkg.is_enterprise ? <span className="pill p-amber" style={{ marginLeft: 8 }}>Enterprise</span> : null}
                                </td>
                                <td className="muted">{pkg.code}</td>
                                {svc.priceMode === 'expo' ? (
                                  <>
                                    <td>{pkg.duration_days || '—'}</td>
                                    <td>{formatMinor(gbp.monthly_price_minor, 'GBP')}</td>
                                    <td>{formatMinor(gbp.yearly_price_minor, 'GBP')}</td>
                                  </>
                                ) : svc.key === 'smart_card' ? (
                                  <>
                                    <td>{pkg.tier || 'seat'}</td>
                                    <td><strong>{formatMinor(gbp.yearly_price_minor, 'GBP')}</strong></td>
                                    <td className="muted">{pkg.monthly_unit_hint_usd_cents ?? 500}</td>
                                  </>
                                ) : (
                                  <>
                                    <td>{formatMinor(gbp.monthly_price_minor, 'GBP')}</td>
                                    <td>{formatMinor(gbp.yearly_price_minor, 'GBP')}</td>
                                  </>
                                )}
                                <td className="pricingPkgActions">
                                  <button className="btn soft pricingSaveBtn" type="button" onClick={() => openEdit(svc.key, pkg)}>
                                    Edit
                                  </button>
                                  <button className="btn ghost pricingSaveBtn" type="button" onClick={() => void deactivate(pkg)}>
                                    Off
                                  </button>
                                </td>
                              </tr>
                            )
                          })
                        )}
                      </tbody>
                    </table>
                  </div>
                </section>
              )
            })}
          </div>

          <div className={`pricingPkgOverlay${drawer ? ' open' : ''}`} onClick={closeDrawer} />
          <div className={`pricingPkgDrawer${drawer ? ' open' : ''}`} role="dialog" aria-modal={Boolean(drawer)}>
            {drawer ? (
              <div className="pricingPkgDrawerInner">
                <div className="pricingPkgDrawerHeader">
                  <div>
                    <div className="pricingPkgDrawerTitle">
                      {drawer.mode === 'create' ? 'Create package' : 'Edit package'}
                    </div>
                    <div className="muted">{SERVICES.find((s) => s.key === drawer.serviceKey)?.title}</div>
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
                    <input
                      className="input"
                      value={drawer.draft.code || ''}
                      onChange={(e) => setDraftField('code', e.target.value)}
                      disabled={drawer.mode === 'edit'}
                    />
                  </div>

                  <div className="pricingPkgToggleRow">
                    <span>Active</span>
                    <button
                      type="button"
                      className={`toggle${drawer.draft.is_active ? ' on' : ''}`}
                      onClick={() => setDraftField('is_active', !drawer.draft.is_active)}
                    >
                      <span />
                    </button>
                  </div>
                  <div className="pricingPkgToggleRow">
                    <span>Featured</span>
                    <button
                      type="button"
                      className={`toggle${drawer.draft.is_featured ? ' on' : ''}`}
                      onClick={() => setDraftField('is_featured', !drawer.draft.is_featured)}
                    >
                      <span />
                    </button>
                  </div>

                  {drawer.serviceKey === 'voxbulk' ? (
                    <>
                      <div className="pricingPkgFieldGrid">
                        <div className="pricingPkgField">
                          <label>Minutes included</label>
                          <input className="input" type="number" value={drawer.draft.calls_included ?? 0} onChange={(e) => setDraftField('calls_included', e.target.value)} />
                        </div>
                        <div className="pricingPkgField">
                          <label>WA included</label>
                          <input className="input" type="number" value={drawer.draft.whatsapp_included ?? 0} onChange={(e) => setDraftField('whatsapp_included', e.target.value)} />
                        </div>
                        <div className="pricingPkgField">
                          <label>CV scans</label>
                          <input className="input" type="number" value={drawer.draft.cv_scans_included ?? 0} onChange={(e) => setDraftField('cv_scans_included', e.target.value)} />
                        </div>
                      </div>
                    </>
                  ) : null}

                  {drawer.serviceKey === 'customer_feedback' ? (
                    <div className="pricingPkgFieldGrid">
                      <div className="pricingPkgField">
                        <label>Locations</label>
                        <input className="input" type="number" value={drawer.draft.max_locations ?? 1} onChange={(e) => setDraftField('max_locations', e.target.value)} />
                      </div>
                      <div className="pricingPkgField">
                        <label>WA units / mo</label>
                        <input className="input" type="number" value={drawer.draft.wa_units_included ?? 0} onChange={(e) => setDraftField('wa_units_included', e.target.value)} />
                      </div>
                      <div className="pricingPkgField">
                        <label>Web units / mo (−1 = unlimited)</label>
                        <input className="input" type="number" value={drawer.draft.web_units_included ?? 0} onChange={(e) => setDraftField('web_units_included', e.target.value)} />
                      </div>
                    </div>
                  ) : null}

                  {drawer.serviceKey === 'expo' ? (
                    <div className="pricingPkgFieldGrid">
                      <div className="pricingPkgField">
                        <label>Duration (days)</label>
                        <input className="input" type="number" min="1" value={drawer.draft.duration_days ?? 1} onChange={(e) => setDraftField('duration_days', e.target.value)} />
                      </div>
                      <div className="pricingPkgField">
                        <label>Max booths</label>
                        <input className="input" type="number" min="1" value={drawer.draft.max_booths ?? 1} onChange={(e) => setDraftField('max_booths', e.target.value)} />
                      </div>
                      <div className="pricingPkgField">
                        <label>Max assets</label>
                        <input className="input" type="number" min="1" value={drawer.draft.max_assets ?? 5} onChange={(e) => setDraftField('max_assets', e.target.value)} />
                      </div>
                    </div>
                  ) : null}

                  {drawer.serviceKey === 'smart_card' ? (
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

                  <div className="pricingPkgField">
                    <label>Features (one per line)</label>
                    <textarea
                      className="input"
                      rows={4}
                      value={drawer.draft.featuresText || ''}
                      onChange={(e) => setDraftField('featuresText', e.target.value)}
                    />
                  </div>

                  <h4 className="pricingPkgPricesTitle">
                    {drawer.serviceKey === 'expo'
                      ? 'One-time & optional annual prices'
                      : drawer.serviceKey === 'smart_card'
                        ? 'Yearly seat prices (billed annually)'
                        : 'Monthly & yearly prices'}
                  </h4>
                  <table className="pricingPlanPriceTable">
                    <thead>
                      <tr>
                        <th>Currency</th>
                        {drawer.serviceKey === 'smart_card' ? null : (
                          <th>{drawer.serviceKey === 'expo' ? 'One-time' : 'Monthly'}</th>
                        )}
                        <th>
                          {drawer.serviceKey === 'expo'
                            ? 'Annual (optional)'
                            : drawer.serviceKey === 'smart_card'
                              ? 'Yearly (per seat)'
                              : 'Yearly'}
                        </th>
                        {drawer.serviceKey === 'voxbulk' ? (
                          <>
                            <th>Per minute</th>
                            <th>Extra / min</th>
                          </>
                        ) : null}
                      </tr>
                    </thead>
                    <tbody>
                      {CURRENCIES.map((currency) => {
                        const row = drawer.draft.prices?.[currency] || {}
                        const sym = CURRENCY_SYMBOLS[currency] || currency
                        return (
                          <tr key={currency}>
                            <td><strong>{sym} {currency}</strong></td>
                            {drawer.serviceKey === 'smart_card' ? null : (
                              <td>
                                <MoneyInput value={row.monthly ?? ''} onChange={(v) => setPriceField(currency, 'monthly', v)} />
                              </td>
                            )}
                            <td>
                              <MoneyInput
                                value={row.yearly ?? ''}
                                onChange={(v) => setPriceField(currency, 'yearly', v)}
                                placeholder={drawer.serviceKey === 'expo' ? 'Optional' : '0.00'}
                              />
                            </td>
                            {drawer.serviceKey === 'voxbulk' ? (
                              <>
                                <td>
                                  <MoneyInput value={row.perMin ?? ''} onChange={(v) => setPriceField(currency, 'perMin', v)} />
                                </td>
                                <td>
                                  <MoneyInput value={row.extraPerMin ?? ''} onChange={(v) => setPriceField(currency, 'extraPerMin', v)} />
                                </td>
                              </>
                            ) : null}
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="pricingPkgDrawerFooter">
                  <button className="btn ghost" type="button" onClick={closeDrawer}>Cancel</button>
                  <button className="btn primary" type="button" disabled={drawer.saving} onClick={() => void saveDrawer()}>
                    {drawer.saving ? 'Saving…' : 'Save package'}
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </PricingPageFrame>
      ) : null}
    </PricingLoadGate>
  )
}
