import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { statusPillClass, truncate } from '../lib/billingAdminUtils'

function severityPill(sev) {
  if (sev === 'error') return 'p-red'
  if (sev === 'warning') return 'p-amber'
  return 'p-cyan'
}

export default function BillingExceptions() {
  const [items, setItems] = useState([])
  const [summary, setSummary] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setError('')
    const res = await apiFetch('/admin/billing/exceptions?limit=200')
    setItems(Array.isArray(res?.items) ? res.items : [])
    setSummary(res?.summary || {})
  }, [])

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
          <h1>Billing exceptions</h1>
          <p>Failed renewals, missing billing dates, currency mismatches, and pending refund queue.</p>
        </div>
        <div className="actions">
          <button type="button" className="btn soft" onClick={load} disabled={loading}>Refresh</button>
          <Link className="btn soft" to="/billing/reports">Revenue reports</Link>
        </div>
      </div>

      {error ? <div className="note billingErrorNote">{error}</div> : null}

      <div className="billingPageShell">
        <div className="billingStats">
          <div className="billingStat" style={{ '--accent': '#dc2626' }}>
            <label>Total exceptions</label>
            <strong>{summary.total ?? items.length}</strong>
          </div>
          <div className="billingStat" style={{ '--accent': '#d97706' }}>
            <label>Missing next billing</label>
            <strong>{summary.missing_next_billing_date ?? 0}</strong>
          </div>
          <div className="billingStat" style={{ '--accent': '#7c3aed' }}>
            <label>Pending refunds</label>
            <strong>{summary.pending_refund_queue ?? 0}</strong>
          </div>
        </div>

        <div className="billingPanel">
          <div className="billingTableWrap">
            {loading ? <div className="billingEmpty muted">Loading…</div> : null}
            {!loading && !items.length ? <div className="billingEmpty muted">No billing exceptions detected.</div> : null}
            {!loading && items.length > 0 ? (
              <table className="table billingTable">
                <thead>
                  <tr>
                    <th>Severity</th>
                    <th>Kind</th>
                    <th>Organisation</th>
                    <th>Detail</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {items.map((row, idx) => (
                    <tr key={`${row.kind}-${row.org_id}-${idx}`}>
                      <td><span className={`pill ${severityPill(row.severity)}`}>{row.severity}</span></td>
                      <td>{row.kind}</td>
                      <td>{truncate(row.org_name, 28)}</td>
                      <td className="muted">{truncate(row.detail, 64)}</td>
                      <td>
                        {row.org_id ? (
                          <Link className="btn soft xs" to="/organisations/all-users" onClick={() => localStorage.setItem('voxbulk_admin_selected_org_id', row.org_id)}>OCC</Link>
                        ) : null}
                      </td>
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
