import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
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

function fmtMoneyPence(pence, orgOrSymbol = '£') {
  const symbol = typeof orgOrSymbol === 'string' ? orgOrSymbol : orgOrSymbol?.currency_symbol || '£'
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

function channelLabel(channel) {
  const ch = String(channel || '').toLowerCase()
  if (ch === 'whatsapp') return 'WhatsApp'
  if (ch === 'sms') return 'SMS'
  if (ch === 'zoom') return 'Zoom'
  if (ch === 'ai_call') return 'AI call'
  if (ch === 'call') return 'Call'
  return ch || '—'
}

function pctUsed(used, included) {
  const inc = Number(included || 0)
  if (inc <= 0) return 0
  return Math.min(100, Math.round((Number(used || 0) / inc) * 100))
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
        <div className="occ-kpi-card-label">Current plan</div>
        <div className="occ-kpi-card-value large">{org.plan || '—'}</div>
        <div className="occ-kpi-card-sub">{org.subscription_status || '—'}</div>
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
  const [notes, setNotes] = useState('')
  const [notesBusy, setNotesBusy] = useState(false)
  const [modal, setModal] = useState(null)
  const [modalBusy, setModalBusy] = useState(false)
  const [fundAmount, setFundAmount] = useState('')
  const [fundNote, setFundNote] = useState('')
  const [planCode, setPlanCode] = useState('')
  const [planReason, setPlanReason] = useState('')
  const [invoiceAmount, setInvoiceAmount] = useState('')
  const [invoiceDue, setInvoiceDue] = useState('')
  const [countryFilter, setCountryFilter] = useState('')
  const [campaignStatusFilter, setCampaignStatusFilter] = useState('')
  const [channelFilter, setChannelFilter] = useState('')
  const [invoiceType, setInvoiceType] = useState('manual')
  const [promoCode, setPromoCode] = useState('')
  const [allowOverage, setAllowOverage] = useState(true)
  const [invoiceNote, setInvoiceNote] = useState('')
  const [editInvoice, setEditInvoice] = useState(null)
  const [editInvoiceAmount, setEditInvoiceAmount] = useState('')
  const [editInvoiceDue, setEditInvoiceDue] = useState('')
  const [editInvoiceDesc, setEditInvoiceDesc] = useState('')
  const [toasts, setToasts] = useState([])
  const [walletHistory, setWalletHistory] = useState([])
  const [walletModalMode, setWalletModalMode] = useState('credit')
  const [actionBusy, setActionBusy] = useState('')

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
      const res = await apiFetch(`/admin/organisations/control-center?${buildQuery()}`)
      setItems(Array.isArray(res?.items) ? res.items : [])
    } catch (e) {
      setError(e?.message || 'Could not load organisations')
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
    apiFetch('/admin/billing/plans')
      .then((rows) => setPlans(Array.isArray(rows) ? rows : []))
      .catch(() => setPlans([]))
  }, [])

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

  const org = detail?.organisation
  const campaigns = detail?.campaigns || []
  const invoices = detail?.invoices || []
  const activity = detail?.activity || []
  const invoiceSummary = detail?.invoice_summary || {}
  const subscriptionCancellation = detail?.subscription_cancellation || null
  const refundReviews = detail?.refund_reviews || []

  const selectOrg = async (id) => {
    setSelectedId(id)
    setActiveTab('overview')
    await loadDetail(id)
    setTimeout(() => {
      document.getElementById('occ-detail-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 80)
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

  const immediateCancellation = async (issueWalletCredit = false) => {
    if (!selectedId) return
    const note = window.prompt('Admin note for immediate cancellation:', 'Admin immediate cancellation')
    if (!note) return
    setActionBusy('cancel-immediate')
    try {
      await occ('/cancellation/immediate', {
        method: 'POST',
        body: JSON.stringify({ note, issue_wallet_credit: issueWalletCredit }),
      })
      pushToast(issueWalletCredit ? 'Cancelled immediately with wallet credit' : 'Cancelled immediately', 'success')
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
    setActionBusy(`refund-${reviewId}`)
    try {
      await occ(`/refund-reviews/${encodeURIComponent(reviewId)}/resolve`, {
        method: 'POST',
        body: JSON.stringify({ review_status: reviewStatus, admin_notes: adminNotes, ...extra }),
      })
      pushToast(`Refund review ${reviewStatus}`, 'success')
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

  const applyPlanChange = async () => {
    if (!selectedId || !planCode.trim()) {
      pushToast('Select a plan', 'warning')
      return
    }
    setModalBusy(true)
    try {
      await apiFetch(`/admin/organisations/${encodeURIComponent(selectedId)}/subscription`, {
        method: 'PUT',
        body: JSON.stringify({ plan_code: planCode.trim(), status: 'active' }),
      })
      pushToast('Plan updated', 'success')
      setModal(null)
      await refreshAll()
    } catch (e) {
      pushToast(e?.message || 'Plan change failed', 'danger')
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
    if (type === 'package' && org?.plan_code) setPlanCode(org.plan_code)
    setModal(type)
  }

  return (
    <div className="occ">
      <ToastStack toasts={toasts} />

      {error ? (
        <div className="card alertCard" style={{ marginBottom: 16 }}>
          <div className="cardBody alertText">{error}</div>
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

      <div className="occ-search-bar">
        <div className="occ-search-inner">
          <div className="occ-search-input-wrap">
            <i className="ti ti-search" aria-hidden="true" />
            <input
              type="text"
              placeholder="Search by org name, ID, email…"
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

      <div className="occ-kpi-section">
        <div className="occ-section-eyebrow">Selected organisation — KPI overview</div>
        <KpiCards org={org || items.find((x) => x.id === selectedId)} />
      </div>

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

      {selectedId && (detail || detailLoading) ? (
        <div className="occ-detail-panel" id="occ-detail-panel">
          <div className="occ-detail-header">
            <div className="occ-detail-org-row">
              <div>
                <div className="occ-detail-org-name">{org?.name || '…'}</div>
                <div className="occ-detail-org-meta">
                  <span className="occ-detail-org-id">{selectedId}</span>
                  {statusBadge(org?.status)}
                  <span className="occ-badge occ-badge-gray">{org?.plan || '—'}</span>
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
                  Change plan
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
              </div>
            </div>
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
            <div className="occ-two-col">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div className="occ-info-block">
                  <div className="occ-info-block-title">Account details</div>
                  <div className="occ-info-row">
                    <span className="occ-info-row-label">Org ID</span>
                    <span className="occ-info-row-value">{selectedId}</span>
                  </div>
                  <div className="occ-info-row">
                    <span className="occ-info-row-label">Contact</span>
                    <span className="occ-info-row-value">{org?.contact_name || '—'}</span>
                  </div>
                  <div className="occ-info-row">
                    <span className="occ-info-row-label">Email</span>
                    <span className="occ-info-row-value">{org?.contact_email || '—'}</span>
                  </div>
                  <div className="occ-info-row">
                    <span className="occ-info-row-label">Phone</span>
                    <span className="occ-info-row-value">{org?.contact_phone || '—'}</span>
                  </div>
                  <div className="occ-info-row">
                    <span className="occ-info-row-label">Status</span>
                    <span className="occ-info-row-value">{statusBadge(org?.status)}</span>
                  </div>
                  <div className="occ-info-row">
                    <span className="occ-info-row-label">Active campaigns</span>
                    <span className="occ-info-row-value">{org?.running_campaigns ?? 0}</span>
                  </div>
                  <div className="occ-info-row">
                    <span className="occ-info-row-label">Billing period</span>
                    <span className="occ-info-row-value">
                      {org?.billing_start || '—'} – {org?.billing_end || '—'}
                    </span>
                  </div>
                </div>
                <div className="occ-info-block">
                  <div className="occ-info-block-title">Support notes</div>
                  <textarea className="occ-notes-area" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Add internal support notes here…" />
                  <div style={{ marginTop: 10 }}>
                    <button type="button" className="occ-btn primary" disabled={notesBusy} onClick={saveNotes}>
                      {notesBusy ? 'Saving…' : 'Save notes'}
                    </button>
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div className="occ-info-block">
                  <div className="occ-info-block-title">Billing summary</div>
                  <div className="occ-info-row">
                    <span className="occ-info-row-label">Wallet</span>
                    <span className="occ-info-row-value">{org?.wallet_display || fmtMoneyPence(org?.wallet_pence)}</span>
                  </div>
                  <div className="occ-info-row">
                    <span className="occ-info-row-label">Survey credits</span>
                    <span className="occ-info-row-value">{fmtN(org?.survey_credits)}</span>
                  </div>
                  <div className="occ-info-row">
                    <span className="occ-info-row-label">Interview credits</span>
                    <span className="occ-info-row-value">{fmtN(org?.interview_credits)}</span>
                  </div>
                  <div className="occ-info-row">
                    <span className="occ-info-row-label">Payment status</span>
                    <span className="occ-info-row-value">{statusBadge(org?.payment_status)}</span>
                  </div>
                  <div className="occ-info-row">
                    <span className="occ-info-row-label">Last payment</span>
                    <span className="occ-info-row-value">{org?.last_payment || '—'}</span>
                  </div>
                  <div className="occ-info-row">
                    <span className="occ-info-row-label">Open invoices</span>
                    <span className="occ-info-row-value">{org?.open_invoices ?? 0}</span>
                  </div>
                </div>
                <div className="occ-info-block">
                  <div className="occ-info-block-title">Subscription cancellation</div>
                  <div className="occ-info-row">
                    <span className="occ-info-row-label">Status</span>
                    <span className="occ-info-row-value">{statusBadge(subscriptionCancellation?.status || 'none')}</span>
                  </div>
                  <div className="occ-info-row">
                    <span className="occ-info-row-label">Effective date</span>
                    <span className="occ-info-row-value">{fmtWhen(subscriptionCancellation?.effective_at) || '—'}</span>
                  </div>
                  <div className="occ-info-row">
                    <span className="occ-info-row-label">Unused value (est.)</span>
                    <span className="occ-info-row-value">{subscriptionCancellation?.calculated_unused_value_display || '—'}</span>
                  </div>
                  <div className="occ-info-row">
                    <span className="occ-info-row-label">Refund preference</span>
                    <span className="occ-info-row-value">{subscriptionCancellation?.requested_refund_type || '—'}</span>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 10 }}>
                    {['scheduled', 'requested'].includes(String(subscriptionCancellation?.status || '').toLowerCase()) ? (
                      <button type="button" className="occ-btn" disabled={actionBusy === 'cancel-reverse'} onClick={reverseCancellation}>
                        Reverse scheduled cancellation
                      </button>
                    ) : null}
                    {String(subscriptionCancellation?.status || 'none').toLowerCase() !== 'cancelled' ? (
                      <>
                        <button type="button" className="occ-btn danger" disabled={actionBusy === 'cancel-immediate'} onClick={() => immediateCancellation(false)}>
                          Cancel immediately (admin)
                        </button>
                        <button type="button" className="occ-btn" disabled={actionBusy === 'cancel-immediate'} onClick={() => immediateCancellation(true)}>
                          Cancel now + wallet credit
                        </button>
                      </>
                    ) : null}
                  </div>
                </div>
                <div className="occ-info-block">
                  <div className="occ-info-block-title">Refund reviews</div>
                  {!refundReviews.length ? (
                    <div className="occ-empty-state" style={{ padding: '12px 0' }}>No refund review cases.</div>
                  ) : (
                    refundReviews.map((review) => (
                      <div key={review.id} style={{ borderTop: '1px solid var(--occ-border)', paddingTop: 10, marginTop: 10 }}>
                        <div className="occ-info-row">
                          <span className="occ-info-row-label">Status</span>
                          <span className="occ-info-row-value">{statusBadge(review.review_status)}</span>
                        </div>
                        <div className="occ-info-row">
                          <span className="occ-info-row-label">Requested</span>
                          <span className="occ-info-row-value">{review.requested_refund_type}</span>
                        </div>
                        <div className="occ-info-row">
                          <span className="occ-info-row-label">Provider</span>
                          <span className="occ-info-row-value">{review.source_payment_provider || '—'}</span>
                        </div>
                        <div className="occ-info-row">
                          <span className="occ-info-row-label">Payment ref</span>
                          <span className="occ-info-row-value occ-mono">{review.source_payment_reference || '—'}</span>
                        </div>
                        <div className="occ-info-row">
                          <span className="occ-info-row-label">Wallet credit</span>
                          <span className="occ-info-row-value">{fmtMoneyPence(review.approved_wallet_credit_pence)}</span>
                        </div>
                        <div className="occ-info-row">
                          <span className="occ-info-row-label">External refund</span>
                          <span className="occ-info-row-value">{fmtMoneyPence(review.approved_external_refund_pence)}</span>
                        </div>
                        {['pending', 'approved'].includes(String(review.review_status || '').toLowerCase()) ? (
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                            <button type="button" className="occ-btn-xs" onClick={() => resolveRefundReview(review.id, 'approved', { issue_wallet_credit: true })}>
                              Approve wallet credit
                            </button>
                            <button type="button" className="occ-btn-xs" onClick={() => resolveRefundReview(review.id, 'completed', { approved_external_refund_pence: review.calculated_unused_value_pence, defaultNote: 'Mark refunded externally' })}>
                              Mark refunded externally
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
                    ))
                  )}
                </div>
                <div className="occ-info-block">
                  <div className="occ-info-block-title">Quick actions</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <button type="button" className="occ-btn" onClick={() => { setWalletModalMode('credit'); openModal('funds') }}>
                      Add wallet funds
                    </button>
                    <button type="button" className="occ-btn" onClick={() => { setWalletModalMode('debit'); openModal('funds') }}>
                      Remove wallet funds
                    </button>
                    <button type="button" className="occ-btn" onClick={() => { setWalletModalMode('refund'); openModal('funds') }}>
                      Refund wallet
                    </button>
                    <button type="button" className="occ-btn" onClick={() => openModal('package')}>
                      Change plan
                    </button>
                    <button type="button" className="occ-btn" onClick={() => openModal('invoice')}>
                      Create invoice
                    </button>
                    <button type="button" className="occ-btn danger" onClick={() => openModal('stopAll')}>
                      Stop all campaigns
                    </button>
                    <button type="button" className="occ-btn danger" onClick={() => openModal('purge')}>
                      Purge queued campaigns
                    </button>
                    <button type="button" className="occ-btn success" disabled={actionBusy === 'resume-all'} onClick={resumeAllCampaigns}>
                      Resume paused campaigns
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className={`occ-tab-content ${activeTab === 'orders' ? 'active' : ''}`}>
            <div className="occ-table-wrap">
              <table className="occ-data-table">
                <thead>
                  <tr>
                    <th>Order</th>
                    <th>Service</th>
                    <th>Channel</th>
                    <th>Recipients</th>
                    <th>Quote</th>
                    <th>Pay status</th>
                    <th>Workflow</th>
                    <th>Created</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {!campaigns.length ? (
                    <tr>
                      <td colSpan={9}>
                        <div className="occ-empty-state">No orders found.</div>
                      </td>
                    </tr>
                  ) : (
                    campaigns.map((ord) => (
                      <tr key={ord.id}>
                        <td className="occ-mono">{ord.id?.slice(0, 8)}…</td>
                        <td>{ord.service_label || ord.title || '—'}</td>
                        <td>{channelLabel(ord.channel)}</td>
                        <td className="occ-mono">{fmtN(ord.recipient_count)}</td>
                        <td className="occ-mono">{fmtMoneyPence(ord.quote_total_pence)}</td>
                        <td>{statusBadge(ord.payment_status)}</td>
                        <td>{statusBadge(ord.workflow_label || ord.workflow_state || ord.status)}</td>
                        <td style={{ fontSize: 12, color: 'var(--occ-text3)' }}>{fmtWhen(ord.created_at)}</td>
                        <td>
                          <Link className="occ-btn-xs" to={`/billing/service-orders?order=${ord.id}`}>
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
              <div className="occ-info-block">
                <div className="occ-info-block-title">Wallet history</div>
                {!walletHistory.length ? (
                  <div className="occ-empty-state">No wallet transactions yet.</div>
                ) : (
                  walletHistory.slice(0, 20).map((tx) => (
                    <div key={tx.id} className="occ-info-row">
                      <span className="occ-info-row-label">
                        {tx.kind} · {fmtWhen(tx.created_at)}
                        {tx.invoice_id ? ` · inv ${String(tx.invoice_id).slice(0, 8)}` : tx.order_id ? ` · ord ${String(tx.order_id).slice(0, 8)}` : ''}
                      </span>
                      <span className="occ-info-row-value" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        {tx.direction === 'credit' ? '+' : '-'}
                        {tx.amount_display || fmtMoneyPence(tx.amount_minor, org)}
                        <button type="button" className="occ-btn-xs" disabled={actionBusy === `reverse-${tx.id}`} onClick={() => reverseWalletTx(tx.id)}>
                          Reverse
                        </button>
                      </span>
                    </div>
                  ))
                )}
              </div>
              </div>
            </div>
          </div>

          <div className={`occ-tab-content ${activeTab === 'invoices' ? 'active' : ''}`}>
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
                  {!invoices.length ? (
                    <tr>
                      <td colSpan={8}>
                        <div className="occ-empty-state">No invoices found.</div>
                      </td>
                    </tr>
                  ) : (
                    invoices.map((inv) => {
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
                              <button
                                type="button"
                                className="occ-btn-xs"
                                title={lifecycle.suggested_action_label || lifecycle.lock_reason || ''}
                                onClick={() => pushToast(lifecycle.suggested_action_label || lifecycle.lock_reason || 'Invoice is locked', 'warning')}
                              >
                                Locked
                              </button>
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
                                  Collect (wallet)
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
            {!activity.length ? (
              <div className="occ-empty-state">No activity recorded.</div>
            ) : (
              activity.map((ev) => (
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
                <label className="occ-modal-label">Amount (£)</label>
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
                <div className="occ-modal-title">Change plan</div>
                <div className="occ-modal-sub">Select a new subscription plan for this organisation.</div>
                <label className="occ-modal-label">New plan</label>
                <select className="occ-modal-input" value={planCode} onChange={(e) => setPlanCode(e.target.value)}>
                  <option value="">Select plan…</option>
                  {plans.map((p) => (
                    <option key={p.code} value={p.code}>
                      {p.name || p.code}
                    </option>
                  ))}
                </select>
                <label className="occ-modal-label">Reason</label>
                <input className="occ-modal-input" type="text" value={planReason} onChange={(e) => setPlanReason(e.target.value)} />
                <div className="occ-modal-footer">
                  <button type="button" className="occ-btn" onClick={() => setModal(null)}>
                    Cancel
                  </button>
                  <button type="button" className="occ-btn primary" disabled={modalBusy} onClick={applyPlanChange}>
                    Confirm change
                  </button>
                </div>
              </>
            ) : null}

            {modal === 'editInvoice' ? (
              <>
                <div className="occ-modal-title">Edit invoice</div>
                <div className="occ-modal-sub">Only unpaid invoices before collection can be edited.</div>
                <label className="occ-modal-label">Amount (£ ex VAT subtotal)</label>
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
                <label className="occ-modal-label">Amount (£)</label>
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
          </div>
        ) : null}
      </div>
    </div>
  )
}
