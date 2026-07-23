import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import {
  PARTNER_PROVIDERS,
  connectionBadge,
  getPartnerProvider,
  modeBadge,
  moneyGbp,
} from '../lib/partnersCatalog'
import './partners.css'

function emptyKpi() {
  return {
    totals: { connected: 0, total: PARTNER_PROVIDERS.length, jobs: 0, completed: 0, gross: 0, remittance: 0, profit: 0 },
    rows: PARTNER_PROVIDERS.map((p) => ({
      key: p.key,
      connection: 'none',
      mode: null,
      jobs: 0,
      completed: 0,
      gross: 0,
      commission: p.commissionDefault,
      remittance: 0,
      cost: 0,
      profit: 0,
      lastActivity: null,
    })),
  }
}

export default function PartnersDashboard() {
  const [range, setRange] = useState('7')
  const [modeFilter, setModeFilter] = useState('all')
  const [kpi, setKpi] = useState(emptyKpi)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError('')
      try {
        const data = await apiFetch('/admin/partners/kpi')
        if (!cancelled) setKpi(data || emptyKpi())
      } catch (e) {
        if (!cancelled) {
          setError(e?.message || 'Failed to load partner KPI')
          setKpi(emptyKpi())
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const rows = useMemo(() => {
    return (kpi.rows || []).filter((row) => {
      if (modeFilter === 'all') return true
      if (modeFilter === 'sandbox') return row.mode === 'sandbox'
      if (modeFilter === 'live') return row.mode === 'live'
      return true
    })
  }, [modeFilter, kpi.rows])

  const t = kpi.totals || emptyKpi().totals

  return (
    <div className='partners-page'>
      <div className='partners-header'>
        <div>
          <h1>Provider Dashboard</h1>
          <div className='partners-sub'>Connection status, jobs, and profit by marketplace partner</div>
        </div>
        <div className='partners-filters'>
          <label className='partners-chip'>
            <i className='ti ti-calendar' />
            <select value={range} onChange={(e) => setRange(e.target.value)} aria-label='Date range'>
              <option value='7'>Last 7 days</option>
              <option value='30'>Last 30 days</option>
              <option value='90'>Last 90 days</option>
            </select>
          </label>
          <label className='partners-chip'>
            <i className='ti ti-adjustments-horizontal' />
            <select value={modeFilter} onChange={(e) => setModeFilter(e.target.value)} aria-label='Mode filter'>
              <option value='all'>All modes</option>
              <option value='sandbox'>Sandbox</option>
              <option value='live'>Live</option>
            </select>
          </label>
        </div>
      </div>

      {error ? <div className='partners-warn'>{error}</div> : null}
      {loading ? <div className='partners-footer-note'>Loading partner KPIs…</div> : null}

      <div className='partners-kpi-grid'>
        <div className='partners-kpi-card'>
          <div className='label'>Total providers</div>
          <div className='value'>
            {t.connected} <small>/ {t.total}</small>
          </div>
        </div>
        <div className='partners-kpi-card'>
          <div className='label'>Jobs</div>
          <div className='value'>{t.jobs}</div>
        </div>
        <div className='partners-kpi-card'>
          <div className='label'>Candidates completed</div>
          <div className='value'>{t.completed}</div>
        </div>
        <div className='partners-kpi-card'>
          <div className='label'>Gross charged</div>
          <div className='value'>{moneyGbp(t.gross)}</div>
        </div>
        <div className='partners-kpi-card'>
          <div className='label'>Est. remittance</div>
          <div className='value'>{moneyGbp(t.remittance)}</div>
        </div>
        <div className='partners-kpi-card'>
          <div className='label'>Est. profit</div>
          <div className='value'>{moneyGbp(t.profit)}</div>
        </div>
      </div>

      <div className='partners-table-wrap'>
        <table className='partners-table'>
          <thead>
            <tr>
              <th>Provider</th>
              <th>Connection</th>
              <th>Mode</th>
              <th>Jobs</th>
              <th>Candidates</th>
              <th>Gross charged</th>
              <th>Commission %</th>
              <th>Est. remittance</th>
              <th>Est. cost</th>
              <th>Est. profit</th>
              <th>Last activity</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const meta = getPartnerProvider(row.key) || PARTNER_PROVIDERS.find((p) => p.key === row.key)
              const conn = connectionBadge(row.connection)
              const mode = modeBadge(row.mode)
              return (
                <tr key={row.key}>
                  <td>
                    <div className='partners-provider-cell'>
                      <span className='partners-logo'>{meta?.initials || '??'}</span>
                      {meta?.short || row.key}
                    </div>
                  </td>
                  <td>
                    <span className={`partners-badge ${conn.cls}`}>{conn.text}</span>
                  </td>
                  <td>
                    <span className={`partners-badge ${mode.cls}`}>{mode.text}</span>
                  </td>
                  <td>{row.jobs}</td>
                  <td>{row.completed}</td>
                  <td>{moneyGbp(row.gross)}</td>
                  <td>{row.commission}%</td>
                  <td>{moneyGbp(row.remittance)}</td>
                  <td>{moneyGbp(row.cost)}</td>
                  <td>{moneyGbp(row.profit)}</td>
                  <td>{row.last_activity || row.lastActivity || '—'}</td>
                  <td>
                    <Link className='partners-action-link' to={`/partners/${row.key}`}>
                      Open settings →
                    </Link>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className='partners-footer-note'>
        <i className='ti ti-info-circle' /> Profit is estimated from logged charges and commission %. Reconcile with
        marketplace payouts monthly.
      </div>
    </div>
  )
}
