import React, { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'

const money = (pence, currency = 'GBP') => {
  const amount = Number(pence || 0) / 100
  try {
    return new Intl.NumberFormat('en-GB', { style: 'currency', currency: currency || 'GBP' }).format(amount)
  } catch {
    return `£${amount.toFixed(2)}`
  }
}
const n = (value) => Number(value || 0).toLocaleString()
const dateText = (value) => (value ? new Date(value).toLocaleString() : '—')

export default function Billing() {
  const [state, setState] = useState({ loading: true, error: '', overview: null, plans: [], invoices: [], events: [] })
  const [pendingCash, setPendingCash] = useState([])
  const [pendingBusy, setPendingBusy] = useState('')

  useEffect(() => {
    let cancelled = false
    async function load() {
      setState((s) => ({ ...s, loading: true, error: '' }))
      const [overview, plans, invoices, events, pending] = await Promise.all([
        apiFetch('/admin/billing/overview'),
        apiFetch('/admin/billing/plans'),
        apiFetch('/admin/billing/invoices/recent?limit=20').catch(() => []),
        apiFetch('/admin/billing/payment-events/recent?limit=20').catch(() => []),
        apiFetch('/admin/billing/subscriptions/pending-cash').catch(() => []),
      ])
      if (!cancelled) {
        setState({
          loading: false,
          error: '',
          overview,
          plans: Array.isArray(plans) ? plans : [],
          invoices: Array.isArray(invoices) ? invoices : [],
          events: Array.isArray(events) ? events : [],
        })
        setPendingCash(Array.isArray(pending) ? pending : [])
      }
    }
    load().catch((e) => {
      if (!cancelled) {
        setState({
          loading: false,
          error: e?.message || 'Could not load billing overview',
          overview: null,
          plans: [],
          invoices: [],
          events: [],
        })
      }
    })
    return () => {
      cancelled = true
    }
  }, [])

  const refreshPending = async () => {
    const pending = await apiFetch('/admin/billing/subscriptions/pending-cash').catch(() => [])
    setPendingCash(Array.isArray(pending) ? pending : [])
  }

  const approveCash = async (orgId) => {
    setPendingBusy(orgId)
    try {
      await apiFetch(`/admin/billing/subscriptions/${encodeURIComponent(orgId)}/approve-cash`, { method: 'POST' })
      await refreshPending()
    } catch (e) {
      setState((s) => ({ ...s, error: e?.message || 'Approve failed' }))
    } finally {
      setPendingBusy('')
    }
  }

  const rejectCash = async (orgId) => {
    setPendingBusy(orgId)
    try {
      await apiFetch(`/admin/billing/subscriptions/${encodeURIComponent(orgId)}/reject-cash`, { method: 'POST' })
      await refreshPending()
    } catch (e) {
      setState((s) => ({ ...s, error: e?.message || 'Reject failed' }))
    } finally {
      setPendingBusy('')
    }
  }

  const overview = state.overview || {}
  const failedEvents = useMemo(() => state.events.filter((e) => String(e.status || '').toLowerCase().includes('fail')), [state.events])

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>Billing & Finance</h1>
          <p>
            Live billing overview. Cash (testing) subscription changes require admin approval. GoCardless sandbox
            payments activate automatically.
          </p>
        </div>
        <div className="actions">
          <button className="btn soft" disabled>
            {state.loading ? 'Loading…' : 'Live DB data'}
          </button>
          <button className="btn primary" onClick={() => { window.location.href = '/billing/products' }}>
            Open Products hub
          </button>
        </div>
      </div>

      {state.error ? <div className="note" style={{ marginBottom: 16 }}>{state.error}</div> : null}

      <div className="grid-4" style={{ marginBottom: 16 }}>
        <div className="card stat" style={{ '--accent': '#0f766e' }}>
          <div className="muted">Active subscriptions</div>
          <div className="statValue">{n(overview.subscriptions_active)}</div>
          <span className="pill p-green">{n(overview.subscriptions_total)} total</span>
        </div>
        <div className="card stat" style={{ '--accent': '#0891b2' }}>
          <div className="muted">Plans</div>
          <div className="statValue">{n(overview.plans_total || state.plans.length)}</div>
          <span className="pill p-cyan">Editable packages</span>
        </div>
        <div className="card stat" style={{ '--accent': '#d97706' }}>
          <div className="muted">Pending payments</div>
          <div className="statValue">{n(overview.subscriptions_pending_payment)}</div>
          <span className="pill p-amber">GC + cash pending</span>
        </div>
        <div className="card stat" style={{ '--accent': '#dc2626' }}>
          <div className="muted">Past due / failed</div>
          <div className="statValue">{n((overview.subscriptions_past_due || 0) + failedEvents.length)}</div>
          <span className="pill p-red">Needs review</span>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="cardHead">
          <h3>Cash subscription approvals</h3>
          <span className="pill p-amber">{n(pendingCash.length)}</span>
        </div>
        <div className="cardBody">
          {!pendingCash.length ? (
            <div className="muted">No cash subscription changes waiting for approval.</div>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Organisation</th>
                  <th>Current plan</th>
                  <th>Requested plan</th>
                  <th>Price</th>
                  <th>Submitted</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {pendingCash.map((row) => (
                  <tr key={row.subscription_id}>
                    <td>{row.org_name || row.org_id}</td>
                    <td>{row.current_plan_name || row.current_plan_code || '—'}</td>
                    <td>{row.pending_plan_name}</td>
                    <td>{money(row.pending_plan_price_gbp_pence)}</td>
                    <td>{dateText(row.updated_at)}</td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <button
                        type="button"
                        className="btn primary bsm"
                        disabled={pendingBusy === row.org_id}
                        onClick={() => approveCash(row.org_id)}
                      >
                        Approve
                      </button>{' '}
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
          )}
        </div>
      </div>

      <div className="grid-12">
        <div className="span-8 card">
          <div className="cardHead">
            <h3>Plan catalogue</h3>
            <span className="pill p-cyan">DB-backed</span>
          </div>
          <div className="cardBody">
            <table className="table">
              <thead>
                <tr>
                  <th>Plan</th>
                  <th>Code</th>
                  <th>Price</th>
                  <th>Interval</th>
                  <th>Description</th>
                </tr>
              </thead>
              <tbody>
                {state.plans.length ? (
                  state.plans.map((p) => (
                    <tr key={p.id}>
                      <td>{p.name}</td>
                      <td>{p.code}</td>
                      <td>{money(p.price_gbp_pence)}</td>
                      <td>{p.interval}</td>
                      <td>{p.description || '—'}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5}>No plans found.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="span-4 stack">
          <div className="card">
            <div className="cardHead"><h3>Billing reality check</h3></div>
            <div className="cardBody">
              <div className="list">
                <div className="listRow"><span>Latest subscription</span><strong>{dateText(overview.latest_subscription_created_at)}</strong></div>
                <div className="listRow"><span>Test/manual mode</span><strong>{n(overview.subscriptions_test_mode)}</strong></div>
                <div className="listRow"><span>Production mode</span><strong>{n(overview.subscriptions_production_mode)}</strong></div>
                <div className="listRow"><span>Service order cash</span><strong><button className="btn soft" onClick={() => { window.location.href = '/billing/service-orders' }}>Open</button></strong></div>
              </div>
            </div>
          </div>
        </div>

        <div className="span-8 card">
          <div className="cardHead">
            <h3>Recent invoices</h3>
            <span className="pill p-cyan">{n(state.invoices.length)}</span>
          </div>
          <div className="cardBody">
            <table className="table">
              <thead>
                <tr>
                  <th>Invoice</th>
                  <th>Org</th>
                  <th>Email</th>
                  <th>Amount</th>
                  <th>Status</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {state.invoices.length ? (
                  state.invoices.map((r) => (
                    <tr key={r.id}>
                      <td>{r.external_invoice_id || r.id}</td>
                      <td>{r.org_id || '—'}</td>
                      <td>{r.client_email || '—'}</td>
                      <td>{money(r.amount_gbp_pence, r.currency)}</td>
                      <td><span className="pill p-cyan">{r.status || '—'}</span></td>
                      <td>{dateText(r.created_at)}</td>
                    </tr>
                  ))
                ) : (
                  <tr><td colSpan={6}>No invoice records found.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="span-4 card">
          <div className="cardHead">
            <h3>Recent payment events</h3>
            <span className="pill p-amber">{n(state.events.length)}</span>
          </div>
          <div className="cardBody">
            <div className="list">
              {state.events.length ? (
                state.events.slice(0, 8).map((r) => (
                  <div className="listRow" key={r.id}>
                    <span>{r.client_email || r.external_event_id || `Event ${r.id}`}</span>
                    <strong>{r.status || '—'}</strong>
                  </div>
                ))
              ) : (
                <div className="note">No payment events found.</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
