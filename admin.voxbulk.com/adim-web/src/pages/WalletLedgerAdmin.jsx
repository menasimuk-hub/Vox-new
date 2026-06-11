import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { dateText, money, truncate } from '../lib/billingAdminUtils'

export default function WalletLedgerAdmin() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filters, setFilters] = useState({ search: '', kind: '', direction: '' })

  const load = useCallback(async () => {
    setError('')
    const params = new URLSearchParams({ limit: '250' })
    if (filters.search.trim()) params.set('search', filters.search.trim())
    if (filters.kind) params.set('kind', filters.kind)
    if (filters.direction) params.set('direction', filters.direction)
    const res = await apiFetch(`/admin/billing/wallet-ledger?${params.toString()}`)
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

  useEffect(() => {
    const timer = window.setTimeout(() => load().catch(() => {}), 250)
    return () => window.clearTimeout(timer)
  }, [filters, load])

  const liability = useMemo(() => rows.reduce((sum, r) => sum + Number(r.signed_amount_minor || 0), 0), [rows])

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>Wallet ledger</h1>
          <p>All signed wallet balance changes with running balance after each entry.</p>
        </div>
        <div className="actions">
          <button type="button" className="btn soft" onClick={load} disabled={loading}>Refresh</button>
        </div>
      </div>

      {error ? <div className="note billingErrorNote">{error}</div> : null}

      <div className="billingPageShell">
        <div className="billingStats" style={{ marginBottom: 14 }}>
          <div className="billingStat" style={{ '--accent': '#0f766e' }}>
            <label>Entries shown</label>
            <strong>{rows.length}</strong>
          </div>
        </div>
        <div className="billingPanel">
          <div className="billingToolbar">
            <div className="billingToolbarFilters">
              <input className="input billingSearch" placeholder="Search org, ref, note…" value={filters.search} onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))} />
              <select className="input billingSelect" value={filters.direction} onChange={(e) => setFilters((f) => ({ ...f, direction: e.target.value }))}>
                <option value="">All directions</option>
                <option value="credit">Credit</option>
                <option value="debit">Debit</option>
              </select>
              <input className="input billingSelect" placeholder="Kind" value={filters.kind} onChange={(e) => setFilters((f) => ({ ...f, kind: e.target.value }))} />
            </div>
          </div>
          <div className="billingTableWrap">
            {loading ? <div className="billingEmpty muted">Loading…</div> : null}
            {!loading && !rows.length ? <div className="billingEmpty muted">No ledger entries.</div> : null}
            {!loading && rows.length > 0 ? (
              <table className="table billingTable">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Organisation</th>
                    <th>Kind</th>
                    <th>Direction</th>
                    <th>Amount</th>
                    <th>Balance after</th>
                    <th>Reference</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id}>
                      <td className="muted">{dateText(row.created_at)}</td>
                      <td>
                        <strong>{truncate(row.org_name, 22)}</strong>
                        <button type="button" className="btn soft xs" style={{ marginLeft: 6 }} onClick={() => { localStorage.setItem('voxbulk_admin_selected_org_id', row.org_id); window.location.assign('/organisations/all-users') }}>OCC</button>
                      </td>
                      <td>{row.kind}</td>
                      <td>{row.direction}</td>
                      <td><strong>{row.amount_display || money(row.amount_minor, row.currency)}</strong></td>
                      <td>{row.balance_after_display || money(row.balance_after_minor, row.currency)}</td>
                      <td className="muted">{truncate(row.provider_reference || row.description, 28)}</td>
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
