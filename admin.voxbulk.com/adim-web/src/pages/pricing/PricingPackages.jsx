import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { apiFetch } from '../../lib/api'
import { CURRENCY_SYMBOLS } from '../../lib/billingAdminUtils'
import PricingPageFrame, { PricingLoadGate } from './PricingPageFrame'
import { penceToPounds, poundsToPence } from './pricingUtils'
import { Button } from '@/components/ui/Button'

const CURRENCIES = ['GBP', 'EUR', 'USD', 'CAD', 'AUD']
const FX_QUOTES = ['EUR', 'USD', 'CAD', 'AUD']

const SERVICES = [
  { key: 'voxbulk', label: 'Core package', blurb: 'AI interviews, WA surveys and ATS — each package has its own rates. Only the connection fee is shared.' },
  { key: 'customer_feedback', label: 'Customer feedback', blurb: 'Location packages with WhatsApp and web survey allowances.' },
  { key: 'expo', label: 'Expo', blurb: 'One-off exhibition booth packages.' },
  { key: 'smart_card', label: 'Smart card', blurb: 'Per-seat QR pricing.' },
]

function money(minor, currency = 'GBP') {
  if (minor == null || minor === '') return '—'
  const sym = CURRENCY_SYMBOLS[currency] || ''
  return `${sym}${(Number(minor) / 100).toFixed(2)}`
}

function Num({ value, onChange, prefix, disabled, step = '0.01' }) {
  return (
    <div className="uppInputWrap">
      {prefix ? <span className="uppPrefix">{prefix}</span> : null}
      <input
        className={`input uppNum${prefix ? ' withPrefix' : ''}`}
        type="number"
        step={step}
        min="0"
        disabled={disabled}
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}

function Toggle({ checked, onChange, label }) {
  return (
    <label className="uppToggle">
      <button type="button" className={`toggle${checked ? ' on' : ''}`} onClick={() => onChange(!checked)}>
        <span />
      </button>
      {label ? <span className="uppToggleLabel">{label}</span> : null}
    </label>
  )
}

export default function PricingPackages() {
  const [searchParams, setSearchParams] = useSearchParams()
  const rawService = searchParams.get('service') || 'voxbulk'
  const serviceKey = rawService === 'core' ? 'voxbulk' : rawService === 'smartcard' ? 'smart_card' : rawService
  const active = SERVICES.some((s) => s.key === serviceKey) ? serviceKey : 'voxbulk'

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [packagesByService, setPackagesByService] = useState({})
  const [fxRates, setFxRates] = useState({})
  const [currency, setCurrency] = useState('GBP')
  const [expanded, setExpanded] = useState({})
  const [drafts, setDrafts] = useState({})
  const [dirty, setDirty] = useState({})
  const [savingId, setSavingId] = useState(null)
  const [fxOpen, setFxOpen] = useState(false)
  const [sharedDraft, setSharedDraft] = useState({ connection: '' })
  const [sharedDirty, setSharedDirty] = useState(false)
  const [howOpen, setHowOpen] = useState(false)

  const editable = currency === 'GBP'
  const sym = CURRENCY_SYMBOLS[currency] || currency

  const load = useCallback(async () => {
    setError('')
    try {
      const [pkgBody, curBody, fxBody] = await Promise.all([
        apiFetch('/admin/pricing/packages?active_only=false'),
        apiFetch('/admin/pricing/currency-settings'),
        apiFetch('/admin/pricing/fx-rates'),
      ])
      setPackagesByService(pkgBody.packages || {})
      const settings = curBody.currency_settings || []
      const gbp = settings.find((r) => r.currency === 'GBP') || settings[0]
      setSharedDraft({ connection: gbp ? penceToPounds(gbp.connection_fee_minor) : '' })
      setSharedDirty(false)
      setDrafts({})
      setDirty({})
      const fxNext = {}
      for (const r of fxBody.fx_rates || curBody.fx_rates || []) {
        fxNext[r.quote_currency] = String(r.rate ?? '')
      }
      for (const q of FX_QUOTES) if (fxNext[q] == null) fxNext[q] = ''
      setFxRates(fxNext)
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
    return () => {
      cancelled = true
    }
  }, [load])

  const list = useMemo(() => packagesByService[active] || [], [packagesByService, active])

  const buildDraft = useCallback((pkg) => {
    const gbpPrice = pkg.prices?.GBP || {}
    const gbpUnit = pkg.unit_rates?.GBP || {}
    return {
      name: pkg.name || '',
      description: pkg.description || '',
      is_active: Boolean(pkg.is_active),
      is_featured: Boolean(pkg.is_featured),
      monthly: gbpPrice.monthly_price_minor != null ? penceToPounds(gbpPrice.monthly_price_minor) : '',
      yearly: gbpPrice.yearly_price_minor != null ? penceToPounds(gbpPrice.yearly_price_minor) : '',
      perMin: penceToPounds(gbpPrice.per_min_minor || 0),
      extraPerMin: penceToPounds(gbpPrice.extra_per_min_minor || 0),
      waPackage: gbpUnit.wa_package_fee_minor != null ? penceToPounds(gbpUnit.wa_package_fee_minor) : '',
      waExtra: gbpUnit.wa_extra_minor != null ? penceToPounds(gbpUnit.wa_extra_minor) : '',
      cvFee: gbpUnit.cv_scan_fee_minor != null ? penceToPounds(gbpUnit.cv_scan_fee_minor) : '',
      calls_included: pkg.calls_included ?? pkg.minutes_included ?? 0,
      whatsapp_included: pkg.whatsapp_included ?? 0,
      cv_scans_included: pkg.cv_scans_included ?? 0,
      wa_units_included: pkg.wa_units_included ?? 0,
      web_units_included: pkg.web_units_included ?? 0,
      max_locations: pkg.max_locations ?? 1,
      duration_days: pkg.duration_days ?? 1,
      max_booths: pkg.max_booths ?? 1,
      max_assets: pkg.max_assets ?? 5,
      lead_scoring_enabled: Boolean(pkg.lead_scoring_enabled),
      post_show_followup_enabled: Boolean(pkg.post_show_followup_enabled),
      ai_summary_report_enabled: Boolean(pkg.ai_summary_report_enabled),
      oneOff: gbpPrice.monthly_price_minor != null ? penceToPounds(gbpPrice.monthly_price_minor) : '',
      seatYearly: gbpPrice.yearly_price_minor != null ? penceToPounds(gbpPrice.yearly_price_minor) : penceToPounds(gbpPrice.monthly_price_minor || 0),
    }
  }, [])

  useEffect(() => {
    setDrafts((d) => {
      const next = { ...d }
      let changed = false
      for (const pkg of list) {
        if (!next[pkg.id]) {
          next[pkg.id] = buildDraft(pkg)
          changed = true
        }
      }
      return changed ? next : d
    })
  }, [list, buildDraft])

  const setService = (key) => {
    setSearchParams(key === 'voxbulk' ? {} : { service: key })
    setMsg('')
  }

  const patchDraft = (id, patch) => {
    setDrafts((d) => ({ ...d, [id]: { ...(d[id] || {}), ...patch } }))
    setDirty((d) => ({ ...d, [id]: true }))
  }

  const toggleExpand = (id) => {
    setExpanded((e) => ({ ...e, [id]: !e[id] }))
    if (!drafts[id]) {
      const pkg = list.find((p) => p.id === id)
      if (pkg) setDrafts((d) => ({ ...d, [id]: buildDraft(pkg) }))
    }
  }

  const saveShared = async () => {
    setError('')
    setMsg('')
    try {
      const rates = {}
      for (const q of FX_QUOTES) {
        const n = Number(fxRates[q])
        if (!Number.isFinite(n) || n <= 0) throw new Error(`FX rate for ${q} must be positive`)
        rates[q] = n
      }
      await apiFetch('/admin/pricing/fx-rates', { method: 'PUT', body: JSON.stringify({ rates }) })
      await apiFetch('/admin/pricing/currency-settings/GBP', {
        method: 'PUT',
        body: JSON.stringify({ connection_fee_minor: poundsToPence(sharedDraft.connection) }),
      })
      await load()
      setMsg('Shared connection fee and FX rates saved.')
    } catch (e) {
      setError(e?.message || 'Shared save failed')
    }
  }

  const savePackage = async (pkg) => {
    const draft = drafts[pkg.id]
    if (!draft) return
    setSavingId(pkg.id)
    setError('')
    setMsg('')
    try {
      const payload = {
        name: draft.name,
        description: draft.description,
        is_active: draft.is_active,
        is_featured: draft.is_featured,
      }

      if (active === 'voxbulk') {
        payload.calls_included = Number(draft.calls_included || 0)
        payload.whatsapp_included = Number(draft.whatsapp_included || 0)
        payload.cv_scans_included = Number(draft.cv_scans_included || 0)
        const isPayg = String(pkg.code || '').toLowerCase() === 'payg'
        const isEnt = Boolean(pkg.is_enterprise)
        payload.prices = {
          GBP: {
            monthly_price_minor: isPayg || isEnt ? (isEnt ? null : 0) : poundsToPence(draft.monthly),
            yearly_price_minor: isPayg || isEnt ? null : poundsToPence(draft.yearly || 0),
            per_min_minor: poundsToPence(draft.perMin || 0),
            extra_per_min_minor: poundsToPence(draft.extraPerMin || 0),
          },
        }
        payload.unit_rates = {
          GBP: {
            wa_package_fee_minor: poundsToPence(draft.waPackage || 0),
            wa_extra_minor: poundsToPence(draft.waExtra || 0),
            cv_scan_fee_minor: poundsToPence(draft.cvFee || 0),
          },
        }
      } else if (active === 'customer_feedback') {
        payload.wa_units_included = Number(draft.wa_units_included || 0)
        payload.web_units_included = Number(draft.web_units_included || 0)
        payload.max_locations = Number(draft.max_locations || 1)
        payload.prices = {
          GBP: {
            monthly_price_minor: poundsToPence(draft.monthly),
            yearly_price_minor: poundsToPence(draft.yearly || 0),
            per_min_minor: 0,
            extra_per_min_minor: 0,
          },
        }
      } else if (active === 'expo') {
        payload.duration_days = Number(draft.duration_days || 1)
        payload.max_booths = Number(draft.max_booths || 1)
        payload.max_assets = Number(draft.max_assets || 5)
        payload.lead_scoring_enabled = Boolean(draft.lead_scoring_enabled)
        payload.post_show_followup_enabled = Boolean(draft.post_show_followup_enabled)
        payload.ai_summary_report_enabled = Boolean(draft.ai_summary_report_enabled)
        payload.prices = {
          GBP: {
            monthly_price_minor: poundsToPence(draft.oneOff || draft.monthly || 0),
            yearly_price_minor: null,
            per_min_minor: 0,
            extra_per_min_minor: 0,
          },
        }
      } else if (active === 'smart_card') {
        payload.prices = {
          GBP: {
            monthly_price_minor: null,
            yearly_price_minor: poundsToPence(draft.seatYearly || 0),
            per_min_minor: 0,
            extra_per_min_minor: 0,
          },
        }
      }

      await apiFetch(`/admin/pricing/packages/${encodeURIComponent(pkg.id)}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      })
      await load()
      setDirty((d) => ({ ...d, [pkg.id]: false }))
      setMsg(`${pkg.name} saved.`)
    } catch (e) {
      setError(e?.message || 'Save failed')
    } finally {
      setSavingId(null)
    }
  }

  const svcMeta = SERVICES.find((s) => s.key === active)

  const renderCoreBody = (pkg, draft) => {
    const isPayg = String(pkg.code || '').toLowerCase() === 'payg'
    const isEnt = Boolean(pkg.is_enterprise)
    if (isEnt) {
      return (
        <div className="uppStory">
          Enterprise is price-on-application. Use Private packages for negotiated deals.
        </div>
      )
    }
    return (
      <>
        <div className="uppStory">
          {isPayg ? (
            <>
              <strong>{pkg.name}</strong> has no monthly fee — wallet rates below apply per AI minute, WA recipient and CV scan.
            </>
          ) : (
            <>
              <strong>{pkg.name}</strong> costs <strong>{money(poundsToPence(draft.monthly), 'GBP')}/mo</strong>
              {' '}→ includes <strong>{Number(draft.calls_included || 0).toLocaleString()} AI mins</strong>
              {' '}+ <strong>{Number(draft.whatsapp_included || 0).toLocaleString()} WA recipients</strong>
              {' '}+ <strong>{Number(draft.cv_scans_included || 0).toLocaleString()} CV scans</strong>
              {' '}→ extras bill at this package&apos;s overage rates (connection fee is shared).
            </>
          )}
        </div>

        {!isPayg ? (
          <section className="uppSection">
            <h4><span className="uppLetter">A</span> Plan price</h4>
            <div className="uppGrid">
              <label>Monthly <Num prefix={sym} value={draft.monthly} disabled={!editable} onChange={(v) => patchDraft(pkg.id, { monthly: v })} /></label>
              <label>Yearly <Num prefix={sym} value={draft.yearly} disabled={!editable} onChange={(v) => patchDraft(pkg.id, { yearly: v })} /></label>
              <Toggle checked={draft.is_active} onChange={(v) => patchDraft(pkg.id, { is_active: v })} label="Active" />
              <Toggle checked={draft.is_featured} onChange={(v) => patchDraft(pkg.id, { is_featured: v })} label="Featured" />
            </div>
          </section>
        ) : null}

        {!isPayg ? (
          <section className="uppSection">
            <h4><span className="uppLetter">B</span> What customers get (included)</h4>
            <div className="uppGrid">
              <label>AI minutes <Num step="1" value={draft.calls_included} disabled={!editable} onChange={(v) => patchDraft(pkg.id, { calls_included: v })} /></label>
              <label>WA recipients <Num step="1" value={draft.whatsapp_included} disabled={!editable} onChange={(v) => patchDraft(pkg.id, { whatsapp_included: v })} /></label>
              <label>CV scans <Num step="1" value={draft.cv_scans_included} disabled={!editable} onChange={(v) => patchDraft(pkg.id, { cv_scans_included: v })} /></label>
            </div>
            <p className="uppHint">1 WA unit = 1 recipient / survey session (multi-message thread still counts as 1).</p>
          </section>
        ) : null}

        <section className="uppSection">
          <h4><span className="uppLetter">C</span> How usage is priced (this package only)</h4>
          <div className="uppMiniPanels">
            <div className="uppMini">
              <div className="uppMiniHead">AI calls</div>
              <label>{isPayg ? 'Wallet / min' : 'Per minute (in package)'}
                <Num prefix={sym} value={draft.perMin} disabled={!editable} onChange={(v) => patchDraft(pkg.id, { perMin: v })} />
              </label>
              {!isPayg ? (
                <label>Extra / min
                  <Num prefix={sym} value={draft.extraPerMin} disabled={!editable} onChange={(v) => patchDraft(pkg.id, { extraPerMin: v })} />
                </label>
              ) : null}
            </div>
            <div className="uppMini">
              <div className="uppMiniHead">WhatsApp surveys</div>
              <label>{isPayg ? 'Wallet / recipient' : 'Per recipient (in package)'}
                <Num prefix={sym} value={draft.waPackage} disabled={!editable} onChange={(v) => patchDraft(pkg.id, { waPackage: v })} />
              </label>
              {!isPayg ? (
                <label>Extra / recipient
                  <Num prefix={sym} value={draft.waExtra} disabled={!editable} onChange={(v) => patchDraft(pkg.id, { waExtra: v })} />
                </label>
              ) : null}
              <p className="uppHint">Not per WhatsApp message.</p>
            </div>
            <div className="uppMini">
              <div className="uppMiniHead">ATS / CV</div>
              <label>Fee per scan
                <Num prefix={sym} value={draft.cvFee} disabled={!editable} onChange={(v) => patchDraft(pkg.id, { cvFee: v })} />
              </label>
            </div>
          </div>
        </section>

        <section className="uppSection">
          <h4><span className="uppLetter">D</span> Connection fee <span className="uppHintInline">shared — edit in strip above</span></h4>
          <div className="uppSharedRow">
            <span>Per call across all Core packages</span>
            <strong>{money(poundsToPence(sharedDraft.connection), 'GBP')}</strong>
          </div>
        </section>

        {!editable ? <p className="uppHint">Switch currency to GBP to edit (or unlock a market later).</p> : null}
      </>
    )
  }

  const renderFeedbackBody = (pkg, draft) => (
    <>
      <div className="uppStory">
        <strong>{pkg.name}</strong> costs <strong>{money(poundsToPence(draft.monthly), 'GBP')}/mo</strong>
        {' '}→ <strong>{Number(draft.wa_units_included || 0)} WA</strong> + <strong>{Number(draft.web_units_included || 0)} web</strong>
        {' '}across <strong>{Number(draft.max_locations || 0)} location(s)</strong>. When units run out, upgrade (no auto overage charge).
      </div>
      <section className="uppSection">
        <h4><span className="uppLetter">A</span> Plan price</h4>
        <div className="uppGrid">
          <label>Monthly <Num prefix={sym} value={draft.monthly} disabled={!editable} onChange={(v) => patchDraft(pkg.id, { monthly: v })} /></label>
          <label>Yearly <Num prefix={sym} value={draft.yearly} disabled={!editable} onChange={(v) => patchDraft(pkg.id, { yearly: v })} /></label>
          <Toggle checked={draft.is_active} onChange={(v) => patchDraft(pkg.id, { is_active: v })} label="Active" />
          <Toggle checked={draft.is_featured} onChange={(v) => patchDraft(pkg.id, { is_featured: v })} label="Featured" />
        </div>
      </section>
      <section className="uppSection">
        <h4><span className="uppLetter">B</span> Included</h4>
        <div className="uppGrid">
          <label>WA surveys / mo <Num step="1" value={draft.wa_units_included} disabled={!editable} onChange={(v) => patchDraft(pkg.id, { wa_units_included: v })} /></label>
          <label>Web surveys / mo <Num step="1" value={draft.web_units_included} disabled={!editable} onChange={(v) => patchDraft(pkg.id, { web_units_included: v })} /></label>
          <label>Locations <Num step="1" value={draft.max_locations} disabled={!editable} onChange={(v) => patchDraft(pkg.id, { max_locations: v })} /></label>
        </div>
      </section>
    </>
  )

  const renderExpoBody = (pkg, draft) => (
    <>
      <div className="uppStory">
        <strong>{pkg.name}</strong> is a one-off <strong>{money(poundsToPence(draft.oneOff), 'GBP')}</strong> for <strong>{draft.duration_days} day(s)</strong>.
      </div>
      <section className="uppSection">
        <h4><span className="uppLetter">A</span> One-off fee</h4>
        <div className="uppGrid">
          <label>Price <Num prefix={sym} value={draft.oneOff} disabled={!editable} onChange={(v) => patchDraft(pkg.id, { oneOff: v })} /></label>
          <label>Days active <Num step="1" value={draft.duration_days} disabled={!editable} onChange={(v) => patchDraft(pkg.id, { duration_days: v })} /></label>
          <Toggle checked={draft.is_active} onChange={(v) => patchDraft(pkg.id, { is_active: v })} label="Active" />
        </div>
      </section>
      <section className="uppSection">
        <h4><span className="uppLetter">B</span> Limits & features</h4>
        <div className="uppGrid">
          <label>Max booths <Num step="1" value={draft.max_booths} disabled={!editable} onChange={(v) => patchDraft(pkg.id, { max_booths: v })} /></label>
          <label>Max assets <Num step="1" value={draft.max_assets} disabled={!editable} onChange={(v) => patchDraft(pkg.id, { max_assets: v })} /></label>
          <Toggle checked={draft.lead_scoring_enabled} onChange={(v) => patchDraft(pkg.id, { lead_scoring_enabled: v })} label="Lead scoring" />
          <Toggle checked={draft.post_show_followup_enabled} onChange={(v) => patchDraft(pkg.id, { post_show_followup_enabled: v })} label="Post-show follow-up" />
          <Toggle checked={draft.ai_summary_report_enabled} onChange={(v) => patchDraft(pkg.id, { ai_summary_report_enabled: v })} label="AI summary" />
        </div>
      </section>
    </>
  )

  const renderSmartBody = (pkg, draft) => (
    <>
      <div className="uppStory">
        <strong>{pkg.name}</strong> seat price <strong>{money(poundsToPence(draft.seatYearly), 'GBP')}</strong> / year — unlimited scans while active.
      </div>
      <section className="uppSection">
        <h4><span className="uppLetter">A</span> Seat price</h4>
        <div className="uppGrid">
          <label>Yearly / seat <Num prefix={sym} value={draft.seatYearly} disabled={!editable} onChange={(v) => patchDraft(pkg.id, { seatYearly: v })} /></label>
          <Toggle checked={draft.is_active} onChange={(v) => patchDraft(pkg.id, { is_active: v })} label="Active" />
          <Toggle checked={draft.is_featured} onChange={(v) => patchDraft(pkg.id, { is_featured: v })} label="Featured" />
        </div>
      </section>
    </>
  )

  return (
    <PricingLoadGate loading={loading} error={!list.length && error ? error : ''} title="Package pricing" description={svcMeta?.blurb} onRetry={load}>
      <PricingPageFrame
        title="Package pricing"
        description="Author in GBP. Each Core package has its own AI, WA and ATS fees. Only the connection fee and usage-calculation rules are shared."
        error={error}
        msg={msg}
        actions={
          <div className="uppTopActions">
            <select className="input" value={currency} onChange={(e) => setCurrency(e.target.value)}>
              {CURRENCIES.map((c) => (
                <option key={c} value={c}>{c}{c === 'GBP' ? ' (authoring)' : ''}</option>
              ))}
            </select>
            <Button type="button" size="sm" variant="outline" onClick={() => setFxOpen(true)}>FX rates</Button>
          </div>
        }
      >
        <div className="uppTabs">
          {SERVICES.map((s) => (
            <button
              key={s.key}
              type="button"
              className={`uppTab${active === s.key ? ' on' : ''}`}
              onClick={() => setService(s.key)}
            >
              {s.label}
              <span className="uppTabCount">{(packagesByService[s.key] || []).length}</span>
            </button>
          ))}
        </div>

        <div className="uppExplainer">
          <span>Subscription → includes allowance → usage burns units → extras after allowance</span>
          <button type="button" className="linkish" onClick={() => setHowOpen((v) => !v)}>
            {howOpen ? 'Hide how billing works' : 'How billing works'}
          </button>
        </div>
        {howOpen ? (
          <ol className="uppHow">
            <li><strong>Subscription</strong> — fixed monthly/yearly price for the package.</li>
            <li><strong>Included</strong> — minutes, WA recipients and CV scans on that package.</li>
            <li><strong>Usage</strong> — same calculation rules for everyone; rates come from the subscribed package.</li>
            <li><strong>Extras</strong> — after allowance, bill at this package&apos;s overage rates. Connection fee is the only shared unit fee.</li>
            <li className="uppHowCallout">£59 is the plan price — not 59 minutes and not 59 WhatsApp messages.</li>
          </ol>
        ) : null}

        {active === 'voxbulk' ? (
          <div className="uppSharedStrip">
            <div>
              <strong>Shared</strong>
              <span className="uppHintInline"> Connection fee + FX only. AI / WA / ATS live on each package.</span>
            </div>
            <div className="uppGrid" style={{ marginTop: 10 }}>
              <label>Connection fee / call
                <Num prefix="£" value={sharedDraft.connection} onChange={(v) => { setSharedDraft({ connection: v }); setSharedDirty(true) }} />
              </label>
              {FX_QUOTES.map((q) => (
                <label key={q}>1 GBP = {q}
                  <Num step="0.0001" value={fxRates[q]} onChange={(v) => { setFxRates((f) => ({ ...f, [q]: v })); setSharedDirty(true) }} />
                </label>
              ))}
            </div>
            <div style={{ marginTop: 10 }}>
              <Button type="button" size="sm" disabled={!sharedDirty} onClick={() => void saveShared()}>Save shared rates</Button>
            </div>
          </div>
        ) : null}

        <div className="uppList">
          {list.map((pkg) => {
            const open = Boolean(expanded[pkg.id])
            const draft = drafts[pkg.id] || buildDraft(pkg)
            const gbp = pkg.prices?.GBP || {}
            const summary =
              active === 'expo'
                ? money(gbp.monthly_price_minor, 'GBP')
                : active === 'smart_card'
                  ? money(gbp.yearly_price_minor ?? gbp.monthly_price_minor, 'GBP')
                  : String(pkg.code || '').toLowerCase() === 'payg'
                    ? `${money(gbp.per_min_minor, 'GBP')}/min`
                    : pkg.is_enterprise
                      ? 'On application'
                      : `${money(gbp.monthly_price_minor, 'GBP')}/mo`

            return (
              <div key={pkg.id} className={`uppCard${open ? ' open' : ''}${dirty[pkg.id] ? ' dirty' : ''}`}>
                <button type="button" className="uppCardHead" onClick={() => toggleExpand(pkg.id)}>
                  <span className="uppChevron">{open ? '▾' : '▸'}</span>
                  <span className="uppCardName">
                    <strong>{pkg.name}</strong>
                    <span className="uppBadges">
                      <span className={`uppBadge${pkg.is_active ? ' on' : ''}`}>{pkg.is_active ? 'Active' : 'Inactive'}</span>
                      {pkg.is_featured ? <span className="uppBadge feat">Featured</span> : null}
                    </span>
                  </span>
                  <span className="uppSummary">{summary}</span>
                </button>
                {open ? (
                  <div className="uppCardBody">
                    <label className="uppDesc">
                      Description
                      <textarea
                        className="input"
                        rows={2}
                        value={draft.description}
                        disabled={!editable}
                        onChange={(e) => patchDraft(pkg.id, { description: e.target.value })}
                      />
                    </label>
                    {active === 'voxbulk' ? renderCoreBody(pkg, draft) : null}
                    {active === 'customer_feedback' ? renderFeedbackBody(pkg, draft) : null}
                    {active === 'expo' ? renderExpoBody(pkg, draft) : null}
                    {active === 'smart_card' ? renderSmartBody(pkg, draft) : null}
                    {!pkg.is_enterprise ? (
                      <div className="uppSaveBar">
                        <span>{dirty[pkg.id] ? `Unsaved changes to ${pkg.name}` : 'Up to date'}</span>
                        <Button
                          type="button"
                          size="sm"
                          disabled={!dirty[pkg.id] || savingId === pkg.id || !editable}
                          onClick={() => void savePackage(pkg)}
                        >
                          {savingId === pkg.id ? 'Saving…' : `Save ${pkg.name}`}
                        </Button>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>

        {fxOpen ? (
          <div className="uppOverlay" onClick={() => setFxOpen(false)} onKeyDown={() => {}}>
            <div className="uppDrawer" onClick={(e) => e.stopPropagation()} onKeyDown={() => {}}>
              <button type="button" className="close-x" onClick={() => setFxOpen(false)}>×</button>
              <h3>FX rates</h3>
              <p className="uppHint">GBP is authoring default. Saving a Core package fills unlocked markets from these rates.</p>
              {FX_QUOTES.map((q) => (
                <label key={q} className="pricingPkgField">
                  1 GBP = {q}
                  <Num step="0.0001" value={fxRates[q]} onChange={(v) => { setFxRates((f) => ({ ...f, [q]: v })); setSharedDirty(true) }} />
                </label>
              ))}
              <Button type="button" size="sm" onClick={() => void saveShared()}>Save FX rates</Button>
            </div>
          </div>
        ) : null}
      </PricingPageFrame>
    </PricingLoadGate>
  )
}
