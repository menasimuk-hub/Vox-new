import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { dateText, statusPillClass, truncate } from '../lib/billingAdminUtils'

export default function PaymentEventsAdmin() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filters, setFilters] = useState({ provider: '', status: '', duplicates_only: false })

  const load = useCallback(async () => {
    setError('')
    const params = new URLSearchParams({ limit: '200' })
    if (filters.provider) params.set('provider', filters.provider)
    if (filters.status) params.set('status', filters.status)
    if (filters.duplicates_only) params.set('duplicates_only', 'true')
    const res = await apiFetch(`/admin/billing/payment-events?${params.toString()}`)
    setRows(Array.isArray(res?.items) ? res.items : [])
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

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>Payment events</h1>
          <p>Provider webhooks and internal admin billing events.</p>
          <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            For failed-only view see <Link to="/billing/failed-payments">Failed payments</Link>.
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn soft" onClick={load} disabled={loading}>Refresh</button>
        </div>
      </div>

      {error ? <div className="note billingErrorNote">{error}</div> : null}

      <div className="billingPageShell">
        <div className="billingPanel">
          <div className="billingToolbar">
            <div className="billingToolbarFilters">
              <input className="input billingSearch" placeholder="Provider" value={filters.provider} onChange={(e) => setFilters((f) => ({ ...f, provider: e.target.value }))} />
              <input className="input billingSelect" placeholder="Status" value={filters.status} onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))} />
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
                <input type="checkbox" checked={filters.duplicates_only} onChange={(e) => setFilters((f) => ({ ...f, duplicates_only: e.target.checked }))} />
                Duplicates only
              </label>
            </div>
          </div>
          <div className="billingTableWrap">
            {loading ? <div className="billingEmpty muted">Loading…</div> : null}
            {!loading && !rows.length ? <div className="billingEmpty muted">No payment events.</div> : null}
            {!loading && rows.length > 0 ? (
              <table className="table billingTable">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Provider</th>
                    <th>Kind</th>
                    <th>Organisation</th>
                    <th>Status</th>
                    <th>Reason</th>
                    <th>Event ID</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id}>
                      <td className="muted">{dateText(row.created_at)}</td>
                      <td>{row.provider}</td>
                      <td>{row.event_kind || '—'}</td>
                      <td>{truncate(row.organisation_name, 24)}</td>
                      <td>
                        <span className={`pill ${statusPillClass(row.status)}`}>{row.status}</span>
                        {row.is_duplicate ? <span className="pill p-amber" style={{ marginLeft: 4 }}>dup</span> : null}
                      </td>
                      <td className="muted">{truncate(row.failure_reason, 36)}</td>
                      <td><code className="billingCodePill">{truncate(row.external_event_id, 22)}</code></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
          </div>
        </div>
      </div>
    </>
  )
}
