import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'
import './CustomPackages.css'

const CURRENCIES = [
  { code: 'GBP', label: 'GBP (£)' },
  { code: 'USD', label: 'USD ($)' },
  { code: 'EUR', label: 'EURO (€)' },
  { code: 'CAD', label: 'CAD (CA$)' },
  { code: 'AUD', label: 'AU$ (A$)' },
]
const SYMBOLS = { GBP: '£', USD: '$', EUR: '€', CAD: 'CA$', AUD: 'A$' }
const CORE_COUNTRIES = [
  { code: 'GB', name: 'United Kingdom' },
  { code: 'AU', name: 'Australia' },
  { code: 'CA', name: 'Canada' },
  { code: 'USA', name: 'United States' },
]
const EXTRA_COUNTRY_OPTIONS = [
  { code: 'DE', name: 'Germany' },
  { code: 'FR', name: 'France' },
  { code: 'IT', name: 'Italy' },
  { code: 'ES', name: 'Spain' },
  { code: 'AE', name: 'United Arab Emirates' },
  { code: 'NL', name: 'Netherlands' },
  { code: 'BE', name: 'Belgium' },
  { code: 'IE', name: 'Ireland' },
  { code: 'PT', name: 'Portugal' },
  { code: 'PL', name: 'Poland' },
  { code: 'SE', name: 'Sweden' },
  { code: 'NO', name: 'Norway' },
  { code: 'DK', name: 'Denmark' },
  { code: 'CH', name: 'Switzerland' },
  { code: 'TR', name: 'Turkey' },
  { code: 'MA', name: 'Morocco' },
  { code: 'EG', name: 'Egypt' },
  { code: 'PS', name: 'Palestine' },
  { code: 'SA', name: 'Saudi Arabia' },
  { code: 'QA', name: 'Qatar' },
  { code: 'IN', name: 'India' },
  { code: 'TH', name: 'Thailand' },
  { code: 'SG', name: 'Singapore' },
  { code: 'JP', name: 'Japan' },
  { code: 'ZA', name: 'South Africa' },
  { code: 'NZ', name: 'New Zealand' },
  { code: 'MX', name: 'Mexico' },
  { code: 'BR', name: 'Brazil' },
]
const SVC_META = {
  customer_feedback: { short: 'CF', label: 'Customer Feedback', badge: 'customer_feedback' },
  core: { short: 'CO', label: 'Core / Voice', badge: 'core' },
  smart_card: { short: 'SC', label: 'Smart Card', badge: 'smart_card' },
  expo: { short: 'EX', label: 'Expo', badge: 'expo' },
  survey: { short: 'SU', label: 'WA Survey', badge: 'survey' },
  ai_followback: { short: 'AI', label: 'AI Follow-back', badge: 'ai_followback' },
}

function poundsToMinor(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return 0
  return Math.max(0, Math.round(n * 100))
}
function minorToMajor(minor) {
  return (Number(minor || 0) / 100).toFixed(2)
}
function formatMoney(minor, currency) {
  const sym = SYMBOLS[currency] || ''
  return `${sym}${minorToMajor(minor)}`
}

function emptyModules() {
  return {
    ai_followback: { minutes_included: 0, connection_fee_minor: 0, per_min_minor: 0 },
    customer_feedback: {
      enabled: false,
      max_locations: 1,
      wa_units_included: 100,
      web_units_included: 0,
      wa_extra_minor: 0,
      web_extra_minor: 0,
      notes: '',
    },
    core: {
      enabled: false,
      minutes_included: 0,
      whatsapp_included: 0,
      cv_scans_included: 0,
      per_min_minor: 0,
      overage_per_min_minor: 0,
      unit_rates: {
        connection_fee_minor: 0,
        interview_per_min_minor: 0,
        wa_package_fee_minor: 0,
        wa_extra_minor: 0,
        cv_scan_fee_minor: 0,
      },
    },
    smart_card: { enabled: false, seats: 1, per_seat_minor: 0 },
    expo: {
      enabled: false,
      duration_days: 1,
      max_booths: 1,
      max_assets: 5,
      max_categories: 1,
      lead_scoring_enabled: false,
      post_show_followup_enabled: false,
      post_event_survey_enabled: false,
      ai_summary_report_enabled: false,
    },
    survey: {
      enabled: false,
      max_active_campaigns: 5,
      whatsapp_recipients_included: 500,
      call_minutes_included: 100,
      wa_extra_minor: 0,
      call_overage_per_min_minor: 0,
      connection_fee_minor: 0,
    },
  }
}

function emptyDraft() {
  return {
    id: null,
    name: '',
    code: '',
    interval: 'monthly',
    currency: 'GBP',
    price_major: '0.00',
    status: 'draft',
    admin_notes: '',
    modules: emptyModules(),
    allowlist: { mode: 'default', core: ['GB', 'AU', 'CA', 'USA'], extra: [] },
    internal_cost_notes: '',
    org_ids: [],
  }
}

function packageToDraft(pkg) {
  const base = emptyModules()
  const incoming = pkg.modules || {}
  const modules = emptyModules()
  for (const key of Object.keys(base)) {
    if (key === 'ai_followback') continue
    const src = incoming[key]
    if (!src || typeof src !== 'object') continue
    modules[key] = { ...base[key], ...src }
    if (key === 'core' && src.unit_rates) {
      modules[key].unit_rates = { ...base[key].unit_rates, ...src.unit_rates }
    }
  }
  const legacyFb = incoming?.customer_feedback?.ai_followback
  modules.ai_followback = {
    ...base.ai_followback,
    ...(incoming.ai_followback || {}),
    ...(legacyFb && !incoming.ai_followback ? legacyFb : {}),
  }
  return {
    id: pkg.id,
    name: pkg.name || '',
    code: pkg.code || '',
    interval: pkg.interval === 'yearly' ? 'yearly' : 'monthly',
    currency: pkg.currency || 'GBP',
    price_major: minorToMajor(pkg.price_minor),
    status: pkg.status || 'draft',
    admin_notes: pkg.admin_notes || '',
    modules,
    allowlist: {
      mode: pkg.allowlist?.mode === 'custom' ? 'custom' : 'default',
      core: Array.isArray(pkg.allowlist?.core) ? pkg.allowlist.core : ['GB', 'AU', 'CA', 'USA'],
      extra: Array.isArray(pkg.allowlist?.extra) ? pkg.allowlist.extra : [],
    },
    internal_cost_notes: pkg.internal_cost_notes || '',
    org_ids: Array.isArray(pkg.org_ids) ? [...pkg.org_ids] : [],
  }
}

function draftToPayload(draft, { status } = {}) {
  const modules = { ...(draft.modules || {}) }
  if (modules.customer_feedback && modules.customer_feedback.ai_followback) {
    const { ai_followback: _drop, ...cfRest } = modules.customer_feedback
    modules.customer_feedback = cfRest
  }
  return {
    name: draft.name,
    code: draft.code || undefined,
    interval: draft.interval,
    currency: draft.currency,
    price_minor: poundsToMinor(draft.price_major),
    status: status || draft.status || 'draft',
    admin_notes: draft.admin_notes || null,
    modules,
    allowlist: draft.allowlist,
    internal_cost_notes: draft.internal_cost_notes || null,
    org_ids: draft.org_ids,
  }
}

function StatusPill({ status }) {
  const s = status || 'draft'
  return (
    <span className={`cpStatus cpStatus-${s}`}>
      <span className="cpDot" />
      {s.charAt(0).toUpperCase() + s.slice(1)}
    </span>
  )
}

function Toggle({ checked, onChange, label }) {
  return (
    <label className="cpToggle">
      <input type="checkbox" checked={!!checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="cpTrack" />
      {label ? <span>{label}</span> : null}
    </label>
  )
}

function MoneyInput({ currency, value, onChange, disabled }) {
  return (
    <div className="cpMoney">
      <span className="cur">{SYMBOLS[currency] || ''}</span>
      <input type="number" step="0.01" min="0" value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
    </div>
  )
}

function ModuleToggle({ id, short, title, desc, enabled, onToggle, children, optional }) {
  return (
    <div className="cpModule">
      <div className="cpModuleHead">
        <div className={`cpSvcBadge cpSvc-${id}`}>{short}</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600 }}>
            {title} {optional ? <span className="sub" style={{ fontSize: 10, border: '1px solid #cbc9c4', borderRadius: 99, padding: '1px 7px', marginLeft: 6 }}>Optional</span> : null}
          </div>
          <div style={{ color: '#9b9892', fontSize: 11.5 }}>{desc}</div>
        </div>
        <Toggle checked={enabled} onChange={onToggle} />
      </div>
      {enabled ? <div className="cpModuleBody">{children}</div> : null}
    </div>
  )
}

export default function CustomPackages() {
  const [view, setView] = useState('list')
  const [items, setItems] = useState([])
  const [orgs, setOrgs] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [draft, setDraft] = useState(emptyDraft())
  const [q, setQ] = useState('')
  const [serviceFilter, setServiceFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [orgFilter, setOrgFilter] = useState('')
  const [orgQuery, setOrgQuery] = useState('')
  const [extraSearch, setExtraSearch] = useState('')
  const [unitRatesOpen, setUnitRatesOpen] = useState(false)

  const load = useCallback(async () => {
    setError('')
    try {
      const params = new URLSearchParams()
      if (statusFilter) params.set('status', statusFilter)
      if (serviceFilter) params.set('service', serviceFilter)
      if (orgFilter) params.set('org_id', orgFilter)
      if (q.trim()) params.set('q', q.trim())
      const qs = params.toString()
      const [pkgBody, orgList] = await Promise.all([
        apiFetch(`/admin/pricing/custom-packages${qs ? `?${qs}` : ''}`),
        apiFetch('/admin/organisations?limit=500'),
      ])
      setItems(Array.isArray(pkgBody?.items) ? pkgBody.items : [])
      setOrgs(Array.isArray(orgList) ? orgList : Array.isArray(orgList?.items) ? orgList.items : [])
      return true
    } catch (e) {
      setError(e?.message || 'Could not load custom packages')
      return false
    }
  }, [q, serviceFilter, statusFilter, orgFilter])

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
    const needle = orgQuery.trim().toLowerCase()
    if (!needle) return orgs
    return orgs.filter((o) => String(o.name || '').toLowerCase().includes(needle) || String(o.id || '').includes(needle))
  }, [orgs, orgQuery])

  const setField = (key, value) => setDraft((d) => ({ ...d, [key]: value }))
  const setModule = (key, patch) => setDraft((d) => ({
    ...d,
    modules: { ...d.modules, [key]: { ...d.modules[key], ...patch } },
  }))
  const setNested = (mod, nestedKey, patch) => setDraft((d) => ({
    ...d,
    modules: {
      ...d.modules,
      [mod]: {
        ...d.modules[mod],
        [nestedKey]: { ...(d.modules[mod][nestedKey] || {}), ...patch },
      },
    },
  }))

  const openCreate = () => {
    setDraft(emptyDraft())
    setView('editor')
    setError('')
    setMsg('')
  }
  const openEdit = (pkg) => {
    setDraft(packageToDraft(pkg))
    setView('editor')
    setError('')
    setMsg('')
  }

  const toggleOrg = (orgId) => {
    setDraft((d) => {
      const set = new Set(d.org_ids || [])
      if (set.has(orgId)) set.delete(orgId)
      else set.add(orgId)
      return { ...d, org_ids: Array.from(set) }
    })
  }

  const save = async ({ activate = false, asDraft = false } = {}) => {
    setSaving(true)
    setError('')
    setMsg('')
    try {
      const payload = draftToPayload(draft, {
        status: asDraft ? 'draft' : activate ? 'active' : draft.status || 'draft',
      })
      if (!payload.name) throw new Error('Name is required')
      let saved
      if (draft.id) {
        saved = await apiFetch(`/admin/pricing/custom-packages/${encodeURIComponent(draft.id)}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        })
      } else {
        saved = await apiFetch('/admin/pricing/custom-packages', {
          method: 'POST',
          body: JSON.stringify(payload),
        })
      }
      setMsg(activate ? 'Package saved and activated.' : asDraft ? 'Draft saved.' : 'Package saved.')
      setDraft(packageToDraft(saved.item || saved))
      await load()
      if (activate || asDraft) setView('list')
    } catch (e) {
      setError(e?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const duplicate = async (pkg) => {
    try {
      const body = await apiFetch(`/admin/pricing/custom-packages/${encodeURIComponent(pkg.id)}/duplicate`, { method: 'POST' })
      setMsg('Package duplicated as draft.')
      await load()
      if (body?.item) openEdit(body.item)
    } catch (e) {
      setError(e?.message || 'Duplicate failed')
    }
  }

  const deactivate = async (pkg) => {
    if (!window.confirm(`Deactivate “${pkg.name}”? Assigned orgs lose this package access.`)) return
    try {
      await apiFetch(`/admin/pricing/custom-packages/${encodeURIComponent(pkg.id)}`, { method: 'DELETE' })
      setMsg('Package deactivated.')
      await load()
    } catch (e) {
      setError(e?.message || 'Deactivate failed')
    }
  }

  const enabledServices = useMemo(() => Object.keys(SVC_META).filter((k) => draft.modules?.[k]?.enabled), [draft.modules])
  const currency = draft.currency || 'GBP'
  const allowlistCount =
    draft.allowlist.mode === 'custom'
      ? (draft.allowlist.core?.length || 0) + (draft.allowlist.extra?.length || 0)
      : null
  const mismatchOrgs = useMemo(() => {
    return (draft.org_ids || [])
      .map((id) => orgs.find((o) => o.id === id))
      .filter(Boolean)
  }, [draft.org_ids, orgs])

  const extraSuggestions = useMemo(() => {
    const needle = extraSearch.trim().toLowerCase()
    const taken = new Set(draft.allowlist.extra || [])
    return EXTRA_COUNTRY_OPTIONS.filter((c) => !taken.has(c.code) && (!needle || c.name.toLowerCase().includes(needle) || c.code.toLowerCase().includes(needle))).slice(0, 8)
  }, [extraSearch, draft.allowlist.extra])

  if (view === 'editor') {
    return (
      <div className="cpPage">
        <div className="cpPageHead">
          <div>
            <h1>{draft.id ? 'Edit custom package' : 'New custom package'}</h1>
            <p>One package is one commercial deal — combine services, set price in one currency, and assign organisations.</p>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button type="button" className="cpBtn" onClick={() => setView('list')}>Cancel</button>
            <button type="button" className="cpBtn" disabled={saving} onClick={() => save({ asDraft: true })}>Save as draft</button>
            <button type="button" className="cpBtn cpBtnPrimary" disabled={saving} onClick={() => save({ activate: true })}>Save &amp; activate</button>
          </div>
        </div>
        {error ? <div className="cpMsg cpMsgErr">{error}</div> : null}
        {msg ? <div className="cpMsg cpMsgOk">{msg}</div> : null}

        <div className="cpEditorShell">
          <nav className="cpStepnav">
            {[
              ['#sec-basics', 'Basics'],
              ['#sec-services', 'Services'],
              ['#sec-allowlist', 'Call allowlist'],
              ['#sec-pricing', 'Pricing'],
              ['#sec-orgs', 'Organisations'],
              ['#sec-review', 'Review'],
            ].map(([href, label], i) => (
              <a key={href} href={href}><span className="cpMono" style={{ width: 16, textAlign: 'center' }}>{i + 1}</span>{label}</a>
            ))}
          </nav>

          <div className="cpFormCol">
            <div className="cpCard" id="sec-basics">
              <h2>Basics</h2>
              <p className="cpHint">Identifies this deal internally. Currency applies to the whole package.</p>
              <div className="cpFieldRow">
                <div className="cpField">
                  <label>Package name</label>
                  <input value={draft.name} onChange={(e) => setField('name', e.target.value)} />
                </div>
                <div className="cpField">
                  <label>Package code <span className="sub">optional</span></label>
                  <input className="cpMono" value={draft.code} onChange={(e) => setField('code', e.target.value)} placeholder="auto if blank" disabled={!!draft.id} />
                </div>
              </div>
              <div className="cpFieldRow">
                <div className="cpField">
                  <label>Billing interval</label>
                  <div className="cpSegmented">
                    <button type="button" className={draft.interval === 'monthly' ? 'active' : ''} onClick={() => setField('interval', 'monthly')}>Monthly</button>
                    <button type="button" className={draft.interval === 'yearly' ? 'active' : ''} onClick={() => setField('interval', 'yearly')}>Annually</button>
                  </div>
                </div>
                <div className="cpField">
                  <label>Billing currency</label>
                  <select value={draft.currency} onChange={(e) => setField('currency', e.target.value)}>
                    {CURRENCIES.map((c) => <option key={c.code} value={c.code}>{c.label}</option>)}
                  </select>
                  <span className="help">All fees and overage rates use this currency only — no FX conversion.</span>
                </div>
              </div>
              <div className="cpFieldRow">
                <div className="cpField">
                  <label>Status</label>
                  <Toggle
                    checked={draft.status === 'active'}
                    onChange={(on) => setField('status', on ? 'active' : 'draft')}
                    label={draft.status === 'active' ? 'Active' : 'Draft'}
                  />
                </div>
              </div>
              <div className="cpFieldRow single">
                <div className="cpField">
                  <label>Internal admin notes <span className="sub">not shown to customer</span></label>
                  <textarea value={draft.admin_notes} onChange={(e) => setField('admin_notes', e.target.value)} rows={3} />
                </div>
              </div>
            </div>

            <div className="cpCard" id="sec-services">
              <h2>Services</h2>
              <p className="cpHint">Turn on modules this deal includes. Money fields use {currency}.</p>

              <ModuleToggle
                id="customer_feedback"
                short="CF"
                title="Customer Feedback"
                desc="QR / venue feedback via WhatsApp and web scan"
                enabled={draft.modules.customer_feedback.enabled}
                onToggle={(on) => setModule('customer_feedback', { enabled: on })}
              >
                <div className="cpGrid3">
                  <div className="cpField"><label>Max locations</label><input type="number" min="0" value={draft.modules.customer_feedback.max_locations} onChange={(e) => setModule('customer_feedback', { max_locations: Number(e.target.value) })} /></div>
                  <div className="cpField"><label>WhatsApp / mo</label><input type="number" min="0" value={draft.modules.customer_feedback.wa_units_included} onChange={(e) => setModule('customer_feedback', { wa_units_included: Number(e.target.value) })} /></div>
                  <div className="cpField"><label>Web / mo (−1 share, 0 none)</label><input type="number" min="-1" value={draft.modules.customer_feedback.web_units_included} onChange={(e) => setModule('customer_feedback', { web_units_included: Number(e.target.value) })} /></div>
                </div>
                <div className="cpGrid3" style={{ marginTop: 8 }}>
                  <div className="cpField"><label>WA extra / unit</label><MoneyInput currency={currency} value={minorToMajor(draft.modules.customer_feedback.wa_extra_minor || 0)} onChange={(v) => setModule('customer_feedback', { wa_extra_minor: poundsToMinor(v) })} /></div>
                  <div className="cpField"><label>Web extra / unit</label><MoneyInput currency={currency} value={minorToMajor(draft.modules.customer_feedback.web_extra_minor || 0)} onChange={(v) => setModule('customer_feedback', { web_extra_minor: poundsToMinor(v) })} /></div>
                </div>
              </ModuleToggle>

              <div className="cpModule cpModule-ai_followback" style={{ marginTop: 14 }}>
                <div className="cpModuleHead">
                  <div className="cpModuleIcon" aria-hidden>AI</div>
                  <div className="cpModuleTitles">
                    <h3>AI Follow-back</h3>
                    <p>Shared minutes for Survey + Customer Feedback callback calls</p>
                  </div>
                  <span className="cpModuleTag">Shared pool</span>
                </div>
                <p className="cpHint" style={{ marginTop: 0 }}>
                  Included minutes apply across both products; connection fee and per-minute apply only to overage.
                </p>
                <div className="cpGrid3">
                  <div className="cpField">
                    <label>Allowance (min)</label>
                    <input
                      type="number"
                      min="0"
                      value={draft.modules.ai_followback?.minutes_included ?? 0}
                      onChange={(e) => setModule('ai_followback', { minutes_included: Number(e.target.value) })}
                    />
                  </div>
                  <div className="cpField">
                    <label>Connection fee</label>
                    <MoneyInput
                      currency={currency}
                      value={minorToMajor(draft.modules.ai_followback?.connection_fee_minor || 0)}
                      onChange={(v) => setModule('ai_followback', { connection_fee_minor: poundsToMinor(v) })}
                    />
                  </div>
                  <div className="cpField">
                    <label>Cost per minute (extra)</label>
                    <MoneyInput
                      currency={currency}
                      value={minorToMajor(draft.modules.ai_followback?.per_min_minor || 0)}
                      onChange={(v) => setModule('ai_followback', { per_min_minor: poundsToMinor(v) })}
                    />
                  </div>
                </div>
                <span className="help">Extras after allowance are charged to the wallet (or next invoice when on DD).</span>
              </div>

              <ModuleToggle
                id="core"
                short="CO"
                title="Core / Voice & Interview"
                desc="AI outbound minutes, WhatsApp, CV screening"
                enabled={draft.modules.core.enabled}
                onToggle={(on) => setModule('core', { enabled: on })}
              >
                <div className="cpGrid3">
                  <div className="cpField"><label>Minutes included</label><input type="number" min="0" value={draft.modules.core.minutes_included} onChange={(e) => setModule('core', { minutes_included: Number(e.target.value) })} /></div>
                  <div className="cpField"><label>WhatsApp included</label><input type="number" min="0" value={draft.modules.core.whatsapp_included} onChange={(e) => setModule('core', { whatsapp_included: Number(e.target.value) })} /></div>
                  <div className="cpField"><label>CV scans included</label><input type="number" min="0" value={draft.modules.core.cv_scans_included} onChange={(e) => setModule('core', { cv_scans_included: Number(e.target.value) })} /></div>
                </div>
                <div className="cpGrid3" style={{ marginTop: 8 }}>
                  <div className="cpField"><label>Per-minute rate</label><MoneyInput currency={currency} value={minorToMajor(draft.modules.core.per_min_minor)} onChange={(v) => setModule('core', { per_min_minor: poundsToMinor(v) })} /></div>
                  <div className="cpField"><label>Overage rate</label><MoneyInput currency={currency} value={minorToMajor(draft.modules.core.overage_per_min_minor)} onChange={(v) => setModule('core', { overage_per_min_minor: poundsToMinor(v) })} /></div>
                </div>
                <button type="button" className="cpBtn cpBtnSm" style={{ marginTop: 10 }} onClick={() => setUnitRatesOpen((v) => !v)}>
                  {unitRatesOpen ? 'Hide' : 'Show'} optional unit rates
                </button>
                {unitRatesOpen ? (
                  <div className="cpGrid4" style={{ marginTop: 10 }}>
                    {['connection_fee_minor', 'interview_per_min_minor', 'wa_package_fee_minor', 'wa_extra_minor', 'cv_scan_fee_minor'].map((k) => (
                      <div className="cpField" key={k}>
                        <label>{k.replace(/_minor$/, '').replace(/_/g, ' ')}</label>
                        <MoneyInput
                          currency={currency}
                          value={minorToMajor(draft.modules.core.unit_rates[k])}
                          onChange={(v) => setNested('core', 'unit_rates', { [k]: poundsToMinor(v) })}
                        />
                      </div>
                    ))}
                  </div>
                ) : null}
              </ModuleToggle>

              <ModuleToggle
                id="smart_card"
                short="SC"
                title="Smart Card"
                desc="Digital business card seats"
                enabled={draft.modules.smart_card.enabled}
                onToggle={(on) => setModule('smart_card', { enabled: on })}
              >
                <div className="cpGrid3">
                  <div className="cpField"><label>Seat count</label><input type="number" min="0" value={draft.modules.smart_card.seats} onChange={(e) => setModule('smart_card', { seats: Number(e.target.value) })} /></div>
                  <div className="cpField"><label>Price / seat ({draft.interval === 'yearly' ? 'yearly' : 'monthly'})</label><MoneyInput currency={currency} value={minorToMajor(draft.modules.smart_card.per_seat_minor)} onChange={(v) => setModule('smart_card', { per_seat_minor: poundsToMinor(v) })} /></div>
                </div>
              </ModuleToggle>

              <ModuleToggle
                id="expo"
                short="EX"
                title="Expo"
                desc="Event booth & lead management"
                optional
                enabled={draft.modules.expo.enabled}
                onToggle={(on) => setModule('expo', { enabled: on })}
              >
                <div className="cpGrid3">
                  <div className="cpField"><label>Duration (days)</label><input type="number" min="1" value={draft.modules.expo.duration_days} onChange={(e) => setModule('expo', { duration_days: Number(e.target.value) })} /></div>
                  <div className="cpField"><label>Max booths</label><input type="number" min="0" value={draft.modules.expo.max_booths} onChange={(e) => setModule('expo', { max_booths: Number(e.target.value) })} /></div>
                  <div className="cpField"><label>Max assets</label><input type="number" min="0" value={draft.modules.expo.max_assets} onChange={(e) => setModule('expo', { max_assets: Number(e.target.value) })} /></div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 12 }}>
                  <Toggle checked={draft.modules.expo.lead_scoring_enabled} onChange={(on) => setModule('expo', { lead_scoring_enabled: on })} label="Lead scoring" />
                  <Toggle checked={draft.modules.expo.post_show_followup_enabled} onChange={(on) => setModule('expo', { post_show_followup_enabled: on })} label="Post-show follow-up" />
                  <Toggle checked={draft.modules.expo.post_event_survey_enabled} onChange={(on) => setModule('expo', { post_event_survey_enabled: on })} label="Post-event survey" />
                  <Toggle checked={draft.modules.expo.ai_summary_report_enabled} onChange={(on) => setModule('expo', { ai_summary_report_enabled: on })} label="AI summary report" />
                </div>
              </ModuleToggle>

              <ModuleToggle
                id="survey"
                short="SU"
                title="WA Survey"
                desc="WhatsApp survey campaigns — recipients, call minutes, and overage"
                enabled={draft.modules.survey.enabled}
                onToggle={(on) => setModule('survey', { enabled: on })}
              >
                <div className="cpGrid3">
                  <div className="cpField"><label>Max active campaigns</label><input type="number" min="0" value={draft.modules.survey.max_active_campaigns ?? 5} onChange={(e) => setModule('survey', { max_active_campaigns: Number(e.target.value) })} /></div>
                  <div className="cpField"><label>WhatsApp recipients</label><input type="number" min="0" value={draft.modules.survey.whatsapp_recipients_included ?? 0} onChange={(e) => setModule('survey', { whatsapp_recipients_included: Number(e.target.value) })} /></div>
                  <div className="cpField"><label>Call minutes included</label><input type="number" min="0" value={draft.modules.survey.call_minutes_included ?? 0} onChange={(e) => setModule('survey', { call_minutes_included: Number(e.target.value) })} /></div>
                </div>
                <div className="cpGrid3" style={{ marginTop: 8 }}>
                  <div className="cpField"><label>WA extra / recipient</label><MoneyInput currency={currency} value={minorToMajor(draft.modules.survey.wa_extra_minor || 0)} onChange={(v) => setModule('survey', { wa_extra_minor: poundsToMinor(v) })} /></div>
                  <div className="cpField"><label>Call overage / min</label><MoneyInput currency={currency} value={minorToMajor(draft.modules.survey.call_overage_per_min_minor || 0)} onChange={(v) => setModule('survey', { call_overage_per_min_minor: poundsToMinor(v) })} /></div>
                  <div className="cpField"><label>Connection fee</label><MoneyInput currency={currency} value={minorToMajor(draft.modules.survey.connection_fee_minor || 0)} onChange={(v) => setModule('survey', { connection_fee_minor: poundsToMinor(v) })} /></div>
                </div>
                <span className="help">Extras after allowance accrue to the next monthly invoice (same currency as Basics).</span>
              </ModuleToggle>
            </div>

            <div className="cpCard" id="sec-allowlist">
              <h2>Outbound call allowlist</h2>
              <p className="cpHint">Countries this deal may dial for AI voice — not WhatsApp sender countries.</p>
              <div className="cpRadioRow">
                <label className={`cpRadioOpt ${draft.allowlist.mode === 'custom' ? 'selected' : ''}`}>
                  <input type="radio" checked={draft.allowlist.mode === 'custom'} onChange={() => setField('allowlist', { ...draft.allowlist, mode: 'custom' })} />
                  <div><div style={{ fontWeight: 600 }}>Custom for this package</div><div className="help">Override platform default</div></div>
                </label>
                <label className={`cpRadioOpt ${draft.allowlist.mode === 'default' ? 'selected' : ''}`}>
                  <input type="radio" checked={draft.allowlist.mode === 'default'} onChange={() => setField('allowlist', { ...draft.allowlist, mode: 'default' })} />
                  <div><div style={{ fontWeight: 600 }}>Use platform default</div><div className="help">Inherit Integrations Telnyx allowlist</div></div>
                </label>
              </div>
              {draft.allowlist.mode === 'custom' ? (
                <>
                  <div className="cpCountryRow">
                    {CORE_COUNTRIES.map((c) => {
                      const on = (draft.allowlist.core || []).includes(c.code)
                      return (
                        <button
                          type="button"
                          key={c.code}
                          className={`cpCountry ${on ? 'on' : ''}`}
                          onClick={() => {
                            const set = new Set(draft.allowlist.core || [])
                            if (set.has(c.code)) set.delete(c.code)
                            else set.add(c.code)
                            setField('allowlist', { ...draft.allowlist, core: Array.from(set) })
                          }}
                        >
                          <span className="cpMono" style={{ fontSize: 10.5 }}>{c.code}</span> {c.name}
                        </button>
                      )
                    })}
                  </div>
                  <div className="cpField">
                    <label>Extra countries</label>
                    <div className="cpChipList">
                      {(draft.allowlist.extra || []).map((code) => {
                        const name = EXTRA_COUNTRY_OPTIONS.find((c) => c.code === code)?.name || code
                        return (
                          <span className="cpPill" key={code}>
                            {name}
                            <button type="button" onClick={() => setField('allowlist', { ...draft.allowlist, extra: draft.allowlist.extra.filter((x) => x !== code) })}>×</button>
                          </span>
                        )
                      })}
                    </div>
                    <input value={extraSearch} onChange={(e) => setExtraSearch(e.target.value)} placeholder="Search a country to add…" />
                    {extraSearch && extraSuggestions.length ? (
                      <div style={{ border: '1px solid #cbc9c4', borderRadius: 6, marginTop: 4 }}>
                        {extraSuggestions.map((c) => (
                          <button
                            type="button"
                            key={c.code}
                            className="cpBtn"
                            style={{ width: '100%', justifyContent: 'space-between', border: 'none', borderRadius: 0 }}
                            onClick={() => {
                              setField('allowlist', { ...draft.allowlist, extra: [...(draft.allowlist.extra || []), c.code] })
                              setExtraSearch('')
                            }}
                          >
                            <span>{c.name}</span><span className="cpMono help">{c.code}</span>
                          </button>
                        ))}
                      </div>
                    ) : null}
                    <span className="help">{allowlistCount} countries in this package allowlist.</span>
                  </div>
                </>
              ) : (
                <div className="help">Platform default dial countries from Integrations → Telnyx will apply.</div>
              )}
            </div>

            <div className="cpCard" id="sec-pricing">
              <h2>Pricing</h2>
              <p className="cpHint">Single currency ({currency}) — package fee for the selected interval. Overage rates live on each service module.</p>
              <div className="cpFieldRow">
                <div className="cpField">
                  <label>{draft.interval === 'yearly' ? 'Annual package price' : 'Monthly package price'}</label>
                  <MoneyInput currency={currency} value={draft.price_major} onChange={(v) => setField('price_major', v)} />
                </div>
              </div>
              <div className="cpFieldRow single">
                <div className="cpField">
                  <label>Internal cost notes <span className="sub">admin only</span></label>
                  <textarea value={draft.internal_cost_notes} onChange={(e) => setField('internal_cost_notes', e.target.value)} rows={2} placeholder="Telnyx cost reference / margin notes…" />
                </div>
              </div>
            </div>

            <div className="cpCard" id="sec-orgs">
              <h2>Assign organisations</h2>
              <p className="cpHint">This package applies to every organisation selected. One custom package per org.</p>
              {draft.id && draft.org_ids.length ? (
                <div className="cpWarn">
                  <div><b>Editing this deal changes access</b> for {draft.org_ids.length} assigned organisation(s) as soon as you save.</div>
                </div>
              ) : null}
              <div className="cpOrgPicker">
                <div style={{ padding: 9, borderBottom: '1px solid #e2e1de' }}>
                  <input value={orgQuery} onChange={(e) => setOrgQuery(e.target.value)} placeholder="Search organisations by name or ID…" />
                </div>
                <div className="cpOrgList">
                  {filteredOrgs.map((o) => (
                    <label className="cpOrgRow" key={o.id}>
                      <input type="checkbox" checked={(draft.org_ids || []).includes(o.id)} onChange={() => toggleOrg(o.id)} />
                      <div>
                        <div style={{ fontWeight: 500 }}>{o.name}</div>
                        <div className="cpMono help">{o.id}</div>
                      </div>
                    </label>
                  ))}
                </div>
              </div>
              <div style={{ marginTop: 12, fontWeight: 700 }}>Assigned to {draft.org_ids.length} organisations</div>
              <div className="cpChipList" style={{ marginTop: 8 }}>
                {mismatchOrgs.map((o) => (
                  <span className="cpPill org" key={o.id}>
                    {o.name}
                    <button type="button" onClick={() => toggleOrg(o.id)}>×</button>
                  </span>
                ))}
              </div>
            </div>

            <div className="cpCard" id="sec-review">
              <h2>Review &amp; save</h2>
              <p className="cpHint">Read-only summary before it goes live.</p>
              <div className="cpReviewBlock">
                <h4>Basics</h4>
                <div className="cpKv"><span className="k">Name</span><span>{draft.name || '—'}</span></div>
                <div className="cpKv"><span className="k">Interval</span><span>{draft.interval === 'yearly' ? 'Annually' : 'Monthly'}</span></div>
                <div className="cpKv"><span className="k">Currency</span><span>{currency}</span></div>
                <div className="cpKv"><span className="k">Price</span><span>{formatMoney(poundsToMinor(draft.price_major), currency)}{draft.interval === 'yearly' ? ' /yr' : ' /mo'}</span></div>
              </div>
              <div className="cpReviewBlock">
                <h4>Services</h4>
                {enabledServices.length === 0 ? <div className="help">No modules enabled</div> : enabledServices.map((k) => (
                  <div className="cpKv" key={k}><span className="k">{SVC_META[k].label}</span><span>On</span></div>
                ))}
              </div>
              <div className="cpReviewBlock">
                <h4>Allowlist</h4>
                <div className="cpKv"><span className="k">Mode</span><span>{draft.allowlist.mode === 'custom' ? `Custom (${allowlistCount} countries)` : 'Platform default'}</span></div>
              </div>
              <div className="cpReviewBlock">
                <h4>Organisations</h4>
                <div className="cpKv"><span className="k">Assigned</span><span>{draft.org_ids.length}</span></div>
              </div>
              <div className="cpActions">
                <button type="button" className="cpBtn" disabled={saving} onClick={() => save({ asDraft: true })}>Save as draft</button>
                <button type="button" className="cpBtn cpBtnPrimary" disabled={saving} onClick={() => save({ activate: true })}>Save &amp; activate package</button>
              </div>
            </div>
          </div>

          <div className="cpSummaryCol">
            <div className="cpTicket">
              <div className="cpTicketHead">
                <div className="help" style={{ textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, fontSize: 10 }}>Deal ticket</div>
                <div style={{ fontWeight: 700, fontSize: 14 }}>{draft.name || 'Untitled package'}</div>
                <div className="cpMono help">{draft.code || 'auto code'}</div>
              </div>
              <div className="cpTicketBody">
                <div className="cpTicketRow"><span className="k">Status</span><StatusPill status={draft.status} /></div>
                <div className="cpTicketRow"><span className="k">Interval</span><span>{draft.interval === 'yearly' ? 'Annually' : 'Monthly'}</span></div>
                <div className="cpTicketRow"><span className="k">Currency</span><span>{currency}</span></div>
                <div style={{ borderTop: '1px dashed #cbc9c4', margin: '4px 0' }} />
                <div className="help" style={{ textTransform: 'uppercase', fontSize: 11, letterSpacing: '0.04em' }}>Services</div>
                {enabledServices.length === 0 ? <div className="help">None</div> : enabledServices.map((k) => (
                  <div className="cpTicketRow" key={k}><span className="k">{SVC_META[k].label}</span><span>On</span></div>
                ))}
                <div style={{ borderTop: '1px dashed #cbc9c4', margin: '4px 0' }} />
                <div className="cpTicketRow"><span className="k">Allowlist</span><span>{draft.allowlist.mode === 'custom' ? `${allowlistCount} countries` : 'Platform default'}</span></div>
                <div className="cpTicketRow"><span className="k">Organisations</span><span>{draft.org_ids.length} assigned</span></div>
                <div className="cpTicketPrice">{formatMoney(poundsToMinor(draft.price_major), currency)}<span className="help"> {draft.interval === 'yearly' ? '/yr' : '/mo'}</span></div>
              </div>
              <div className="cpTicketFoot">
                <button type="button" className="cpBtn" disabled={saving} onClick={() => save({ asDraft: true })}>Draft</button>
                <button type="button" className="cpBtn cpBtnPrimary" disabled={saving} onClick={() => save({ activate: true })}>Save</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="cpPage">
      <div className="cpPageHead">
        <div>
          <h1>Custom packages</h1>
          <p>Bundled multi-service deals for organisations. Hidden from the public catalog. Monthly or annual billing in one currency.</p>
        </div>
        <button type="button" className="cpBtn cpBtnPrimary" onClick={openCreate}>+ New custom package</button>
      </div>
      {error ? <div className="cpMsg cpMsgErr">{error}</div> : null}
      {msg ? <div className="cpMsg cpMsgOk">{msg}</div> : null}

      <div className="cpFilterbar">
        <div className="cpSearch">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name, code or org…" />
        </div>
        <button type="button" className={`cpChip ${!serviceFilter ? 'on' : ''}`} onClick={() => setServiceFilter('')}>All services</button>
        {Object.entries(SVC_META).map(([key, meta]) => (
          <button key={key} type="button" className={`cpChip ${serviceFilter === key ? 'on' : ''}`} onClick={() => setServiceFilter(key)}>{meta.label}</button>
        ))}
        <select className="cpSelect" style={{ width: 'auto' }} value={orgFilter} onChange={(e) => setOrgFilter(e.target.value)}>
          <option value="">Any organisation</option>
          {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
        <select className="cpSelect" style={{ width: 'auto' }} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Active + Draft + Inactive</option>
          <option value="active">Active only</option>
          <option value="draft">Draft only</option>
          <option value="inactive">Inactive</option>
        </select>
      </div>

      {loading ? <div className="help">Loading…</div> : null}
      {!loading && items.length === 0 ? (
        <div className="cpEmpty">
          <h3>No custom packages yet</h3>
          <p>Create a bundled deal with allowances, overage rates, dial countries, and org assignment.</p>
          <button type="button" className="cpBtn cpBtnPrimary" onClick={openCreate}>New custom package</button>
        </div>
      ) : (
        <div className="cpTableWrap">
          <table className="cpTable">
            <thead>
              <tr>
                <th>Package</th>
                <th>Services</th>
                <th>Orgs</th>
                <th>Price</th>
                <th>Interval</th>
                <th>Allowlist</th>
                <th>Status</th>
                <th>Updated</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((pkg) => (
                <tr key={pkg.id}>
                  <td>
                    <div className="cpPkgName">{pkg.name}</div>
                    <div className="cpPkgCode cpMono">{pkg.code}</div>
                  </td>
                  <td>
                    <div className="cpSvcIcons">
                      {(pkg.enabled_services || []).map((k) => (
                        <div
                          key={k}
                          className={`cpSvcBadge cpSvc-${SVC_META[k]?.badge || k}`}
                          title={SVC_META[k]?.label || k}
                        >
                          {SVC_META[k]?.short || k}
                        </div>
                      ))}
                    </div>
                  </td>
                  <td>{pkg.org_count || 0}</td>
                  <td className="cpMono">{formatMoney(pkg.price_minor, pkg.currency)} <span className="help">{pkg.interval === 'yearly' ? '/yr' : '/mo'}</span></td>
                  <td>{pkg.interval === 'yearly' ? 'Annually' : 'Monthly'}</td>
                  <td>{pkg.allowlist?.mode === 'custom' ? `${pkg.allowlist_country_count || 0} countries` : 'Platform default'}</td>
                  <td><StatusPill status={pkg.status} /></td>
                  <td className="cpMono help">{pkg.updated_at ? String(pkg.updated_at).slice(0, 10) : '—'}</td>
                  <td className="cpRowActions">
                    <button type="button" className="cpBtn cpBtnSm" onClick={() => openEdit(pkg)}>Edit</button>
                    <button type="button" className="cpBtn cpBtnSm" onClick={() => duplicate(pkg)}>Duplicate</button>
                    {pkg.status !== 'inactive' ? (
                      <button type="button" className="cpBtn cpBtnSm cpBtnDanger" onClick={() => deactivate(pkg)}>Deactivate</button>
                    ) : (
                      <button type="button" className="cpBtn cpBtnSm" disabled>Deactivated</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
