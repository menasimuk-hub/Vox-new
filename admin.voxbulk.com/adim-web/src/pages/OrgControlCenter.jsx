import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Building2, CircleCheck, CreditCard, FileText, Megaphone, Snowflake } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { adminOrderViewPath, filterOrdersByWorkflow, interviewFormatLabel, nextColumnSort, orderMatchesSearch, sortRowsByColumn, ORDER_PAYMENT_HELP } from '../lib/serviceOrderAdmin'
import { currencySymbol } from '../lib/billingAdminUtils'
import { KpiCard } from '@/components/ui/KpiCard'
import PlanPickerSelect from '@/components/billing/PlanPickerSelect'
import './orgControlCenter.css'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'orders', label: 'Orders' },
  { id: 'campaigns', label: 'Campaigns' },
  { id: 'billing', label: 'Billing & plan' },
  { id: 'invoices', label: 'Invoices' },
  { id: 'activity', label: 'Activity log' },
]

const COUNTRY_OPTIONS = [
  { value: '', label: 'All countries' },
  { value: 'gb', label: 'United Kingdom' },
  { value: 'us', label: 'United States' },
  { value: 'ca', label: 'Canada' },
  { value: 'au', label: 'Australia' },
]

const INVOICE_TYPES = [
  { value: 'subscription', label: 'Subscription' },
  { value: 'service_order', label: 'Service order' },
  { value: 'overage', label: 'Overage' },
  { value: 'manual', label: 'Manual adjustment' },
]
const CHIP_KEYS = [
  { key: 'active', label: 'Active' },
  { key: 'frozen', label: 'Frozen' },
  { key: 'overage', label: 'Overage risk' },
  { key: 'invoices', label: 'Invoices due' },
  { key: 'campaigns', label: 'Running campaigns' },
]

function fmtMoneyPence(pence, orgOrSymbol = '$') {
  const symbol = typeof orgOrSymbol === 'string'
    ? (orgOrSymbol.length === 3 ? currencySymbol(orgOrSymbol) : orgOrSymbol)
    : orgOrSymbol?.currency_symbol || currencySymbol(orgOrSymbol?.billing_currency)
  const n = Number(pence || 0) / 100
  return `${symbol}${n.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function moneyDisplay(org, pence, fallbackDisplay) {
  if (fallbackDisplay) return fallbackDisplay
  return fmtMoneyPence(pence, org)
}

function fmtN(n) {
  return Number(n || 0).toLocaleString('en-GB')
}

function fmtWhen(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  return d.toLocaleString()
}

function barClass(pct) {
  const p = Number(pct || 0)
  if (p >= 90) return 'occ-bar-red'
  if (p >= 70) return 'occ-bar-amber'
  return 'occ-bar-green'
}

function statusBadge(status) {
  const s = String(status || '').toLowerCase()
  const map = {
    active: 'occ-badge-green',
    frozen: 'occ-badge-red',
    paused: 'occ-badge-amber',
    running: 'occ-badge-blue',
    scheduled: 'occ-badge-amber',
    paid: 'occ-badge-green',
    due: 'occ-badge-amber',
    overdue: 'occ-badge-red',
    completed: 'occ-badge-gray',
    draft: 'occ-badge-gray',
    cancelled: 'occ-badge-gray',
    approved: 'occ-badge-green',
    unpaid: 'occ-badge-amber',
    rejected: 'occ-badge-red',
  }
  return <span className={`occ-badge ${map[s] || 'occ-badge-gray'}`}>{s || '—'}</span>
}

function resolveInvoiceLifecycle(inv) {
  if (inv?.lifecycle) return inv.lifecycle
  const st = String(inv?.status || '').toLowerCase()
  const ddActive = st === 'collecting' || (st === 'pending' && inv?.dd_payment_id)
  const locked = ['paid', 'void', 'cancelled', 'refunded', 'disputed', 'credited'].includes(st) || Boolean(inv?.disputed)
  if (ddActive) {
    return {
      can_edit: false,
      can_void: false,
      is_locked: true,
      lock_reason: 'Direct Debit collection is in progress.',
      suggested_action: 'stop_collection',
      suggested_action_label: 'Stop DD collection before editing or voiding.',
    }
  }
  if (locked) {
    return {
      can_edit: false,
      can_void: false,
      is_locked: true,
      lock_reason: st === 'paid' ? 'Paid invoices cannot be edited or voided.' : 'This invoice is locked.',
      suggested_action_label: 'Use credit note, refund, or reissue instead.',
    }
  }
  return { can_edit: true, can_void: true, is_locked: false, lock_reason: null, suggested_action_label: null }
}

function channelLabel(channel, order) {
  if (order?.service_code === 'interview') return interviewFormatLabel(order)
  const ch = String(channel || '').toLowerCase()
  if (ch === 'meeting' || ch === 'ai_meeting') return 'Web interview'
  if (ch === 'mixed') return 'Phone + web'
  if (ch === 'whatsapp') return 'WhatsApp'
  if (ch === 'sms') return 'SMS'
  if (ch === 'ai_call') return 'AI call'
  if (ch === 'call') return 'Call'
  return ch || '—'
}

function pctUsed(used, included) {
  const inc = Number(included || 0)
  if (inc <= 0) return 0
  return Math.min(100, Math.round((Number(used || 0) / inc) * 100))
}

function OccInfoBlock({ title, action, children }) {
  return (
    <div className="occ-info-block">
      <div className="occ-info-block-head">
        <div className="occ-info-block-title">{title}</div>
        {action || null}
      </div>
      {children}
    </div>
  )
}

function OccInfoRow({ label, value }) {
  return (
    <div className="occ-info-row">
      <span className="occ-info-row-label">{label}</span>
      <span className="occ-info-row-value">{value}</span>
    </div>
  )
}

function ToastStack({ toasts }) {
  if (!toasts.length) return null
  return (
    <div className="occ-toast-wrap">
      {toasts.map((t) => (
        <div key={t.id} className={`occ-toast ${t.type || ''}`}>
          {t.message}
        </div>
      ))}
    </div>
  )
}

function KpiCards({ org }) {
  if (!org) {
    return (
      <div className="occ-kpi-placeholder">
        <p>Select an organisation from the table below to view KPIs and details.</p>
      </div>
    )
  }

  const callPct = pctUsed(org.calls_used, org.calls_included)
  const waPct = pctUsed(org.wa_used, org.wa_included)
  const smsPct = pctUsed(org.sms_used, org.sms_included)
  const sharedPool = Boolean(org.shared_package_pool)
  const pkgPct = org.package_included_units
    ? pctUsed(org.package_used_units, org.package_included_units)
    : org.package_included
      ? pctUsed(org.package_used, org.package_included)
      : 0
  const walletLow = Number(org.wallet_pence || 0) < 5000
  const estimateLabel = org.estimate_label || (org.estimate_source === 'wallet' ? 'Estimated from wallet' : org.estimate_source === 'package' ? 'Estimated from plan' : '')

  return (
    <div className="occ-kpi-grid">
      <div className="occ-kpi-card" style={walletLow ? { borderColor: 'var(--occ-red-border)', background: 'var(--occ-red-bg)' } : undefined}>
        <div className="occ-kpi-card-label">Wallet balance</div>
        <div className="occ-kpi-card-value" style={walletLow ? { color: 'var(--occ-red)' } : undefined}>
          {org.wallet_display || fmtMoneyPence(org.wallet_pence)}
        </div>
        <div className="occ-kpi-card-sub">{org.payment_method || '—'}</div>
      </div>
      <div className="occ-kpi-card">
        <div className="occ-kpi-card-label">C.P plan</div>
        <div className="occ-kpi-card-value large">{org.core_plan || org.plan || '—'}</div>
        <div className="occ-kpi-card-sub">{org.core_subscription_status || org.subscription_status || '—'}</div>
      </div>
      <div className="occ-kpi-card">
        <div className="occ-kpi-card-label">F.B plan</div>
        <div className="occ-kpi-card-value large">{org.feedback_plan || '—'}</div>
        <div className="occ-kpi-card-sub">{org.feedback_subscription_status || '—'}</div>
      </div>
      {sharedPool ? (
        <div className="occ-kpi-card" style={{ borderColor: 'var(--occ-blue-border, #bfdbfe)', background: 'var(--occ-blue-bg, #eff6ff)' }}>
          <div className="occ-kpi-card-label">Package remaining</div>
          <div className="occ-kpi-card-value">{org.package_remaining_display || fmtMoneyPence(org.package_remaining_pence, org)}</div>
          <div className="occ-kpi-card-sub">
            {org.package_used_display || fmtMoneyPence(org.package_used_pence, org)} used of{' '}
            {org.package_included_display || fmtMoneyPence(org.package_included_pence, org)}
          </div>
          <div className="occ-kpi-card-bar">
            <div className={`occ-kpi-card-bar-fill ${barClass(pkgPct)}`} style={{ width: `${pkgPct}%` }} />
          </div>
        </div>
      ) : (
        <>
          <div className="occ-kpi-card">
            <div className="occ-kpi-card-label">AI calls remaining</div>
            <div className="occ-kpi-card-value">{fmtN(org.calls_remaining)}</div>
            <div className="occ-kpi-card-sub">
              {fmtN(org.calls_used)} of {fmtN(org.calls_included)} used
            </div>
            <div className="occ-kpi-card-bar">
              <div className={`occ-kpi-card-bar-fill ${barClass(callPct)}`} style={{ width: `${callPct}%` }} />
            </div>
          </div>
          <div className="occ-kpi-card">
            <div className="occ-kpi-card-label">WhatsApp remaining</div>
            <div className="occ-kpi-card-value">{fmtN(org.wa_remaining)}</div>
            <div className="occ-kpi-card-sub">
              {fmtN(org.wa_used)} of {fmtN(org.wa_included)} used
            </div>
            <div className="occ-kpi-card-bar">
              <div className={`occ-kpi-card-bar-fill ${barClass(waPct)}`} style={{ width: `${waPct}%` }} />
            </div>
          </div>
        </>
      )}
      <div className="occ-kpi-card">
        <div className="occ-kpi-card-label">Est. WA surveys left</div>
        <div className="occ-kpi-card-value">{fmtN(org.estimated_wa_surveys)}</div>
        <div className="occ-kpi-card-sub">{estimateLabel || 'Approximate capacity only'}</div>
      </div>
      <div className="occ-kpi-card">
        <div className="occ-kpi-card-label">Est. AI minutes left</div>
        <div className="occ-kpi-card-value">{fmtN(org.estimated_ai_minutes)}</div>
        <div className="occ-kpi-card-sub">{estimateLabel || 'Approximate capacity only'}</div>
      </div>
      <div className="occ-kpi-card">
        <div className="occ-kpi-card-label">SMS remaining</div>
        <div className="occ-kpi-card-value">{fmtN(org.sms_remaining)}</div>
        <div className="occ-kpi-card-sub">
          {fmtN(org.sms_used)} of {fmtN(org.sms_included)} used
        </div>
        <div className="occ-kpi-card-bar">
          <div className={`occ-kpi-card-bar-fill ${barClass(smsPct)}`} style={{ width: `${smsPct}%` }} />
        </div>
      </div>
      <div className="occ-kpi-card">
        <div className="occ-kpi-card-label">Survey credits</div>
        <div className="occ-kpi-card-value">{fmtN(org.survey_credits)}</div>
      </div>
      <div className="occ-kpi-card">
        <div className="occ-kpi-card-label">Interview credits</div>
        <div className="occ-kpi-card-value">{fmtN(org.interview_credits)}</div>
      </div>
      <div className="occ-kpi-card">
        <div className="occ-kpi-card-label">Billing period</div>
        <div className="occ-kpi-card-value large">{org.billing_start || '—'}</div>
        <div className="occ-kpi-card-sub">ends {org.billing_end || '—'}</div>
      </div>
      <div
        className="occ-kpi-card"
        style={org.overage_risk ? { borderColor: 'var(--occ-amber-border)', background: 'var(--occ-amber-bg)' } : undefined}
      >
        <div className="occ-kpi-card-label">Overage risk</div>
        <div className="occ-kpi-card-value large" style={{ color: org.overage_risk ? 'var(--occ-amber)' : 'var(--occ-green)' }}>
          {org.overage_risk ? 'At risk' : 'Normal'}
        </div>
        <div className="occ-kpi-card-sub">{org.usage_pct ?? 0}% overall usage</div>
      </div>
      <div className="occ-kpi-card">
        <div className="occ-kpi-card-label">Payment status</div>
        <div className="occ-kpi-card-value large">{statusBadge(org.payment_status)}</div>
        <div className="occ-kpi-card-sub">
          {org.open_invoices ?? org.invoices ?? 0} open invoice(s)
        </div>
      </div>
    </div>
  )
}

export default function OrgControlCenter() {
  const navigate = useNavigate()
  const { orgId: routeOrgId } = useParams()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [planFilter, setPlanFilter] = useState('')
  const [payFilter, setPayFilter] = useState('')
  const [chips, setChips] = useState(() => new Set())
  const [sortField, setSortField] = useState('name')
  const [sortAsc, setSortAsc] = useState(true)
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('overview')
  const [plans, setPlans] = useState([])
  const [feedbackPlans, setFeedbackPlans] = useState([])
  const [notes, setNotes] = useState('')
  const [notesBusy, setNotesBusy] = useState(false)
  const [modal, setModal] = useState(null)
  const [modalBusy, setModalBusy] = useState(false)
  const [fundAmount, setFundAmount] = useState('')
  const [fundNote, setFundNote] = useState('')
  const [planCode, setPlanCode] = useState('')
  const [feedbackPlanCode, setFeedbackPlanCode] = useState('')
  const [planReason, setPlanReason] = useState('')
  const [upgradePreview, setUpgradePreview] = useState(null)
  const [invoiceAmount, setInvoiceAmount] = useState('')
  const [invoiceDue, setInvoiceDue] = useState('')
  const [countryFilter, setCountryFilter] = useState('')
  const [campaignStatusFilter, setCampaignStatusFilter] = useState('')
  const [channelFilter, setChannelFilter] = useState('')
  const [invoiceType, setInvoiceType] = useState('manual')
  const [promoCode, setPromoCode] = useState('')
  const [allowOverage, setAllowOverage] = useState(true)
  const [billingPaymentProvider, setBillingPaymentProvider] = useState('auto')
  const [invoiceNote, setInvoiceNote] = useState('')
  const [editInvoice, setEditInvoice] = useState(null)
  const [editInvoiceAmount, setEditInvoiceAmount] = useState('')
  const [editInvoiceDue, setEditInvoiceDue] = useState('')
  const [editInvoiceDesc, setEditInvoiceDesc] = useState('')
  const [toasts, setToasts] = useState([])
  const [walletHistory, setWalletHistory] = useState([])
  const [walletModalMode, setWalletModalMode] = useState('credit')
  const [actionBusy, setActionBusy] = useState('')
  const [activityDeletionOnly, setActivityDeletionOnly] = useState(false)
  const [deleteConfirmText, setDeleteConfirmText] = useState('')
  const [deleteAdminNotes, setDeleteAdminNotes] = useState('')
  const [ordersWorkflowFilter, setOrdersWorkflowFilter] = useState('all')
  const [ordersSort, setOrdersSort] = useState('date_desc')
  const [ordersSearch, setOrdersSearch] = useState('')
  const [ordersTableSortField, setOrdersTableSortField] = useState('created')
  const [ordersTableSortAsc, setOrdersTableSortAsc] = useState(false)

  const pushToast = useCallback((message, type = '') => {
    const id = `${Date.now()}-${Math.random()}`
    setToasts((prev) => [...prev, { id, message, type }])
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3100)
  }, [])

  const buildQuery = useCallback(() => {
    const params = new URLSearchParams()
    params.set('limit', '200')
    if (search.trim()) params.set('search', search.trim())
    if (statusFilter) params.set('status', statusFilter)
    if (planFilter) params.set('plan_code', planFilter)
    if (payFilter) params.set('payment_status', payFilter)
    if (countryFilter) params.set('country', countryFilter)
    if (campaignStatusFilter) params.set('campaign_status', campaignStatusFilter)
    if (channelFilter) params.set('channel', channelFilter)
    if (chips.has('overage')) params.set('overage_only', 'true')
    if (chips.has('invoices')) params.set('invoices_due_only', 'true')
    if (chips.has('campaigns')) params.set('running_campaigns_only', 'true')
    if (chips.has('active') && !chips.has('frozen')) params.set('status', 'active')
    if (chips.has('frozen') && !chips.has('active')) params.set('status', 'frozen')
    return params.toString()
  }, [search, statusFilter, planFilter, payFilter, countryFilter, campaignStatusFilter, channelFilter, chips])

  const loadList = useCallback(async () => {
    setError('')
    setLoading(true)
    try {
      const res = await apiFetch(`/admin/organisations/control-center?${buildQuery()}`, {
        timeoutMs: 90000,
        quietNetworkHint: true,
      })
      setItems(Array.isArray(res?.items) ? res.items : [])
    } catch (e) {
      const raw = e?.message || 'Could not load organisations'
      const short = raw.split('\n')[0].replace(/\.$/, '')
      setError(short || 'Could not load organisations')
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [buildQuery])

  const loadDetail = useCallback(async (orgId) => {
    if (!orgId) return
    setDetailLoading(true)
    try {
      const res = await apiFetch(`/admin/organisations/${encodeURIComponent(orgId)}/control-center`)
      setDetail(res)
      setNotes(res?.organisation?.profile_notes || '')
      setAllowOverage(Boolean(res?.organisation?.allow_overage ?? true))
      setBillingPaymentProvider(res?.organisation?.billing_payment_provider || 'auto')
      setWalletHistory(Array.isArray(res?.wallet_history) ? res.wallet_history : [])
    } catch (e) {
      pushToast(e?.message || 'Could not load organisation detail', 'danger')
      setDetail(null)
    } finally {
      setDetailLoading(false)
    }
  }, [pushToast])

  useEffect(() => {
    loadList()
  }, [loadList])

  useEffect(() => {
    if (routeOrgId) {
      setSelectedId(routeOrgId)
      setActiveTab('overview')
      loadDetail(routeOrgId)
      window.scrollTo({ top: 0 })
    } else {
      setSelectedId(null)
      setDetail(null)
    }
  }, [routeOrgId, loadDetail])

  useEffect(() => {
    apiFetch('/admin/billing/plans')
      .then((rows) => setPlans(Array.isArray(rows) ? rows : []))
      .catch(() => setPlans([]))
  }, [])

  useEffect(() => {
    const zone = detail?.organisation?.market_zone || 'gb'
    if (!selectedId) {
      setFeedbackPlans([])
      return
    }
    apiFetch(`/admin/customer-feedback/plans?market_zone=${encodeURIComponent(zone)}`)
      .then((res) => setFeedbackPlans(Array.isArray(res?.items) ? res.items : []))
      .catch(() => setFeedbackPlans([]))
  }, [selectedId, detail?.organisation?.market_zone])

  const filteredItems = useMemo(() => {
    let rows = [...items]
    if (chips.has('active') && chips.has('frozen')) {
      rows = rows.filter((r) => r.status === 'active' || r.status === 'frozen')
    }
    rows.sort((a, b) => {
      let va = a[sortField]
      let vb = b[sortField]
      if (sortField === 'wallet') {
        va = a.wallet_pence
        vb = b.wallet_pence
      }
      if (typeof va === 'string') return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va)
      return sortAsc ? Number(va || 0) - Number(vb || 0) : Number(vb || 0) - Number(va || 0)
    })
    return rows
  }, [items, chips, sortField, sortAsc])

  const aggregateKpis = useMemo(() => {
    const isDue = (s) => ['due', 'overdue', 'failed', 'past_due'].includes(String(s || '').toLowerCase())
    return {
      total: items.length,
      active: items.filter((o) => o.status === 'active').length,
      frozen: items.filter((o) => o.status === 'frozen').length,
      paymentDue: items.filter((o) => isDue(o.payment_status)).length,
      campaigns: items.reduce((acc, o) => acc + (Number(o.campaigns) || 0), 0),
      invoices: items.reduce((acc, o) => acc + (Number(o.invoices) || 0), 0),
    }
  }, [items])

  const org = detail?.organisation
  const subscriptionRouting = org?.subscription_routing
  const subscriptionFinance = detail?.subscription_finance
  const campaigns = detail?.campaigns || []
  const orderSortAccessors = useMemo(
    () => ({
      reference: (o) => o.reference_id || o.campaign_id || o.id || '',
      service: (o) => o.service_label || o.title || o.service_code || '',
      channel: (o) => channelLabel(o.channel, o),
      recipients: (o) => Number(o.recipient_count) || 0,
      quote: (o) => Number(o.quote_total_pence) || 0,
      payment: (o) => o.payment_status || '',
      workflow: (o) => o.workflow_label || o.workflow_state || o.status || '',
      created: (o) => {
        const raw = o.created_at || o.updated_at
        const t = raw ? new Date(raw).getTime() : 0
        return Number.isNaN(t) ? 0 : t
      },
    }),
    [],
  )

  const sortOrdersColumn = (field) => {
    const next = nextColumnSort(ordersTableSortField, ordersTableSortAsc, field)
    setOrdersTableSortField(next.field)
    setOrdersTableSortAsc(next.asc)
  }

  useEffect(() => {
    const map = {
      amount_desc: ['quote', false],
      amount_asc: ['quote', true],
      date_desc: ['created', false],
      date_asc: ['created', true],
      order_asc: ['reference', true],
      name_asc: ['service', true],
    }
    const [field, asc] = map[ordersSort] || ['created', false]
    setOrdersTableSortField(field)
    setOrdersTableSortAsc(asc)
  }, [ordersSort])

  const filteredOrders = useMemo(() => {
    const workflowRows = filterOrdersByWorkflow(campaigns, ordersWorkflowFilter)
    const q = ordersSearch.trim()
    const searched = q
      ? workflowRows.filter((o) => orderMatchesSearch(o, q))
      : workflowRows
    return sortRowsByColumn(searched, ordersTableSortField, ordersTableSortAsc, orderSortAccessors)
  }, [campaigns, ordersWorkflowFilter, ordersSearch, ordersTableSortField, ordersTableSortAsc, orderSortAccessors])
  const [invoiceSearch, setInvoiceSearch] = useState('')
  const invoices = detail?.invoices || []
  const filteredInvoices = useMemo(() => {
    const term = invoiceSearch.trim().toLowerCase()
    if (!term) return invoices
    return invoices.filter((inv) => {
      const hay = [
        inv.invoice_number,
        inv.external_invoice_id,
        inv.id,
        inv.description,
      ]
        .map((v) => String(v || '').toLowerCase())
        .join(' ')
      return hay.includes(term)
    })
  }, [invoices, invoiceSearch])
  const activity = detail?.activity || []
  const deletionRequest = detail?.deletion_request || null
  const filteredActivity = useMemo(() => {
    if (!activityDeletionOnly) return activity
    return activity.filter((ev) => {
      const t = String(ev.event_type || ev.action || '').toLowerCase()
      return t.includes('account.deletion') || t.includes('deletion')
    })
  }, [activity, activityDeletionOnly])
  const invoiceSummary = detail?.invoice_summary || {}
  const subscriptionCancellation = detail?.subscription_cancellation || null
  const refundReviews = detail?.refund_reviews || []

  const selectOrg = (id) => {
    navigate(`/organisations/all-users/${encodeURIComponent(id)}`)
  }

  const toggleChip = (key) => {
    setChips((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const sortTable = (field) => {
    if (sortField === field) setSortAsc((v) => !v)
    else {
      setSortField(field)
      setSortAsc(true)
    }
  }

  const refreshAll = async () => {
    await loadList()
    if (selectedId) await loadDetail(selectedId)
  }

  const occ = (path, options) =>
    apiFetch(`/admin/organisations/${encodeURIComponent(selectedId)}/control-center${path}`, options)

  const billingInvoice = (invoiceId, path, options = {}) =>
    apiFetch(`/admin/billing/invoices/${encodeURIComponent(invoiceId)}${path}`, options)

  const setSuspended = async (orgId, suspended) => {
    setActionBusy(orgId)
    try {
      await apiFetch(`/admin/organisations/${encodeURIComponent(orgId)}/control-center/suspend`, {
        method: 'PATCH',
        body: JSON.stringify({ is_suspended: suspended }),
      })
      pushToast(suspended ? 'Account frozen' : 'Account activated', suspended ? 'danger' : 'success')
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Status update failed', 'danger')
    } finally {
      setActionBusy('')
    }
  }

  const saveNotes = async () => {
    if (!selectedId) return
    setNotesBusy(true)
    try {
      await apiFetch(`/admin/organisations/${encodeURIComponent(selectedId)}/control-center/notes`, {
        method: 'PATCH',
        body: JSON.stringify({ profile_notes: notes.trim() || null }),
      })
      pushToast('Notes saved', 'success')
      await loadDetail(selectedId)
    } catch (e) {
      pushToast(e?.message || 'Could not save notes', 'danger')
    } finally {
      setNotesBusy(false)
    }
  }

  const applyFunds = async () => {
    const gbp = Number(fundAmount)
    if (!selectedId || !Number.isFinite(gbp) || gbp <= 0) {
      pushToast('Enter a positive amount', 'warning')
      return
    }
    setModalBusy(true)
    try {
      const path =
        walletModalMode === 'debit'
          ? '/wallet/debit'
          : walletModalMode === 'refund'
            ? '/wallet/refund'
            : '/wallet/credit'
      await occ(path, {
        method: 'POST',
        body: JSON.stringify({
          amount_minor: Math.round(gbp * 100),
          reason: fundNote.trim() || undefined,
        }),
      })
      pushToast(
        walletModalMode === 'debit' ? 'Wallet debited' : walletModalMode === 'refund' ? 'Wallet refunded' : 'Wallet credited',
        'success',
      )
      setModal(null)
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Wallet update failed', 'danger')
    } finally {
      setModalBusy(false)
    }
  }

  const reverseWalletTx = async (transactionId) => {
    if (!selectedId || !transactionId) return
    const reason = window.prompt('Reason for reversal (required for audit trail):', fundNote.trim() || 'Admin reversal')
    if (!reason) return
    setActionBusy(`reverse-${transactionId}`)
    try {
      await occ(`/wallet/transactions/${encodeURIComponent(transactionId)}/reverse`, {
        method: 'POST',
        body: JSON.stringify({ reason }),
      })
      pushToast('Wallet transaction reversed', 'success')
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Reversal failed', 'danger')
    } finally {
      setActionBusy('')
    }
  }

  const reverseCancellation = async () => {
    if (!selectedId) return
    const note = window.prompt('Reason for reversing scheduled cancellation:', 'Customer changed mind')
    if (!note) return
    setActionBusy('cancel-reverse')
    try {
      await occ('/cancellation/reverse', { method: 'POST', body: JSON.stringify({ note }) })
      pushToast('Cancellation reversed', 'success')
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Could not reverse cancellation', 'danger')
    } finally {
      setActionBusy('')
    }
  }

  const promptWalletCreditPence = (defaultDisplay) => {
    const prefill = defaultDisplay ? String(defaultDisplay).replace(/[^\d.]/g, '') : ''
    const input = window.prompt(
      `Wallet credit amount in ${org?.billing_currency || 'billing currency'} (remaining subscription period only).\nLeave blank to use calculated value${defaultDisplay ? ` (${defaultDisplay})` : ''}:`,
      prefill,
    )
    if (input === null) return undefined
    const trimmed = String(input).trim()
    if (!trimmed) return null
    const pounds = Number.parseFloat(trimmed.replace(/[^\d.]/g, ''))
    if (!Number.isFinite(pounds) || pounds < 0) return undefined
    return Math.round(pounds * 100)
  }

  const immediateCancellation = async (issueWalletCredit = false) => {
    if (!selectedId) return
    const note = window.prompt('Admin note for immediate cancellation:', 'Admin immediate cancellation')
    if (!note) return
    let walletCreditPence = null
    if (issueWalletCredit) {
      const amount = promptWalletCreditPence(subscriptionCancellation?.calculated_unused_value_display)
      if (amount === undefined) return
      walletCreditPence = amount
    }
    setActionBusy('cancel-immediate')
    try {
      const result = await occ('/cancellation/immediate', {
        method: 'POST',
        body: JSON.stringify({
          note,
          issue_wallet_credit: issueWalletCredit,
          wallet_credit_pence: walletCreditPence,
        }),
      })
      const credited = result?.wallet_credit?.wallet_credit_pence
      const balance = result?.wallet_credit?.wallet_balance_display
      if (issueWalletCredit && credited) {
        pushToast(`Cancelled with wallet credit ${fmtMoneyPence(credited)}${balance ? ` — balance ${balance}` : ''}`, 'success')
      } else {
        pushToast(issueWalletCredit ? 'Cancelled immediately with wallet credit' : 'Cancelled immediately', 'success')
      }
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Immediate cancellation failed', 'danger')
    } finally {
      setActionBusy('')
    }
  }

  const resolveRefundReview = async (reviewId, reviewStatus, extra = {}) => {
    if (!selectedId || !reviewId) return
    const adminNotes = window.prompt('Admin notes for refund review:', extra.defaultNote || '')
    if (adminNotes === null) return
    let walletCreditPence = extra.wallet_credit_pence
    if (extra.issue_wallet_credit && walletCreditPence === undefined) {
      const review = refundReviews.find((r) => r.id === reviewId)
      const defaultDisplay = review?.calculated_unused_value_pence != null ? fmtMoneyPence(review.calculated_unused_value_pence) : subscriptionCancellation?.calculated_unused_value_display
      const amount = promptWalletCreditPence(defaultDisplay)
      if (amount === undefined) return
      walletCreditPence = amount
    }
    if (extra.approved_external_refund_pence != null && extra.issue_stripe_refund !== false) {
      const review = refundReviews.find((r) => r.id === reviewId)
      const defaultPence = extra.approved_external_refund_pence ?? review?.calculated_unused_value_pence
      const defaultGbp = defaultPence != null ? (defaultPence / 100).toFixed(2) : ''
      const input = window.prompt(`Bank refund amount in ${org?.billing_currency || 'billing currency'} (remaining period only):`, defaultGbp)
      if (input === null) return
      const pounds = Number.parseFloat(String(input).trim().replace(/[^\d.]/g, ''))
      if (!Number.isFinite(pounds) || pounds < 0) return
      extra = { ...extra, approved_external_refund_pence: Math.round(pounds * 100) }
    }
    setActionBusy(`refund-${reviewId}`)
    try {
      const result = await occ(`/refund-reviews/${encodeURIComponent(reviewId)}/resolve`, {
        method: 'POST',
        body: JSON.stringify({
          review_status: reviewStatus,
          admin_notes: adminNotes,
          ...extra,
          wallet_credit_pence: walletCreditPence,
        }),
      })
      const wallet = result?.wallet_credit?.wallet_credit_pence
      const external = result?.refund_review?.approved_external_refund_pence
      if (wallet) {
        pushToast(`Wallet credit ${fmtMoneyPence(wallet)} issued`, 'success')
      } else if (external) {
        pushToast(`Bank refund ${fmtMoneyPence(external)} recorded — customer notified (2 working days + up to 3 days to bank)`, 'success')
      } else {
        pushToast(`Refund review ${reviewStatus}`, 'success')
      }
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Refund review update failed', 'danger')
    } finally {
      setActionBusy('')
    }
  }

  const reverseCancellationWalletCredit = async (reviewId) => {
    if (!selectedId || !reviewId) return
    const reason = window.prompt('Reason for reversing wallet credit:', 'Mistaken credit')
    if (!reason) return
    setActionBusy(`refund-reverse-${reviewId}`)
    try {
      await occ(`/refund-reviews/${encodeURIComponent(reviewId)}/reverse-wallet`, {
        method: 'POST',
        body: JSON.stringify({ reason }),
      })
      pushToast('Cancellation wallet credit reversed', 'success')
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Wallet credit reversal failed', 'danger')
    } finally {
      setActionBusy('')
    }
  }

  const stopDdCollection = async (invoiceId) => {
    if (!invoiceId) return
    const note = window.prompt('Reason for stopping DD collection:', 'Admin stop collection')
    if (note === null) return
    setActionBusy(`stop-dd-${invoiceId}`)
    try {
      await billingInvoice(invoiceId, '/stop-dd-collection', {
        method: 'POST',
        body: JSON.stringify({ reason: note }),
      })
      pushToast('DD collection stopped', 'success')
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Stop DD failed', 'danger')
    } finally {
      setActionBusy('')
    }
  }

  const collectInvoice = async (invoiceId, method = 'wallet') => {
    if (!invoiceId) return
    setActionBusy(`collect-${invoiceId}`)
    try {
      await billingInvoice(invoiceId, '/collect', {
        method: 'POST',
        body: JSON.stringify({ method }),
      })
      pushToast('Invoice payment collected', 'success')
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Collect payment failed', 'danger')
    } finally {
      setActionBusy('')
    }
  }

  const applyCredits = async (serviceCode, delta) => {
    if (!selectedId) return
    setModalBusy(true)
    try {
      await occ('/credits/adjust', {
        method: 'POST',
        body: JSON.stringify({ service_code: serviceCode, delta, reason: fundNote.trim() || 'Admin adjustment' }),
      })
      pushToast('Credits updated', 'success')
      setModal(null)
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Credit adjustment failed', 'danger')
    } finally {
      setModalBusy(false)
    }
  }

  const applyPromo = async () => {
    if (!selectedId || !promoCode.trim()) {
      pushToast('Enter a promo code', 'warning')
      return
    }
    setModalBusy(true)
    try {
      await occ('/promo/apply', {
        method: 'POST',
        body: JSON.stringify({ promo_code: promoCode.trim() }),
      })
      pushToast('Promo applied', 'success')
      setModal(null)
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Promo apply failed', 'danger')
    } finally {
      setModalBusy(false)
    }
  }

  const saveOverageSetting = async (next) => {
    if (!selectedId) return
    setActionBusy('overage')
    try {
      await occ('/overage', {
        method: 'PATCH',
        body: JSON.stringify({ allow_overage: next }),
      })
      setAllowOverage(next)
      pushToast(`Overage ${next ? 'enabled' : 'disabled'}`, 'success')
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Overage update failed', 'danger')
    } finally {
      setActionBusy('')
    }
  }

  const saveBillingPaymentProvider = async (next) => {
    if (!selectedId) return
    setActionBusy('billing-provider')
    try {
      await occ('/billing-payment-provider', {
        method: 'PATCH',
        body: JSON.stringify({ billing_payment_provider: next === 'auto' ? null : next }),
      })
      setBillingPaymentProvider(next)
      pushToast('Subscription checkout provider updated', 'success')
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Provider update failed', 'danger')
    } finally {
      setActionBusy('')
    }
  }

  useEffect(() => {
    if (modal !== 'package' || !selectedId || !planCode.trim() || planCode.trim() === String(org?.core_plan_code || org?.plan_code || '').trim()) {
      setUpgradePreview(null)
      return undefined
    }
    let cancelled = false
    const timer = window.setTimeout(() => {
      apiFetch(
        `/admin/organisations/${encodeURIComponent(selectedId)}/billing/upgrade-preview?plan_code=${encodeURIComponent(planCode.trim())}`,
      )
        .then((res) => {
          if (!cancelled) setUpgradePreview(res)
        })
        .catch(() => {
          if (!cancelled) setUpgradePreview(null)
        })
    }, 300)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [modal, selectedId, planCode, org?.core_plan_code, org?.plan_code])

  const applyPlanChange = async () => {
    if (!selectedId || !planCode.trim()) {
      pushToast('Select a C.P plan', 'warning')
      return
    }
    setModalBusy(true)
    try {
      await apiFetch(`/admin/organisations/${encodeURIComponent(selectedId)}/subscription`, {
        method: 'PUT',
        body: JSON.stringify({ plan_code: planCode.trim(), status: 'active' }),
      })
      pushToast('C.P plan updated', 'success')
      setModal(null)
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'C.P plan change failed', 'danger')
    } finally {
      setModalBusy(false)
    }
  }

  const applyFeedbackPlanChange = async () => {
    if (!selectedId || !feedbackPlanCode.trim()) {
      pushToast('Select an F.B plan', 'warning')
      return
    }
    setModalBusy(true)
    try {
      await apiFetch(`/admin/organisations/${encodeURIComponent(selectedId)}/feedback-subscription`, {
        method: 'PUT',
        body: JSON.stringify({ plan_code: feedbackPlanCode.trim(), status: 'active' }),
      })
      pushToast('F.B plan updated', 'success')
      setModal(null)
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'F.B plan change failed', 'danger')
    } finally {
      setModalBusy(false)
    }
  }

  const createInvoice = async () => {
    const gbp = Number(invoiceAmount)
    if (!selectedId) return
    if (!Number.isFinite(gbp) || gbp <= 0) {
      pushToast('Enter a positive invoice amount', 'warning')
      return
    }
    setModalBusy(true)
    try {
      await occ('/invoices', {
        method: 'POST',
        body: JSON.stringify({
          amount_minor: Math.round(gbp * 100),
          invoice_type: invoiceType,
          due_date: invoiceDue || undefined,
          note: invoiceNote.trim() || undefined,
        }),
      })
      pushToast('Invoice created', 'success')
      setModal(null)
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Invoice creation failed', 'danger')
    } finally {
      setModalBusy(false)
    }
  }

  const markInvoicePaid = async (invoiceId) => {
    try {
      await billingInvoice(invoiceId, '/mark-paid', { method: 'POST', body: '{}' })
      pushToast('Invoice marked paid', 'success')
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Mark paid failed', 'danger')
    }
  }

  const resendInvoice = async (invoiceId) => {
    try {
      await occ(`/invoices/${encodeURIComponent(invoiceId)}/resend`, { method: 'POST', body: '{}' })
      pushToast('Invoice email resent', 'success')
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Resend failed', 'danger')
    }
  }

  const reissueInvoice = async (invoiceId) => {
    try {
      await occ(`/invoices/${encodeURIComponent(invoiceId)}/reissue`, { method: 'POST', body: '{}' })
      pushToast('Invoice reissued', 'success')
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Reissue failed', 'danger')
    }
  }

  const openEditInvoice = (inv) => {
    setEditInvoice(inv)
    setEditInvoiceAmount(String((inv.subtotal_pence ?? inv.amount_gbp_pence ?? 0) / 100))
    setEditInvoiceDue(inv.due_date ? String(inv.due_date).slice(0, 10) : '')
    setEditInvoiceDesc(inv.description || '')
    setModal('editInvoice')
  }

  const saveEditInvoice = async () => {
    if (!editInvoice?.id) return
    const gbp = Number(editInvoiceAmount)
    if (!Number.isFinite(gbp) || gbp <= 0) {
      pushToast('Enter a positive amount', 'warning')
      return
    }
    setModalBusy(true)
    try {
      await billingInvoice(editInvoice.id, '', {
        method: 'PATCH',
        body: JSON.stringify({
          amount_minor: Math.round(gbp * 100),
          due_date: editInvoiceDue || undefined,
          description: editInvoiceDesc.trim() || undefined,
        }),
      })
      pushToast('Invoice updated', 'success')
      setModal(null)
      setEditInvoice(null)
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Invoice edit failed', 'danger')
    } finally {
      setModalBusy(false)
    }
  }

  const voidInvoice = async (invoiceId) => {
    const reason = window.prompt('Reason for voiding this invoice (required for audit):', 'Voided by support')
    if (!reason) return
    setActionBusy(`void-${invoiceId}`)
    try {
      await billingInvoice(invoiceId, '/void', {
        method: 'POST',
        body: JSON.stringify({ reason }),
      })
      pushToast('Invoice voided', 'success')
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Void failed', 'danger')
    } finally {
      setActionBusy('')
    }
  }

  const orderAction = async (orderId, action) => {
    if (!selectedId) return
    setActionBusy(`${orderId}-${action}`)
    try {
      await apiFetch(
        `/admin/organisations/${encodeURIComponent(selectedId)}/control-center/campaigns/${encodeURIComponent(orderId)}/${action}`,
        { method: 'POST', body: '{}' },
      )
      pushToast(`Campaign ${action} successful`, 'success')
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || `${action} failed`, 'danger')
    } finally {
      setActionBusy('')
    }
  }

  const retryFailed = async (orderId) => {
    if (!selectedId) return
    setActionBusy(`${orderId}-retry`)
    try {
      await apiFetch(
        `/admin/organisations/${encodeURIComponent(selectedId)}/control-center/campaigns/${encodeURIComponent(orderId)}/retry-failed`,
        { method: 'POST', body: '{}' },
      )
      pushToast('Failed recipients queued for retry', 'success')
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Retry failed', 'danger')
    } finally {
      setActionBusy('')
    }
  }

  const stopAllCampaigns = async () => {
    if (!selectedId) return
    setModalBusy(true)
    try {
      await apiFetch(`/admin/organisations/${encodeURIComponent(selectedId)}/control-center/campaigns/stop-all`, {
        method: 'POST',
        body: '{}',
      })
      pushToast('All campaigns stopped', 'danger')
      setModal(null)
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Stop all failed', 'danger')
    } finally {
      setModalBusy(false)
    }
  }

  const purgeQueue = async () => {
    if (!selectedId) return
    setModalBusy(true)
    try {
      await apiFetch(`/admin/organisations/${encodeURIComponent(selectedId)}/control-center/campaigns/purge-queue`, {
        method: 'POST',
        body: '{}',
      })
      pushToast('Queued campaigns purged', 'danger')
      setModal(null)
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Purge failed', 'danger')
    } finally {
      setModalBusy(false)
    }
  }

  const resumeAllCampaigns = async () => {
    const paused = campaigns.filter((c) => String(c.status || '').toLowerCase() === 'paused')
    if (!paused.length) {
      pushToast('No paused campaigns', 'warning')
      return
    }
    setActionBusy('resume-all')
    try {
      for (const c of paused) {
        await apiFetch(
          `/admin/organisations/${encodeURIComponent(selectedId)}/control-center/campaigns/${encodeURIComponent(c.id)}/resume`,
          { method: 'POST', body: '{}' },
        )
      }
      pushToast('Campaigns resumed', 'success')
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Resume failed', 'danger')
    } finally {
      setActionBusy('')
    }
  }

  const openInvoicePdf = async (invoiceId) => {
    if (!selectedId) return
    try {
      const { apiFetchBlob } = await import('../lib/api')
      const blob = await apiFetchBlob(
        `/admin/organisations/${encodeURIComponent(selectedId)}/control-center/invoices/${encodeURIComponent(invoiceId)}/pdf`,
      )
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank', 'noopener,noreferrer')
      setTimeout(() => URL.revokeObjectURL(url), 60000)
    } catch (e) {
      pushToast(e?.message || 'Could not open invoice PDF', 'danger')
    }
  }

  const exportCsv = () => {
    const header = ['id', 'name', 'status', 'plan', 'wallet', 'calls_remaining', 'wa_remaining', 'usage_pct', 'payment_status', 'campaigns', 'invoices']
    const lines = filteredItems.map((o) =>
      [
        o.id,
        o.name,
        o.status,
        o.plan,
        o.wallet_display || fmtMoneyPence(o.wallet_pence),
        o.calls_remaining,
        o.wa_remaining,
        o.usage_pct,
        o.payment_status,
        o.campaigns,
        o.invoices,
      ]
        .map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`)
        .join(','),
    )
    const blob = new Blob([[header.join(','), ...lines].join('\n')], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `org-control-center-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
    pushToast('CSV exported', 'success')
  }

  const openModal = (type) => {
    if (type === 'package' && (org?.core_plan_code || org?.plan_code)) setPlanCode(org.core_plan_code || org.plan_code)
    if (type === 'feedbackPackage' && org?.feedback_plan_code) setFeedbackPlanCode(org.feedback_plan_code)
    if (type === 'completeDeletion') {
      setDeleteConfirmText('')
      setDeleteAdminNotes('')
    }
    setModal(type)
  }

  const completeAccountDeletion = async () => {
    if (!selectedId || !deletionRequest?.id) return
    if (deleteConfirmText.trim().toUpperCase() !== 'DELETE') {
      pushToast('Type DELETE to confirm', 'danger')
      return
    }
    setModalBusy(true)
    try {
      await apiFetch(`/admin/account-deletions/${encodeURIComponent(deletionRequest.id)}/complete`, {
        method: 'POST',
        body: JSON.stringify({ confirm: 'DELETE', admin_notes: deleteAdminNotes.trim() || undefined }),
      })
      pushToast('Account deletion completed', 'success')
      setModal(null)
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Deletion failed', 'danger')
    } finally {
      setModalBusy(false)
    }
  }

  const hardDeleteAnyUser = async () => {
    const defaultEmail = String(org?.contact_email || org?.billing_email || '').trim()
    const email = window.prompt(
      'TEST ONLY — permanently delete a dashboard user by email.\n' +
        'Solo-member org is wiped; shared orgs keep other members.\n\n' +
        'Enter user email:',
      defaultEmail,
    )
    if (email === null) return
    const trimmed = String(email).trim()
    if (!trimmed) {
      pushToast('Email is required', 'warning')
      return
    }
    const typed = window.prompt(
      `Permanently delete ${trimmed}?\n\nType exactly: HARD_DELETE`,
    )
    if (typed === null) return
    if (String(typed).trim() !== 'HARD_DELETE') {
      pushToast('Cancelled — type HARD_DELETE to confirm', 'warning')
      return
    }
    setActionBusy('hardDeleteUser')
    try {
      const res = await apiFetch('/admin/users/hard-delete-test', {
        method: 'POST',
        body: JSON.stringify({
          email: trimmed,
          confirm: 'HARD_DELETE',
          delete_solo_org: true,
          delete_service_orders: true,
        }),
      })
      const solo = (res?.report?.solo_orgs || []).filter((x) => x?.purged).length
      const shared = (res?.report?.shared_orgs_kept || []).length
      pushToast(
        `Hard deleted ${trimmed}` +
          (solo ? ` · ${solo} solo org wiped` : '') +
          (shared ? ` · ${shared} shared org kept` : ''),
        'success',
      )
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Hard delete failed', 'danger')
    } finally {
      setActionBusy('')
    }
  }

  return (
    <div className="occ">
      <ToastStack toasts={toasts} />

      {error ? (
        <div className="card alertCard" style={{ marginBottom: 16 }}>
          <div className="cardBody alertText">{error}</div>
          <div className="cardBody" style={{ paddingTop: 0 }}>
            <button type="button" className="btn soft" onClick={loadList} disabled={loading}>
              {loading ? 'Retrying…' : 'Retry'}
            </button>
          </div>
        </div>
      ) : null}

      <div className="occ-page-header">
        <div>
          <div className="occ-page-title">Organisation Control Center</div>
          <div className="occ-page-sub">Internal support console · billing, usage, orders &amp; campaigns</div>
        </div>
        <button type="button" className="occ-btn" onClick={refreshAll} disabled={loading}>
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      {!routeOrgId ? (
      <div className="occ-search-bar">
        <div className="occ-search-inner">
          <div className="occ-search-input-wrap">
            <i className="ti ti-search" aria-hidden="true" />
            <input
              type="text"
              placeholder="Search by org name, ID, email, invoice #…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') loadList()
              }}
            />
          </div>
          <select className="occ-filter-sel" value={countryFilter} onChange={(e) => setCountryFilter(e.target.value)}>
            {COUNTRY_OPTIONS.map((c) => (
              <option key={c.value || 'all'} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
          <select className="occ-filter-sel" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">All statuses</option>
            <option value="active">Active</option>
            <option value="frozen">Frozen</option>
          </select>
          <select className="occ-filter-sel" value={planFilter} onChange={(e) => setPlanFilter(e.target.value)}>
            <option value="">All plans</option>
            {plans.map((p) => (
              <option key={p.code || p.id} value={p.code}>
                {p.name || p.code}
              </option>
            ))}
          </select>
          <select className="occ-filter-sel" value={payFilter} onChange={(e) => setPayFilter(e.target.value)}>
            <option value="">All payments</option>
            <option value="paid">Paid</option>
            <option value="due">Due</option>
            <option value="overdue">Overdue</option>
          </select>
          <button type="button" className="occ-btn primary" onClick={loadList}>
            Apply
          </button>
          <div className="occ-chip-wrap">
            {CHIP_KEYS.map(({ key, label }) => (
              <span
                key={key}
                className={`occ-chip ${chips.has(key) ? 'active' : ''}`}
                onClick={() => toggleChip(key)}
                onKeyDown={() => {}}
                role="button"
                tabIndex={0}
              >
                {label}
              </span>
            ))}
          </div>
        </div>
      </div>
      ) : null}

      {!routeOrgId ? (
        <div className="occ-kpi-section">
          <div className="occ-section-eyebrow">KPI overview</div>
          <div className="ds-scope grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <KpiCard icon={Building2} label="Total organisations" value={aggregateKpis.total} tone="primary" index={0} />
            <KpiCard icon={CircleCheck} label="Active" value={aggregateKpis.active} tone="success" index={1} />
            <KpiCard icon={Snowflake} label="Frozen" value={aggregateKpis.frozen} tone="info" index={2} />
            <KpiCard icon={CreditCard} label="Payment due" value={aggregateKpis.paymentDue} tone="warning" index={3} />
            <KpiCard icon={Megaphone} label="Running campaigns" value={aggregateKpis.campaigns} tone="primary" index={4} />
            <KpiCard icon={FileText} label="Open invoices" value={aggregateKpis.invoices} tone="danger" index={5} />
          </div>
        </div>
      ) : null}

      {!routeOrgId ? (
      <div className="occ-table-section">
        <div className="occ-section-header">
          <div className="occ-section-title">
            Organisations <span className="muted">({filteredItems.length})</span>
          </div>
          <button type="button" className="occ-btn" onClick={exportCsv}>
            Export CSV
          </button>
        </div>
        <div className="occ-table-wrap">
          <table className="occ-data-table">
            <thead>
              <tr>
                <th onClick={() => sortTable('id')}>ID</th>
                <th onClick={() => sortTable('name')}>Organisation</th>
                <th>Country</th>
                <th>Status</th>
                <th onClick={() => sortTable('plan')}>Plan</th>
                <th onClick={() => sortTable('wallet')}>Wallet</th>
                <th>Package rem.</th>
                <th>Est. WA</th>
                <th>Est. AI</th>
                <th onClick={() => sortTable('usage_pct')}>Usage</th>
                <th>Payment</th>
                <th>Campaigns</th>
                <th>Invoices</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {!filteredItems.length ? (
                <tr>
                  <td colSpan={14}>
                    <div className="occ-empty-state">No organisations match your filters.</div>
                  </td>
                </tr>
              ) : (
                filteredItems.map((o) => {
                  const selected = selectedId === o.id
                  const pkgRem = o.shared_package_pool
                    ? o.package_remaining_display || fmtMoneyPence(o.package_remaining_pence, o)
                    : '—'
                  return (
                    <tr key={o.id} className={selected ? 'selected' : ''} onClick={() => selectOrg(o.id)}>
                      <td className="occ-mono">{o.id.slice(0, 8)}…</td>
                      <td>
                        <div style={{ fontWeight: 500 }}>{o.name}</div>
                        <div style={{ fontSize: 11, color: 'var(--occ-text3)' }}>{o.contact_email || o.market_label || '—'}</div>
                      </td>
                      <td>{o.market_label || o.country || '—'}</td>
                      <td>{statusBadge(o.status)}</td>
                      <td>
                        <span className="occ-badge occ-badge-gray">{o.plan || '—'}</span>
                      </td>
                      <td className="occ-mono">{o.wallet_display || fmtMoneyPence(o.wallet_pence)}</td>
                      <td className="occ-mono">{pkgRem}</td>
                      <td className="occ-mono">{fmtN(o.estimated_wa_surveys)}</td>
                      <td className="occ-mono">{fmtN(o.estimated_ai_minutes)}</td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                          <div className="occ-usage-bar">
                            <div className={`occ-usage-bar-fill ${barClass(o.usage_pct)}`} style={{ width: `${o.usage_pct || 0}%` }} />
                          </div>
                          <span className="occ-mono" style={{ fontSize: 11 }}>
                            {o.usage_pct || 0}%
                          </span>
                        </div>
                      </td>
                      <td>{statusBadge(o.payment_status)}</td>
                      <td className="occ-mono">{o.campaigns || 0}</td>
                      <td className="occ-mono">{o.invoices || 0}</td>
                      <td onClick={(e) => e.stopPropagation()}>
                        <div className="occ-row-actions">
                          <button type="button" className="occ-btn-xs primary" onClick={() => selectOrg(o.id)}>
                            View
                          </button>
                          <button
                            type="button"
                            className={`occ-btn-xs ${o.status === 'frozen' ? 'success' : 'danger'}`}
                            disabled={actionBusy === o.id}
                            onClick={() => setSuspended(o.id, o.status !== 'frozen')}
                          >
                            {o.status === 'frozen' ? 'Unfreeze' : 'Freeze'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
      ) : null}

      {routeOrgId ? (
        <div className="occ-detail-panel" id="occ-detail-panel">
          <div className="ds-scope" style={{ marginBottom: 12 }}>
            <button
              type="button"
              className="occ-btn"
              onClick={() => navigate('/organisations/all-users')}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
            >
              <ArrowLeft size={15} /> Back to all users
            </button>
          </div>
          <div className="occ-detail-header">
            <div className="occ-detail-org-row">
              <div>
                <div className="occ-detail-org-name">{org?.name || '…'}</div>
                <div className="occ-detail-org-meta">
                  <span className="occ-detail-org-id">{selectedId}</span>
                  {statusBadge(org?.status)}
                  <span className="occ-badge occ-badge-gray">C.P {org?.core_plan || org?.plan || '—'}</span>
                  <span className="occ-badge occ-badge-gray">F.B {org?.feedback_plan || '—'}</span>
                  {org?.market_label ? <span className="muted">{org.market_label}</span> : null}
                  {org?.billing_currency ? (
                    <span className="occ-badge occ-badge-gray">{org.billing_currency}</span>
                  ) : null}
                </div>
              </div>
              <div className="occ-detail-actions">
                <button type="button" className="occ-btn" onClick={() => openModal('funds')}>
                  Add funds
                </button>
                <button type="button" className="occ-btn" onClick={() => openModal('package')}>
                  Change C.P plan
                </button>
                <button type="button" className="occ-btn" onClick={() => openModal('feedbackPackage')}>
                  Change F.B plan
                </button>
                <button type="button" className="occ-btn" onClick={() => openModal('invoice')}>
                  Invoice
                </button>
                <button
                  type="button"
                  className={`occ-btn ${org?.status === 'frozen' ? 'success' : 'danger'}`}
                  onClick={() => (org?.status === 'frozen' ? setSuspended(selectedId, false) : openModal('freeze'))}
                >
                  {org?.status === 'frozen' ? 'Unfreeze account' : 'Freeze account'}
                </button>
                <Link className="occ-btn" to={`/organisations/${encodeURIComponent(selectedId)}`}>
                  Full profile
                </Link>
                <button
                  type="button"
                  className="occ-btn danger"
                  disabled={actionBusy === 'hardDeleteUser'}
                  onClick={() => void hardDeleteAnyUser()}
                >
                  {actionBusy === 'hardDeleteUser' ? 'Deleting…' : 'Hard delete user (TEST)'}
                </button>
                {org?.deletion_status === 'pending' && deletionRequest ? (
                  <button type="button" className="occ-btn danger" onClick={() => openModal('completeDeletion')}>
                    Complete account deletion
                  </button>
                ) : null}
              </div>
            </div>
            {org?.deletion_status === 'pending' && deletionRequest ? (
              <div
                style={{
                  margin: '0 0 12px',
                  padding: '12px 16px',
                  borderRadius: 10,
                  border: '1px solid rgba(220,38,38,0.35)',
                  background: 'rgba(220,38,38,0.06)',
                  fontSize: 13,
                }}
              >
                <strong style={{ color: 'var(--occ-red)' }}>Pending account deletion</strong>
                <div className="muted" style={{ marginTop: 4 }}>
                  Requested by {deletionRequest.requested_by_email || '—'}
                  {deletionRequest.requested_at ? ` · ${fmtWhen(deletionRequest.requested_at)}` : ''}
                </div>
              </div>
            ) : null}
            <div className="occ-tabs">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  className={`occ-tab-btn ${activeTab === t.id ? 'active' : ''}`}
                  onClick={() => setActiveTab(t.id)}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          {detailLoading && !detail ? (
            <div className="occ-tab-content active">
              <div className="occ-empty-state">Loading organisation detail…</div>
            </div>
          ) : null}

          <div className={`occ-tab-content ${activeTab === 'overview' ? 'active' : ''}`}>
            {org ? (
              <div className="occ-kpi-section occ-kpi-section-in-tab">
                <div className="occ-section-eyebrow">Usage & wallet KPIs</div>
                <KpiCards org={org} />
              </div>
            ) : null}
            <div className="occ-overview-layout">
              <div className="occ-overview-grid occ-overview-grid-3">
                <OccInfoBlock
                  title="Account details"
                  action={
                    <Link className="occ-btn-xs" to={`/organisations/${encodeURIComponent(selectedId)}`}>
                      Profile
                    </Link>
                  }
                >
                  <OccInfoRow label="Org ID" value={<span className="occ-mono">{selectedId}</span>} />
                  <OccInfoRow label="Company" value={org?.name || '—'} />
                  <OccInfoRow label="Contact" value={org?.contact_name || '—'} />
                  <OccInfoRow label="Email" value={org?.contact_email || '—'} />
                  <OccInfoRow label="Phone" value={org?.contact_phone || '—'} />
                  <OccInfoRow label="Market" value={org?.market_label || org?.country || '—'} />
                  <OccInfoRow label="Status" value={statusBadge(org?.status)} />
                  <OccInfoRow label="Deletion" value={statusBadge(org?.deletion_status || 'active')} />
                  <OccInfoRow label="Active campaigns" value={fmtN(org?.running_campaigns)} />
                  <OccInfoRow
                    label="Overage"
                    value={org?.allow_overage === false ? 'Blocked' : org?.overage_risk ? 'At risk' : 'Allowed'}
                  />
                </OccInfoBlock>

                <OccInfoBlock
                  title="Billing summary"
                  action={
                    <button type="button" className="occ-btn-xs" onClick={() => setActiveTab('billing')}>
                      Billing tab
                    </button>
                  }
                >
                  <OccInfoRow label="Wallet" value={org?.wallet_display || fmtMoneyPence(org?.wallet_pence, org)} />
                  <OccInfoRow label="Paid (all time)" value={invoiceSummary.paid_display || '—'} />
                  <OccInfoRow label="Outstanding" value={invoiceSummary.outstanding_display || '—'} />
                  <OccInfoRow label="Overdue" value={invoiceSummary.overdue_display || '—'} />
                  <OccInfoRow label="Open invoices" value={fmtN(org?.open_invoices)} />
                  <OccInfoRow label="Payment status" value={statusBadge(org?.payment_status)} />
                  <OccInfoRow label="Last payment" value={org?.last_payment || '—'} />
                  <OccInfoRow label="Last invoice" value={org?.last_invoice || '—'} />
                  <OccInfoRow label="Survey credits" value={fmtN(org?.survey_credits)} />
                  <OccInfoRow label="Interview credits" value={fmtN(org?.interview_credits)} />
                </OccInfoBlock>

                <OccInfoBlock
                  title="Plan & usage"
                  action={
                    <span style={{ display: 'inline-flex', gap: 6, flexWrap: 'wrap' }}>
                      <button type="button" className="occ-btn-xs" onClick={() => openModal('package')}>
                        Change C.P
                      </button>
                      <button type="button" className="occ-btn-xs" onClick={() => openModal('feedbackPackage')}>
                        Change F.B
                      </button>
                    </span>
                  }
                >
                  <OccInfoRow label="C.P plan" value={org?.core_plan_name || org?.core_plan || org?.plan_name || org?.plan || '—'} />
                  <OccInfoRow label="C.P status" value={statusBadge(org?.core_subscription_status || org?.subscription_status)} />
                  <OccInfoRow label="F.B plan" value={org?.feedback_plan_name || org?.feedback_plan || '—'} />
                  <OccInfoRow label="F.B status" value={statusBadge(org?.feedback_subscription_status || 'none')} />
                  <OccInfoRow label="Payment method" value={org?.payment_method || '—'} />
                  <OccInfoRow label="Billing period" value={`${org?.billing_start || '—'} → ${org?.billing_end || '—'}`} />
                  <OccInfoRow label="Overall usage" value={`${org?.usage_pct ?? 0}%`} />
                  <OccInfoRow label="AI calls left" value={fmtN(org?.calls_remaining)} />
                  <OccInfoRow label="WhatsApp left" value={fmtN(org?.wa_remaining)} />
                  <OccInfoRow label="SMS left" value={fmtN(org?.sms_remaining)} />
                  <OccInfoRow
                    label="Next charge"
                    value={org?.amount_next_payment_display || (org?.next_billing_date ? fmtWhen(org.next_billing_date) : '—')}
                  />
                  <OccInfoRow label="Mandate" value={org?.mandate_status || subscriptionFinance?.mandate_status || '—'} />
                </OccInfoBlock>
              </div>

              <div className="occ-overview-grid occ-overview-grid-2">
                <OccInfoBlock title="Support notes">
                  <textarea
                    className="occ-notes-area"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Internal support notes — billing context, escalations, customer requests…"
                  />
                  <div className="occ-info-block-actions">
                    <button type="button" className="occ-btn primary" disabled={notesBusy} onClick={saveNotes}>
                      {notesBusy ? 'Saving…' : 'Save notes'}
                    </button>
                  </div>
                </OccInfoBlock>

                <OccInfoBlock title="Quick tools">
                  <div className="occ-quick-tools">
                    <button type="button" className="occ-btn" onClick={() => { setWalletModalMode('credit'); openModal('funds') }}>
                      Add wallet funds
                    </button>
                    <button type="button" className="occ-btn" onClick={() => { setWalletModalMode('debit'); openModal('funds') }}>
                      Remove wallet funds
                    </button>
                    <button type="button" className="occ-btn" onClick={() => openModal('invoice')}>
                      Create invoice
                    </button>
                    <button type="button" className="occ-btn" onClick={() => setActiveTab('invoices')}>
                      View invoices
                    </button>
                    <button type="button" className="occ-btn" onClick={() => setActiveTab('campaigns')}>
                      Campaign controls
                    </button>
                    <button type="button" className="occ-btn" onClick={() => setActiveTab('activity')}>
                      Activity log
                    </button>
                    <button type="button" className="occ-btn danger" onClick={() => openModal('stopAll')}>
                      Stop all campaigns
                    </button>
                    <button type="button" className="occ-btn success" disabled={actionBusy === 'resume-all'} onClick={resumeAllCampaigns}>
                      Resume paused
                    </button>
                    <Link className="occ-btn" to={`/organisations/${encodeURIComponent(selectedId)}`}>
                      Full org profile
                    </Link>
                    <Link className="occ-btn" to="/billing/refunds">
                      Refunds queue
                    </Link>
                  </div>
                </OccInfoBlock>
              </div>

              {(subscriptionCancellation?.status && subscriptionCancellation.status !== 'none') || refundReviews.length > 0 ? (
                <div className="occ-overview-grid occ-overview-grid-2">
                  {subscriptionCancellation?.status && subscriptionCancellation.status !== 'none' ? (
                    <OccInfoBlock title="Subscription cancellation">
                      <OccInfoRow label="Status" value={statusBadge(subscriptionCancellation?.status || 'none')} />
                      <OccInfoRow label="Effective" value={fmtWhen(subscriptionCancellation?.effective_at) || '—'} />
                      <OccInfoRow label="Unused value" value={subscriptionCancellation?.calculated_unused_value_display || '—'} />
                      <OccInfoRow label="Refund type" value={subscriptionCancellation?.requested_refund_type || '—'} />
                      <p className="occ-muted occ-info-block-note">
                        Bank refunds: Stripe auto when possible; GoCardless manual. Wallet credit available from admin actions.
                      </p>
                      <div className="occ-info-block-actions occ-info-block-actions-wrap">
                        {['scheduled', 'requested'].includes(String(subscriptionCancellation?.status || '').toLowerCase()) ? (
                          <button type="button" className="occ-btn" disabled={actionBusy === 'cancel-reverse'} onClick={reverseCancellation}>
                            Reverse cancellation
                          </button>
                        ) : null}
                        {String(subscriptionCancellation?.status || 'none').toLowerCase() !== 'cancelled' ? (
                          <>
                            <button type="button" className="occ-btn danger" disabled={actionBusy === 'cancel-immediate'} onClick={() => immediateCancellation(false)}>
                              Cancel immediately
                            </button>
                            <button type="button" className="occ-btn" disabled={actionBusy === 'cancel-immediate'} onClick={() => immediateCancellation(true)}>
                              Cancel + wallet credit
                            </button>
                          </>
                        ) : null}
                      </div>
                    </OccInfoBlock>
                  ) : null}

                  {refundReviews.length > 0 ? (
                    <OccInfoBlock title="Refund reviews">
                      {refundReviews.map((review) => (
                        <div key={review.id} className="occ-refund-review-item">
                          <OccInfoRow label="Status" value={statusBadge(review.review_status)} />
                          <OccInfoRow label="Requested" value={review.requested_refund_type} />
                          <OccInfoRow label="Provider" value={review.source_payment_provider || '—'} />
                          <OccInfoRow label="Wallet credit" value={fmtMoneyPence(review.approved_wallet_credit_pence, org)} />
                          {['pending', 'approved'].includes(String(review.review_status || '').toLowerCase()) ? (
                            <div className="occ-info-block-actions occ-info-block-actions-wrap">
                              <button type="button" className="occ-btn-xs" onClick={() => resolveRefundReview(review.id, 'approved', { issue_wallet_credit: true })}>
                                Approve wallet
                              </button>
                              <button type="button" className="occ-btn-xs" onClick={() => resolveRefundReview(review.id, 'completed', { approved_external_refund_pence: review.calculated_unused_value_pence, defaultNote: 'Mark refunded externally' })}>
                                Mark refunded
                              </button>
                              <button type="button" className="occ-btn-xs danger" onClick={() => resolveRefundReview(review.id, 'rejected')}>
                                Reject
                              </button>
                              {review.wallet_transaction_id ? (
                                <button type="button" className="occ-btn-xs" onClick={() => reverseCancellationWalletCredit(review.id)}>
                                  Reverse wallet credit
                                </button>
                              ) : null}
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </OccInfoBlock>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>

          <div className={`occ-tab-content ${activeTab === 'orders' ? 'active' : ''}`}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', marginBottom: 12 }}>
              <input
                type="search"
                className="occ-filter-sel"
                placeholder="Search order ID, VB-CMP, reference, title…"
                value={ordersSearch}
                onChange={(e) => setOrdersSearch(e.target.value)}
                style={{ minWidth: 240, flex: '1 1 220px' }}
              />
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
                Show
                <select className="occ-filter-sel" value={ordersWorkflowFilter} onChange={(e) => setOrdersWorkflowFilter(e.target.value)}>
                  <option value="all">All (default)</option>
                  <option value="completed">Completed</option>
                  <option value="running">Running / scheduled</option>
                  <option value="paid">Paid — any workflow</option>
                </select>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
                Sort
                <select className="occ-filter-sel" value={ordersSort} onChange={(e) => setOrdersSort(e.target.value)}>
                  <option value="amount_desc">Amount (high → low)</option>
                  <option value="amount_asc">Amount (low → high)</option>
                  <option value="date_desc">Date (newest)</option>
                  <option value="date_asc">Date (oldest)</option>
                  <option value="order_asc">Reference A–Z</option>
                  <option value="name_asc">Title A–Z</option>
                </select>
              </label>
              <span className="muted" style={{ fontSize: 12, flex: '1 1 280px' }}>{ORDER_PAYMENT_HELP}</span>
            </div>
            <div className="occ-table-wrap">
              <table className="occ-data-table">
                <thead>
                  <tr>
                    <th style={{ cursor: 'pointer' }} onClick={() => sortOrdersColumn('reference')}>Order</th>
                    <th style={{ cursor: 'pointer' }} onClick={() => sortOrdersColumn('service')}>Service</th>
                    <th style={{ cursor: 'pointer' }} onClick={() => sortOrdersColumn('channel')}>Channel</th>
                    <th style={{ cursor: 'pointer' }} onClick={() => sortOrdersColumn('recipients')}>Recipients</th>
                    <th style={{ cursor: 'pointer' }} onClick={() => sortOrdersColumn('quote')}>Quote</th>
                    <th style={{ cursor: 'pointer' }} onClick={() => sortOrdersColumn('payment')}>Pay status</th>
                    <th style={{ cursor: 'pointer' }} onClick={() => sortOrdersColumn('workflow')}>Workflow</th>
                    <th style={{ cursor: 'pointer' }} onClick={() => sortOrdersColumn('created')}>Created</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {!filteredOrders.length ? (
                    <tr>
                      <td colSpan={9}>
                        <div className="occ-empty-state">No orders match this filter.</div>
                      </td>
                    </tr>
                  ) : (
                    filteredOrders.map((ord) => (
                      <tr key={ord.id}>
                        <td className="occ-mono">{ord.reference_id || ord.campaign_id || `${ord.id?.slice(0, 8)}…`}</td>
                        <td>{ord.service_label || ord.title || '—'}</td>
                        <td>{channelLabel(ord.channel, ord)}</td>
                        <td className="occ-mono">{fmtN(ord.recipient_count)}</td>
                        <td className="occ-mono">{fmtMoneyPence(ord.quote_total_pence)}</td>
                        <td>{statusBadge(ord.payment_status)}</td>
                        <td>{statusBadge(ord.workflow_label || ord.workflow_state || ord.status)}</td>
                        <td style={{ fontSize: 12, color: 'var(--occ-text3)' }}>{fmtWhen(ord.created_at)}</td>
                        <td>
                          <Link className="occ-btn-xs" to={adminOrderViewPath(ord)}>
                            View
                          </Link>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className={`occ-tab-content ${activeTab === 'campaigns' ? 'active' : ''}`}>
            <div className="occ-table-wrap">
              <table className="occ-data-table">
                <thead>
                  <tr>
                    <th>Campaign</th>
                    <th>Type</th>
                    <th>Channel</th>
                    <th>Status</th>
                    <th>Total</th>
                    <th>Done</th>
                    <th>Failed</th>
                    <th>In progress</th>
                    <th>Progress</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {!campaigns.length ? (
                    <tr>
                      <td colSpan={10}>
                        <div className="occ-empty-state">No campaigns for this organisation.</div>
                      </td>
                    </tr>
                  ) : (
                    campaigns.map((c) => {
                      const p = c.progress || {}
                      const total = Number(p.total || c.recipient_count || 0)
                      const done = Number(p.done || 0)
                      const pct = total > 0 ? Math.round((done / total) * 100) : 0
                      const st = String(c.status || '').toLowerCase()
                      return (
                        <tr key={c.id}>
                          <td className="occ-mono">{c.id?.slice(0, 8)}…</td>
                          <td>{c.service_label || '—'}</td>
                          <td>{channelLabel(c.channel)}</td>
                          <td>{statusBadge(c.status)}</td>
                          <td className="occ-mono">{fmtN(total)}</td>
                          <td className="occ-mono">{fmtN(p.done)}</td>
                          <td className="occ-mono">{fmtN(p.failed)}</td>
                          <td className="occ-mono">{fmtN(p.in_progress)}</td>
                          <td>
                            <div className="occ-camp-progress">
                              <div className={`occ-camp-progress-fill ${barClass(pct)}`} style={{ width: `${pct}%` }} />
                            </div>{' '}
                            <span className="occ-mono" style={{ fontSize: 11 }}>
                              {pct}%
                            </span>
                          </td>
                          <td>
                            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                              {st === 'running' ? (
                                <>
                                  <button type="button" className="occ-btn-xs" disabled={!!actionBusy} onClick={() => orderAction(c.id, 'pause')}>
                                    Pause
                                  </button>
                                  <button type="button" className="occ-btn-xs danger" disabled={!!actionBusy} onClick={() => orderAction(c.id, 'stop')}>
                                    Stop
                                  </button>
                                </>
                              ) : null}
                              {st === 'paused' ? (
                                <>
                                  <button type="button" className="occ-btn-xs success" disabled={!!actionBusy} onClick={() => orderAction(c.id, 'resume')}>
                                    Resume
                                  </button>
                                  <button type="button" className="occ-btn-xs danger" disabled={!!actionBusy} onClick={() => orderAction(c.id, 'stop')}>
                                    Stop
                                  </button>
                                </>
                              ) : null}
                              {Number(p.failed || 0) > 0 ? (
                                <button type="button" className="occ-btn-xs" disabled={!!actionBusy} onClick={() => retryFailed(c.id)}>
                                  Retry failed
                                </button>
                              ) : null}
                            </div>
                          </td>
                        </tr>
                      )
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className={`occ-tab-content ${activeTab === 'billing' ? 'active' : ''}`}>
            {org?.next_billing_date || org?.amount_next_payment_display ? (
              <div className="occ-info-block" style={{ marginBottom: 12 }}>
                <div className="occ-info-block-title">Subscription renewal</div>
                <div className="occ-info-row">
                  <span className="occ-info-row-label">Next billing date</span>
                  <span className="occ-info-row-value">{org.next_billing_date ? fmtWhen(org.next_billing_date) : '—'}</span>
                </div>
                <div className="occ-info-row">
                  <span className="occ-info-row-label">Next charge</span>
                  <span className="occ-info-row-value">{org.amount_next_payment_display || '—'}</span>
                </div>
                <div className="occ-info-row">
                  <span className="occ-info-row-label">Mandate</span>
                  <span className="occ-info-row-value">{org.mandate_status || '—'}</span>
                </div>
                {org.cancel_at_period_end ? (
                  <div className="occ-info-row">
                    <span className="occ-info-row-label">Cancellation</span>
                    <span className="occ-info-row-value">Active until period end</span>
                  </div>
                ) : null}
                <Link className="occ-btn" to="/billing/refunds" style={{ marginTop: 8, display: 'inline-block' }}>Global refunds queue</Link>
              </div>
            ) : null}
            <p className="occ-muted" style={{ fontSize: 13, marginBottom: 12 }}>
              Wallet credits, plan changes, and overage settings. To edit or void invoices, open the{' '}
              <button
                type="button"
                style={{ background: 'none', border: 'none', padding: 0, textDecoration: 'underline', cursor: 'pointer', font: 'inherit', color: 'inherit' }}
                onClick={() => setActiveTab('invoices')}
              >
                Invoices
              </button>{' '}
              tab.
            </p>
            <div className="occ-two-col">
              <div className="occ-plan-card">
                <div className="occ-plan-name">{org?.plan_name || org?.plan || '—'}</div>
                <div className="occ-plan-interval">{org?.subscription_status || '—'}</div>
                <div className="occ-plan-features" style={{ marginTop: 16 }}>
                  <div className="occ-plan-feature">AI calls: {fmtN(org?.calls_included)} included</div>
                  <div className="occ-plan-feature">WhatsApp: {fmtN(org?.wa_included)} included</div>
                  <div className="occ-plan-feature">SMS: {fmtN(org?.sms_included)} included</div>
                  <div className="occ-plan-feature">Billing email: {org?.billing_email || org?.contact_email || '—'}</div>
                  <div className="occ-plan-feature">Currency: {org?.billing_currency || '—'}</div>
                  <div className="occ-plan-feature">
                    Overage:{' '}
                    <button type="button" className="occ-btn-xs" disabled={actionBusy === 'overage'} onClick={() => saveOverageSetting(!allowOverage)}>
                      {allowOverage ? 'Enabled — click to disable' : 'Disabled — click to enable'}
                    </button>
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div className="occ-info-block">
                <div className="occ-info-block-title">Commercial balance</div>
                <div className="occ-info-row">
                  <span className="occ-info-row-label">Package remaining</span>
                  <span className="occ-info-row-value">
                    {org?.package_remaining_display || fmtMoneyPence(org?.package_remaining_pence, org)}
                  </span>
                </div>
                <div className="occ-info-row">
                  <span className="occ-info-row-label">Wallet balance</span>
                  <span className="occ-info-row-value">{org?.wallet_display || fmtMoneyPence(org?.wallet_pence, org)}</span>
                </div>
                <div className="occ-info-row">
                  <span className="occ-info-row-label">Est. WA / AI left</span>
                  <span className="occ-info-row-value">
                    {fmtN(org?.estimated_wa_surveys)} / {fmtN(org?.estimated_ai_minutes)} ({org?.estimate_label || '—'})
                  </span>
                </div>
                {org?.next_action_label ? (
                  <div className="occ-info-row">
                    <span className="occ-info-row-label">Next step</span>
                    <span className="occ-info-row-value">{org.next_action_label}</span>
                  </div>
                ) : null}
              </div>
              <div className="occ-info-block">
                <div className="occ-info-block-title">Actual usage this period</div>
                <div className="occ-info-row">
                  <span className="occ-info-row-label">AI calls</span>
                  <span className="occ-info-row-value">
                    {fmtN(org?.calls_used)} / {fmtN(org?.calls_included)}
                  </span>
                </div>
                <div className="occ-info-row">
                  <span className="occ-info-row-label">WhatsApp</span>
                  <span className="occ-info-row-value">
                    {fmtN(org?.wa_used)} / {fmtN(org?.wa_included)}
                  </span>
                </div>
                <div className="occ-info-row">
                  <span className="occ-info-row-label">SMS</span>
                  <span className="occ-info-row-value">
                    {fmtN(org?.sms_used)} / {fmtN(org?.sms_included)}
                  </span>
                </div>
              </div>
              {subscriptionFinance?.tax_country_code || subscriptionFinance?.tax_rate_percent != null ? (
                <div className="occ-info-block">
                  <div className="occ-info-block-title">Tax profile</div>
                  <div className="occ-info-row">
                    <span className="occ-info-row-label">Billing country</span>
                    <span className="occ-info-row-value">{subscriptionFinance.tax_country_code || detail?.billing_profile?.country_code || '—'}</span>
                  </div>
                  <div className="occ-info-row">
                    <span className="occ-info-row-label">VAT / tax rate</span>
                    <span className="occ-info-row-value">
                      {subscriptionFinance.tax_rate_percent != null ? `${subscriptionFinance.tax_rate_percent}%` : '—'}
                    </span>
                  </div>
                  <div className="occ-info-row">
                    <span className="occ-info-row-label">Billing currency</span>
                    <span className="occ-info-row-value">{subscriptionFinance.billing_currency || org?.billing_currency || 'GBP'}</span>
                  </div>
                </div>
              ) : null}
              <div className="occ-info-block">
                <div className="occ-info-block-title">Subscription checkout routing</div>
                <div className="occ-info-row">
                  <span className="occ-info-row-label">Provider override</span>
                  <span className="occ-info-row-value">
                    <select
                      className="occ-input"
                      value={billingPaymentProvider || 'auto'}
                      disabled={actionBusy === 'billing-provider'}
                      onChange={(e) => saveBillingPaymentProvider(e.target.value)}
                      style={{ maxWidth: 220 }}
                    >
                      <option value="auto">Auto (country-based)</option>
                      <option value="gocardless">Force GoCardless</option>
                      <option value="airwallex">Force Airwallex</option>
                      <option value="stripe">Force Stripe</option>
                    </select>
                  </span>
                </div>
                {subscriptionRouting ? (
                  <>
                    <div className="occ-info-row">
                      <span className="occ-info-row-label">Resolved provider</span>
                      <span className="occ-info-row-value">{subscriptionRouting.primary_provider || '—'}</span>
                    </div>
                    <div className="occ-info-row">
                      <span className="occ-info-row-label">Reason</span>
                      <span className="occ-info-row-value" style={{ fontSize: 12 }}>{subscriptionRouting.reason || '—'}</span>
                    </div>
                  </>
                ) : null}
                <p className="occ-muted" style={{ fontSize: 12, marginTop: 8 }}>
                  GoCardless when org country supports Direct Debit and GoCardless is enabled; otherwise Airwallex card checkout.
                </p>
              </div>
              <div className="occ-info-block">
                <div className="occ-info-block-title">
                  Wallet ledger
                  <Link className="occ-btn" to="/billing/wallet-ledger" style={{ marginLeft: 8, fontSize: 11 }}>
                    Global ledger
                  </Link>
                </div>
                {!walletHistory.length ? (
                  <div className="occ-empty-state">No wallet transactions yet.</div>
                ) : (
                  <div className="occ-data-table-wrap">
                    <table className="occ-data-table">
                      <thead>
                        <tr>
                          <th>When</th>
                          <th>Kind</th>
                          <th>Amount</th>
                          <th>Balance</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {walletHistory.map((tx) => (
                          <tr key={tx.id}>
                            <td style={{ fontSize: 12 }}>{fmtWhen(tx.created_at)}</td>
                            <td style={{ fontSize: 12 }}>{tx.kind}</td>
                            <td style={{ fontSize: 12 }}>
                              {tx.direction === 'credit' ? '+' : '-'}
                              {tx.amount_display || fmtMoneyPence(tx.amount_minor, org)}
                            </td>
                            <td style={{ fontSize: 12 }}>{tx.balance_after_display || '—'}</td>
                            <td>
                              <button type="button" className="occ-btn-xs" disabled={actionBusy === `reverse-${tx.id}`} onClick={() => reverseWalletTx(tx.id)}>
                                Reverse
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
              </div>
            </div>
          </div>

          <div className={`occ-tab-content ${activeTab === 'invoices' ? 'active' : ''}`}>
            <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
              <input
                type="search"
                className="occ-input"
                placeholder="Search invoice number or ID…"
                value={invoiceSearch}
                onChange={(e) => setInvoiceSearch(e.target.value)}
                style={{ maxWidth: 280 }}
              />
              {invoiceSearch ? (
                <button type="button" className="occ-btn-xs" onClick={() => setInvoiceSearch('')}>
                  Clear
                </button>
              ) : null}
            </div>
            <p className="occ-muted" style={{ fontSize: 13, marginBottom: 12 }}>
              <strong>Edit</strong> and <strong>Void</strong> unpaid invoices here. Paid, collecting, and disputed invoices are locked — use reissue, refund, or credit instead.
            </p>
            <div className="occ-invoice-summary">
              <div className="occ-inv-stat">
                <div className="occ-inv-stat-label">Total billed ({org?.billing_currency || 'GBP'})</div>
                <div className="occ-inv-stat-value">{invoiceSummary.total_display || moneyDisplay(org, invoiceSummary.total_pence)}</div>
              </div>
              <div className="occ-inv-stat">
                <div className="occ-inv-stat-label">Paid</div>
                <div className="occ-inv-stat-value">{invoiceSummary.paid_display || moneyDisplay(org, invoiceSummary.paid_pence)}</div>
              </div>
              <div className="occ-inv-stat">
                <div className="occ-inv-stat-label">Outstanding</div>
                <div className="occ-inv-stat-value">{invoiceSummary.outstanding_display || moneyDisplay(org, invoiceSummary.outstanding_pence)}</div>
              </div>
              <div className="occ-inv-stat">
                <div className="occ-inv-stat-label">Overdue</div>
                <div className="occ-inv-stat-value">{invoiceSummary.overdue_display || moneyDisplay(org, invoiceSummary.overdue_pence)}</div>
              </div>
            </div>
            <div className="occ-table-wrap">
              <table className="occ-data-table">
                <thead>
                  <tr>
                    <th>Invoice</th>
                    <th>Amount</th>
                    <th>Status</th>
                    <th>Lifecycle</th>
                    <th>Email status</th>
                    <th>Due</th>
                    <th>Issued</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {!filteredInvoices.length ? (
                    <tr>
                      <td colSpan={8}>
                        <div className="occ-empty-state">{invoiceSearch ? 'No invoices match your search.' : 'No invoices found.'}</div>
                      </td>
                    </tr>
                  ) : (
                    filteredInvoices.map((inv) => {
                      const lifecycle = resolveInvoiceLifecycle(inv)
                      return (
                      <tr key={inv.id}>
                        <td className="occ-mono">{inv.invoice_number || inv.id?.slice(0, 8)}</td>
                        <td className="occ-mono">{inv.total_gbp || moneyDisplay(org, inv.amount_gbp_pence)}</td>
                        <td>{statusBadge(inv.status)}</td>
                        <td className="occ-text-xs" title={lifecycle.lock_reason || ''}>
                          {lifecycle.is_locked ? 'Locked' : lifecycle.can_edit ? 'Editable' : 'Open'}
                        </td>
                        <td>{statusBadge(inv.invoice_email_status || (inv.emailed_at ? 'sent' : 'pending'))}</td>
                        <td>{inv.due_date ? fmtWhen(inv.due_date) : '—'}</td>
                        <td>{fmtWhen(inv.created_at)}</td>
                        <td>
                          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                            <button type="button" className="occ-btn-xs" onClick={() => openInvoicePdf(inv.id)}>
                              PDF
                            </button>
                            <button type="button" className="occ-btn-xs" onClick={() => resendInvoice(inv.id)}>
                              Resend
                            </button>
                            {lifecycle.can_edit ? (
                              <button type="button" className="occ-btn-xs" onClick={() => openEditInvoice(inv)}>
                                Edit
                              </button>
                            ) : lifecycle.is_locked ? (
                              lifecycle.suggested_action === 'stop_collection' ? (
                                <button type="button" className="occ-btn-xs" disabled={actionBusy === `stop-dd-${inv.id}`} onClick={() => stopDdCollection(inv.id)}>
                                  Stop DD
                                </button>
                              ) : (
                                <button
                                  type="button"
                                  className="occ-btn-xs"
                                  title={lifecycle.suggested_action_label || lifecycle.lock_reason || ''}
                                  onClick={() => pushToast(lifecycle.suggested_action_label || lifecycle.lock_reason || 'Invoice is locked', 'warning')}
                                >
                                  Locked
                                </button>
                              )
                            ) : null}
                            {lifecycle.can_void ? (
                              <button
                                type="button"
                                className="occ-btn-xs danger"
                                disabled={actionBusy === `void-${inv.id}`}
                                onClick={() => voidInvoice(inv.id)}
                              >
                                Void
                              </button>
                            ) : null}
                            <button type="button" className="occ-btn-xs" onClick={() => reissueInvoice(inv.id)}>
                              Reissue
                            </button>
                            {String(inv.status).toLowerCase() !== 'paid' ? (
                              <>
                                <button type="button" className="occ-btn-xs" disabled={actionBusy === `collect-${inv.id}`} onClick={() => collectInvoice(inv.id, 'wallet')}>
                                  Wallet
                                </button>
                                <button type="button" className="occ-btn-xs" disabled={actionBusy === `collect-${inv.id}`} onClick={() => collectInvoice(inv.id, 'direct_debit')}>
                                  DD
                                </button>
                                <button type="button" className="occ-btn-xs success" onClick={() => markInvoicePaid(inv.id)}>
                                  Mark paid
                                </button>
                              </>
                            ) : (
                              <span className="occ-badge occ-badge-green">Paid</span>
                            )}
                          </div>
                        </td>
                      </tr>
                    )})
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className={`occ-tab-content ${activeTab === 'activity' ? 'active' : ''}`}>
            <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
              <button
                type="button"
                className={`occ-btn-xs ${activityDeletionOnly ? 'primary' : ''}`}
                onClick={() => setActivityDeletionOnly((v) => !v)}
              >
                Deletion
              </button>
            </div>
            {!filteredActivity.length ? (
              <div className="occ-empty-state">No activity recorded.</div>
            ) : (
              filteredActivity.map((ev) => (
                <div key={ev.id} className="occ-activity-item">
                  <div className="occ-activity-dot" style={{ background: 'var(--occ-blue)' }} />
                  <div style={{ flex: 1 }}>
                    <div className="occ-activity-action">{ev.action || ev.event_type}</div>
                    <div className="occ-activity-meta">
                      {[ev.entity_type && ev.entity_id ? `${ev.entity_type}:${ev.entity_id.slice(0, 8)}` : null, ev.detail, ev.actor_email, fmtWhen(ev.created_at)]
                        .filter(Boolean)
                        .join(' · ')}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      ) : null}

      <div
        className={`occ-modal-overlay ${modal ? 'open' : ''}`}
        onClick={(e) => {
          if (e.target === e.currentTarget) setModal(null)
        }}
      >
        {modal ? (
          <div className="occ-modal" role="dialog">
            {modal === 'freeze' ? (
              <>
                <div className="occ-modal-title" style={{ color: 'var(--occ-red)' }}>
                  Freeze account
                </div>
                <div className="occ-modal-sub">
                  This will suspend outbound activity for this organisation. Continue?
                </div>
                <div className="occ-modal-footer">
                  <button type="button" className="occ-btn" onClick={() => setModal(null)}>
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="occ-btn danger"
                    disabled={modalBusy}
                    onClick={async () => {
                      setModalBusy(true)
                      await setSuspended(selectedId, true)
                      setModal(null)
                      setModalBusy(false)
                    }}
                  >
                    Confirm freeze
                  </button>
                </div>
              </>
            ) : null}

            {modal === 'funds' ? (
              <>
                <div className="occ-modal-title">
                  {walletModalMode === 'debit' ? 'Remove wallet funds' : walletModalMode === 'refund' ? 'Refund wallet' : 'Add wallet funds'}
                </div>
                <div className="occ-modal-sub">
                  {walletModalMode === 'debit'
                    ? 'Debit wallet balance with an audit note.'
                    : walletModalMode === 'refund'
                      ? 'Credit wallet as a refund with an audit note.'
                      : `Credit wallet in ${org?.billing_currency || 'org billing currency'}.`}
                </div>
                <label className="occ-modal-label">Amount ({currencySymbol(org?.billing_currency)})</label>
                <input className="occ-modal-input" type="number" min="0" step="0.01" value={fundAmount} onChange={(e) => setFundAmount(e.target.value)} />
                <label className="occ-modal-label">Reason</label>
                <input className="occ-modal-input" type="text" value={fundNote} onChange={(e) => setFundNote(e.target.value)} placeholder="Internal note" />
                <div className="occ-modal-footer">
                  <button type="button" className="occ-btn" onClick={() => setModal(null)}>
                    Cancel
                  </button>
                  <button type="button" className="occ-btn primary" disabled={modalBusy} onClick={applyFunds}>
                    Apply
                  </button>
                </div>
              </>
            ) : null}

            {modal === 'package' ? (
              <>
                <div className="occ-modal-title">Change C.P plan</div>
                <div className="occ-modal-sub">Core Platform subscription — does not change the F.B plan.</div>
                <label className="occ-modal-label">C.P plan</label>
                <PlanPickerSelect
                  value={planCode}
                  onChange={setPlanCode}
                  productLine="core"
                  placeholder="Select Core platform plan…"
                />
                <label className="occ-modal-label">Reason</label>
                <input className="occ-modal-input" type="text" value={planReason} onChange={(e) => setPlanReason(e.target.value)} />
                {upgradePreview ? (
                  <div className="occ-info-block" style={{ marginTop: 10 }}>
                    <div className="occ-info-block-title">Upgrade preview</div>
                    <div className="occ-info-row">
                      <span className="occ-info-row-label">Pro-rata charge</span>
                      <span className="occ-info-row-value">{upgradePreview.pro_rata_display || '—'}</span>
                    </div>
                    <div className="occ-info-row">
                      <span className="occ-info-row-label">New monthly</span>
                      <span className="occ-info-row-value">{upgradePreview.new_monthly_display || '—'}</span>
                    </div>
                  </div>
                ) : null}
                <div className="occ-modal-footer">
                  <button type="button" className="occ-btn" onClick={() => setModal(null)}>
                    Cancel
                  </button>
                  <button type="button" className="occ-btn primary" disabled={modalBusy} onClick={applyPlanChange}>
                    Confirm C.P change
                  </button>
                </div>
              </>
            ) : null}

            {modal === 'feedbackPackage' ? (
              <>
                <div className="occ-modal-title">Change F.B plan</div>
                <div className="occ-modal-sub">Customer Feedback subscription — separate from C.P billing.</div>
                <label className="occ-modal-label">F.B plan</label>
                <PlanPickerSelect
                  value={feedbackPlanCode}
                  onChange={setFeedbackPlanCode}
                  productLine="feedback"
                  marketZone={detail?.organisation?.market_zone || org?.market_zone || 'gb'}
                  placeholder="Select Customer feedback plan…"
                />
                <div className="occ-modal-footer">
                  <button type="button" className="occ-btn" onClick={() => setModal(null)}>
                    Cancel
                  </button>
                  <button type="button" className="occ-btn primary" disabled={modalBusy} onClick={applyFeedbackPlanChange}>
                    Confirm F.B change
                  </button>
                </div>
              </>
            ) : null}

            {modal === 'editInvoice' ? (
              <>
                <div className="occ-modal-title">Edit invoice</div>
                <div className="occ-modal-sub">Only unpaid invoices before collection can be edited.</div>
                <label className="occ-modal-label">Amount ({currencySymbol(org?.billing_currency)} ex VAT subtotal)</label>
                <input className="occ-modal-input" type="number" min="0" step="0.01" value={editInvoiceAmount} onChange={(e) => setEditInvoiceAmount(e.target.value)} />
                <label className="occ-modal-label">Due date</label>
                <input className="occ-modal-input" type="date" value={editInvoiceDue} onChange={(e) => setEditInvoiceDue(e.target.value)} />
                <label className="occ-modal-label">Description</label>
                <input className="occ-modal-input" type="text" value={editInvoiceDesc} onChange={(e) => setEditInvoiceDesc(e.target.value)} />
                <div className="occ-modal-footer">
                  <button type="button" className="occ-btn" onClick={() => setModal(null)}>
                    Cancel
                  </button>
                  <button type="button" className="occ-btn primary" disabled={modalBusy} onClick={saveEditInvoice}>
                    Save changes
                  </button>
                </div>
              </>
            ) : null}

            {modal === 'invoice' ? (
              <>
                <div className="occ-modal-title">Create invoice</div>
                <div className="occ-modal-sub">Manually generate an invoice for this organisation.</div>
                <label className="occ-modal-label">Amount ({currencySymbol(org?.billing_currency)})</label>
                <input className="occ-modal-input" type="number" min="0" step="0.01" value={invoiceAmount} onChange={(e) => setInvoiceAmount(e.target.value)} />
                <label className="occ-modal-label">Due date</label>
                <input className="occ-modal-input" type="date" value={invoiceDue} onChange={(e) => setInvoiceDue(e.target.value)} />
                <label className="occ-modal-label">Notes</label>
                <input className="occ-modal-input" type="text" value={invoiceNote} onChange={(e) => setInvoiceNote(e.target.value)} />
                <div className="occ-modal-footer">
                  <button type="button" className="occ-btn" onClick={() => setModal(null)}>
                    Cancel
                  </button>
                  <button type="button" className="occ-btn primary" disabled={modalBusy} onClick={createInvoice}>
                    Create invoice
                  </button>
                </div>
              </>
            ) : null}

            {modal === 'stopAll' ? (
              <>
                <div className="occ-modal-title" style={{ color: 'var(--occ-red)' }}>
                  Stop all active campaigns
                </div>
                <div className="occ-modal-sub">This halts all running, paused, and scheduled campaigns for this organisation.</div>
                <div className="occ-modal-footer">
                  <button type="button" className="occ-btn" onClick={() => setModal(null)}>
                    Cancel
                  </button>
                  <button type="button" className="occ-btn danger" disabled={modalBusy} onClick={stopAllCampaigns}>
                    Stop all campaigns
                  </button>
                </div>
              </>
            ) : null}

            {modal === 'purge' ? (
              <>
                <div className="occ-modal-title" style={{ color: 'var(--occ-red)' }}>
                  Purge queued campaigns
                </div>
                <div className="occ-modal-sub">Stops all queued/scheduled paid campaigns that have not launched yet.</div>
                <div className="occ-modal-footer">
                  <button type="button" className="occ-btn" onClick={() => setModal(null)}>
                    Cancel
                  </button>
                  <button type="button" className="occ-btn danger" disabled={modalBusy} onClick={purgeQueue}>
                    Purge queue
                  </button>
                </div>
              </>
            ) : null}

            {modal === 'promo' ? (
              <>
                <div className="occ-modal-title">Apply promo / discount</div>
                <label className="occ-modal-label">Promo code</label>
                <input className="occ-modal-input" value={promoCode} onChange={(e) => setPromoCode(e.target.value)} placeholder="PROMOCODE" />
                <div className="occ-modal-footer">
                  <button type="button" className="occ-btn" onClick={() => setModal(null)}>
                    Cancel
                  </button>
                  <button type="button" className="occ-btn primary" disabled={modalBusy} onClick={applyPromo}>
                    Apply promo
                  </button>
                </div>
              </>
            ) : null}

            {modal === 'credits' ? (
              <>
                <div className="occ-modal-title">Adjust service credits</div>
                <label className="occ-modal-label">Reason</label>
                <input className="occ-modal-input" value={fundNote} onChange={(e) => setFundNote(e.target.value)} />
                <div className="occ-modal-footer" style={{ flexWrap: 'wrap' }}>
                  <button type="button" className="occ-btn" onClick={() => setModal(null)}>
                    Cancel
                  </button>
                  <button type="button" className="occ-btn success" disabled={modalBusy} onClick={() => applyCredits('survey', 10)}>
                    +10 survey
                  </button>
                  <button type="button" className="occ-btn success" disabled={modalBusy} onClick={() => applyCredits('interview', 10)}>
                    +10 interview
                  </button>
                  <button type="button" className="occ-btn danger" disabled={modalBusy} onClick={() => applyCredits('survey', -10)}>
                    -10 survey
                  </button>
                </div>
              </>
            ) : null}

            {modal === 'completeDeletion' ? (
              <>
                <div className="occ-modal-title" style={{ color: 'var(--occ-red)' }}>
                  Complete account deletion
                </div>
                <div className="occ-modal-sub">
                  Archives the organisation, anonymizes PII, and retains invoices and audit records. Stop running campaigns first.
                </div>
                <label className="occ-modal-label">Admin notes (optional)</label>
                <textarea
                  className="occ-modal-input"
                  rows={2}
                  value={deleteAdminNotes}
                  onChange={(e) => setDeleteAdminNotes(e.target.value)}
                />
                <label className="occ-modal-label">Type DELETE to confirm</label>
                <input className="occ-modal-input" value={deleteConfirmText} onChange={(e) => setDeleteConfirmText(e.target.value)} />
                <div className="occ-modal-footer">
                  <button type="button" className="occ-btn" onClick={() => setModal(null)}>
                    Cancel
                  </button>
                  <button type="button" className="occ-btn danger" disabled={modalBusy} onClick={() => void completeAccountDeletion()}>
                    {modalBusy ? 'Processing…' : 'Confirm deletion'}
                  </button>
                </div>
              </>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  )
}
