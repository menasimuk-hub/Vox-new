import React, { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { formatDurationSeconds } from '../lib/serviceOrderAdmin'
import OrderAdminBillingPanel from '../components/OrderAdminBillingPanel'
import './orgControlCenter.css'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'calls', label: 'Calls & costs' },
  { id: 'contacts', label: 'Contacts' },
  { id: 'audit', label: 'Audit' },
]

function fmtWhen(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

function statusBadge(status) {
  const s = String(status || '').toLowerCase()
  const map = {
    running: 'occ-badge-blue',
    approved: 'occ-badge-green',
    completed: 'occ-badge-gray',
    paused: 'occ-badge-amber',
    pending: 'occ-badge-amber',
    failed: 'occ-badge-red',
    rejected: 'occ-badge-red',
    paid: 'occ-badge-green',
  }
  return <span className={`occ-badge ${map[s] || 'occ-badge-gray'}`}>{status || '—'}</span>
}

function InfoRow({ label, value }) {
  return (
    <div className="occ-info-row">
      <span className="occ-info-row-label">{label}</span>
      <span className="occ-info-row-value">{value}</span>
    </div>
  )
}

export default function ServiceOrderDetail() {
  const { orderId } = useParams()
  const [order, setOrder] = useState(null)
  const [audit, setAudit] = useState([])
  const [tab, setTab] = useState('overview')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    if (!orderId) return
    setError('')
    const [row, auditRes] = await Promise.all([
      apiFetch(`/admin/platform-services/orders/${encodeURIComponent(orderId)}`),
      apiFetch(`/admin/platform-services/orders/${encodeURIComponent(orderId)}/audit`),
    ])
    setOrder(row)
    setAudit(auditRes?.timeline || [])
  }, [orderId])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load order')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [load])

  const recipients = order?.recipients || []
  const cost = order?.cost_summary || {}
  const cfg = order?.config || {}
  const isWa = String(cfg.survey_channel || cfg.channel || '').toLowerCase() === 'whatsapp'

  return (
    <div className="occ">
      {error ? (
        <div className="card alertCard" style={{ marginBottom: 16 }}>
          <div className="cardBody alertText">{error}</div>
        </div>
      ) : null}

      {loading ? (
        <div className="occ-kpi-placeholder" style={{ margin: 24 }}>Loading order…</div>
      ) : null}

      {!loading && order ? (
        <div className="occ-detail-panel">
          <div className="occ-detail-header">
            <div className="occ-detail-org-row">
              <div>
                <div className="occ-detail-org-name">{order.title || 'Service order'}</div>
                <div className="occ-detail-org-meta">
                  <span className="occ-detail-org-id">{order.id}</span>
                  {statusBadge(order.status_label || order.status)}
                  <span className="occ-badge occ-badge-gray">{order.service_code || 'order'}</span>
                  <span className="muted">{order.org_name || '—'}</span>
                </div>
              </div>
              <div className="occ-detail-actions">
                <Link className="occ-btn" to="/organisations/all-users">← Control Center</Link>
                {order.org_id ? (
                  <Link className="occ-btn" to={`/organisations/${order.org_id}`}>Organisation</Link>
                ) : null}
                {order.service_code === 'survey' ? (
                  <Link className="occ-btn" to={`/operations/running-surveys?order=${encodeURIComponent(orderId)}`}>
                    Manage survey
                  </Link>
                ) : null}
                {order.service_code === 'interview' ? (
                  <Link className="occ-btn" to={`/operations/running-interviews?order=${encodeURIComponent(orderId)}`}>
                    Manage interview
                  </Link>
                ) : null}
                <button type="button" className="occ-btn primary" onClick={() => load().catch((e) => setError(e?.message))}>
                  Refresh
                </button>
              </div>
            </div>

            <div className="occ-kpi-grid" style={{ marginBottom: 16 }}>
              <div className="occ-kpi-card">
                <div className="occ-kpi-card-label">Payment</div>
                <div className="occ-kpi-card-value" style={{ fontSize: 16 }}>{order.payment_status || '—'}</div>
                <div className="occ-kpi-card-sub">{order.payment_method || '—'}</div>
              </div>
              <div className="occ-kpi-card">
                <div className="occ-kpi-card-label">R.cost (retail)</div>
                <div className="occ-kpi-card-value">{cost.total_retail_cost_display || '—'}</div>
                <div className="occ-kpi-card-sub">Billable minutes × your rate</div>
              </div>
              <div className="occ-kpi-card">
                <div className="occ-kpi-card-label">O.cost (Telnyx)</div>
                <div className="occ-kpi-card-value">{cost.total_operator_cost_display || '—'}</div>
                <div className="occ-kpi-card-sub">Operator detail records</div>
              </div>
              <div className="occ-kpi-card">
                <div className="occ-kpi-card-label">Recipients</div>
                <div className="occ-kpi-card-value">{order.recipient_count ?? recipients.length}</div>
                <div className="occ-kpi-card-sub">Quote {order.quote_total_gbp || '—'}</div>
              </div>
            </div>

            <div className="occ-tabs">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  className={`occ-tab-btn ${tab === t.id ? 'active' : ''}`}
                  onClick={() => setTab(t.id)}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          <div className={`occ-tab-content ${tab === 'overview' ? 'active' : ''}`}>
            <div className="occ-two-col">
              <div className="occ-info-block">
                <div className="occ-info-block-title">Order</div>
                <InfoRow label="Reference" value={order.reference_id || '—'} />
                <InfoRow label="Channel" value={cfg.survey_channel || cfg.channel || order.quote_survey_channel || '—'} />
                <InfoRow label="Created" value={fmtWhen(order.created_at)} />
                <InfoRow label="Started" value={fmtWhen(order.started_at)} />
                <InfoRow label="Completed" value={fmtWhen(order.completed_at)} />
              </div>
              <div className="occ-info-block">
                <div className="occ-info-block-title">Customer</div>
                <InfoRow label="Organisation" value={order.org_name || '—'} />
                <InfoRow label="Owner" value={order.owner_email || '—'} />
                {(cfg.wa_template_name || cfg.template_name) ? (
                  <InfoRow label="WA template" value={cfg.wa_template_name || cfg.template_name} />
                ) : null}
                {cfg.goal ? <InfoRow label="Goal" value={cfg.goal} /> : null}
              </div>
            </div>
            <OrderAdminBillingPanel order={order} />
          </div>

          <div className={`occ-tab-content ${tab === 'calls' ? 'active' : ''}`}>
            <div className="occ-table-wrap">
              <table className="occ-data-table">
                <thead>
                  <tr>
                    <th>Contact</th>
                    <th>Phone</th>
                    <th>Call type</th>
                    <th>Duration</th>
                    <th>Bill min</th>
                    <th>R.cost</th>
                    <th>O.cost</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {!recipients.length ? (
                    <tr><td colSpan={8}><div className="occ-empty-state">No contacts.</div></td></tr>
                  ) : recipients.map((r) => (
                    <tr key={r.id}>
                      <td>{r.name || '—'}</td>
                      <td className="occ-mono">{r.phone || '—'}</td>
                      <td>{r.call_type || '—'}</td>
                      <td>{formatDurationSeconds(r.duration_seconds)}</td>
                      <td className="occ-mono">{r.billable_minutes ?? '—'}</td>
                      <td className="occ-mono">{r.retail_cost_display || '—'}</td>
                      <td className="occ-mono">{r.operator_cost_display || '—'}</td>
                      <td>{r.status || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted" style={{ marginTop: 12, fontSize: 13 }}>
              <strong>R.cost</strong> — retail charge (billable minutes × your rate).{' '}
              <strong>O.cost</strong> — Telnyx operator cost from detail records (USD).
            </p>
          </div>

          <div className={`occ-tab-content ${tab === 'contacts' ? 'active' : ''}`}>
            <div className="occ-table-wrap">
              <table className="occ-data-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Name</th>
                    <th>Phone</th>
                    <th>Email</th>
                    {!isWa ? <th>Call type</th> : null}
                    {!isWa ? <th>Duration</th> : null}
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {recipients.map((r) => (
                    <tr key={r.id}>
                      <td>{r.row_number}</td>
                      <td>{r.name}</td>
                      <td>{r.phone || '—'}</td>
                      <td>{r.email || '—'}</td>
                      {!isWa ? <td>{r.call_type || '—'}</td> : null}
                      {!isWa ? <td>{formatDurationSeconds(r.duration_seconds)}</td> : null}
                      <td>{r.status || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className={`occ-tab-content ${tab === 'audit' ? 'active' : ''}`}>
            {!audit.length ? (
              <div className="occ-empty-state">No audit events.</div>
            ) : (
              <div className="occ-table-wrap">
                <table className="occ-data-table">
                  <thead>
                    <tr><th>When</th><th>Event</th><th>Detail</th></tr>
                  </thead>
                  <tbody>
                    {audit.map((ev, i) => (
                      <tr key={`${ev.at}-${i}`}>
                        <td style={{ color: 'var(--occ-text3)', fontSize: 12 }}>{fmtWhen(ev.at)}</td>
                        <td>{ev.label || ev.kind}</td>
                        <td>{ev.detail || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  )
}
