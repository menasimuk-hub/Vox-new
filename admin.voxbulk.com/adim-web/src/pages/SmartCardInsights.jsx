import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { BarChart3, Flame, QrCode, RefreshCw, Users } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { KpiCard } from '@/components/ui/KpiCard'
import '../styles/ops-theme.css'

function fmtWhen(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
}

export default function SmartCardInsights() {
  const [overview, setOverview] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setError('')
    const ov = await apiFetch('/admin/smart-card/overview')
    setOverview(ov || null)
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load Smart Card insights')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [load])

  const subs = overview?.subscriptions || []

  return (
    <div className="opsPage">
      <div className="opsHeader">
        <div>
          <h1>Smart Card QR insights</h1>
          <p className="muted">Platform scans, sessions, leads, and seat subscription expiry.</p>
        </div>
        <div className="opsHeaderActions">
          <Link to="/billing/products?filter=smart_card" className="btn ghost">
            Products
          </Link>
          <Link to="/pricing/packages?service=smart_card" className="btn ghost">
            Pricing
          </Link>
          <button type="button" className="btn" onClick={() => load()} disabled={loading}>
            <RefreshCw size={16} /> Refresh
          </button>
        </div>
      </div>

      {error ? <div className="banner err">{error}</div> : null}

      {loading && !overview ? (
        <p className="muted">Loading…</p>
      ) : (
        <>
          <div className="opsKpiGrid">
            <KpiCard label="Scans" value={overview?.scans ?? '—'} icon={QrCode} tone="info" />
            <KpiCard label="Sessions" value={overview?.sessions ?? '—'} icon={BarChart3} tone="info" />
            <KpiCard
              label="Completed"
              value={overview?.sessions_completed ?? 0}
              hint={`${overview?.sessions ?? 0} total sessions`}
              icon={BarChart3}
              tone="success"
            />
            <KpiCard label="Leads" value={overview?.leads ?? '—'} icon={Users} tone="info" />
            <KpiCard label="Hot leads" value={overview?.hot_leads ?? 0} icon={Flame} tone="warning" />
            <KpiCard
              label="Companies / reps"
              value={`${overview?.companies ?? 0} / ${overview?.representatives ?? 0}`}
              icon={Users}
              tone="neutral"
            />
          </div>

          <div className="card" style={{ marginTop: 16 }}>
            <div className="cardHead">
              <h2>Seat subscriptions</h2>
              <p className="muted">Shows when seats expire after purchase (`period_end`).</p>
            </div>
            <div className="tableWrap">
              <table className="dataTable">
                <thead>
                  <tr>
                    <th>Org</th>
                    <th>Status</th>
                    <th>Seats</th>
                    <th>Expires</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {subs.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="muted">
                        No Smart Card seat subscriptions yet.
                      </td>
                    </tr>
                  ) : (
                    subs.map((s) => (
                      <tr key={s.id}>
                        <td>
                          <Link to={`/organisations/${s.org_id}`}>{s.org_id}</Link>
                        </td>
                        <td>
                          <span className={s.expired ? 'pill danger' : 'pill'}>{s.status}</span>
                          {s.expired ? ' expired' : ''}
                        </td>
                        <td>{s.seat_quantity}</td>
                        <td>{fmtWhen(s.period_end)}</td>
                        <td>{fmtWhen(s.created_at)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
