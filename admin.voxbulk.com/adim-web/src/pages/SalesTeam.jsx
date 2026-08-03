import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import './salesTeam.css'

const EU_COUNTRIES = new Set(['AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR', 'DE', 'GR', 'HU', 'IE', 'IT', 'LV', 'LT', 'LU', 'MT', 'NL', 'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE'])
const COUNTRY_CURRENCY = { GB: 'GBP', US: 'USD', CA: 'CAD', AU: 'AUD' }
const CURRENCY_SYMBOLS = { GBP: '£', EUR: '€', USD: '$', CAD: 'CA$', AUD: 'A$' }
const COUNTRIES = [
  { code: 'GB', label: 'United Kingdom' },
  { code: 'US', label: 'United States' },
  { code: 'CA', label: 'Canada' },
  { code: 'AU', label: 'Australia' },
  { code: 'IE', label: 'Ireland' },
  { code: 'DE', label: 'Germany' },
  { code: 'FR', label: 'France' },
  { code: 'ES', label: 'Spain' },
  { code: 'AE', label: 'United Arab Emirates' },
  { code: 'SA', label: 'Saudi Arabia' },
  { code: 'EG', label: 'Egypt' },
  { code: 'IN', label: 'India' },
]
const SERVICE_IDS = ['ai_interview', 'wa_survey', 'customer_feedback', 'voxbulk_expo']
const SERVICE_LABELS = {
  ai_interview: 'AI Interview Screening',
  wa_survey: 'WA Survey / AI Call Survey',
  customer_feedback: 'Customer Feedback',
  voxbulk_expo: 'Voxbulk Expo',
}
const SERVICE_OPTIONS = {
  ai_interview: [
    { kind: 'fixed_topup', label: 'Fixed top-up', unit: 'minor' },
    { kind: 'percent_discount', label: 'Percentage discount', unit: '%' },
  ],
  wa_survey: [
    { kind: 'percent_discount', label: 'Percentage discount', unit: '%' },
    { kind: 'fixed_topup', label: 'Fixed top-up', unit: 'minor' },
    { kind: 'free_days', label: 'Free trial days', unit: 'days' },
  ],
  customer_feedback: [
    { kind: 'percent_discount', label: 'Percentage discount', unit: '%' },
    { kind: 'free_days', label: 'Free days from 1st scan', unit: 'days' },
  ],
  voxbulk_expo: [
    { kind: 'free_package_days', label: 'Free package days', unit: 'days' },
    { kind: 'percent_discount', label: 'Percentage discount', unit: '%' },
  ],
}

const IconEdit = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='M12 20h9' /><path d='M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z' /></svg>
)
const IconReset = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='M3 12a9 9 0 1 0 2.6-6.3' /><path d='M3 4v5h5' /></svg>
)
const IconDelete = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='M3 6h18' /><path d='M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2' /><path d='M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6' /><path d='M10 11v6M14 11v6' /></svg>
)
const IconFreeze = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='M12 2v20M4.9 4.9l14.2 14.2M19.1 4.9 4.9 19.1M2 12h20' /></svg>
)
const IconUnfreeze = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><circle cx='12' cy='12' r='10' /><path d='M9 12l2 2 4-4' /></svg>
)
const IconProfile = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='M4 20c0-3.3 3.6-5.5 8-5.5s8 2.2 8 5.5' /><circle cx='12' cy='8' r='4' /></svg>
)
const IconSearch = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><circle cx='11' cy='11' r='7' /><path d='M21 21l-4.3-4.3' /></svg>
)
const IconPlus = () => (
  <svg width='15' height='15' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2.4'><path d='M12 5v14M5 12h14' /></svg>
)
const IconClose = () => (
  <svg width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='M18 6L6 18M6 6l12 12' /></svg>
)
const IconBack = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='M15 18l-6-6 6-6' /></svg>
)
const IconEmptyPeople = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='1.5'><path d='M17 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2' /><circle cx='10' cy='7' r='4' /></svg>
)
const IconAccounts = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><rect x='3' y='3' width='7' height='7' rx='1' /><rect x='14' y='3' width='7' height='7' rx='1' /><rect x='3' y='14' width='7' height='7' rx='1' /><rect x='14' y='14' width='7' height='7' rx='1' /></svg>
)
const IconInvoices = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z' /><path d='M14 2v6h6' /><path d='M8 13h8M8 17h8' /></svg>
)
const IconUsers = () => (
  <svg className='kpi-icon' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2' /><circle cx='9' cy='7' r='4' /><path d='M22 21v-2a4 4 0 0 0-3-3.87' /><path d='M16 3.13a4 4 0 0 1 0 7.75' /></svg>
)
const IconTarget = () => (
  <svg className='kpi-icon' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><circle cx='12' cy='12' r='10' /><circle cx='12' cy='12' r='6' /><circle cx='12' cy='12' r='2' /></svg>
)
const IconTrend = () => (
  <svg className='kpi-icon' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='m22 7-8.5 8.5-5-5L2 17' /><path d='M16 7h6v6' /></svg>
)
const IconWallet = () => (
  <svg className='kpi-icon' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='M19 7V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-1' /><path d='M3 10h18v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z' /><path d='M17 14h.01' /></svg>
)
const IconCoins = () => (
  <svg className='kpi-icon' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><circle cx='8' cy='8' r='6' /><path d='M18.09 10.37A6 6 0 1 1 10.34 18' /><path d='M7 6h1v4' /><path d='m16.71 13.88.7.71-2.82 2.82' /></svg>
)
const IconReceipt = () => (
  <svg className='kpi-icon' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z' /><path d='M8 10h8M8 14h6' /></svg>
)
const IconMore = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><circle cx='12' cy='5' r='1' /><circle cx='12' cy='12' r='1' /><circle cx='12' cy='19' r='1' /></svg>
)

const COUNTRY_NAMES = Object.fromEntries(COUNTRIES.map((c) => [c.code, c.label]))

function currencyForCountry(country) {
  const code = String(country || '').trim().toUpperCase().slice(0, 2)
  if (EU_COUNTRIES.has(code)) return 'EUR'
  return COUNTRY_CURRENCY[code] || 'USD'
}

function currencySymbol(currency) {
  return CURRENCY_SYMBOLS[String(currency || 'GBP').toUpperCase()] || '$'
}

function money(minor, currency = 'GBP') {
  const n = Number(minor || 0) / 100
  return `${currencySymbol(currency)}${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function genPassword() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#'
  let out = 'Temp#'
  for (let i = 0; i < 6; i++) out += chars[Math.floor(Math.random() * chars.length)]
  return out
}

function tabFromPath(pathname, search) {
  const q = new URLSearchParams(search || '')
  if (q.get('tab') === 'partners' || String(pathname || '').includes('partner-channel')) return 'partners'
  return 'salesman'
}

function defaultPromoBenefits() {
  const services = {}
  SERVICE_IDS.forEach((sid) => {
    const opts = SERVICE_OPTIONS[sid]
    services[sid] = { enabled: false, kind: opts[0].kind, value: opts[0].unit === '%' ? 20 : 0 }
  })
  return {
    wallet_voucher: { enabled: true, amount_major: '20' },
    services,
    usage_limit: '',
    expires_at: '',
  }
}

function defaultCommissionTiers(pct = 15) {
  return [
    { month: 2, enabled: true, kind: 'percent', value: String(pct) },
    { month: 3, enabled: false, kind: 'percent', value: String(pct) },
    { month: 4, enabled: false, kind: 'percent', value: String(pct) },
  ]
}

function defaultPartnerTerms() {
  return { discount_percent: '0', billing: 'customer_pays' }
}

function defaultPayout() {
  return {
    payout_method: 'bank',
    bank_holder_name: '',
    bank_name: '',
    bank_sort_code: '',
    bank_account_number: '',
    bank_address: '',
    paypal_email: '',
  }
}

function emptyForm(isPartner) {
  return {
    name: '',
    email: '',
    password: genPassword(),
    mobile: '',
    country: 'GB',
    company_name: '',
    promo_code: '',
    promo_benefits: defaultPromoBenefits(),
    commission_tiers: defaultCommissionTiers(isPartner ? 15 : 15),
    partner_terms: defaultPartnerTerms(),
    payout: defaultPayout(),
    partner_comm_kind: 'percent',
    partner_comm_value: '15',
  }
}

function repToForm(rep) {
  const benefits = rep.promo_benefits || {}
  const wv = benefits.wallet_voucher || {}
  const services = {}
  SERVICE_IDS.forEach((sid) => {
    const src = (benefits.services || {})[sid] || {}
    const opts = SERVICE_OPTIONS[sid]
    const kind = src.kind || opts[0].kind
    const opt = opts.find((o) => o.kind === kind) || opts[0]
    let value = src.value ?? (opt.unit === '%' ? 20 : 0)
    if (opt.unit === 'minor') value = Number(value || 0) / 100
    services[sid] = {
      enabled: Boolean(src.enabled),
      kind,
      value: String(value),
    }
  })
  const tiers = (rep.commission_tiers || defaultCommissionTiers()).map((t) => ({
    month: t.month,
    enabled: Boolean(t.enabled),
    kind: t.kind === 'fixed' ? 'fixed' : 'percent',
    value: t.kind === 'fixed' ? String(Number(t.value || 0) / 100) : String(t.value ?? ''),
  }))
  const pt = rep.partner_terms || defaultPartnerTerms()
  const enabledTier = tiers.find((t) => t.enabled) || tiers[0]
  return {
    name: rep.name || '',
    email: rep.email || '',
    password: '',
    mobile: rep.mobile || '',
    country: rep.country || 'GB',
    company_name: rep.company_name || '',
    promo_code: rep.promo_code || '',
    promo_benefits: {
      wallet_voucher: {
        enabled: Boolean(wv.enabled),
        amount_major: wv.amount_minor != null ? String(Number(wv.amount_minor) / 100) : '20',
      },
      services,
      usage_limit: benefits.usage_limit != null ? String(benefits.usage_limit) : '',
      expires_at: benefits.expires_at ? String(benefits.expires_at).slice(0, 10) : '',
    },
    commission_tiers: tiers,
    partner_terms: {
      discount_percent: String(pt.discount_percent ?? '0'),
      billing: pt.billing || 'customer_pays',
    },
    payout: { ...defaultPayout(), ...(rep.payout || {}) },
    partner_comm_kind: enabledTier?.kind || 'percent',
    partner_comm_value: enabledTier?.value || '15',
  }
}

function buildPromoBenefitsPayload(form, currency) {
  const pb = form.promo_benefits
  const services = {}
  SERVICE_IDS.forEach((sid) => {
    const src = pb.services[sid]
    const opt = (SERVICE_OPTIONS[sid] || []).find((o) => o.kind === src.kind) || SERVICE_OPTIONS[sid][0]
    let value = parseFloat(src.value || '0')
    if (opt.unit === 'minor') value = Math.round(value * 100)
    services[sid] = { enabled: Boolean(src.enabled), kind: src.kind, value }
  })
  return {
    wallet_voucher: {
      enabled: Boolean(pb.wallet_voucher.enabled),
      amount_minor: Math.round(parseFloat(pb.wallet_voucher.amount_major || '0') * 100),
    },
    services,
    usage_limit: pb.usage_limit ? parseInt(pb.usage_limit, 10) : null,
    expires_at: pb.expires_at || null,
  }
}

function buildCommissionTiersPayload(form, isPartner) {
  if (isPartner) {
    const kind = form.partner_comm_kind
    const val = parseFloat(form.partner_comm_value || '0')
    return [
      {
        month: 2,
        enabled: true,
        kind,
        value: kind === 'fixed' ? Math.round(val * 100) : val,
      },
      { month: 3, enabled: false, kind: 'percent', value: 0 },
      { month: 4, enabled: false, kind: 'percent', value: 0 },
    ]
  }
  return form.commission_tiers.map((t) => ({
    month: t.month,
    enabled: Boolean(t.enabled),
    kind: t.kind,
    value: t.kind === 'fixed' ? Math.round(parseFloat(t.value || '0') * 100) : parseFloat(t.value || '0'),
  }))
}

function statusBadge(status) {
  const s = String(status || '').toLowerCase()
  if (s === 'paid') return <span className='badge badge-paid'>Paid</span>
  if (s === 'sent') return <span className='badge badge-sent'>Sent</span>
  if (s === 'new') return <span className='badge badge-new'>New</span>
  if (s === 'rejected') return <span className='badge badge-rejected'>Rejected</span>
  if (s === 'submitted') return <span className='badge badge-requested'>Awaiting Approval</span>
  return <span className='badge badge-pending'>{status || '—'}</span>
}

export default function SalesTeam() {
  const location = useLocation()
  const navigate = useNavigate()

  const [view, setView] = useState('accounts')
  const [tab, setTab] = useState(() => tabFromPath(location.pathname, location.search))
  const [editorTab, setEditorTab] = useState('profile')
  const [reps, setReps] = useState([])
  const [allReps, setAllReps] = useState([])
  const [kpis, setKpis] = useState(null)
  const [hubInvoices, setHubInvoices] = useState([])
  const [hubKpis, setHubKpis] = useState({})
  const [invoiceFilter, setInvoiceFilter] = useState('all')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [search, setSearch] = useState('')
  const [invoiceSearch, setInvoiceSearch] = useState('')
  const [menuRepId, setMenuRepId] = useState(null)
  const [toast, setToast] = useState('')

  const [editId, setEditId] = useState(null)
  const [form, setForm] = useState(() => emptyForm(false))
  const [formErr, setFormErr] = useState('')
  const [catalog, setCatalog] = useState({ packages: [], services: [] })

  const [pwRep, setPwRep] = useState(null)
  const [pwValue, setPwValue] = useState('')

  const [profileRep, setProfileRep] = useState(null)
  const [profile, setProfile] = useState(null)

  const [invoiceDetail, setInvoiceDetail] = useState(null)
  const [invoiceDetailRep, setInvoiceDetailRep] = useState(null)

  const [showCreateInvoice, setShowCreateInvoice] = useState(false)
  const [createInvForm, setCreateInvForm] = useState({
    sales_rep_id: '',
    kind: 'commission',
    customer: '',
    discount_percent: '0',
    tax_percent: '0',
    commission_amount_major: '0',
    items: [{ service_id: 'wa_survey', description: '', quantity: '1', unit_price_major: '0' }],
  })
  const [createInvErr, setCreateInvErr] = useState('')

  const [editorInvoices, setEditorInvoices] = useState([])
  const [editorPayoutInvoices, setEditorPayoutInvoices] = useState([])

  const kind = tab === 'partners' ? 'partner_channel' : 'salesman'
  const isPartner = kind === 'partner_channel'
  const formCurrency = currencyForCountry(form.country)

  const showToast = useCallback((msg) => {
    setToast(msg)
    window.setTimeout(() => setToast(''), 2600)
  }, [])

  const computeKpisFromReps = useCallback((items, hubKpiData) => {
    const outstanding = (Number(hubKpiData?.new || 0) + Number(hubKpiData?.sent || 0))
    return {
      accounts: items.length,
      leads: 0,
      paying_customers: items.reduce((s, r) => s + Number(r.customers || 0), 0),
      revenue_minor: items.reduce((s, r) => s + Number(r.revenue_minor || 0), 0),
      commission_earned_minor: items.reduce((s, r) => s + Number(r.commission_minor || 0), 0),
      commission_paid_minor: 0,
      invoices_outstanding_minor: outstanding,
    }
  }, [])

  const loadKpis = useCallback(async (items, hubKpiData) => {
    try {
      const res = await apiFetch('/admin/sales-reps/team-kpis')
      setKpis(res)
    } catch {
      setKpis(computeKpisFromReps(items, hubKpiData))
    }
  }, [computeKpisFromReps])

  const loadHubInvoices = useCallback(async () => {
    try {
      const res = await apiFetch('/admin/sales-reps/hub-invoices')
      setHubInvoices(res?.items || [])
      setHubKpis(res?.kpis || {})
      return res
    } catch (e) {
      showToast(e?.message || 'Failed to load invoices')
      return { items: [], kpis: {} }
    }
  }, [showToast])

  const loadReps = useCallback(async () => {
    setLoading(true)
    try {
      const [res, allRes, hubRes] = await Promise.all([
        apiFetch(`/admin/sales-reps?kind=${kind}`),
        apiFetch('/admin/sales-reps'),
        apiFetch('/admin/sales-reps/hub-invoices').catch(() => ({ items: [], kpis: {} })),
      ])
      setReps(res?.items || [])
      setAllReps(allRes?.items || [])
      setHubInvoices(hubRes?.items || [])
      setHubKpis(hubRes?.kpis || {})
      await loadKpis(allRes?.items || [], hubRes?.kpis || {})
    } catch (e) {
      showToast(e?.message || 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [kind, loadKpis, showToast])

  const loadCatalog = useCallback(async (country) => {
    try {
      const res = await apiFetch(`/admin/sales-reps/hub-catalog?country=${encodeURIComponent(country || 'GB')}`)
      setCatalog({ packages: res?.packages || [], services: res?.services || [] })
    } catch {
      setCatalog({ packages: [], services: [] })
    }
  }, [])

  useEffect(() => {
    setTab(tabFromPath(location.pathname, location.search))
  }, [location.pathname, location.search])

  useEffect(() => {
    if (view === 'accounts' || view === 'invoices') loadReps()
  }, [tab, view, loadReps])

  useEffect(() => {
    if (view === 'editor') loadCatalog(form.country)
  }, [view, form.country, loadCatalog])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return reps
    return reps.filter((r) =>
      [r.name, r.email, r.mobile, r.promo_code, r.company_name].some((v) => String(v || '').toLowerCase().includes(q))
    )
  }, [reps, search])

  const switchTab = (next) => {
    setTab(next)
    setSearch('')
    navigate(next === 'partners' ? '/marketing/partner-channel-sales' : '/marketing/salesmen')
  }

  const openAdd = () => {
    setEditId(null)
    setForm(emptyForm(tab === 'partners'))
    setFormErr('')
    setEditorTab('profile')
    setView('editor')
  }

  const openEdit = async (rep) => {
    setEditId(rep.id)
    setForm(repToForm(rep))
    setFormErr('')
    setEditorTab('profile')
    setView('editor')
    try {
      const [hub, payout] = await Promise.all([
        apiFetch(`/admin/sales-reps/hub-invoices?rep_id=${rep.id}`),
        apiFetch(`/admin/sales-reps/payout-invoices?rep_id=${rep.id}`),
      ])
      setEditorInvoices(hub?.items || [])
      setEditorPayoutInvoices(payout?.items || [])
    } catch {
      setEditorInvoices([])
      setEditorPayoutInvoices([])
    }
  }

  const saveForm = async () => {
    setBusy(true)
    setFormErr('')
    if (!form.country) {
      setFormErr('Country is required.')
      setBusy(false)
      return
    }
    const tiers = buildCommissionTiersPayload(form, isPartner)
    const primary = tiers.find((t) => t.enabled) || tiers[0]
    const commissionType = isPartner
      ? (primary.kind === 'fixed' ? 'fixed' : 'percent')
      : (primary.month === 2 && primary.enabled ? 'month2' : primary.kind === 'fixed' ? 'fixed' : 'percent')
    const payload = {
      name: form.name,
      email: form.email,
      password: form.password,
      mobile: form.mobile,
      country: form.country,
      company_name: form.company_name,
      promo_code: form.promo_code,
      kind,
      commission_type: commissionType,
      commission_pct: primary.kind === 'percent' ? String(primary.value) : '15',
      commission_fixed_minor: primary.kind === 'fixed' ? primary.value : 0,
      promo_benefits: buildPromoBenefitsPayload(form, formCurrency),
      commission_tiers: tiers,
      partner_terms: {
        discount_percent: parseFloat(form.partner_terms.discount_percent || '0'),
        billing: form.partner_terms.billing,
      },
      payout: form.payout,
    }
    try {
      if (editId) {
        const patch = { ...payload }
        delete patch.email
        delete patch.password
        delete patch.kind
        await apiFetch(`/admin/sales-reps/${editId}`, { method: 'PATCH', body: JSON.stringify(patch) })
        showToast('Saved')
      } else {
        if (!form.email) {
          setFormErr('Email is required.')
          setBusy(false)
          return
        }
        await apiFetch('/admin/sales-reps', { method: 'POST', body: JSON.stringify(payload) })
        showToast('Created')
      }
      setView('accounts')
      await loadReps()
    } catch (e) {
      setFormErr(e?.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  const resetPassword = async () => {
    if (!pwRep) return
    setBusy(true)
    try {
      await apiFetch(`/admin/sales-reps/${pwRep.id}/reset-password`, {
        method: 'POST',
        body: JSON.stringify({ password: pwValue }),
      })
      showToast('Password reset')
      setPwRep(null)
      setPwValue('')
    } catch (e) {
      showToast(e?.message || 'Reset failed')
    } finally {
      setBusy(false)
    }
  }

  const toggleFreeze = async (rep) => {
    setBusy(true)
    try {
      await apiFetch(`/admin/sales-reps/${rep.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: !rep.is_active }),
      })
      showToast(`${rep.name} ${rep.is_active ? 'has been frozen.' : 'has been reactivated.'}`)
      await loadReps()
      if (profileRep?.id === rep.id) await openProfile({ ...rep, is_active: !rep.is_active })
    } catch (e) {
      showToast(e?.message || 'Update failed')
    } finally {
      setBusy(false)
    }
  }

  const deleteRep = async (rep) => {
    if (!window.confirm(`Delete ${rep.name}? This cannot be undone.`)) return
    setBusy(true)
    try {
      await apiFetch(`/admin/sales-reps/${rep.id}`, { method: 'DELETE' })
      showToast(`${rep.name} was deleted.`)
      if (profileRep?.id === rep.id) {
        setProfileRep(null)
        setProfile(null)
        setView('accounts')
      }
      await loadReps()
    } catch (e) {
      showToast(e?.message || 'Delete failed')
    } finally {
      setBusy(false)
    }
  }

  const openProfile = async (rep) => {
    setProfileRep(rep)
    setView('profile')
    try {
      const res = await apiFetch(`/admin/sales-reps/${rep.id}/dashboard`)
      setProfile(res)
      if (res?.rep) setProfileRep(res.rep)
    } catch (e) {
      showToast(e?.message || 'Failed to load profile')
    }
  }

  const openInvoiceDetail = async (invoiceId) => {
    setView('invoiceDetail')
    try {
      const res = await apiFetch(`/admin/sales-reps/hub-invoices/${invoiceId}`)
      setInvoiceDetail(res?.invoice || null)
      setInvoiceDetailRep(res?.rep || null)
    } catch (e) {
      showToast(e?.message || 'Failed to load invoice')
      setView('invoices')
    }
  }

  const hubInvoiceAction = async (invoiceId, action, body = {}) => {
    setBusy(true)
    try {
      const res = await apiFetch(`/admin/sales-reps/hub-invoices/${invoiceId}/${action}`, {
        method: 'POST',
        body: JSON.stringify(body),
      })
      if (res?.invoice) setInvoiceDetail(res.invoice)
      showToast(`Invoice ${action.replace('-', ' ')}`)
      await loadHubInvoices()
    } catch (e) {
      showToast(e?.message || 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  const approvePay = async (invoiceId) => {
    if (!window.confirm('Approve this invoice and mark as paid?')) return
    setBusy(true)
    try {
      await apiFetch(`/admin/sales-reps/payout-invoices/${invoiceId}/approve-pay`, { method: 'POST', body: '{}' })
      showToast('Approved and marked as paid.')
      if (editId) {
        const payout = await apiFetch(`/admin/sales-reps/payout-invoices?rep_id=${editId}`)
        setEditorPayoutInvoices(payout?.items || [])
      }
      if (profileRep) await openProfile(profileRep)
    } catch (e) {
      showToast(e?.message || 'Approve failed')
    } finally {
      setBusy(false)
    }
  }

  const rejectPayoutInvoice = async (invoiceId) => {
    if (!window.confirm('Reject this invoice? Commission returns to available.')) return
    setBusy(true)
    try {
      await apiFetch(`/admin/sales-reps/payout-invoices/${invoiceId}/reject`, {
        method: 'POST',
        body: JSON.stringify({ reason: '' }),
      })
      showToast('Invoice rejected.')
      if (editId) {
        const payout = await apiFetch(`/admin/sales-reps/payout-invoices?rep_id=${editId}`)
        setEditorPayoutInvoices(payout?.items || [])
      }
      if (profileRep) await openProfile(profileRep)
    } catch (e) {
      showToast(e?.message || 'Reject failed')
    } finally {
      setBusy(false)
    }
  }

  const createHubInvoice = async () => {
    setBusy(true)
    setCreateInvErr('')
    const rep = allReps.find((r) => r.id === createInvForm.sales_rep_id)
    const cur = rep?.currency || 'GBP'
    const items = createInvForm.items.map((it) => ({
      service_id: it.service_id || null,
      description: it.description || 'Line item',
      quantity: Math.max(1, parseInt(it.quantity || '1', 10)),
      unit_price_minor: Math.round(parseFloat(it.unit_price_major || '0') * 100),
    }))
    if (!createInvForm.sales_rep_id) {
      setCreateInvErr('Select a salesman/partner.')
      setBusy(false)
      return
    }
    if (!items.length || items.every((it) => !it.unit_price_minor && !it.description)) {
      setCreateInvErr('Add at least one line item.')
      setBusy(false)
      return
    }
    try {
      await apiFetch('/admin/sales-reps/hub-invoices', {
        method: 'POST',
        body: JSON.stringify({
          sales_rep_id: createInvForm.sales_rep_id,
          kind: createInvForm.kind,
          customer: createInvForm.customer,
          currency: cur,
          discount_percent: parseFloat(createInvForm.discount_percent || '0'),
          tax_percent: parseFloat(createInvForm.tax_percent || '0'),
          commission_amount_minor: Math.round(parseFloat(createInvForm.commission_amount_major || '0') * 100),
          items,
        }),
      })
      showToast('Invoice created')
      setShowCreateInvoice(false)
      await loadHubInvoices()
      await loadReps()
    } catch (e) {
      setCreateInvErr(e?.message || 'Create failed')
    } finally {
      setBusy(false)
    }
  }

  const packageForService = (serviceId) => catalog.packages.find((p) => p.service_id === serviceId)

  const renderSubNav = () => {
    const accountsActive = view === 'accounts' || view === 'editor' || view === 'profile'
    const invoicesActive = view === 'invoices' || view === 'invoiceDetail'
    return (
      <div className='hub-topnav'>
        <div className='hub-topnav-inner'>
          <button
            type='button'
            className={accountsActive ? 'active' : ''}
            onClick={() => { setView('accounts'); setProfileRep(null); setProfile(null) }}
          >
            <IconAccounts /> Accounts
          </button>
          <button
            type='button'
            className={invoicesActive ? 'active' : ''}
            onClick={() => { setView('invoices'); setInvoiceDetail(null) }}
          >
            <IconInvoices /> Invoices
          </button>
        </div>
      </div>
    )
  }

  const renderKpiStrip = () => {
    const k = kpis || {}
    const cur = 'GBP'
    const salesmen = k.salesmen ?? allReps.filter((r) => r.kind !== 'partner_channel').length
    const partners = k.partners ?? allReps.filter((r) => r.kind === 'partner_channel').length
    const pending = Math.max(0, Number(k.commission_earned_minor || 0) - Number(k.commission_paid_minor || 0))
    const cards = [
      { label: 'Accounts', value: k.accounts ?? allReps.length, hint: `${salesmen} salesmen · ${partners} partners`, icon: <IconUsers /> },
      { label: 'Leads', value: k.leads ?? 0, hint: 'all sources', icon: <IconTarget /> },
      { label: 'Paying customers', value: k.paying_customers ?? 0, hint: 'active companies', icon: <IconTrend />, tone: 'positive' },
      { label: 'Revenue', value: money(k.revenue_minor, cur), hint: 'base currency', icon: <IconWallet /> },
      { label: 'Commission earned', value: money(k.commission_earned_minor, cur), icon: <IconCoins /> },
      { label: 'Commission paid', value: money(k.commission_paid_minor, cur), hint: `${money(pending, cur)} pending`, icon: <IconCoins /> },
      { label: 'Invoices outstanding', value: money(k.invoices_outstanding_minor, cur), hint: `${hubInvoices.filter((i) => i.status === 'new' || i.status === 'sent').length} open`, icon: <IconReceipt />, tone: 'warning' },
    ]
    return (
      <section className='kpi-grid kpi-7'>
        {cards.map((c) => (
          <div key={c.label} className='kpi-card'>
            <div className='kpi-card-top'>
              <span className='label'>{c.label}</span>
              {c.icon}
            </div>
            <div className={`value${c.tone ? ` tone-${c.tone}` : ''}`}>{c.value}</div>
            {c.hint ? <p className='hint'>{c.hint}</p> : null}
          </div>
        ))}
      </section>
    )
  }

  const renderAccountsView = () => (
    <>
      <header className='hub-header'>
        <div>
          <h1>Salesmen &amp; Partners</h1>
          <p className='subtitle'>Accounts, promo codes, commission terms and invoicing — all in one place.</p>
        </div>
        <div className='hub-header-actions'>
          <button type='button' className='btn btn-primary' onClick={openAdd}>
            <IconPlus />
            New {isPartner ? 'partner' : 'salesman'}
          </button>
        </div>
      </header>
      {renderKpiStrip()}
      <section className='accounts-layout'>
        <div className='accounts-main'>
          <div className='tabs-toolbar'>
            <div className='tabs-list'>
              <button type='button' className={tab === 'salesman' ? 'active' : ''} onClick={() => switchTab('salesman')}>
                Salesmen ({allReps.filter((r) => r.kind !== 'partner_channel').length})
              </button>
              <button type='button' className={tab === 'partners' ? 'active' : ''} onClick={() => switchTab('partners')}>
                Partners ({allReps.filter((r) => r.kind === 'partner_channel').length})
              </button>
            </div>
            <div className='search-box'>
              <IconSearch />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder='Search ID, name, email or code'
              />
            </div>
          </div>
          {loading ? (
            <div className='empty-state' style={{ marginTop: 16 }}>Loading…</div>
          ) : filtered.length === 0 ? (
            <div className='empty-state' style={{ marginTop: 16 }}>
              <IconEmptyPeople />
              <div>No accounts yet.</div>
            </div>
          ) : (
            <div className='table-wrap'>
              <table>
                <thead>
                  <tr>
                    <th style={{ width: 80 }}>ID</th>
                    <th>Name</th>
                    <th>Location</th>
                    <th>Currency</th>
                    <th>Contact</th>
                    <th>Promo code</th>
                    <th>Commission</th>
                    <th className='tabular'>Revenue</th>
                    <th>Status</th>
                    <th style={{ width: 48 }} />
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((rep, idx) => {
                    const cur = rep.currency || currencyForCountry(rep.country)
                    const refId = String(1000 + idx + 1).slice(-4)
                    return (
                      <tr key={rep.id} className={rep.is_active ? '' : 'frozen'}>
                        <td className='mono'>#{String(rep.ref_id || refId)}</td>
                        <td>
                          <button type='button' className='person-name link-btn' onClick={() => openProfile(rep)} style={{ fontWeight: 500 }}>
                            {rep.name}
                          </button>
                          {rep.company_name ? <div className='muted'>{rep.company_name}</div> : null}
                        </td>
                        <td>
                          <span className='mono'>{rep.country || '—'}</span>
                          {rep.country ? <span className='muted' style={{ marginLeft: 6 }}>{COUNTRY_NAMES[rep.country] || ''}</span> : null}
                        </td>
                        <td>{cur}</td>
                        <td>
                          <div>{rep.email}</div>
                          <div className='muted'>{rep.mobile || '—'}</div>
                        </td>
                        <td>
                          {rep.promo_code ? (
                            <>
                              <span className='badge badge-mono'>{rep.promo_code}</span>
                              <div className='benefit-lines'>
                                {(rep.promo_benefit_summaries || []).slice(0, 4).map((line) => (
                                  <div key={line}>{line}</div>
                                ))}
                              </div>
                            </>
                          ) : (
                            <span className='muted'>None</span>
                          )}
                        </td>
                        <td>
                          {rep.commission_summary ? (
                            <>
                              <div>{rep.commission_summary}</div>
                              <div className='muted'>{isPartner ? 'next payment only' : 'monthly tiers'}</div>
                            </>
                          ) : (
                            <span className='muted'>—</span>
                          )}
                        </td>
                        <td className='tabular'>{money(rep.revenue_minor || 0, cur)}</td>
                        <td>
                          <span className={`badge ${rep.is_active ? 'badge-active' : 'badge-frozen'}`}>
                            {rep.is_active ? 'active' : 'frozen'}
                          </span>
                        </td>
                        <td>
                          <div
                            className={`row-menu${menuRepId === rep.id ? ' open' : ''}`}
                            onClick={(e) => e.stopPropagation()}
                          >
                            <button
                              type='button'
                              className='row-menu-trigger'
                              aria-label='Actions'
                              onClick={(e) => {
                                e.stopPropagation()
                                setMenuRepId(menuRepId === rep.id ? null : rep.id)
                              }}
                            >
                              <IconMore />
                            </button>
                            {menuRepId === rep.id ? (
                              <div className='row-menu-panel' role='menu'>
                                <button type='button' onClick={() => { setMenuRepId(null); openProfile(rep) }}>
                                  <IconProfile /> View profile
                                </button>
                                <button type='button' onClick={() => { setMenuRepId(null); openEdit(rep) }}>
                                  <IconEdit /> Edit
                                </button>
                                <button type='button' onClick={() => { setMenuRepId(null); toggleFreeze(rep) }}>
                                  {rep.is_active ? <><IconFreeze /> Freeze</> : <><IconUnfreeze /> Unfreeze</>}
                                </button>
                                <button type='button' onClick={() => { setMenuRepId(null); setPwRep(rep); setPwValue(genPassword()) }}>
                                  <IconReset /> Reset password
                                </button>
                                <div className='row-menu-sep' />
                                <button type='button' className='danger' onClick={() => { setMenuRepId(null); deleteRep(rep) }}>
                                  <IconDelete /> Delete
                                </button>
                              </div>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <aside className='aside-card'>
          <div className='aside-card-head'>
            <h2>Latest invoices</h2>
            <button type='button' className='link-all' onClick={() => setView('invoices')}>View all</button>
          </div>
          <ul className='aside-list'>
            {hubInvoices.slice(0, 6).map((inv) => (
              <li key={inv.id}>
                <div className='aside-invoice' onClick={() => openInvoiceDetail(inv.id)} role='presentation'>
                  <div className='aside-invoice-row'>
                    <span className='inv-num'>{inv.number}</span>
                    {statusBadge(inv.status)}
                  </div>
                  <div className='inv-meta'>
                    <span className='trunc'>{inv.rep_name || inv.customer || '—'}</span>
                    <span className='tabular'>{inv.total_display || money(inv.total_minor, inv.currency)}</span>
                  </div>
                </div>
              </li>
            ))}
          </ul>
          {hubInvoices.length === 0 ? <p className='muted' style={{ marginTop: 12 }}>No hub invoices yet.</p> : null}
        </aside>
      </section>
    </>
  )

  const renderInvoicesView = () => {
    const statusKpis = [
      { key: 'new', label: 'New' },
      { key: 'sent', label: 'Sent / awaiting payment' },
      { key: 'paid', label: 'Paid' },
      { key: 'rejected', label: 'Rejected' },
    ]
    const q = invoiceSearch.trim().toLowerCase()
    const filteredInv = hubInvoices.filter((i) => {
      if (invoiceFilter !== 'all' && i.status !== invoiceFilter) return false
      if (!q) return true
      const hay = `${i.number || ''} ${i.customer || ''} ${i.rep_name || ''} ${i.kind || ''}`.toLowerCase()
      return hay.includes(q)
    })
    return (
      <>
        <header className='hub-header'>
          <div>
            <h1>Invoices</h1>
            <p className='subtitle'>Everything we charge partners and everything we owe in commission.</p>
          </div>
          <div className='hub-header-actions'>
            <button type='button' className='btn btn-primary' onClick={() => {
              setCreateInvForm({
                sales_rep_id: allReps[0]?.id || '',
                kind: 'commission',
                customer: '',
                discount_percent: '0',
                tax_percent: '0',
                commission_amount_major: '0',
                items: [{ service_id: 'wa_survey', description: '', quantity: '1', unit_price_major: '0' }],
              })
              setCreateInvErr('')
              setShowCreateInvoice(true)
            }}>
              <IconPlus /> Create invoice
            </button>
          </div>
        </header>
        <div className='kpi-grid'>
          {statusKpis.map(({ key, label }) => (
            <div key={key} className='kpi-card'>
              <div className='kpi-card-top'>
                <span className='label'>{label}</span>
              </div>
              <div className={`value${key === 'sent' ? ' tone-warning' : key === 'paid' ? ' tone-positive' : ''}`}>
                {money(hubKpis[key], 'GBP')}
              </div>
              <p className='hint'>{hubInvoices.filter((i) => i.status === key).length} invoices</p>
            </div>
          ))}
        </div>
        <div className='toolbar'>
          <div className='tabs-list'>
            {['all', 'new', 'sent', 'paid', 'rejected'].map((f) => (
              <button
                key={f}
                type='button'
                className={invoiceFilter === f ? 'active' : ''}
                onClick={() => setInvoiceFilter(f)}
                style={{ textTransform: 'capitalize' }}
              >
                {f}
              </button>
            ))}
          </div>
          <div className='search-box'>
            <IconSearch />
            <input
              value={invoiceSearch}
              onChange={(e) => setInvoiceSearch(e.target.value)}
              placeholder='Search invoice, account or customer'
            />
          </div>
        </div>
        <div className='table-wrap' style={{ marginTop: 0 }}>
          <table>
            <thead>
              <tr>
                <th>Invoice</th>
                <th>Account</th>
                <th>Bill to</th>
                <th>Type</th>
                <th>Issued</th>
                <th>Due</th>
                <th className='tabular'>Total</th>
                <th className='tabular'>Commission</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredInv.length === 0 ? (
                <tr><td colSpan={9}><div className='empty-state' style={{ border: 'none' }}>No hub invoices yet.</div></td></tr>
              ) : filteredInv.map((inv) => (
                <tr key={inv.id} style={{ cursor: 'pointer' }} onClick={() => openInvoiceDetail(inv.id)}>
                  <td className='mono'>
                    <button type='button' className='link-btn' style={{ fontFamily: 'inherit' }} onClick={(e) => { e.stopPropagation(); openInvoiceDetail(inv.id) }}>
                      {inv.number}
                    </button>
                  </td>
                  <td>{inv.rep_name || '—'}</td>
                  <td>{inv.customer || '—'}</td>
                  <td style={{ textTransform: 'capitalize' }}>{inv.kind}</td>
                  <td>{(inv.issued_at || inv.created_at || '').slice(0, 10) || '—'}</td>
                  <td>{(inv.due_at || '').slice(0, 10) || '—'}</td>
                  <td className='tabular'>{inv.total_display || money(inv.total_minor, inv.currency)}</td>
                  <td className='tabular'>
                    {inv.kind === 'commission'
                      ? (inv.commission_amount_display || money(inv.commission_amount_minor, inv.currency))
                      : '—'}
                  </td>
                  <td>{statusBadge(inv.status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </>
    )
  }

  const renderEditorProfileTab = () => (
    <>
      <div className='field-row'>
        <div className='field'>
          <label>Full name</label>
          <input type='text' value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder='e.g. Ahmed Khaled' />
        </div>
        <div className='field'>
          <label>Mobile</label>
          <input type='tel' value={form.mobile} onChange={(e) => setForm({ ...form, mobile: e.target.value })} placeholder='+44 7700 900123' />
        </div>
      </div>
      {!editId ? (
        <>
          <div className='field'>
            <label>Email</label>
            <input type='email' value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </div>
          <div className='field'>
            <label>Temporary password <span className='hint'>shared at first login</span></label>
            <div className='pw-row'>
              <input type='text' value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
              <button type='button' className='btn btn-ghost btn-sm pw-gen' onClick={() => setForm({ ...form, password: genPassword() })}>Generate</button>
            </div>
          </div>
        </>
      ) : null}
      <div className='field-row'>
        <div className='field'>
          <label>Country <span className='hint'>required</span></label>
          <select value={form.country} onChange={(e) => setForm({ ...form, country: e.target.value })}>
            {COUNTRIES.map((c) => (
              <option key={c.code} value={c.code}>{c.label}</option>
            ))}
          </select>
        </div>
        {isPartner ? (
          <div className='field'>
            <label>Company</label>
            <input type='text' value={form.company_name} onChange={(e) => setForm({ ...form, company_name: e.target.value })} />
          </div>
        ) : (
          <div className='field'>
            <label>Currency</label>
            <div style={{ paddingTop: 10 }}>
              <span className='currency-badge'>{formCurrency} {currencySymbol(formCurrency)}</span>
            </div>
          </div>
        )}
      </div>
      {isPartner ? (
        <div className='field'>
          <label>Currency</label>
          <span className='currency-badge'>{formCurrency} {currencySymbol(formCurrency)}</span>
        </div>
      ) : null}
    </>
  )

  const renderEditorPromoTab = () => (
    <>
      <div className='field'>
        <label>Promo code</label>
        <input type='text' value={form.promo_code} onChange={(e) => setForm({ ...form, promo_code: e.target.value.toUpperCase() })} style={{ textTransform: 'uppercase' }} />
      </div>
      <div className='field'>
        <label>
          <input
            type='checkbox'
            checked={form.promo_benefits.wallet_voucher.enabled}
            onChange={(e) => setForm({
              ...form,
              promo_benefits: {
                ...form.promo_benefits,
                wallet_voucher: { ...form.promo_benefits.wallet_voucher, enabled: e.target.checked },
              },
            })}
            style={{ marginRight: 8 }}
          />
          Wallet voucher ({formCurrency})
        </label>
        <input
          type='number'
          min='0'
          step='0.01'
          value={form.promo_benefits.wallet_voucher.amount_major}
          disabled={!form.promo_benefits.wallet_voucher.enabled}
          onChange={(e) => setForm({
            ...form,
            promo_benefits: {
              ...form.promo_benefits,
              wallet_voucher: { ...form.promo_benefits.wallet_voucher, amount_major: e.target.value },
            },
          })}
        />
      </div>
      {SERVICE_IDS.map((sid) => {
        const svc = form.promo_benefits.services[sid]
        const pkg = packageForService(sid)
        const opts = SERVICE_OPTIONS[sid]
        const selectedOpt = opts.find((o) => o.kind === svc.kind) || opts[0]
        return (
          <div key={sid} className='service-row'>
            <div className='service-row-head'>
              <label>
                <input
                  type='checkbox'
                  checked={svc.enabled}
                  onChange={(e) => setForm({
                    ...form,
                    promo_benefits: {
                      ...form.promo_benefits,
                      services: {
                        ...form.promo_benefits.services,
                        [sid]: { ...svc, enabled: e.target.checked },
                      },
                    },
                  })}
                />
                {SERVICE_LABELS[sid]}
              </label>
              {pkg?.list_price_display ? (
                <span className='service-price'>List: {pkg.list_price_display}{pkg.yearly_display ? ` / yr ${pkg.yearly_display}` : ''}</span>
              ) : null}
            </div>
            {svc.enabled ? (
              <div className='service-fields'>
                <select
                  value={svc.kind}
                  onChange={(e) => setForm({
                    ...form,
                    promo_benefits: {
                      ...form.promo_benefits,
                      services: {
                        ...form.promo_benefits.services,
                        [sid]: { ...svc, kind: e.target.value },
                      },
                    },
                  })}
                >
                  {opts.map((o) => (
                    <option key={o.kind} value={o.kind}>{o.label}</option>
                  ))}
                </select>
                <input
                  type='number'
                  min='0'
                  step={selectedOpt.unit === 'minor' ? '0.01' : '1'}
                  value={svc.value}
                  onChange={(e) => setForm({
                    ...form,
                    promo_benefits: {
                      ...form.promo_benefits,
                      services: {
                        ...form.promo_benefits.services,
                        [sid]: { ...svc, value: e.target.value },
                      },
                    },
                  })}
                  placeholder={selectedOpt.unit === '%' ? '%' : selectedOpt.unit === 'minor' ? formCurrency : 'days'}
                />
              </div>
            ) : null}
          </div>
        )
      })}
      <div className='field-row'>
        <div className='field'>
          <label>Usage limit <span className='hint'>optional</span></label>
          <input type='number' min='1' value={form.promo_benefits.usage_limit} onChange={(e) => setForm({
            ...form,
            promo_benefits: { ...form.promo_benefits, usage_limit: e.target.value },
          })} />
        </div>
        <div className='field'>
          <label>Expires at <span className='hint'>optional</span></label>
          <input type='date' value={form.promo_benefits.expires_at} onChange={(e) => setForm({
            ...form,
            promo_benefits: { ...form.promo_benefits, expires_at: e.target.value },
          })} />
        </div>
      </div>
    </>
  )

  const renderEditorCommissionTab = () => {
    if (isPartner) {
      return (
        <>
          <div className='field'>
            <label>Next payment commission</label>
            <div className='field-row'>
              <select value={form.partner_comm_kind} onChange={(e) => setForm({ ...form, partner_comm_kind: e.target.value })}>
                <option value='percent'>Percentage</option>
                <option value='fixed'>Fixed amount</option>
              </select>
              <input
                type='number'
                min='0'
                step={form.partner_comm_kind === 'fixed' ? '0.01' : '0.1'}
                value={form.partner_comm_value}
                onChange={(e) => setForm({ ...form, partner_comm_value: e.target.value })}
                placeholder={form.partner_comm_kind === 'fixed' ? formCurrency : '%'}
              />
            </div>
          </div>
          <div className='field-row'>
            <div className='field'>
              <label>Partner discount %</label>
              <input type='number' min='0' max='100' value={form.partner_terms.discount_percent} onChange={(e) => setForm({
                ...form,
                partner_terms: { ...form.partner_terms, discount_percent: e.target.value },
              })} />
            </div>
            <div className='field'>
              <label>Billing</label>
              <select value={form.partner_terms.billing} onChange={(e) => setForm({
                ...form,
                partner_terms: { ...form.partner_terms, billing: e.target.value },
              })}>
                <option value='customer_pays'>Customer pays</option>
                <option value='invoice_partner'>Invoice partner</option>
              </select>
            </div>
          </div>
        </>
      )
    }
    return (
      <>
        <p style={{ fontSize: 13, color: 'var(--ink-soft)', margin: '0 0 14px' }}>
          Enable commission for months 2, 3, and 4. Yearly plans use month 2 only.
        </p>
        {form.commission_tiers.map((tier, idx) => (
          <div key={tier.month} className='tier-row'>
            <label>
              <input
                type='checkbox'
                checked={tier.enabled}
                onChange={(e) => {
                  const tiers = [...form.commission_tiers]
                  tiers[idx] = { ...tier, enabled: e.target.checked }
                  setForm({ ...form, commission_tiers: tiers })
                }}
              />
              {' '}Month {tier.month}
            </label>
            <select
              value={tier.kind}
              disabled={!tier.enabled}
              onChange={(e) => {
                const tiers = [...form.commission_tiers]
                tiers[idx] = { ...tier, kind: e.target.value }
                setForm({ ...form, commission_tiers: tiers })
              }}
            >
              <option value='percent'>Percent</option>
              <option value='fixed'>Fixed</option>
            </select>
            <input
              type='number'
              min='0'
              disabled={!tier.enabled}
              step={tier.kind === 'fixed' ? '0.01' : '0.1'}
              value={tier.value}
              onChange={(e) => {
                const tiers = [...form.commission_tiers]
                tiers[idx] = { ...tier, value: e.target.value }
                setForm({ ...form, commission_tiers: tiers })
              }}
              placeholder={tier.kind === 'fixed' ? formCurrency : '%'}
            />
            <span style={{ fontSize: 12, color: 'var(--ink-soft)' }}>{tier.kind === 'fixed' ? formCurrency : '%'}</span>
          </div>
        ))}
      </>
    )
  }

  const renderEditorPayoutTab = () => (
    <>
      <div className='comm-options'>
        <label className={`comm-option ${form.payout.payout_method === 'bank' ? 'selected' : ''}`}>
          <input type='radio' name='paytype' checked={form.payout.payout_method === 'bank'} onChange={() => setForm({ ...form, payout: { ...form.payout, payout_method: 'bank' } })} />
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: 13.5 }}>Bank account</div>
            {form.payout.payout_method === 'bank' ? (
              <div style={{ marginTop: 10 }}>
                {['bank_holder_name', 'bank_name', 'bank_sort_code', 'bank_account_number', 'bank_address'].map((key) => (
                  <div key={key} className='field'>
                    <label style={{ fontSize: 11.5 }}>{key.replace(/_/g, ' ')}</label>
                    <input type='text' value={form.payout[key] || ''} onChange={(e) => setForm({ ...form, payout: { ...form.payout, [key]: e.target.value } })} />
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </label>
        <label className={`comm-option ${form.payout.payout_method === 'paypal' ? 'selected' : ''}`}>
          <input type='radio' name='paytype' checked={form.payout.payout_method === 'paypal'} onChange={() => setForm({ ...form, payout: { ...form.payout, payout_method: 'paypal' } })} />
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: 13.5 }}>PayPal</div>
            {form.payout.payout_method === 'paypal' ? (
              <div className='field' style={{ marginTop: 10 }}>
                <label style={{ fontSize: 11.5 }}>PayPal email</label>
                <input type='email' value={form.payout.paypal_email || ''} onChange={(e) => setForm({ ...form, payout: { ...form.payout, paypal_email: e.target.value } })} />
              </div>
            ) : null}
          </div>
        </label>
      </div>
    </>
  )

  const renderEditorInvoicesTab = () => (
    <>
      <h3 style={{ margin: '0 0 12px', fontSize: 13, textTransform: 'uppercase', color: 'var(--ink-soft)' }}>Hub invoices</h3>
      <div className='card' style={{ marginBottom: 20 }}>
        <table>
          <thead>
            <tr><th>Number</th><th>Total</th><th>Status</th><th /></tr>
          </thead>
          <tbody>
            {editorInvoices.length === 0 ? (
              <tr><td colSpan={4} className='empty-state'>No hub invoices.</td></tr>
            ) : editorInvoices.map((inv) => (
              <tr key={inv.id}>
                <td>{inv.number}</td>
                <td>{inv.total_display || money(inv.total_minor, inv.currency)}</td>
                <td>{statusBadge(inv.status)}</td>
                <td><button type='button' className='link-btn' onClick={() => openInvoiceDetail(inv.id)}>Open</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3 style={{ margin: '0 0 12px', fontSize: 13, textTransform: 'uppercase', color: 'var(--ink-soft)' }}>Payout invoices</h3>
      <div className='card'>
        <table>
          <thead>
            <tr><th>Number</th><th>Amount</th><th>Status</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {editorPayoutInvoices.length === 0 ? (
              <tr><td colSpan={4} className='empty-state'>No payout invoices.</td></tr>
            ) : editorPayoutInvoices.map((inv) => (
              <tr key={inv.id}>
                <td>{inv.invoice_number}</td>
                <td>{inv.amount_display || money(inv.amount_minor, inv.currency || 'GBP')}</td>
                <td>{statusBadge(inv.status)}</td>
                <td>
                  {inv.status === 'submitted' ? (
                    <div className='action-stack'>
                      <button type='button' className='mark-btn to-paid' disabled={busy} onClick={() => approvePay(inv.id)}>Approve</button>
                      <button type='button' className='mark-btn to-reject' disabled={busy} onClick={() => rejectPayoutInvoice(inv.id)}>Reject</button>
                    </div>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )

  const renderEditorView = () => (
    <div>
      <button type='button' className='back-link' onClick={() => setView('accounts')}>
        <IconBack /> Back to accounts
      </button>
      <header className='hub-header'>
        <div>
          <h1>{editId ? 'Edit account' : (isPartner ? 'New partner' : 'New salesman')}</h1>
          <p className='subtitle'>{isPartner ? 'Partner channel sales' : 'Salesman account'}</p>
        </div>
      </header>
      <div className='editor-tabs'>
        {['profile', 'promo', 'commission', 'payout', 'invoices'].map((t) => (
          <button key={t} type='button' className={editorTab === t ? 'active' : ''} onClick={() => setEditorTab(t)}>
            {t === 'promo' ? 'Promo & services' : t === 'payout' ? 'Bank/payout' : t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>
      <div className='editor-panel'>
        {formErr ? <p className='form-error'>{formErr}</p> : null}
        {editorTab === 'profile' ? renderEditorProfileTab() : null}
        {editorTab === 'promo' ? renderEditorPromoTab() : null}
        {editorTab === 'commission' ? renderEditorCommissionTab() : null}
        {editorTab === 'payout' ? renderEditorPayoutTab() : null}
        {editorTab === 'invoices' ? renderEditorInvoicesTab() : null}
        {editorTab !== 'invoices' ? (
          <div className='editor-foot'>
            <button type='button' className='btn btn-ghost' onClick={() => setView('accounts')}>Cancel</button>
            <button type='button' className='btn btn-primary' disabled={busy} onClick={saveForm}>Save</button>
          </div>
        ) : null}
      </div>
    </div>
  )

  const renderProfileView = () => {
    if (!profileRep || !profile) return <div className='empty-state'>Loading profile…</div>
    const stats = profile.stats || profile
    const wallet = stats.wallet || {}
    const payout = stats.payout || profileRep.payout || {}
    const invoices = stats.payout_invoices || []
    const commissions = stats.commissions || []
    const cur = profileRep.currency || stats.currency || 'GBP'
    const joined = (profileRep.created_at || '').slice(0, 10)

    return (
      <div>
        <button type='button' className='back-link' onClick={() => { setView('accounts'); setProfileRep(null); setProfile(null) }}>
          <IconBack /> Back to accounts
        </button>
        <div className='profile-top'>
          <div>
            <h2>{profileRep.name}</h2>
            <div className='profile-meta'>
              <span>{profileRep.email}</span>
              <span>{profileRep.mobile || '—'}</span>
              <span className='currency-badge'>{cur}</span>
              {profileRep.is_active
                ? <span className='badge badge-active'>Active</span>
                : <span className='badge badge-frozen'>Frozen</span>}
            </div>
          </div>
          <div className='actions'>
            <button type='button' className='icon-btn edit' onClick={() => openEdit(profileRep)}><IconEdit /></button>
            <button type='button' className='icon-btn reset' onClick={() => { setPwRep(profileRep); setPwValue(genPassword()) }}><IconReset /></button>
            <button type='button' className='icon-btn freeze' onClick={() => toggleFreeze(profileRep)}>
              {profileRep.is_active ? <IconFreeze /> : <IconUnfreeze />}
            </button>
            <button type='button' className='icon-btn delete' onClick={() => deleteRep(profileRep)}><IconDelete /></button>
          </div>
        </div>
        <div className='stat-grid'>
          <div className='stat-box'><div className='label'>Revenue</div><div className='value'>{money(wallet.revenue_minor, cur)}</div></div>
          <div className='stat-box'><div className='label'>Commission</div><div className='value'>{money(wallet.commission_minor, cur)}</div></div>
          <div className='stat-box paid'><div className='label'>Paid</div><div className='value'>{money(wallet.commission_paid_minor, cur)}</div></div>
          <div className='stat-box requested'><div className='label'>Awaiting approval</div><div className='value'>{money(wallet.commission_requested_minor, cur)}</div></div>
          <div className='stat-box pending'><div className='label'>Available</div><div className='value'>{money(wallet.commission_available_minor, cur)}</div></div>
        </div>
        <div className='profile-grid'>
          <div className='profile-card'>
            <h3>Payout details</h3>
            {payout.payout_method === 'paypal' ? (
              <>
                <div className='profile-row'><span className='k'>Method</span><span className='v'>PayPal</span></div>
                <div className='profile-row'><span className='k'>Email</span><span className='v'>{payout.paypal_email || '—'}</span></div>
              </>
            ) : (
              <>
                <div className='profile-row'><span className='k'>Holder</span><span className='v'>{payout.bank_holder_name || '—'}</span></div>
                <div className='profile-row'><span className='k'>Bank</span><span className='v'>{payout.bank_name || '—'}</span></div>
                <div className='profile-row'><span className='k'>Sort code</span><span className='v'>{payout.bank_sort_code || '—'}</span></div>
                <div className='profile-row'><span className='k'>Account</span><span className='v'>{payout.bank_account_number || '—'}</span></div>
              </>
            )}
            <h3 style={{ marginTop: 18 }}>Commission</h3>
            <div className='profile-row'><span className='k'>Summary</span><span className='v'>{profileRep.commission_summary || stats.commission_summary || '—'}</span></div>
            <div className='profile-row'><span className='k'>Promo</span><span className='v'>{profileRep.promo_code || '—'}</span></div>
            <div className='profile-row'><span className='k'>Joined</span><span className='v'>{joined || '—'}</span></div>
          </div>
          <div className='profile-card'>
            <h3>Payout invoices</h3>
            <div className='card' style={{ boxShadow: 'none', border: 'none' }}>
              <table>
                <thead><tr><th>Invoice</th><th>Amount</th><th>Status</th><th /></tr></thead>
                <tbody>
                  {invoices.length === 0 ? (
                    <tr><td colSpan={4} className='empty-state'>No payout invoices.</td></tr>
                  ) : invoices.map((inv) => (
                    <tr key={inv.id}>
                      <td>{inv.invoice_number}</td>
                      <td>{inv.amount_display || money(inv.amount_minor, cur)}</td>
                      <td>{statusBadge(inv.status)}</td>
                      <td>
                        {inv.status === 'submitted' ? (
                          <div className='action-stack'>
                            <button type='button' className='mark-btn to-paid' disabled={busy} onClick={() => approvePay(inv.id)}>Approve</button>
                            <button type='button' className='mark-btn to-reject' disabled={busy} onClick={() => rejectPayoutInvoice(inv.id)}>Reject</button>
                          </div>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <h3 style={{ marginTop: 18 }}>Commission ledger</h3>
            <div className='card' style={{ boxShadow: 'none', border: 'none' }}>
              <table>
                <thead><tr><th>Date</th><th>Customer</th><th>Amount</th><th>Status</th></tr></thead>
                <tbody>
                  {commissions.length === 0 ? (
                    <tr><td colSpan={4} className='empty-state'>No commission records.</td></tr>
                  ) : commissions.map((c) => (
                    <tr key={c.id}>
                      <td>{(c.created_at || '').slice(0, 10)}</td>
                      <td>{c.org_name || c.org_id}</td>
                      <td>{money(c.amount_minor, c.currency || cur)}</td>
                      <td>{statusBadge(c.status)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    )
  }

  const renderInvoiceDetailView = () => {
    if (!invoiceDetail) return <div className='empty-state'>Loading…</div>
    const inv = invoiceDetail
    const cur = inv.currency || 'GBP'
    const rep = invoiceDetailRep
    return (
      <div>
        <button type='button' className='back-link' onClick={() => { setView('invoices'); setInvoiceDetail(null) }}>
          <IconBack /> Back to invoices
        </button>
        <header className='hub-header'>
          <div>
            <h1>{inv.number}</h1>
            <p className='subtitle'>{rep?.name || '—'} · {inv.customer || '—'} · {statusBadge(inv.status)}</p>
          </div>
        </header>
        <div className='inv-detail-grid'>
          <div className='profile-card'>
            <h3>Summary</h3>
            <div className='profile-row'><span className='k'>Kind</span><span className='v'>{inv.kind}</span></div>
            <div className='profile-row'><span className='k'>Subtotal</span><span className='v'>{money(inv.subtotal_minor, cur)}</span></div>
            <div className='profile-row'><span className='k'>Discount</span><span className='v'>{inv.discount_percent}%</span></div>
            <div className='profile-row'><span className='k'>Tax</span><span className='v'>{inv.tax_percent}%</span></div>
            <div className='profile-row'><span className='k'>Total</span><span className='v'>{inv.total_display || money(inv.total_minor, cur)}</span></div>
            {inv.kind === 'commission' ? (
              <div className='profile-row'>
                <span className='k'>Commission</span>
                <span className='v'>{inv.commission_amount_display || money(inv.commission_amount_minor, cur)}</span>
              </div>
            ) : null}
          </div>
          <div className='profile-card'>
            <h3>Line items</h3>
            {(inv.items || []).map((it) => (
              <div key={it.id || it.description} className='profile-row'>
                <span className='k'>{it.description}</span>
                <span className='v'>{it.quantity} × {it.unit_price_display || money(it.unit_price_minor, cur)}</span>
              </div>
            ))}
          </div>
        </div>
        <div className='inv-actions'>
          {inv.status !== 'paid' && inv.status !== 'rejected' ? (
            <>
              <button type='button' className='btn btn-primary btn-sm' disabled={busy} onClick={() => hubInvoiceAction(inv.id, 'send')}>Send</button>
              <button type='button' className='btn btn-ghost btn-sm' disabled={busy} onClick={() => hubInvoiceAction(inv.id, 'remind')}>Remind</button>
              <button type='button' className='btn btn-ghost btn-sm' disabled={busy} onClick={() => hubInvoiceAction(inv.id, 'mark-paid')}>Mark paid</button>
              <button type='button' className='btn btn-danger btn-sm' disabled={busy} onClick={() => hubInvoiceAction(inv.id, 'reject', { reason: '' })}>Reject</button>
            </>
          ) : null}
          {inv.kind === 'commission' && !inv.commission_approved ? (
            <button type='button' className='btn btn-primary btn-sm' disabled={busy} onClick={() => hubInvoiceAction(inv.id, 'approve-commission', { approved: true })}>Approve commission</button>
          ) : null}
          {inv.kind === 'charge' && inv.status !== 'paid' ? (
            <>
              {['stripe', 'gocardless', 'airwallex', 'manual'].map((provider) => (
                <button
                  key={provider}
                  type='button'
                  className='btn btn-ghost btn-sm'
                  disabled={busy}
                  onClick={() => hubInvoiceAction(inv.id, 'collect', { provider })}
                >
                  Collect ({provider})
                </button>
              ))}
            </>
          ) : null}
        </div>
        {inv.payment_link ? (
          <p style={{ marginTop: 12, fontSize: 13 }}>
            Payment link: <a href={inv.payment_link} target='_blank' rel='noreferrer'>{inv.payment_link}</a>
          </p>
        ) : null}
      </div>
    )
  }

  const renderCreateInvoiceModal = () => (
    <div className={`modal-overlay ${showCreateInvoice ? 'active' : ''}`}>
      <div className='modal wide'>
        <div className='modal-head'>
          <h2>Create hub invoice</h2>
          <button type='button' className='modal-close' onClick={() => setShowCreateInvoice(false)}><IconClose /></button>
        </div>
        <div className='modal-body'>
          {createInvErr ? <p className='form-error'>{createInvErr}</p> : null}
          <div className='field-row'>
            <div className='field'>
              <label>Sales rep</label>
              <select value={createInvForm.sales_rep_id} onChange={(e) => setCreateInvForm({ ...createInvForm, sales_rep_id: e.target.value })}>
                <option value=''>Select…</option>
                {allReps.map((r) => (
                  <option key={r.id} value={r.id}>{r.name} ({r.kind})</option>
                ))}
              </select>
            </div>
            <div className='field'>
              <label>Kind</label>
              <select value={createInvForm.kind} onChange={(e) => setCreateInvForm({ ...createInvForm, kind: e.target.value })}>
                <option value='commission'>Commission</option>
                <option value='charge'>Charge</option>
              </select>
            </div>
          </div>
          <div className='field'>
            <label>Customer</label>
            <input type='text' value={createInvForm.customer} onChange={(e) => setCreateInvForm({ ...createInvForm, customer: e.target.value })} />
          </div>
          <div className='field'>
            <label>Line items</label>
            {createInvForm.items.map((it, idx) => (
              <div key={idx} className='line-item-row'>
                <div className='field'>
                  <select value={it.service_id} onChange={(e) => {
                    const items = [...createInvForm.items]
                    items[idx] = { ...it, service_id: e.target.value }
                    setCreateInvForm({ ...createInvForm, items })
                  }}>
                    {SERVICE_IDS.map((sid) => (
                      <option key={sid} value={sid}>{SERVICE_LABELS[sid]}</option>
                    ))}
                  </select>
                </div>
                <div className='field'>
                  <input type='text' placeholder='Description' value={it.description} onChange={(e) => {
                    const items = [...createInvForm.items]
                    items[idx] = { ...it, description: e.target.value }
                    setCreateInvForm({ ...createInvForm, items })
                  }} />
                </div>
                <div className='field'>
                  <input type='number' min='1' placeholder='Qty' value={it.quantity} onChange={(e) => {
                    const items = [...createInvForm.items]
                    items[idx] = { ...it, quantity: e.target.value }
                    setCreateInvForm({ ...createInvForm, items })
                  }} />
                </div>
                <div className='field'>
                  <input type='number' min='0' step='0.01' placeholder='Unit price' value={it.unit_price_major} onChange={(e) => {
                    const items = [...createInvForm.items]
                    items[idx] = { ...it, unit_price_major: e.target.value }
                    setCreateInvForm({ ...createInvForm, items })
                  }} />
                </div>
                <button type='button' className='btn btn-ghost btn-sm' onClick={() => {
                  const items = createInvForm.items.filter((_, i) => i !== idx)
                  setCreateInvForm({ ...createInvForm, items: items.length ? items : createInvForm.items })
                }}>×</button>
              </div>
            ))}
            <button type='button' className='btn btn-ghost btn-sm' onClick={() => setCreateInvForm({
              ...createInvForm,
              items: [...createInvForm.items, { service_id: 'wa_survey', description: '', quantity: '1', unit_price_major: '0' }],
            })}>Add line</button>
          </div>
          <div className='field-row'>
            <div className='field'>
              <label>Discount %</label>
              <input type='number' min='0' value={createInvForm.discount_percent} onChange={(e) => setCreateInvForm({ ...createInvForm, discount_percent: e.target.value })} />
            </div>
            <div className='field'>
              <label>Tax %</label>
              <input type='number' min='0' value={createInvForm.tax_percent} onChange={(e) => setCreateInvForm({ ...createInvForm, tax_percent: e.target.value })} />
            </div>
            {createInvForm.kind === 'commission' ? (
              <div className='field'>
                <label>Commission amount</label>
                <input type='number' min='0' step='0.01' value={createInvForm.commission_amount_major} onChange={(e) => setCreateInvForm({ ...createInvForm, commission_amount_major: e.target.value })} />
              </div>
            ) : null}
          </div>
        </div>
        <div className='modal-foot'>
          <button type='button' className='btn btn-ghost' onClick={() => setShowCreateInvoice(false)}>Cancel</button>
          <button type='button' className='btn btn-primary' disabled={busy} onClick={createHubInvoice}>Create</button>
        </div>
      </div>
    </div>
  )

  const renderPasswordModal = () => (
    <div className={`modal-overlay ${pwRep ? 'active' : ''}`}>
      <div className='modal' style={{ maxWidth: 380 }}>
        <div className='modal-head'>
          <h2>Reset password</h2>
          <button type='button' className='modal-close' onClick={() => setPwRep(null)}><IconClose /></button>
        </div>
        <div className='modal-body'>
          <p style={{ marginTop: 0, fontSize: 13.5, color: 'var(--ink-soft)' }}>
            Set a new temporary password for <strong>{pwRep?.name}</strong>.
          </p>
          <div className='field'>
            <label>New temporary password</label>
            <div className='pw-row'>
              <input type='text' value={pwValue} onChange={(e) => setPwValue(e.target.value)} />
              <button type='button' className='btn btn-ghost btn-sm' onClick={() => setPwValue(genPassword())}>Generate</button>
            </div>
          </div>
        </div>
        <div className='modal-foot'>
          <button type='button' className='btn btn-ghost' onClick={() => setPwRep(null)}>Cancel</button>
          <button type='button' className='btn btn-primary' disabled={busy || pwValue.length < 6} onClick={resetPassword}>Reset</button>
        </div>
      </div>
    </div>
  )

  return (
    <div className='sales-hub' onClick={() => menuRepId && setMenuRepId(null)}>
      {renderSubNav()}
      <div className='hub-body'>
        {view === 'accounts' ? renderAccountsView() : null}
        {view === 'invoices' ? renderInvoicesView() : null}
        {view === 'editor' ? renderEditorView() : null}
        {view === 'profile' ? renderProfileView() : null}
        {view === 'invoiceDetail' ? renderInvoiceDetailView() : null}
      </div>
      {renderPasswordModal()}
      {renderCreateInvoiceModal()}
      <div className={`toast ${toast ? 'show' : ''}`}>{toast}</div>
    </div>
  )
}
