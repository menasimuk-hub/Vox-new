import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { money } from '../lib/billingAdminUtils'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Pill } from '@/components/ui/Badge'
import { KpiCard } from '@/components/ui/KpiCard'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/Tabs'

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

const selectClass =
  'flex h-8 min-w-[140px] rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring'

function StatCard({ label, value, hint, tone = 'primary', pill, pillTone = 'info', index = 0 }) {
  return (
    <KpiCard
      label={label}
      value={value}
      hint={
        <>
          {hint ? <span>{hint}</span> : null}
          {pill ? (
            <span className="ml-1 inline-flex">
              <Pill tone={pillTone}>{pill}</Pill>
            </span>
          ) : null}
        </>
      }
      tone={tone}
      index={index}
    />
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
          <Button type="button" variant="outline" size="sm" className="h-7" onClick={() => openOrganisation(row.org_id)} title="Open organisation">
            <i className="ti ti-building" />
          </Button>
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
        <Button type="button" variant="outline" size="sm" className="h-7" onClick={() => openOrganisation(row.org_id)} title="Open organisation">
          <i className="ti ti-building" />
        </Button>
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
    { id: 'all', label: 'All subscriptions' },
    { id: 'active', label: 'Active & trial' },
    { id: 'pending', label: 'Pending payment' },
    { id: 'past_due', label: 'Past due' },
  ]

  return (
    <div className="ds-scope space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0">
          <h1 className="text-[15px] font-semibold leading-tight text-foreground">{meta.title}</h1>
          <p className="text-[11px] leading-tight text-muted-foreground">{meta.description}</p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" className="h-8" onClick={refresh} disabled={loading}>
            {loading ? 'Loading…' : 'Refresh'}
          </Button>
          {isSubscriptions ? (
            <Button asChild variant="outline" size="sm" className="h-8">
              <Link to="/billing/products?tab=subscription">
                <i className="ti ti-box" /> Plan catalogue
              </Link>
            </Button>
          ) : null}
          <Button asChild variant="outline" size="sm" className="h-8">
            <Link to="/billing/invoices">
              <i className="ti ti-receipt" /> Invoices
            </Link>
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {(isSubscriptions || isReports) && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <StatCard
            label="Active"
            value={n(ov.subscriptions_active)}
            hint={`${n(ov.subscriptions_trial || 0)} on trial`}
            tone="success"
            pill={`${n(ov.subscriptions_total)} total`}
            pillTone="success"
            index={0}
          />
          <StatCard
            label="Pending payment"
            value={n(ov.subscriptions_pending_payment)}
            hint={
              pendingCash.length
                ? `${pendingCash.length} cash approval${pendingCash.length === 1 ? '' : 's'}`
                : 'Awaiting payment or approval'
            }
            tone="warning"
            pill={pendingCash.length ? 'Action needed' : 'Clear'}
            pillTone={pendingCash.length ? 'warning' : 'info'}
            index={1}
          />
          <StatCard
            label="Past due"
            value={n(ov.subscriptions_past_due)}
            hint="Needs follow-up"
            tone="danger"
            pill="Review"
            pillTone="danger"
            index={2}
          />
          <StatCard
            label="Payment mode"
            value={n(ov.subscriptions_production_mode)}
            hint={`${n(ov.subscriptions_test_mode)} in test mode`}
            tone="info"
            pill="Live"
            pillTone="info"
            index={3}
          />
        </div>
      )}

      {isSubscriptions && pendingCash.length > 0 && (
        <Panel
          title="Cash plan changes — approval queue"
          action={<Pill tone="warning">{pendingCash.length}</Pill>}
        >
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
                    <Button
                      type="button"
                      size="sm"
                      className="h-7"
                      disabled={pendingBusy === row.org_id}
                      onClick={() => approveCash(row.org_id)}
                    >
                      Approve
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-7"
                      disabled={pendingBusy === row.org_id}
                      onClick={() => rejectCash(row.org_id)}
                    >
                      Reject
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}

      {isSubscriptions && (
        <>
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList className="h-auto flex-wrap">
              {subscriptionTabs.map((item) => (
                <TabsTrigger key={item.id} value={item.id} className="gap-1.5">
                  {item.label}
                  <Pill tone="neutral">{tabCounts[item.id] ?? 0}</Pill>
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          <Panel
            title="Subscriptions"
            action={
              <span className="text-[11px] text-muted-foreground">
                {filteredSubscriptions.length} subscription{filteredSubscriptions.length === 1 ? '' : 's'}
              </span>
            }
            bodyClassName="space-y-3"
          >
            <div className="flex flex-wrap items-center gap-2">
              <Input
                className="h-8 max-w-xs"
                placeholder="Search organisation, email, or plan…"
                value={filters.search}
                onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
              />
              <select
                className={selectClass}
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
                className={selectClass}
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

            {loading ? <div className="py-6 text-center text-sm text-muted-foreground">Loading subscriptions…</div> : null}
            {!loading && !filteredSubscriptions.length ? (
              <div className="py-6 text-center text-sm text-muted-foreground">No subscriptions match your filters.</div>
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
          </Panel>
        </>
      )}

      {isMandates && (
        <Panel
          title="GoCardless mandates"
          action={<span className="text-[11px] text-muted-foreground">{mandateRows.length} linked</span>}
        >
          {loading ? <div className="py-6 text-center text-sm text-muted-foreground">Loading mandates…</div> : null}
          {!loading && !mandateRows.length ? (
            <div className="py-6 text-center text-sm text-muted-foreground">No GoCardless mandates found yet.</div>
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
        </Panel>
      )}

      {isFailed && (
        <>
          <Panel title="Failed / stuck invoices" action={<Pill tone="danger">{failedInvoices.length}</Pill>}>
            {loading ? <div className="py-6 text-center text-sm text-muted-foreground">Loading invoices…</div> : null}
            {!loading && !failedInvoices.length ? (
              <div className="py-6 text-center text-sm text-muted-foreground">
                No failed, past due, or collecting invoices.
              </div>
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
                      <td>
                        <span className="pill p-amber">{row.status}</span>
                      </td>
                      <td>{money(row.amount_gbp_pence, row.currency)}</td>
                      <td className="muted">
                        {row.dd_retry_count || 0}
                        {row.dd_next_retry_at ? ` · ${dateShort(row.dd_next_retry_at)}` : ''}
                      </td>
                      <td>
                        <Button asChild variant="outline" size="sm" className="h-7">
                          <Link to="/billing/invoices">Open</Link>
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
          </Panel>

          <Panel title="Failed payment events" action={<Pill tone="danger">{failedEvents.length}</Pill>}>
            {loading ? <div className="py-6 text-center text-sm text-muted-foreground">Loading events…</div> : null}
            {!loading && !failedEvents.length ? (
              <div className="py-6 text-center text-sm text-muted-foreground">
                No failed payment events in the recent window.
              </div>
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
            <p className="mt-3 text-[12px] text-muted-foreground">
              For full invoice history, open{' '}
              <Link to="/billing/invoices" className="font-medium text-foreground underline-offset-2 hover:underline">
                Invoices
              </Link>
              .
            </p>
          </Panel>
        </>
      )}

      {isReports && (
        <div className="grid gap-4 lg:grid-cols-2">
          {opsSummary ? (
            <div className="grid grid-cols-2 gap-3 lg:col-span-2 lg:grid-cols-4">
              <StatCard
                label="Pending refunds"
                value={n(opsSummary.pending_refund_queue)}
                hint="Awaiting admin review"
                tone="warning"
                pill="Queue"
                pillTone="warning"
                index={0}
              />
              <StatCard
                label="Failed payments"
                value={n(opsSummary.failed_payments)}
                hint="Recent provider failures"
                tone="danger"
                pill="Review"
                pillTone="danger"
                index={1}
              />
              <StatCard
                label="Billing exceptions"
                value={n(opsSummary.billing_exceptions?.total)}
                hint="Anomalies detected"
                tone="info"
                index={2}
              />
              <StatCard
                label="Wallet liability"
                value={money(opsSummary.wallet_liability_minor)}
                hint="Sum of org wallet balances"
                tone="success"
                index={3}
              />
            </div>
          ) : null}

          <Panel title="Subscription breakdown">
            <div className="divide-y divide-border text-[12.5px]">
              <div className="flex items-center justify-between py-2">
                <span className="text-muted-foreground">Total subscriptions</span>
                <strong className="font-medium">{n(ov.subscriptions_total)}</strong>
              </div>
              <div className="flex items-center justify-between py-2">
                <span className="text-muted-foreground">Active</span>
                <strong className="font-medium">{n(ov.subscriptions_active)}</strong>
              </div>
              <div className="flex items-center justify-between py-2">
                <span className="text-muted-foreground">Trial</span>
                <strong className="font-medium">{n(ov.subscriptions_trial)}</strong>
              </div>
              <div className="flex items-center justify-between py-2">
                <span className="text-muted-foreground">Pending payment</span>
                <strong className="font-medium">{n(ov.subscriptions_pending_payment)}</strong>
              </div>
              <div className="flex items-center justify-between py-2">
                <span className="text-muted-foreground">Past due</span>
                <strong className="font-medium">{n(ov.subscriptions_past_due)}</strong>
              </div>
              <div className="flex items-center justify-between py-2">
                <span className="text-muted-foreground">Latest subscription created</span>
                <strong className="font-medium">{dateText(ov.latest_subscription_created_at)}</strong>
              </div>
            </div>
          </Panel>

          <Panel title="Quick links" bodyClassName="flex flex-wrap gap-2">
            <Button asChild variant="outline" size="sm" className="h-8">
              <Link to="/billing/subscriptions">Subscriptions</Link>
            </Button>
            <Button asChild variant="outline" size="sm" className="h-8">
              <Link to="/billing/invoices">Invoices</Link>
            </Button>
            <Button asChild variant="outline" size="sm" className="h-8">
              <Link to="/billing/products?tab=subscription">Plan catalogue</Link>
            </Button>
            <Button asChild variant="outline" size="sm" className="h-8">
              <Link to="/billing/service-orders">Service orders (cash)</Link>
            </Button>
            <Button asChild variant="outline" size="sm" className="h-8">
              <Link to="/billing/calls-cost">Calls cost</Link>
            </Button>
            <Button asChild variant="outline" size="sm" className="h-8">
              <Link to="/integrations/gocardless">GoCardless integration</Link>
            </Button>
            <Button asChild variant="outline" size="sm" className="h-8">
              <Link to="/billing/refunds">Refunds queue</Link>
            </Button>
            <Button asChild variant="outline" size="sm" className="h-8">
              <Link to="/billing/exceptions">Billing exceptions</Link>
            </Button>
            <Button asChild variant="outline" size="sm" className="h-8">
              <Link to="/billing/wallet-ledger">Wallet ledger</Link>
            </Button>
          </Panel>
        </div>
      )}
    </div>
  )
}
