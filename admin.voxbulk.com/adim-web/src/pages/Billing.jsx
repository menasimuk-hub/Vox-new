import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { money } from '../lib/billingAdminUtils'

const n = (value) => Number(value || 0).toLocaleString()
const dateText = (value) => (value ? new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—')
const dateShort = (value) => (value ? new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—')

const STATUS_OPTIONS = ['', 'active', 'trial', 'pending_payment', 'past_due', 'cancelled']
const PROVIDER_OPTIONS = ['', 'gocardless', 'manual_cash']

function statusPillClass(status) {
  const s = String(status || '').toLowerCase()
  if (s === 'active') return 'p-green'
  if (s === 'trial') return 'p-cyan'
  if (s === 'pending_payment') return 'p-amber'
  if (s === 'past_due' || s === 'cancelled') return 'p-red'
  return ''
}

function providerLabel(provider) {
  const p = String(provider || '').toLowerCase()
  if (p === 'gocardless') return 'GoCardless'
  if (p === 'manual_cash') return 'Cash'
  return provider || '—'
}

function truncate(text, max = 32) {
  const s = String(text || '').trim()
  if (!s) return '—'
  return s.length > max ? `${s.slice(0, max)}…` : s
}

function pageMeta(pathname) {
  if (pathname.includes('/billing/mandates')) {
    return {
      key: 'mandates',
      title: 'Direct debit mandates',
      description: 'GoCardless mandates linked to organisation subscriptions.',
    }
  }
  if (pathname.includes('/billing/failed-payments')) {
    return {
      key: 'failed',
      title: 'Failed payments',
      description: 'Recent payment failures and webhook events that need review.',
    }
  }
  if (pathname.includes('/billing/reports')) {
    return {
      key: 'reports',
      title: 'Revenue reports',
      description: 'Subscription counts and billing health at a glance.',
    }
  }
  return {
    key: 'subscriptions',
    title: 'Subscriptions',
    description: 'Manage organisation plans, pending cash approvals, and subscription status.',
  }
}

function StatCard({ label, value, hint, accent, pill, pillClass = 'p-cyan' }) {
  return (
    <div className="billingStat" style={{ '--accent': accent }}>
      <label>{label}</label>
      <strong>{value}</strong>
      {hint ? <span>{hint}</span> : null}
      {pill ? <span className={`pill billingStatPill ${pillClass}`}>{pill}</span> : null}
    </div>
  )
}

export default function Billing() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const meta = pageMeta(pathname)
  const isSubscriptions = meta.key === 'subscriptions'
  const isMandates = meta.key === 'mandates'
  const isFailed = meta.key === 'failed'
  const isReports = meta.key === 'reports'

  const [overview, setOverview] = useState(null)
  const [subscriptions, setSubscriptions] = useState([])
  const [pendingCash, setPendingCash] = useState([])
  const [events, setEvents] = useState([])
  const [failedInvoices, setFailedInvoices] = useState([])
  const [opsSummary, setOpsSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [pendingBusy, setPendingBusy] = useState('')
  const [tab, setTab] = useState('all')
  const [filters, setFilters] = useState({ search: '', status: '', provider: '' })

  const loadOverview = useCallback(async () => {
    const row = await apiFetch('/admin/billing/overview')
    setOverview(row || null)
  }, [])

  const loadSubscriptions = useCallback(async () => {
    const params = new URLSearchParams({ limit: '250' })
    if (filters.search.trim()) params.set('search', filters.search.trim())
    if (filters.status) params.set('status', filters.status)
    if (filters.provider) params.set('provider', filters.provider)
    const rows = await apiFetch(`/admin/billing/subscriptions?${params.toString()}`)
    setSubscriptions(Array.isArray(rows) ? rows : [])
  }, [filters])

  const loadPending = useCallback(async () => {
    const rows = await apiFetch('/admin/billing/subscriptions/pending-cash').catch(() => [])
    setPendingCash(Array.isArray(rows) ? rows : [])
  }, [])

  const loadEvents = useCallback(async () => {
    const rows = await apiFetch('/admin/billing/payment-events/recent?limit=50').catch(() => [])
    setEvents(Array.isArray(rows) ? rows : [])
    const inv = await apiFetch('/admin/billing/invoices/failed?limit=80').catch(() => ({ items: [] }))
    setFailedInvoices(Array.isArray(inv?.items) ? inv.items : [])
  }, [])

  const loadOpsSummary = useCallback(async () => {
    const row = await apiFetch('/admin/billing/ops-summary').catch(() => null)
    setOpsSummary(row || null)
  }, [])

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      await loadOverview()
      if (isSubscriptions || isMandates) await loadSubscriptions()
      if (isSubscriptions) await loadPending()
      if (isFailed) await loadEvents()
      if (isReports) await loadOpsSummary()
    } catch (e) {
      setError(e?.message || 'Could not load billing data')
    } finally {
      setLoading(false)
    }
  }, [isSubscriptions, isMandates, isFailed, isReports, loadOverview, loadSubscriptions, loadPending, loadEvents, loadOpsSummary])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError('')
      try {
        await loadOverview()
        if (isSubscriptions || isMandates) await loadSubscriptions()
        if (isSubscriptions) await loadPending()
        if (isFailed) await loadEvents()
        if (isReports) await loadOpsSummary()
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load billing data')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [pathname, isSubscriptions, isMandates, isFailed, isReports, loadOverview, loadSubscriptions, loadPending, loadEvents, loadOpsSummary])

  useEffect(() => {
    if (!isSubscriptions && !isMandates) return undefined
    const timer = window.setTimeout(() => {
      loadSubscriptions().catch((e) => setError(e?.message || 'Could not load subscriptions'))
    }, 250)
    return () => window.clearTimeout(timer)
  }, [filters, isSubscriptions, isMandates, loadSubscriptions])

  const approveCash = async (orgId) => {
    setPendingBusy(orgId)
    setError('')
    try {
      await apiFetch(`/admin/billing/subscriptions/${encodeURIComponent(orgId)}/approve-cash`, { method: 'POST' })
      await loadPending()
      await loadSubscriptions()
      await loadOverview()
    } catch (e) {
      setError(e?.message || 'Approve failed')
    } finally {
      setPendingBusy('')
    }
  }

  const rejectCash = async (orgId) => {
    setPendingBusy(orgId)
    setError('')
    try {
      await apiFetch(`/admin/billing/subscriptions/${encodeURIComponent(orgId)}/reject-cash`, { method: 'POST' })
      await loadPending()
      await loadSubscriptions()
      await loadOverview()
    } catch (e) {
      setError(e?.message || 'Reject failed')
    } finally {
      setPendingBusy('')
    }
  }

  const ov = overview || {}
  const failedEvents = useMemo(
    () => events.filter((e) => String(e.status || '').toLowerCase().includes('fail')),
    [events],
  )

  const mandateRows = useMemo(
    () => subscriptions.filter((row) => String(row.payment_provider || '').toLowerCase() === 'gocardless'),
    [subscriptions],
  )

  const filteredSubscriptions = useMemo(() => {
    if (tab === 'pending') {
      return subscriptions.filter((row) => row.status === 'pending_payment')
    }
    if (tab === 'past_due') {
      return subscriptions.filter((row) => row.status === 'past_due')
    }
    if (tab === 'active') {
      return subscriptions.filter((row) => row.status === 'active' || row.status === 'trial')
    }
    return subscriptions
  }, [subscriptions, tab])

  const tabCounts = useMemo(
    () => ({
      all: subscriptions.length,
      active: subscriptions.filter((r) => r.status === 'active' || r.status === 'trial').length,
      pending: subscriptions.filter((r) => r.status === 'pending_payment').length,
      past_due: subscriptions.filter((r) => r.status === 'past_due').length,
    }),
    [subscriptions],
  )

  const openOrganisation = (orgId, billingTab = 'plan') => {
    if (!orgId) return
    localStorage.setItem('voxbulk_admin_selected_org_id', orgId)
    navigate(`/organisations/profile?tab=${billingTab}`)
  }

  const renderSubscriptionRow = (row) => {
    const hasPendingChange = Boolean(row.pending_plan_name)
    return (
      <tr key={row.id} className="billingListRow">
        <td className="billingListOrg">
          <strong title={row.org_name}>{truncate(row.org_name, 28)}</strong>
          <span className="muted billingListSub">{truncate(row.org_email, 30)}</span>
        </td>
        <td>
          <span className="billingPlanName">{row.plan_name}</span>
          <span className="muted billingListSub">{row.plan_code}</span>
        </td>
        <td className="billingListAmount">{money(row.plan_price_gbp_pence, row.billing_currency)}</td>
        <td>
          <span className={`pill billingStatusPill ${statusPillClass(row.status)}`}>{row.status || '—'}</span>
          {hasPendingChange ? (
            <span className="billingPendingChange" title={`Requested: ${row.pending_plan_name}`}>
              → {row.pending_plan_name}
            </span>
          ) : null}
        </td>
        <td>
          <span className="billingTag">{providerLabel(row.payment_provider)}</span>
          {row.payment_mode ? <span className="muted billingListSub">{row.payment_mode}</span> : null}
        </td>
        <td className="muted">
          {dateShort(row.next_billing_date || row.current_period_end)}
          {row.cancel_at_period_end ? <span className="billingPendingChange"> · cancel pending</span> : null}
        </td>
        <td className="billingListAmount">
          {row.amount_next_payment_display
            || (row.amount_next_payment_minor != null ? money(row.amount_next_payment_minor, row.billing_currency) : '—')}
        </td>
        <td className="muted">{dateShort(row.updated_at)}</td>
        <td className="billingListActions">
          <button type="button" className="btn soft xs" onClick={() => openOrganisation(row.org_id)} title="Open organisation">
            <i className="ti ti-building" />
          </button>
        </td>
      </tr>
    )
  }

  const renderMandateRow = (row) => (
    <tr key={row.id} className="billingListRow">
      <td className="billingListOrg">
        <strong title={row.org_name}>{truncate(row.org_name, 28)}</strong>
        <span className="muted billingListSub">{truncate(row.org_email, 30)}</span>
      </td>
      <td>
        <code className="billingCodePill" title={row.external_customer_id || ''}>
          {truncate(row.external_customer_id || '—', 22)}
        </code>
      </td>
      <td>
        <code className="billingCodePill" title={row.external_subscription_id || ''}>
          {truncate(row.external_subscription_id || '—', 22)}
        </code>
      </td>
      <td>{row.plan_name}</td>
      <td>
        <span className={`pill billingStatusPill ${statusPillClass(row.status)}`}>{row.status || '—'}</span>
      </td>
      <td className="muted">{row.payment_mode || '—'}</td>
      <td className="muted">{dateShort(row.updated_at)}</td>
      <td className="billingListActions">
        <button type="button" className="btn soft xs" onClick={() => openOrganisation(row.org_id)} title="Open organisation">
          <i className="ti ti-building" />
        </button>
      </td>
    </tr>
  )

  const renderFailedRow = (row) => (
    <tr key={row.id} className="billingListRow">
      <td className="muted">{dateText(row.created_at)}</td>
      <td>{row.provider || '—'}</td>
      <td>{truncate(row.client_email, 32)}</td>
      <td>
        <span className="pill p-red">{row.status || 'failed'}</span>
      </td>
      <td className="muted" title={row.failure_reason || ''}>
        {truncate(row.failure_reason || '—', 48)}
      </td>
      <td>
        <code className="billingCodePill">{truncate(row.external_event_id, 24)}</code>
      </td>
    </tr>
  )

  const subscriptionTabs = [
    { id: 'all', label: 'All subscriptions', icon: 'ti-users' },
    { id: 'active', label: 'Active & trial', icon: 'ti-circle-check' },
    { id: 'pending', label: 'Pending payment', icon: 'ti-clock' },
    { id: 'past_due', label: 'Past due', icon: 'ti-alert-triangle' },
  ]

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>{meta.title}</h1>
          <p>{meta.description}</p>
        </div>
        <div className="actions">
          <button type="button" className="btn soft" onClick={refresh} disabled={loading}>
            {loading ? 'Loading…' : 'Refresh'}
          </button>
          {isSubscriptions ? (
            <Link className="btn soft" to="/billing/products?tab=subscription">
              <i className="ti ti-box" /> Plan catalogue
            </Link>
          ) : null}
          <Link className="btn soft" to="/billing/invoices">
            <i className="ti ti-receipt" /> Invoices
          </Link>
        </div>
      </div>

      {error ? <div className="note billingErrorNote">{error}</div> : null}

      <div className="billingPageShell">
        <div className="billingHub">
          {(isSubscriptions || isReports) && (
            <div className="billingStats">
              <StatCard
                label="Active"
                value={n(ov.subscriptions_active)}
                hint={`${n(ov.subscriptions_trial || 0)} on trial`}
                accent="#0f766e"
                pill={`${n(ov.subscriptions_total)} total`}
                pillClass="p-green"
              />
              <StatCard
                label="Pending payment"
                value={n(ov.subscriptions_pending_payment)}
                hint={pendingCash.length ? `${pendingCash.length} cash approval${pendingCash.length === 1 ? '' : 's'}` : 'Awaiting payment or approval'}
                accent="#d97706"
                pill={pendingCash.length ? 'Action needed' : 'Clear'}
                pillClass={pendingCash.length ? 'p-amber' : 'p-cyan'}
              />
              <StatCard
                label="Past due"
                value={n(ov.subscriptions_past_due)}
                hint="Needs follow-up"
                accent="#dc2626"
                pill="Review"
                pillClass="p-red"
              />
              <StatCard
                label="Payment mode"
                value={n(ov.subscriptions_production_mode)}
                hint={`${n(ov.subscriptions_test_mode)} in test mode`}
                accent="#0891b2"
                pill="Live"
                pillClass="p-cyan"
              />
            </div>
          )}

          {isSubscriptions && pendingCash.length > 0 && (
            <div className="billingPanel billingPanelHighlight">
              <div className="billingPanelHead">
                <h3>
                  <i className="ti ti-cash" /> Cash plan changes — approval queue
                </h3>
                <span className="pill p-amber">{pendingCash.length}</span>
              </div>
              <div className="billingTableWrap">
                <table className="table billingTable">
                  <thead>
                    <tr>
                      <th>Organisation</th>
                      <th>Current plan</th>
                      <th>Requested plan</th>
                      <th>Price</th>
                      <th>Submitted</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {pendingCash.map((row) => (
                      <tr key={row.subscription_id}>
                        <td>
                          <strong>{row.org_name || row.org_id}</strong>
                        </td>
                        <td>{row.current_plan_name || row.current_plan_code || '—'}</td>
                        <td>{row.pending_plan_name}</td>
                        <td>{money(row.pending_plan_price_gbp_pence, row.billing_currency)}</td>
                        <td className="muted">{dateText(row.updated_at)}</td>
                        <td className="billingListActions">
                          <button
                            type="button"
                            className="btn primary bsm"
                            disabled={pendingBusy === row.org_id}
                            onClick={() => approveCash(row.org_id)}
                          >
                            Approve
                          </button>
                          <button
                            type="button"
                            className="btn soft bsm"
                            disabled={pendingBusy === row.org_id}
                            onClick={() => rejectCash(row.org_id)}
                          >
                            Reject
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {isSubscriptions && (
            <>
              <div className="billingTabBar">
                {subscriptionTabs.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`billingTabBtn${tab === item.id ? ' active' : ''}`}
                    onClick={() => setTab(item.id)}
                  >
                    <i className={`ti ${item.icon}`} />
                    {item.label}
                    <span className="billingTabCount">{tabCounts[item.id] ?? 0}</span>
                  </button>
                ))}
              </div>

              <div className="billingPanel">
                <div className="billingToolbar">
                  <div className="billingToolbarFilters">
                    <input
                      className="input billingSearch"
                      placeholder="Search organisation, email, or plan…"
                      value={filters.search}
                      onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
                    />
                    <select
                      className="input billingSelect"
                      value={filters.status}
                      onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
                    >
                      {STATUS_OPTIONS.map((opt) => (
                        <option key={opt || 'all'} value={opt}>
                          {opt ? opt.replace('_', ' ') : 'All statuses'}
                        </option>
                      ))}
                    </select>
                    <select
                      className="input billingSelect"
                      value={filters.provider}
                      onChange={(e) => setFilters((f) => ({ ...f, provider: e.target.value }))}
                    >
                      {PROVIDER_OPTIONS.map((opt) => (
                        <option key={opt || 'all'} value={opt}>
                          {opt ? providerLabel(opt) : 'All providers'}
                        </option>
                      ))}
                    </select>
                  </div>
                  <span className="muted billingResultCount">
                    {filteredSubscriptions.length} subscription{filteredSubscriptions.length === 1 ? '' : 's'}
                  </span>
                </div>

                <div className="billingTableWrap">
                  {loading ? <div className="billingEmpty muted">Loading subscriptions…</div> : null}
                  {!loading && !filteredSubscriptions.length ? (
                    <div className="billingEmpty muted">No subscriptions match your filters.</div>
                  ) : null}
                  {!loading && filteredSubscriptions.length > 0 ? (
                    <table className="table billingTable">
                      <thead>
                        <tr>
                          <th>Organisation</th>
                          <th>Plan</th>
                          <th>Price</th>
                          <th>Status</th>
                          <th>Provider</th>
                          <th>Renews</th>
                          <th>Next charge</th>
                          <th>Updated</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>{filteredSubscriptions.map(renderSubscriptionRow)}</tbody>
                    </table>
                  ) : null}
                </div>
              </div>
            </>
          )}

          {isMandates && (
            <div className="billingPanel">
              <div className="billingPanelHead">
                <h3>
                  <i className="ti ti-building-bank" /> GoCardless mandates
                </h3>
                <span className="muted">{mandateRows.length} linked</span>
              </div>
              <div className="billingTableWrap">
                {loading ? <div className="billingEmpty muted">Loading mandates…</div> : null}
                {!loading && !mandateRows.length ? (
                  <div className="billingEmpty muted">No GoCardless mandates found yet.</div>
                ) : null}
                {!loading && mandateRows.length > 0 ? (
                  <table className="table billingTable">
                    <thead>
                      <tr>
                        <th>Organisation</th>
                        <th>Customer ID</th>
                        <th>Subscription / mandate ID</th>
                        <th>Plan</th>
                        <th>Status</th>
                        <th>Mode</th>
                        <th>Updated</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>{mandateRows.map(renderMandateRow)}</tbody>
                  </table>
                ) : null}
              </div>
            </div>
          )}

          {isFailed && (
            <>
            <div className="billingPanel" style={{ marginBottom: 16 }}>
              <div className="billingPanelHead">
                <h3>
                  <i className="ti ti-receipt" /> Failed / stuck invoices
                </h3>
                <span className="pill p-red">{failedInvoices.length}</span>
              </div>
              <div className="billingTableWrap">
                {loading ? <div className="billingEmpty muted">Loading invoices…</div> : null}
                {!loading && !failedInvoices.length ? (
                  <div className="billingEmpty muted">No failed, past due, or collecting invoices.</div>
                ) : null}
                {!loading && failedInvoices.length > 0 ? (
                  <table className="table billingTable">
                    <thead>
                      <tr>
                        <th>Invoice</th>
                        <th>Organisation</th>
                        <th>Status</th>
                        <th>Amount</th>
                        <th>DD retries</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {failedInvoices.map((row) => (
                        <tr key={row.id}>
                          <td>{row.invoice_number || row.id?.slice(0, 8)}</td>
                          <td>{row.organisation_name || row.org_name || '—'}</td>
                          <td><span className="pill p-amber">{row.status}</span></td>
                          <td>{money(row.amount_gbp_pence, row.currency)}</td>
                          <td className="muted">{row.dd_retry_count || 0}{row.dd_next_retry_at ? ` · ${dateShort(row.dd_next_retry_at)}` : ''}</td>
                          <td><Link className="btn soft xs" to="/billing/invoices">Open</Link></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : null}
              </div>
            </div>
            <div className="billingPanel">
              <div className="billingPanelHead">
                <h3>
                  <i className="ti ti-alert-circle" /> Failed payment events
                </h3>
                <span className="pill p-red">{failedEvents.length}</span>
              </div>
              <div className="billingTableWrap">
                {loading ? <div className="billingEmpty muted">Loading events…</div> : null}
                {!loading && !failedEvents.length ? (
                  <div className="billingEmpty muted">No failed payment events in the recent window.</div>
                ) : null}
                {!loading && failedEvents.length > 0 ? (
                  <table className="table billingTable">
                    <thead>
                      <tr>
                        <th>When</th>
                        <th>Provider</th>
                        <th>Customer</th>
                        <th>Status</th>
                        <th>Reason</th>
                        <th>Event ID</th>
                      </tr>
                    </thead>
                    <tbody>{failedEvents.map(renderFailedRow)}</tbody>
                  </table>
                ) : null}
              </div>
              <div className="billingPanelFoot muted">
                For full invoice history, open <Link to="/billing/invoices">Invoices</Link>.
              </div>
            </div>
            </>
          )}

          {isReports && (
            <div className="billingReportsGrid">
              {opsSummary ? (
                <div className="billingStatsRow" style={{ gridColumn: '1 / -1' }}>
                  <StatCard
                    label="Pending refunds"
                    value={n(opsSummary.pending_refund_queue)}
                    hint="Awaiting admin review"
                    accent="var(--amber)"
                    pill="Queue"
                    pillClass="p-amber"
                  />
                  <StatCard
                    label="Failed payments"
                    value={n(opsSummary.failed_payments)}
                    hint="Recent provider failures"
                    accent="var(--red)"
                    pill="Review"
                    pillClass="p-red"
                  />
                  <StatCard
                    label="Billing exceptions"
                    value={n(opsSummary.billing_exceptions?.total)}
                    hint="Anomalies detected"
                    accent="var(--cyan)"
                  />
                  <StatCard
                    label="Wallet liability"
                    value={money(opsSummary.wallet_liability_minor)}
                    hint="Sum of org wallet balances"
                    accent="var(--green)"
                  />
                </div>
              ) : null}
              <div className="billingPanel">
                <div className="billingPanelHead">
                  <h3>Subscription breakdown</h3>
                </div>
                <div className="billingReportList">
                  <div className="billingReportRow">
                    <span>Total subscriptions</span>
                    <strong>{n(ov.subscriptions_total)}</strong>
                  </div>
                  <div className="billingReportRow">
                    <span>Active</span>
                    <strong>{n(ov.subscriptions_active)}</strong>
                  </div>
                  <div className="billingReportRow">
                    <span>Trial</span>
                    <strong>{n(ov.subscriptions_trial)}</strong>
                  </div>
                  <div className="billingReportRow">
                    <span>Pending payment</span>
                    <strong>{n(ov.subscriptions_pending_payment)}</strong>
                  </div>
                  <div className="billingReportRow">
                    <span>Past due</span>
                    <strong>{n(ov.subscriptions_past_due)}</strong>
                  </div>
                  <div className="billingReportRow">
                    <span>Latest subscription created</span>
                    <strong>{dateText(ov.latest_subscription_created_at)}</strong>
                  </div>
                </div>
              </div>

              <div className="billingPanel">
                <div className="billingPanelHead">
                  <h3>Quick links</h3>
                </div>
                <div className="billingQuickLinks">
                  <Link className="billingQuickLink" to="/billing/subscriptions">
                    <i className="ti ti-repeat" /> Subscriptions
                  </Link>
                  <Link className="billingQuickLink" to="/billing/invoices">
                    <i className="ti ti-receipt" /> Invoices
                  </Link>
                  <Link className="billingQuickLink" to="/billing/products?tab=subscription">
                    <i className="ti ti-box" /> Plan catalogue
                  </Link>
                  <Link className="billingQuickLink" to="/billing/service-orders">
                    <i className="ti ti-shopping-cart" /> Service orders (cash)
                  </Link>
                  <Link className="billingQuickLink" to="/billing/calls-cost">
                    <i className="ti ti-phone" /> Calls cost
                  </Link>
                  <Link className="billingQuickLink" to="/integrations/gocardless">
                    <i className="ti ti-plug" /> GoCardless integration
                  </Link>
                  <Link className="billingQuickLink" to="/billing/refunds">
                    <i className="ti ti-arrow-back-up" /> Refunds queue
                  </Link>
                  <Link className="billingQuickLink" to="/billing/exceptions">
                    <i className="ti ti-alert-triangle" /> Billing exceptions
                  </Link>
                  <Link className="billingQuickLink" to="/billing/wallet-ledger">
                    <i className="ti ti-wallet" /> Wallet ledger
                  </Link>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
