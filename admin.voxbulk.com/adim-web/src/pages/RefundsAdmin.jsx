import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { dateShort, dateText, money, statusPillClass, truncate } from '../lib/billingAdminUtils'

const STATUS_OPTIONS = ['', 'pending', 'under_review', 'approved', 'processed', 'rejected', 'failed']

export default function RefundsAdmin() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [filters, setFilters] = useState({ status: '', provider: '', search: '' })

  const load = useCallback(async () => {
    setError('')
    const params = new URLSearchParams({ limit: '200' })
    if (filters.status) params.set('status', filters.status)
    if (filters.provider.trim()) params.set('provider', filters.provider.trim())
    const res = await apiFetch(`/admin/billing/refunds?${params.toString()}`)
    let items = Array.isArray(res?.items) ? res.items : []
    if (filters.search.trim()) {
      const q = filters.search.trim().toLowerCase()
      items = items.filter(
        (r) =>
          String(r.organisation_name || '').toLowerCase().includes(q) ||
          String(r.org_email || '').toLowerCase().includes(q) ||
          String(r.id || '').toLowerCase().includes(q),
      )
    }
    setRows(items)
  }, [filters])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Load failed')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [load])

  const stats = useMemo(() => {
    const pending = rows.filter((r) => ['pending', 'under_review', 'approved'].includes(String(r.review_status_normalized || r.review_status || '').toLowerCase()))
    return { total: rows.length, pending: pending.length }
  }, [rows])

  const resolveReview = async (row, status, extra = {}) => {
    if (!row?.org_id || !row?.id) return
    const note = window.prompt('Admin note:', extra.defaultNote || '')
    if (note === null) return
    setBusy(row.id)
    setError('')
    try {
      await apiFetch(
        `/admin/organisations/${encodeURIComponent(row.org_id)}/control-center/refund-reviews/${encodeURIComponent(row.id)}/resolve`,
        {
          method: 'POST',
          body: JSON.stringify({
            review_status: status,
            admin_notes: note,
            issue_wallet_credit: Boolean(extra.issue_wallet_credit),
            approved_external_refund_pence: extra.approved_external_refund_pence,
          }),
        },
      )
      await load()
    } catch (e) {
      setError(e?.message || 'Action failed')
    } finally {
      setBusy('')
    }
  }

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>Refunds</h1>
          <p>Admin refund review queue — approve wallet credit, mark external refund, or reject.</p>
        </div>
        <div className="actions">
          <button type="button" className="btn soft" onClick={load} disabled={loading}>
            Refresh
          </button>
          <Link className="btn soft" to="/billing/invoices?tab=requests">
            Billing requests
          </Link>
        </div>
      </div>

      {error ? <div className="note billingErrorNote">{error}</div> : null}

      <div className="billingPageShell">
        <div className="billingHub">
          <div className="billingStats">
            <div className="billingStat" style={{ '--accent': '#d97706' }}>
              <label>Pending queue</label>
              <strong>{stats.pending}</strong>
              <span>Awaiting admin action</span>
            </div>
            <div className="billingStat" style={{ '--accent': '#0891b2' }}>
              <label>Total reviews</label>
              <strong>{stats.total}</strong>
            </div>
          </div>

          <div className="billingPanel">
            <div className="billingToolbar">
              <div className="billingToolbarFilters">
                <select className="input billingSelect" value={filters.status} onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}>
                  {STATUS_OPTIONS.map((opt) => (
                    <option key={opt || 'all'} value={opt}>
                      {opt ? opt.replace('_', ' ') : 'All statuses'}
                    </option>
                  ))}
                </select>
                <input className="input billingSearch" placeholder="Search org or email…" value={filters.search} onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))} />
              </div>
            </div>
            <div className="billingTableWrap">
              {loading ? <div className="billingEmpty muted">Loading…</div> : null}
              {!loading && !rows.length ? <div className="billingEmpty muted">No refund reviews match filters.</div> : null}
              {!loading && rows.length > 0 ? (
                <table className="table billingTable">
                  <thead>
                    <tr>
                      <th>Requested</th>
                      <th>Organisation</th>
                      <th>Status</th>
                      <th>Type</th>
                      <th>Unused value</th>
                      <th>Provider ref</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => {
                      const st = row.review_status_normalized || row.review_status
                      const isBusy = busy === row.id
                      return (
                        <tr key={row.id}>
                          <td className="muted">{dateText(row.requested_at)}</td>
                          <td>
                            <strong>{truncate(row.organisation_name, 24)}</strong>
                            <span className="muted billingListSub">{truncate(row.org_email, 28)}</span>
                          </td>
                          <td><span className={`pill billingStatusPill ${statusPillClass(st)}`}>{st}</span></td>
                          <td>{row.requested_refund_type || '—'}</td>
                          <td>{money(row.calculated_unused_value_pence, row.billing_currency)}</td>
                          <td className="muted">{truncate(row.source_payment_reference, 20)}</td>
                          <td className="billingListActions">
                            {['pending', 'under_review', 'approved'].includes(String(st).toLowerCase()) ? (
                              <>
                                <button type="button" className="btn soft xs" disabled={isBusy} onClick={() => resolveReview(row, 'approved', { issue_wallet_credit: true })}>Approve wallet</button>
                                <button type="button" className="btn soft xs" disabled={isBusy} onClick={() => resolveReview(row, 'completed', { approved_external_refund_pence: row.calculated_unused_value_pence })}>Mark refunded</button>
                                <button type="button" className="btn soft xs" disabled={isBusy} onClick={() => resolveReview(row, 'rejected')}>Reject</button>
                              </>
                            ) : null}
                            <Link className="btn soft xs" to="/organisations/all-users" onClick={() => localStorage.setItem('voxbulk_admin_selected_org_id', row.org_id)}>OCC</Link>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
