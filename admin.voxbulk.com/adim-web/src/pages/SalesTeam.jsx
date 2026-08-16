import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { useLocation, useNavigate } from 'react-router-dom'
import { apiFetch, apiFetchBlob } from '../lib/api'
import { brandAssets } from '../lib/brand'
import './salesTeam.css'

/** Source: partner-sales-hub-main/src/lib/accounts.ts COMPANY */
const COMPANY = {
  name: 'Voxbulk Ltd',
  addressLines: ['Unit 12, Kingsway House', '103 Kingsway', 'London WC2B 6QX'],
  country: 'United Kingdom',
  companyNumber: '12345678',
  vatNumber: 'GB 123 4567 89',
  bank: {
    bankName: 'Barclays Bank UK PLC',
    beneficiary: 'Voxbulk Ltd',
    sortCode: '20-00-00',
    accountNumber: '12345678',
    iban: 'GB29 BARC 2000 0012 3456 78',
    country: 'United Kingdom',
  },
}

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
const SERVICE_IDS = ['core_package', 'ai_interview', 'wa_survey', 'customer_feedback', 'voxbulk_expo', 'smart_card']
const SERVICE_LABELS = {
  core_package: 'Core package (Starter / Growth)',
  ai_interview: 'AI Interview Screening',
  wa_survey: 'WA Survey / AI Call Survey',
  customer_feedback: 'Customer Feedback',
  voxbulk_expo: 'Voxbulk Expo',
  smart_card: 'Smart Card QR',
}
const COMMISSION_MODES = [
  { value: 'commission_only', label: 'Commission only' },
  { value: 'one_time_only', label: 'One-time bonus only' },
  { value: 'one_time_plus_commission', label: 'One-time bonus + commission' },
]
/** Exact SERVICES.options from partner-sales-hub-main/src/lib/accounts.ts */
const SERVICE_OPTIONS = {
  core_package: [
    { kind: 'percent_discount', label: 'Percentage discount', unit: '%', defaultValue: 20 },
    { kind: 'free_days', label: 'Free trial days', unit: 'days', defaultValue: 3 },
  ],
  ai_interview: [
    { kind: 'fixed_topup', label: 'Fixed top-up amount', unit: 'minor', defaultValue: 20 },
    { kind: 'percent_discount', label: 'Percentage discount', unit: '%', defaultValue: 20 },
  ],
  wa_survey: [
    { kind: 'percent_discount', label: 'Percentage discount', unit: '%', defaultValue: 20 },
    { kind: 'fixed_topup', label: 'Fixed top-up amount', unit: 'minor', defaultValue: 20 },
    { kind: 'free_days', label: 'Free trial days', unit: 'days', defaultValue: 14 },
  ],
  customer_feedback: [
    { kind: 'percent_discount', label: 'Percentage discount', unit: '%', defaultValue: 20 },
    { kind: 'free_days', label: 'Free days from 1st scan', unit: 'days', defaultValue: 15 },
  ],
  smart_card: [
    { kind: 'percent_discount', label: 'Percentage discount', unit: '%', defaultValue: 20 },
    { kind: 'fixed_topup', label: 'Fixed top-up amount', unit: 'minor', defaultValue: 20 },
    { kind: 'free_days', label: 'Free trial days', unit: 'days', defaultValue: 14 },
  ],
  voxbulk_expo: [
    { kind: 'free_package_days', label: 'Free package days', unit: 'days', defaultValue: 3 },
    { kind: 'percent_discount', label: 'Percentage discount', unit: '%', defaultValue: 20 },
  ],
}

function defaultBenefitValue(opt) {
  if (opt.defaultValue != null) return opt.defaultValue
  if (opt.unit === '%') return 20
  if (opt.unit === 'days') return 14
  if (opt.unit === 'minor') return 20
  return 0
}

/** Hub Switch — visual clone of partner-sales-hub Switch (radix). */
function HubSwitch({ checked, onCheckedChange, disabled }) {
  return (
    <button
      type='button'
      role='switch'
      aria-checked={Boolean(checked)}
      disabled={disabled}
      className={`hub-switch${checked ? ' on' : ''}`}
      onClick={() => onCheckedChange?.(!checked)}
    >
      <span className='hub-switch-thumb' />
    </button>
  )
}

/** Hub Checkbox — visual clone of partner-sales-hub Checkbox (radix). */
function HubCheckbox({ checked, onCheckedChange, disabled }) {
  return (
    <button
      type='button'
      role='checkbox'
      aria-checked={Boolean(checked)}
      disabled={disabled}
      className={`hub-checkbox${checked ? ' on' : ''}`}
      onClick={() => onCheckedChange?.(!checked)}
    >
      {checked ? (
        <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='3' className='hub-checkbox-check'>
          <path d='M5 12l5 5L20 7' />
        </svg>
      ) : null}
    </button>
  )
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
const IconSave = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z' /><path d='M17 21v-8H7v8' /><path d='M7 3v5h8' /></svg>
)
const IconSend = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='m22 2-7 20-4-9-9-4Z' /><path d='M22 2 11 13' /></svg>
)
const IconBell = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9' /><path d='M10.3 21a1.94 1.94 0 0 0 3.4 0' /></svg>
)
const IconCheck = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='M20 6 9 17l-5-5' /></svg>
)
const IconX = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='M18 6 6 18M6 6l12 12' /></svg>
)
const IconBadgeCheck = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'><path d='M3.85 8.62a4 4 0 0 1 4.78-4.77 4 4 0 0 1 6.74 0 4 4 0 0 1 4.78 4.78 4 4 0 0 1 0 6.74 4 4 0 0 1-4.77 4.78 4 4 0 0 1-6.75 0 4 4 0 0 1-4.78-4.77 4 4 0 0 1 0-6.76Z' /><path d='m9 12 2 2 4-4' /></svg>
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
    services[sid] = { enabled: false, kind: opts[0].kind, value: String(defaultBenefitValue(opts[0])) }
  })
  return {
    wallet_voucher: { enabled: true, amount_major: '20' },
    services,
    usage_limit: '',
    expires_at: '',
  }
}

function defaultCommissionTiers(pct = 15) {
  return [1, 2, 3, 4, 5, 6].map((month) => ({
    month,
    enabled: month === 2,
    kind: 'percent',
    value: String(pct),
  }))
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

/** Platform mailbox host for salesman SMTP/IMAP (aaPanel / domain mail). */
const SALESMAN_MAIL_HOST = 'voxbulk.com'

function emptyForm(isPartner) {
  return {
    name: '',
    email: '',
    password: genPassword(),
    assign_existing: false,
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
    commission_mode: 'commission_only',
    one_time_bonus_major: '0',
    mailbox_username: '',
    mailbox_password: '',
    email_signature: '',
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
  const tierByMonth = Object.fromEntries(
    (rep.commission_tiers || defaultCommissionTiers()).map((t) => [Number(t.month), t]),
  )
  const tiers = [1, 2, 3, 4, 5, 6].map((month) => {
    const t = tierByMonth[month] || { month, enabled: month === 2, kind: 'percent', value: 15 }
    return {
      month,
      enabled: Boolean(t.enabled),
      kind: t.kind === 'fixed' ? 'fixed' : 'percent',
      value: t.kind === 'fixed' ? String(Number(t.value || 0) / 100) : String(t.value ?? ''),
    }
  })
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
    commission_mode: rep.commission_mode || 'commission_only',
    one_time_bonus_major: rep.one_time_bonus_minor != null
      ? String(Number(rep.one_time_bonus_minor) / 100)
      : '0',
    mailbox_username: rep.smtp_username || '',
    mailbox_password: '',
    email_signature: rep.email_signature || '',
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
    const month2Enabled = form.commission_tiers.find((t) => t.month === 2)?.enabled ?? true
    return [1, 2, 3, 4, 5, 6].map((month) => {
      if (month === 2) {
        return {
          month: 2,
          enabled: month2Enabled,
          kind,
          value: kind === 'fixed' ? Math.round(val * 100) : val,
        }
      }
      return { month, enabled: false, kind: 'percent', value: 0 }
    })
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
  if (s === 'paid') return <span className='badge badge-paid'>paid</span>
  if (s === 'sent') return <span className='badge badge-sent'>sent</span>
  if (s === 'new') return <span className='badge badge-new'>new</span>
  if (s === 'rejected') return <span className='badge badge-rejected'>rejected</span>
  if (s === 'submitted') return <span className='badge badge-requested'>submitted</span>
  if (s === 'active') return <span className='badge badge-active'>active</span>
  if (s === 'frozen') return <span className='badge badge-frozen'>frozen</span>
  return <span className='badge badge-pending'>{s || '—'}</span>
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
  const [rowMenu, setRowMenu] = useState(null) // { id, top, left } — portaled like Radix
  const [toast, setToast] = useState('')

  const [editId, setEditId] = useState(null)
  const [form, setForm] = useState(() => emptyForm(false))
  const [formErr, setFormErr] = useState('')
  const [catalog, setCatalog] = useState({ packages: [], services: [] })

  const [pwRep, setPwRep] = useState(null)
  const [pwValue, setPwValue] = useState('')

  const [profileRep, setProfileRep] = useState(null)

  const [invoiceDetail, setInvoiceDetail] = useState(null)
  const [invoiceDetailRep, setInvoiceDetailRep] = useState(null)

  const [showCreateInvoice, setShowCreateInvoice] = useState(false)
  const [createInvForm, setCreateInvForm] = useState({
    sales_rep_id: '',
    kind: 'commission',
    customer: '',
    customer_email: '',
    discount_percent: '0',
    tax_percent: '0',
    commission_amount_major: '0',
  })
  const [createInvErr, setCreateInvErr] = useState('')

  const [editorInvoices, setEditorInvoices] = useState([])
  const [editorPayoutInvoices, setEditorPayoutInvoices] = useState([])
  const [editStats, setEditStats] = useState(null)
  const [editRepMeta, setEditRepMeta] = useState(null) // { is_active, ref_id, ... }

  const [testMailboxBusy, setTestMailboxBusy] = useState(false)
  const [testMailboxResult, setTestMailboxResult] = useState(null)

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
    setTestMailboxResult(null)
    setEditorTab('profile')
    setEditStats(null)
    setEditRepMeta({ is_active: true, ref_id: '' })
    setView('editor')
  }

  const openEdit = async (rep) => {
    setEditId(rep.id)
    setForm(repToForm(rep))
    setFormErr('')
    setTestMailboxResult(null)
    setEditorTab('profile')
    setEditRepMeta(rep)
    setProfileRep(rep)
    setView('editor')
    try {
      const [hub, payout, dash] = await Promise.all([
        apiFetch(`/admin/sales-reps/hub-invoices?rep_id=${rep.id}`),
        apiFetch(`/admin/sales-reps/payout-invoices?rep_id=${rep.id}`),
        apiFetch(`/admin/sales-reps/${rep.id}/dashboard`).catch(() => null),
      ])
      setEditorInvoices(hub?.items || [])
      setEditorPayoutInvoices(payout?.items || [])
      setEditStats(dash)
      if (dash?.rep) {
        setEditRepMeta(dash.rep)
        setForm((prev) => ({
          ...prev,
          mailbox_username: dash.rep.smtp_username || prev.mailbox_username,
          email_signature: dash.rep.email_signature ?? prev.email_signature,
        }))
      }
    } catch {
      setEditorInvoices([])
      setEditorPayoutInvoices([])
      setEditStats(null)
    }
  }

  /** Source: View profile → same account page as Edit (accounts.$id) */
  const openProfile = (rep) => openEdit(rep)

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
      assign_existing: Boolean(form.assign_existing) && !editId,
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
      commission_mode: form.commission_mode,
      one_time_bonus_minor: Math.round(parseFloat(form.one_time_bonus_major || '0') * 100),
    }
    if (!isPartner) {
      const mailboxUser = String(form.mailbox_username || form.email || '').trim()
      const mailboxPassword = String(form.mailbox_password || '').trim()
      if (mailboxUser) {
        payload.smtp_host = SALESMAN_MAIL_HOST
        payload.smtp_port = 587
        payload.smtp_use_tls = true
        payload.smtp_use_ssl = false
        payload.smtp_username = mailboxUser
        payload.imap_host = SALESMAN_MAIL_HOST
        payload.imap_port = 993
        payload.imap_use_ssl = true
        payload.imap_use_tls = false
        payload.imap_username = mailboxUser
        payload.email_signature = String(form.email_signature || '').trim()
        if (mailboxPassword) {
          payload.smtp_password = mailboxPassword
          payload.imap_password = mailboxPassword
        } else if (!editId || !(editRepMeta?.has_smtp && editRepMeta?.has_imap)) {
          setFormErr('Mailbox password is required to turn SMTP/IMAP on for this salesman.')
          setBusy(false)
          return
        }
      } else if (editId) {
        payload.email_signature = String(form.email_signature || '').trim()
      }
    }
    try {
      if (editId) {
        const patch = { ...payload }
        delete patch.email
        delete patch.password
        delete patch.kind
        const res = await apiFetch(`/admin/sales-reps/${editId}`, { method: 'PATCH', body: JSON.stringify(patch) })
        const saved = res?.rep
        if (saved) {
          setEditRepMeta(saved)
          setForm((prev) => ({
            ...prev,
            mailbox_username: saved.smtp_username || prev.mailbox_username,
            mailbox_password: '',
            email_signature: saved.email_signature || '',
          }))
          const mailOk = saved.has_smtp && saved.has_imap
          showToast(mailOk ? 'Saved — SMTP and IMAP ready' : 'Saved — mailbox still incomplete (add mailbox password)')
        } else {
          showToast('Saved')
        }
        await loadReps()
      } else {
        if (!form.email) {
          setFormErr('Email is required.')
          setBusy(false)
          return
        }
        if (!form.assign_existing && String(form.password || '').length < 6) {
          setFormErr('Password must be at least 6 characters.')
          setBusy(false)
          return
        }
        if (form.assign_existing && form.password && String(form.password).length < 6) {
          setFormErr('Optional new password must be at least 6 characters.')
          setBusy(false)
          return
        }
        const res = await apiFetch('/admin/sales-reps', { method: 'POST', body: JSON.stringify(payload) })
        const saved = res?.rep
        const mailOk = saved?.has_smtp && saved?.has_imap
        showToast(
          form.assign_existing
            ? (mailOk ? 'Assigned — mailbox ready' : 'Assigned existing user')
            : (mailOk ? 'Created — mailbox ready' : 'Created'),
        )
        setView('accounts')
        await loadReps()
      }
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
        setView('accounts')
      }
      await loadReps()
    } catch (e) {
      showToast(e?.message || 'Delete failed')
    } finally {
      setBusy(false)
    }
  }

  const testMailboxConnection = async () => {
    const username = String(form.mailbox_username || form.email || '').trim()
    const password = String(form.mailbox_password || '').trim()
    setTestMailboxBusy(true)
    setTestMailboxResult(null)
    try {
      const res = await apiFetch(`/admin/sales-reps/${editId || 'test'}/test-mailbox`, {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      })
      setTestMailboxResult(res)
    } catch (e) {
      setTestMailboxResult({
        ok: false,
        smtp_ok: false,
        imap_ok: false,
        message: e?.message || 'Test failed',
      })
    } finally {
      setTestMailboxBusy(false)
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

  const downloadHubInvoicePdf = async (invoiceId) => {
    try {
      const blob = await apiFetchBlob(`/admin/sales-reps/hub-invoices/${encodeURIComponent(invoiceId)}/pdf`)
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank', 'noopener,noreferrer')
      setTimeout(() => URL.revokeObjectURL(url), 60000)
    } catch (e) {
      showToast(e?.message || 'PDF download failed')
    }
  }

  const createHubInvoice = async (options = {}) => {
    const { send_email: sendEmail, downloadPdf } = options
    setBusy(true)
    setCreateInvErr('')
    const rep = allReps.find((r) => r.id === createInvForm.sales_rep_id)
    const cur = rep?.currency || 'GBP'
    const unitPriceMinor = Math.round(parseFloat(createInvForm.commission_amount_major || '0') * 100)
    const items = [{
      service_id: null,
      description: 'Sales commission',
      quantity: 1,
      unit_price_minor: unitPriceMinor,
    }]
    if (!createInvForm.sales_rep_id) {
      setCreateInvErr('Select a salesman/partner.')
      setBusy(false)
      return
    }
    if (!unitPriceMinor) {
      setCreateInvErr('Enter a sales commission amount.')
      setBusy(false)
      return
    }
    try {
      const res = await apiFetch('/admin/sales-reps/hub-invoices', {
        method: 'POST',
        body: JSON.stringify({
          sales_rep_id: createInvForm.sales_rep_id,
          kind: createInvForm.kind,
          customer: createInvForm.customer,
          customer_email: createInvForm.customer_email || null,
          currency: cur,
          discount_percent: parseFloat(createInvForm.discount_percent || '0'),
          tax_percent: parseFloat(createInvForm.tax_percent || '0'),
          commission_amount_minor: unitPriceMinor,
          send_email: Boolean(sendEmail),
          items,
        }),
      })
      showToast(sendEmail ? 'Invoice created and sent' : 'Invoice created')
      setShowCreateInvoice(false)
      await loadHubInvoices()
      await loadReps()
      if (downloadPdf && res?.invoice?.id) {
        await downloadHubInvoicePdf(res.invoice.id)
      }
    } catch (e) {
      setCreateInvErr(e?.message || 'Create failed')
    } finally {
      setBusy(false)
    }
  }

  const packageForService = (serviceId) => catalog.packages.find((p) => p.service_id === serviceId)

  const renderSubNav = () => {
    const accountsActive = view === 'accounts' || view === 'editor'
    const invoicesActive = view === 'invoices' || view === 'invoiceDetail'
    return (
      <div className='hub-topnav'>
        <div className='hub-topnav-inner'>
          <button
            type='button'
            className={accountsActive ? 'active' : ''}
            onClick={() => { setView('accounts'); setProfileRep(null) }}
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
    const leads = Number(k.leads ?? 0)
    const paying = Number(k.paying_customers ?? 0)
    const conversion = leads ? Math.round((paying / leads) * 100) : 0
    const cards = [
      { label: 'Accounts', value: k.accounts ?? allReps.length, hint: `${salesmen} salesmen · ${partners} partners`, icon: <IconUsers /> },
      { label: 'Leads', value: leads, hint: 'all sources', icon: <IconTarget /> },
      { label: 'Paying customers', value: paying, hint: `${conversion}% conversion`, icon: <IconTrend />, tone: 'positive' },
      { label: 'Revenue', value: money(k.revenue_minor, cur), hint: 'lifetime, base currency', icon: <IconWallet /> },
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

  const closeRowMenu = () => setRowMenu(null)

  const openRowMenu = (e, rep) => {
    e.stopPropagation()
    if (rowMenu?.id === rep.id) {
      setRowMenu(null)
      return
    }
    const rect = e.currentTarget.getBoundingClientRect()
    const panelH = 220
    const spaceBelow = window.innerHeight - rect.bottom
    const top = spaceBelow < panelH ? Math.max(8, rect.top - panelH) : rect.bottom + 4
    const left = Math.min(window.innerWidth - 196, Math.max(8, rect.right - 180))
    setRowMenu({ id: rep.id, top, left, rep })
  }

  const renderRowMenuPortal = () => {
    if (!rowMenu) return null
    const rep = rowMenu.rep
    return createPortal(
      <>
        <div className='row-menu-backdrop' onClick={closeRowMenu} aria-hidden='true' />
        <div
          className='row-menu-panel row-menu-portal'
          role='menu'
          style={{ top: rowMenu.top, left: rowMenu.left }}
          onClick={(e) => e.stopPropagation()}
        >
          <button type='button' onClick={() => { closeRowMenu(); openProfile(rep) }}>
            <IconProfile /> View profile
          </button>
          <button type='button' onClick={() => { closeRowMenu(); openEdit(rep) }}>
            <IconEdit /> Edit
          </button>
          <button type='button' onClick={() => { closeRowMenu(); toggleFreeze(rep) }}>
            {rep.is_active ? <><IconFreeze /> Freeze</> : <><IconUnfreeze /> Unfreeze</>}
          </button>
          <button type='button' onClick={() => { closeRowMenu(); setPwRep(rep); setPwValue(genPassword()) }}>
            <IconReset /> Reset password
          </button>
          <div className='row-menu-sep' />
          <button type='button' className='danger' onClick={() => { closeRowMenu(); deleteRep(rep) }}>
            <IconDelete /> Delete
          </button>
        </div>
      </>,
      document.body,
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
      <section className='accounts-main' style={{ marginTop: 24 }}>
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
            <div className='empty-state' style={{ marginTop: 16 }}>No accounts yet.</div>
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
                    <th>Mail</th>
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
                      <tr key={rep.id}>
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
                          {rep.kind === 'partner_channel' ? (
                            <span className='muted'>—</span>
                          ) : (
                            <span className={rep.has_smtp && rep.has_imap ? 'tone-positive' : 'tone-warning'} style={{ fontSize: 12, fontWeight: 600 }}>
                              {rep.has_smtp && rep.has_imap ? 'SMTP/IMAP ready' : 'SMTP/IMAP off'}
                            </span>
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
                        <td>{statusBadge(rep.is_active ? 'active' : 'frozen')}</td>
                        <td>
                          <div className='row-menu'>
                            <button
                              type='button'
                              className={`row-menu-trigger${rowMenu?.id === rep.id ? ' open' : ''}`}
                              aria-label='Actions'
                              onClick={(e) => openRowMenu(e, rep)}
                            >
                              <IconMore />
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
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
                customer_email: '',
                discount_percent: '0',
                tax_percent: '0',
                commission_amount_major: '0',
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
              {(key === 'new' || key === 'sent') ? (
                <p className='hint'>{hubInvoices.filter((i) => i.status === key).length} invoices</p>
              ) : null}
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
                <tr><td colSpan={9} className='empty-cell'>No invoices match this filter.</td></tr>
              ) : filteredInv.map((inv) => {
                const owner = allReps.find((r) => r.id === inv.sales_rep_id) || null
                return (
                <tr key={inv.id}>
                  <td className='mono'>
                    <button type='button' className='link-btn' style={{ fontFamily: 'inherit' }} onClick={() => openInvoiceDetail(inv.id)}>
                      {inv.number}
                    </button>
                  </td>
                  <td>
                    {owner ? (
                      <button type='button' className='link-btn' onClick={() => openProfile(owner)}>
                        <span className='mono'>#{owner.ref_id || '—'}</span>{' '}
                        {owner.company_name || owner.name}
                      </button>
                    ) : (inv.rep_name || '—')}
                  </td>
                  <td>{inv.customer || '—'}</td>
                  <td style={{ textTransform: 'capitalize' }}>{inv.kind}</td>
                  <td>{(inv.issued_at || inv.created_at || '').slice(0, 10) || '—'}</td>
                  <td>{(inv.due_at || '').slice(0, 10) || '—'}</td>
                  <td className='tabular'>{inv.total_display || money(inv.total_minor, inv.currency)}</td>
                  <td className='tabular'>
                    {inv.commission_amount_display || money(inv.commission_amount_minor, inv.currency) || '—'}
                  </td>
                  <td>{statusBadge(inv.status)}</td>
                </tr>
              )})}
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
      <div className='field'>
        <label>Email</label>
        <div className='pw-row'>
          <input
            type='email'
            value={form.email}
            onChange={(e) => {
              const email = e.target.value
              const next = { ...form, email }
              if (!isPartner && !editId && (!form.mailbox_username || form.mailbox_username === form.email)) {
                next.mailbox_username = email
              }
              setForm(next)
            }}
            disabled={Boolean(editId)}
          />
          {!editId ? (
            <button
              type='button'
              className='btn btn-ghost btn-sm'
              onClick={async () => {
                const email = String(form.email || '').trim().toLowerCase()
                if (!email.includes('@')) {
                  setFormErr('Enter a registered user email first.')
                  return
                }
                try {
                  const res = await apiFetch(`/admin/sales-reps/lookup-user?email=${encodeURIComponent(email)}`)
                  if (!res?.found) {
                    setFormErr('No registered user with that email.')
                    return
                  }
                  if (res.user?.already_sales_rep) {
                    setFormErr(`That user is already a ${res.user.sales_rep_kind || 'sales'} account.`)
                    return
                  }
                  setFormErr('')
                  setForm((prev) => ({
                    ...prev,
                    assign_existing: true,
                    email: res.user.email || email,
                    name: prev.name || res.user.suggested_name || '',
                    password: '',
                  }))
                  showToast(`Found ${res.user.email} — assign mode on`)
                } catch (e) {
                  setFormErr(e?.message || 'Lookup failed')
                }
              }}
            >
              Lookup user
            </button>
          ) : null}
        </div>
        {!editId ? (
          <label className='switch-row' style={{ marginTop: 10 }}>
            <input
              type='checkbox'
              checked={Boolean(form.assign_existing)}
              onChange={(e) => setForm({
                ...form,
                assign_existing: e.target.checked,
                password: e.target.checked ? '' : (form.password || genPassword()),
              })}
            />
            <span className='switch-label'>Assign existing registered user (keep their password unless you set a new one)</span>
          </label>
        ) : null}
      </div>
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
    <div className='card-body'>
      <div className='promo-meta-grid'>
        <div className='field'>
          <label>Code</label>
          <input
            type='text'
            value={form.promo_code}
            placeholder='e.g. UK4F2A'
            onChange={(e) => setForm({ ...form, promo_code: e.target.value.toUpperCase() })}
            style={{ textTransform: 'uppercase' }}
          />
        </div>
        <div className='field'>
          <label>Usage limit (blank = unlimited)</label>
          <input
            type='number'
            min='1'
            value={form.promo_benefits.usage_limit}
            onChange={(e) => setForm({
              ...form,
              promo_benefits: { ...form.promo_benefits, usage_limit: e.target.value },
            })}
          />
        </div>
        <div className='field'>
          <label>Expires</label>
          <input
            type='date'
            value={form.promo_benefits.expires_at}
            onChange={(e) => setForm({
              ...form,
              promo_benefits: { ...form.promo_benefits, expires_at: e.target.value },
            })}
          />
        </div>
      </div>

      <div className='field-row' style={{ marginTop: 8, marginBottom: 16, padding: 12, border: '1px solid var(--border, #e5e7eb)', borderRadius: 8 }}>
        <div className='field' style={{ flex: 1 }}>
          <div className='switch-row'>
            <HubSwitch
              checked={Boolean(form.promo_benefits.wallet_voucher?.enabled)}
              onCheckedChange={(v) => setForm({
                ...form,
                promo_benefits: {
                  ...form.promo_benefits,
                  wallet_voucher: {
                    ...form.promo_benefits.wallet_voucher,
                    enabled: v,
                    amount_major: form.promo_benefits.wallet_voucher?.amount_major || '20',
                  },
                },
              })}
            />
            <span className='switch-label'>Customer signup wallet credit</span>
          </div>
          <p className='muted' style={{ marginTop: 6, fontSize: 12 }}>
            Credits the <strong>customer’s</strong> org wallet after they sign up with this promo — not the salesman’s commission.
            Turn off to remove. Change the amount to control the welcome credit (default £20).
          </p>
        </div>
        {form.promo_benefits.wallet_voucher?.enabled ? (
          <div className='field'>
            <label>Credit amount ({currencySymbol(formCurrency)})</label>
            <input
              type='number'
              min='0'
              step='0.01'
              value={form.promo_benefits.wallet_voucher.amount_major}
              onChange={(e) => setForm({
                ...form,
                promo_benefits: {
                  ...form.promo_benefits,
                  wallet_voucher: {
                    ...form.promo_benefits.wallet_voucher,
                    amount_major: e.target.value,
                  },
                },
              })}
            />
          </div>
        ) : null}
      </div>

      <p className='muted' style={{ marginBottom: 8, fontSize: 12 }}>
        Per-service promo benefits (discounts / free days) for customers using this code:
      </p>
      <div className='promo-services-grid'>
        {SERVICE_IDS.map((sid) => {
          const svc = form.promo_benefits.services[sid]
          const pkg = packageForService(sid)
          const opts = SERVICE_OPTIONS[sid]
          const selectedOpt = opts.find((o) => o.kind === svc.kind) || opts[0]
          return (
            <div key={sid} className='service-row'>
              <label className='service-row-head'>
                <HubCheckbox
                  checked={svc.enabled}
                  onCheckedChange={(v) => setForm({
                    ...form,
                    promo_benefits: {
                      ...form.promo_benefits,
                      services: {
                        ...form.promo_benefits.services,
                        [sid]: { ...svc, enabled: v },
                      },
                    },
                  })}
                />
                <span className='service-name'>{SERVICE_LABELS[sid]}</span>
                <span className='service-price'>
                  {pkg?.list_price_display ? `list ${pkg.list_price_display}` : 'list —'}
                </span>
              </label>
              {svc.enabled ? (
                <div className='service-fields'>
                  <select
                    value={svc.kind}
                    onChange={(e) => {
                      const nextKind = e.target.value
                      const nextOpt = opts.find((o) => o.kind === nextKind) || opts[0]
                      setForm({
                        ...form,
                        promo_benefits: {
                          ...form.promo_benefits,
                          services: {
                            ...form.promo_benefits.services,
                            [sid]: { ...svc, kind: nextKind, value: String(defaultBenefitValue(nextOpt)) },
                          },
                        },
                      })
                    }}
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
                  />
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
    </div>
  )

  const renderCommissionModeFields = () => (
    <div className='field-row' style={{ marginTop: 16 }}>
      <div className='field'>
        <label>Commission mode</label>
        <select
          value={form.commission_mode}
          onChange={(e) => setForm({ ...form, commission_mode: e.target.value })}
        >
          {COMMISSION_MODES.map((m) => (
            <option key={m.value} value={m.value}>{m.label}</option>
          ))}
        </select>
      </div>
      {form.commission_mode !== 'commission_only' ? (
        <div className='field'>
          <label>One-time bonus ({currencySymbol(formCurrency)}) — salesman payout</label>
          <input
            type='number'
            min='0'
            step='0.01'
            value={form.one_time_bonus_major}
            onChange={(e) => setForm({ ...form, one_time_bonus_major: e.target.value })}
          />
          <p className='muted' style={{ marginTop: 4, fontSize: 12 }}>
            Accrues to the salesman wallet once when a linked customer’s first qualifying subscription invoice is paid.
            Set to 0 or switch to “Commission only” to remove.
          </p>
        </div>
      ) : null}
    </div>
  )

  const renderEditorCommissionTab = () => {
    if (isPartner) {
      const enabled = form.commission_tiers.find((t) => t.month === 2)?.enabled ?? false
      return (
        <div className='card-body'>
          <div className='commission-partner-grid'>
            <div className='switch-row'>
              <HubSwitch
                checked={enabled}
                onCheckedChange={(v) => {
                  const tiers = form.commission_tiers.map((t) => (
                    t.month === 2 ? { ...t, enabled: v } : { ...t, enabled: false }
                  ))
                  setForm({ ...form, commission_tiers: tiers })
                }}
              />
              <span className='switch-label'>Next payment commission</span>
            </div>
            <select
              value={form.partner_comm_kind}
              onChange={(e) => setForm({ ...form, partner_comm_kind: e.target.value })}
            >
              <option value='percent'>Percentage</option>
              <option value='fixed'>Fixed amount</option>
            </select>
            <input
              type='number'
              min='0'
              step={form.partner_comm_kind === 'fixed' ? '0.01' : '0.1'}
              value={form.partner_comm_value}
              onChange={(e) => setForm({ ...form, partner_comm_value: e.target.value })}
            />
          </div>
          {renderCommissionModeFields()}
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
        </div>
      )
    }
    return (
      <div className='card-body'>
        {form.commission_tiers.map((tier, idx) => (
          <div key={tier.month} className='tier-row'>
            <div className='switch-row'>
              <HubSwitch
                checked={tier.enabled}
                onCheckedChange={(v) => {
                  const tiers = [...form.commission_tiers]
                  tiers[idx] = { ...tier, enabled: v }
                  setForm({ ...form, commission_tiers: tiers })
                }}
              />
              <span className='switch-label'>Month {tier.month}</span>
            </div>
            <select
              value={tier.kind}
              onChange={(e) => {
                const tiers = [...form.commission_tiers]
                tiers[idx] = { ...tier, kind: e.target.value }
                setForm({ ...form, commission_tiers: tiers })
              }}
            >
              <option value='percent'>Percentage</option>
              <option value='fixed'>Fixed amount</option>
            </select>
            <input
              type='number'
              min='0'
              step={tier.kind === 'fixed' ? '0.01' : '0.1'}
              value={tier.value}
              onChange={(e) => {
                const tiers = [...form.commission_tiers]
                tiers[idx] = { ...tier, value: e.target.value }
                setForm({ ...form, commission_tiers: tiers })
              }}
            />
          </div>
        ))}
        {renderCommissionModeFields()}
      </div>
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
    <section className='hub-card'>
      <div className='hub-card-head-row'>
        <div>
          <h3>Invoices</h3>
          <p className='muted'>Commission and charge invoices for this account.</p>
        </div>
        <button
          type='button'
          className='btn btn-primary btn-sm'
          onClick={() => {
            setCreateInvForm({
              sales_rep_id: editId || '',
              kind: 'commission',
              customer: form.name || '',
              customer_email: form.email || '',
              discount_percent: '0',
              tax_percent: '0',
              commission_amount_major: '0',
            })
            setCreateInvErr('')
            setShowCreateInvoice(true)
          }}
        >
          <IconPlus /> Create invoice
        </button>
      </div>
      <div className='table-wrap' style={{ marginTop: 12 }}>
        <table>
          <thead>
            <tr>
              <th>Number</th>
              <th>Type</th>
              <th>Bill to</th>
              <th>Issued</th>
              <th className='tabular'>Total</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {editorInvoices.length === 0 ? (
              <tr><td colSpan={6} className='empty-cell'>No invoices yet.</td></tr>
            ) : editorInvoices.map((inv) => (
              <tr key={inv.id}>
                <td className='mono'>
                  <button type='button' className='link-btn' onClick={() => openInvoiceDetail(inv.id)}>{inv.number}</button>
                </td>
                <td style={{ textTransform: 'capitalize' }}>{inv.kind}</td>
                <td>{inv.customer || '—'}</td>
                <td>{(inv.issued_at || inv.created_at || '').slice(0, 10) || '—'}</td>
                <td className='tabular'>{inv.total_display || money(inv.total_minor, inv.currency)}</td>
                <td>{statusBadge(inv.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editorPayoutInvoices.length > 0 ? (
        <div style={{ marginTop: 20 }}>
          <h3 style={{ margin: '0 0 8px', fontSize: 13 }}>Payout requests</h3>
          <div className='table-wrap'>
            <table>
              <thead>
                <tr><th>Number</th><th>Amount</th><th>Status</th><th>Actions</th></tr>
              </thead>
              <tbody>
                {editorPayoutInvoices.map((inv) => (
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
        </div>
      ) : null}
    </section>
  )

  const renderEditorView = () => {
    const label = isPartner ? 'Partner' : 'Salesman'
    const status = editRepMeta?.is_active === false ? 'frozen' : 'active'
    const refId = editRepMeta?.ref_id || (editId ? String(editId).slice(0, 4) : '—')
    const wallet = editStats?.stats?.wallet || editStats?.wallet || {}
    const cur = formCurrency
    const earned = Number(wallet.commission_minor || 0)
    const paid = Number(wallet.commission_paid_minor || 0)
    const outstanding = Math.max(0, earned - paid)
    return (
      <>
        <header className='hub-header'>
          <div>
            <h1 className='title-row'>
              <span className='mono title-ref'>#{refId}</span>
              <span>{form.name || `New ${label.toLowerCase()}`}</span>
              <span className='badge badge-mono'>{label}</span>
              {statusBadge(status)}
            </h1>
            <p className='subtitle'>{form.company_name || form.email || '—'}</p>
          </div>
          <div className='hub-header-actions'>
            <button type='button' className='btn btn-ghost' onClick={() => setView('accounts')}>
              <IconBack /> Back
            </button>
            {editorTab !== 'invoices' ? (
              <button type='button' className='btn btn-primary' disabled={busy} onClick={saveForm}>
                <IconSave /> Save changes
              </button>
            ) : null}
          </div>
        </header>
        {editId ? (
          <div className='kpi-grid kpi-5'>
            <div className='kpi-card'><div className='kpi-card-top'><span className='label'>Leads</span></div><div className='value'>{editStats?.stats?.leads ?? 0}</div></div>
            <div className='kpi-card'><div className='kpi-card-top'><span className='label'>Paying customers</span></div><div className='value tone-positive'>{editStats?.stats?.paying_customers ?? editRepMeta?.customers ?? 0}</div></div>
            <div className='kpi-card'><div className='kpi-card-top'><span className='label'>Revenue</span></div><div className='value'>{money(wallet.revenue_minor || editRepMeta?.revenue_minor, cur)}</div></div>
            <div className='kpi-card'><div className='kpi-card-top'><span className='label'>Commission earned</span></div><div className='value'>{money(earned, cur)}</div></div>
            <div className='kpi-card'><div className='kpi-card-top'><span className='label'>Commission outstanding</span></div><div className='value tone-warning'>{money(outstanding, cur)}</div></div>
          </div>
        ) : null}
        <div className='editor-tabs' style={{ marginTop: 24 }}>
          {[
            ['profile', 'Profile'],
            ['promo', 'Promo & services'],
            ['commission', 'Commission'],
            ['payout', 'Bank / payout'],
            ['invoices', `Invoices (${editorInvoices.length})`],
          ].map(([t, labelText]) => (
            <button key={t} type='button' className={editorTab === t ? 'active' : ''} onClick={() => setEditorTab(t)}>
              {labelText}
            </button>
          ))}
        </div>
        <div className={editorTab === 'profile' ? 'editor-grid' : undefined} style={{ marginTop: 16 }}>
          {formErr ? <p className='form-error'>{formErr}</p> : null}
          {editorTab === 'profile' ? (
            <>
              <section className='hub-card'>
                <h3>Account details</h3>
                {renderEditorProfileTab()}
              </section>
              <section className='hub-card'>
                <h3>Access</h3>
                {!editId ? (
                  <div className='field'>
                    <label>
                      {form.assign_existing ? 'New password (optional)' : 'Temporary password'}{' '}
                      <span className='hint'>{form.assign_existing ? 'leave blank to keep theirs' : 'shared at first login'}</span>
                    </label>
                    <div className='pw-row'>
                      <input type='text' value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
                      {!form.assign_existing ? (
                        <button type='button' className='btn btn-ghost btn-sm' onClick={() => setForm({ ...form, password: genPassword() })}>Generate</button>
                      ) : null}
                    </div>
                  </div>
                ) : (
                  <p className='muted'>Use the ⋯ menu on the accounts table to reset password.</p>
                )}
              </section>
              {!isPartner ? (
                <section className='hub-card' style={{ gridColumn: '1 / -1' }}>
                  <h3>Mail account</h3>
                  <p className='card-hint'>
                    Mailbox on <strong>{SALESMAN_MAIL_HOST}</strong> (SMTP 587 / IMAP 993). Enter the mailbox username and password so the salesman can send and receive from Sales.
                    {' '}Password is stored encrypted — the field stays blank after save even when credentials are present.
                  </p>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
                    <span className={editRepMeta?.has_smtp ? 'tone-positive' : 'tone-warning'} style={{ fontSize: 12, fontWeight: 600 }}>
                      SMTP {editRepMeta?.has_smtp ? 'ready' : 'off'}
                    </span>
                    <span className={editRepMeta?.has_imap ? 'tone-positive' : 'tone-warning'} style={{ fontSize: 12, fontWeight: 600 }}>
                      IMAP {editRepMeta?.has_imap ? 'ready' : 'off'}
                    </span>
                    {editId && editRepMeta?.smtp_username ? (
                      <span className='muted' style={{ fontSize: 12 }}>Saved as {editRepMeta.smtp_username}</span>
                    ) : null}
                  </div>
                  <div className='field-row'>
                    <div className='field'>
                      <label>Username (email)</label>
                      <input
                        type='email'
                        value={form.mailbox_username}
                        onChange={(e) => setForm({ ...form, mailbox_username: e.target.value })}
                        placeholder={form.email || 'salesman1@voxbulk.com'}
                      />
                    </div>
                    <div className='field'>
                      <label>
                        Mailbox password{' '}
                        {editId && editRepMeta?.has_smtp && editRepMeta?.has_imap ? (
                          <span className='hint'>leave blank to keep saved password</span>
                        ) : (
                          <span className='hint'>required to enable SMTP/IMAP</span>
                        )}
                      </label>
                      <input
                        type='password'
                        value={form.mailbox_password}
                        onChange={(e) => setForm({ ...form, mailbox_password: e.target.value })}
                        placeholder={editId && editRepMeta?.has_smtp ? 'Only if changing' : 'Mailbox password'}
                        autoComplete='new-password'
                      />
                    </div>
                  </div>
                  <div className='field'>
                    <label>Email signature</label>
                    <textarea
                      rows={3}
                      value={form.email_signature}
                      onChange={(e) => setForm({ ...form, email_signature: e.target.value })}
                      placeholder={'Best regards,\nJohn Smith\nVoxBulk Sales'}
                    />
                  </div>
                  <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginTop: 8 }}>
                    <button
                      type='button'
                      className='btn btn-ghost'
                      disabled={testMailboxBusy || !(form.mailbox_username || form.email) || (!form.mailbox_password && !editId)}
                      onClick={testMailboxConnection}
                    >
                      {testMailboxBusy ? 'Testing…' : editId && !form.mailbox_password ? 'Test stored credentials' : 'Test connection'}
                    </button>
                    {testMailboxResult ? (
                      <span className={testMailboxResult.ok ? 'tone-positive' : 'tone-warning'} style={{ fontSize: 13 }}>
                        {testMailboxResult.ok ? '✓ Connection OK' : '✗ Failed'}
                        {' · '}SMTP {testMailboxResult.smtp_ok ? '✓' : '✗'} · IMAP {testMailboxResult.imap_ok ? '✓' : '✗'}
                        {testMailboxResult.message ? ` — ${testMailboxResult.message}` : ''}
                      </span>
                    ) : null}
                  </div>
                </section>
              ) : null}
            </>
          ) : null}
          {editorTab === 'promo' ? (
            <section className='hub-card'>
              <h3>Promo code</h3>
              <p className='card-hint'>One code, valid on every service enabled below.</p>
              {renderEditorPromoTab()}
            </section>
          ) : null}
          {editorTab === 'commission' ? (
            <section className='hub-card'>
              <h3>Commission terms</h3>
              <p className='card-hint'>
                {isPartner
                  ? 'Partners earn commission on the next payment only.'
                  : 'Salesmen earn commission on enabled months (1–6) of customer subscriptions.'}
              </p>
              {renderEditorCommissionTab()}
            </section>
          ) : null}
          {editorTab === 'payout' ? <section className='hub-card'><h3>Bank / payout</h3>{renderEditorPayoutTab()}</section> : null}
          {editorTab === 'invoices' ? renderEditorInvoicesTab() : null}
        </div>
      </>
    )
  }

  const renderInvoiceDetailView = () => {
    if (!invoiceDetail) return <div className='empty-state'>Loading…</div>
    const inv = invoiceDetail
    const cur = inv.currency || 'GBP'
    const rep = invoiceDetailRep
    const payout = rep?.payout || {}
    const items = inv.items || []
    const subtotal = Number(inv.subtotal_minor || 0)
    const discountPct = Number(inv.discount_percent || 0)
    const taxPct = Number(inv.tax_percent || 0)
    const total = Number(inv.total_minor || 0)
    const discountMinor = Math.round(subtotal * discountPct / 100)
    const taxMinor = Math.round((subtotal - discountMinor) * taxPct / 100)
    const gross = subtotal
    return (
      <>
        <header className='hub-header'>
          <div>
            <h1 className='title-row'>
              {inv.number}
              {statusBadge(inv.status)}
            </h1>
            <p className='subtitle'>
              {inv.kind === 'charge' ? 'Charged to' : 'Payout to'}{' '}
              {rep ? (
                <button type='button' className='link-btn' onClick={() => openProfile(rep)}>
                  #{rep.ref_id || '—'} {rep.company_name || rep.name}
                </button>
              ) : '—'}
            </p>
          </div>
          <div className='hub-header-actions'>
            <button type='button' className='btn btn-ghost' disabled={busy} onClick={() => downloadHubInvoicePdf(inv.id)}>
              Download PDF
            </button>
            <button type='button' className='btn btn-ghost' onClick={() => { setView('invoices'); setInvoiceDetail(null) }}>
              <IconBack /> Back
            </button>
            {inv.status === 'new' ? (
              <button type='button' className='btn btn-primary' disabled={busy} onClick={() => hubInvoiceAction(inv.id, 'send')}>
                <IconSend /> Send
              </button>
            ) : null}
            {inv.status === 'sent' ? (
              <button type='button' className='btn btn-ghost' disabled={busy} onClick={() => hubInvoiceAction(inv.id, 'remind')}>
                <IconBell /> Send reminder
              </button>
            ) : null}
            {inv.status !== 'paid' ? (
              <button type='button' className='btn btn-primary' disabled={busy} onClick={() => hubInvoiceAction(inv.id, 'mark-paid')}>
                <IconCheck /> Mark paid
              </button>
            ) : null}
            {inv.status !== 'rejected' ? (
              <button type='button' className='btn btn-ghost' disabled={busy} onClick={() => hubInvoiceAction(inv.id, 'reject', { reason: '' })}>
                <IconX /> Reject
              </button>
            ) : null}
          </div>
        </header>

        <div className='hub-card commission-banner'>
          <div>
            <p className='banner-label'>Commission for {rep?.company_name || rep?.name || 'account'}</p>
            <p className='banner-amount'>{inv.commission_amount_display || money(inv.commission_amount_minor, cur)}</p>
            <p className='muted'>
              {inv.commission_approved ? 'Approved' : 'Awaiting your approval'} · {inv.reminders_sent || 0} reminder(s) sent
            </p>
          </div>
          <button
            type='button'
            className={inv.commission_approved ? 'btn btn-ghost' : 'btn btn-primary'}
            disabled={busy}
            onClick={() => hubInvoiceAction(inv.id, 'approve-commission', { approved: !inv.commission_approved })}
          >
            <IconBadgeCheck /> {inv.commission_approved ? 'Revoke approval' : 'Approve commission'}
          </button>
        </div>

        <div className='inv-doc-layout'>
          <section className='hub-card inv-document'>
            <div className='inv-doc-top'>
              <div className='inv-from'>
                <img
                  src={brandAssets.logoBlack}
                  alt='VoxBulk'
                  className='inv-logo'
                  style={{ height: 36, marginBottom: 12, display: 'block' }}
                  onError={(e) => { e.currentTarget.style.display = 'none' }}
                />
                <p className='strong'>{COMPANY.name}</p>
                {COMPANY.addressLines.map((l) => <p key={l} className='muted'>{l}</p>)}
                <p className='muted'>{COMPANY.country}</p>
                <p className='muted' style={{ marginTop: 4 }}>VAT {COMPANY.vatNumber}</p>
                <p className='muted'>Company no. {COMPANY.companyNumber}</p>
              </div>
              <div className='inv-billto'>
                <p className='banner-label'>Bill to</p>
                <p className='strong'>{inv.customer || '—'}</p>
                {inv.customer_email ? <p className='muted'>{inv.customer_email}</p> : null}
                {inv.customer_tax_number ? <p className='muted'>Tax no. {inv.customer_tax_number}</p> : null}
                <p className='muted' style={{ marginTop: 8 }}>Issued {(inv.issued_at || inv.created_at || '').slice(0, 10) || '—'}</p>
                <p className='muted'>Due {(inv.due_at || '').slice(0, 10) || '—'}</p>
              </div>
            </div>
            <table className='inv-lines'>
              <thead>
                <tr>
                  <th>Description</th>
                  <th className='tabular'>Qty</th>
                  <th className='tabular'>Unit</th>
                  <th className='tabular'>Total</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it) => (
                  <tr key={it.id || it.description}>
                    <td>{it.description || 'Sales commission'}</td>
                    <td className='tabular'>{it.quantity}</td>
                    <td className='tabular'>{it.unit_price_display || money(it.unit_price_minor, cur)}</td>
                    <td className='tabular'>{money(Number(it.unit_price_minor || 0) * Number(it.quantity || 0), cur)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className='inv-totals'>
              <div className='profile-row'><span className='k'>Gross</span><span className='v'>{money(gross, cur)}</span></div>
              <div className='profile-row'><span className='k'>Discount ({discountPct}%)</span><span className='v'>− {money(discountMinor, cur)}</span></div>
              <div className='profile-row'><span className='k'>Subtotal</span><span className='v'>{money(subtotal - discountMinor, cur)}</span></div>
              <div className='profile-row'><span className='k'>VAT ({taxPct}%)</span><span className='v'>{money(taxMinor, cur)}</span></div>
              <div className='profile-row total-row'><span className='k'>Total due</span><span className='v'>{inv.total_display || money(total, cur)}</span></div>
            </div>
            {inv.note ? <p className='muted' style={{ marginTop: 24 }}>Note: {inv.note}</p> : null}
          </section>
          <aside className='inv-aside'>
            <div className='hub-card'>
              <h3>Our payment details</h3>
              <div className='profile-row'><span className='k'>Bank</span><span className='v'>{COMPANY.bank.bankName}</span></div>
              <div className='profile-row'><span className='k'>Beneficiary</span><span className='v'>{COMPANY.bank.beneficiary}</span></div>
              <div className='profile-row'><span className='k'>Sort code</span><span className='v'>{COMPANY.bank.sortCode}</span></div>
              <div className='profile-row'><span className='k'>Account no.</span><span className='v'>{COMPANY.bank.accountNumber}</span></div>
              <div className='profile-row'><span className='k'>IBAN</span><span className='v'>{COMPANY.bank.iban}</span></div>
              <div className='profile-row'><span className='k'>Country</span><span className='v'>{COMPANY.bank.country}</span></div>
            </div>
            {rep ? (
              <div className='hub-card'>
                <h3>Account payout details</h3>
                <div className='profile-row'><span className='k'>Method</span><span className='v'>{payout.payout_method === 'paypal' ? 'PayPal' : 'Bank transfer'}</span></div>
                {payout.payout_method === 'paypal' ? (
                  <div className='profile-row'><span className='k'>PayPal</span><span className='v'>{payout.paypal_email || '—'}</span></div>
                ) : (
                  <>
                    <div className='profile-row'><span className='k'>Bank</span><span className='v'>{payout.bank_name || '—'}</span></div>
                    <div className='profile-row'><span className='k'>Sort code</span><span className='v'>{payout.bank_sort_code || '—'}</span></div>
                    <div className='profile-row'><span className='k'>Account no.</span><span className='v'>{payout.bank_account_number || '—'}</span></div>
                  </>
                )}
                <div className='profile-row'><span className='k'>Currency</span><span className='v'>{rep.currency || currencyForCountry(rep.country)}</span></div>
                <button type='button' className='btn btn-ghost' style={{ width: '100%', marginTop: 12 }} onClick={() => openProfile(rep)}>
                  View full profile
                </button>
              </div>
            ) : null}
          </aside>
        </div>
      </>
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
              <select
                value={createInvForm.sales_rep_id}
                onChange={(e) => {
                  const id = e.target.value
                  const r = allReps.find((x) => x.id === id)
                  setCreateInvForm({
                    ...createInvForm,
                    sales_rep_id: id,
                    customer: r ? (r.company_name || r.name || createInvForm.customer) : createInvForm.customer,
                    customer_email: r ? (r.email || createInvForm.customer_email) : createInvForm.customer_email,
                  })
                }}
              >
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
            <label>Customer email</label>
            <input type='email' value={createInvForm.customer_email} onChange={(e) => setCreateInvForm({ ...createInvForm, customer_email: e.target.value })} />
          </div>
          <div className='field'>
            <label>Sales commission amount</label>
            <input
              type='number'
              min='0'
              step='0.01'
              value={createInvForm.commission_amount_major}
              onChange={(e) => setCreateInvForm({ ...createInvForm, commission_amount_major: e.target.value })}
            />
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
          </div>
        </div>
        <div className='modal-foot'>
          <button type='button' className='btn btn-ghost' onClick={() => setShowCreateInvoice(false)}>Cancel</button>
          <button type='button' className='btn btn-primary' disabled={busy} onClick={() => createHubInvoice()}>Create</button>
          <button type='button' className='btn btn-primary' disabled={busy} onClick={() => createHubInvoice({ downloadPdf: true })}>Create &amp; download PDF</button>
          <button type='button' className='btn btn-primary' disabled={busy} onClick={() => createHubInvoice({ send_email: true })}>Create &amp; send email</button>
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
    <div className='sales-hub'>
      {renderSubNav()}
      <div className='hub-body'>
        {view === 'accounts' ? renderAccountsView() : null}
        {view === 'invoices' ? renderInvoicesView() : null}
        {view === 'editor' ? renderEditorView() : null}
        {view === 'invoiceDetail' ? renderInvoiceDetailView() : null}
      </div>
      {renderRowMenuPortal()}
      {renderPasswordModal()}
      {renderCreateInvoiceModal()}
      <div className={`toast ${toast ? 'show' : ''}`}>{toast}</div>
    </div>
  )
}
