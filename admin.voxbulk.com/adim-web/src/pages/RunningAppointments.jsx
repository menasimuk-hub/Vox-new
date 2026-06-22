import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'

function StatCard({ label, value, hint }) {
  return (
    <div className="card stat runningSurveyStat">
      <div className="statValue">{value}</div>
      <div className="muted">{label}</div>
      {hint ? <div className="muted runningSurveyStatHint">{hint}</div> : null}
    </div>
  )
}

function issuePill(level) {
  if (level === 'error') return 'leadPill leadPillDecline'
  return 'leadPill leadPillHold'
}

export default function RunningAppointments() {
  const [overview, setOverview] = useState(null)
  const [orgs, setOrgs] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')

  const load = useCallback(async () => {
    setError('')
    const [ov, list] = await Promise.all([
      apiFetch('/admin/platform-services/appointments/overview'),
      apiFetch('/admin/platform-services/appointments/organisations'),
    ])
    setOverview(ov || null)
    setOrgs(Array.isArray(list?.organisations) ? list.organisations : [])
  }, [])

  const loadDetail = useCallback(async (orgId) => {
    if (!orgId) return
    const row = await apiFetch(`/admin/platform-services/appointments/organisations/${encodeURIComponent(orgId)}`)
    setDetail(row)
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load appointments')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [load])

  useEffect(() => {
    if (selectedId) void loadDetail(selectedId)
    else setDetail(null)
  }, [selectedId, loadDetail])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return orgs
    return orgs.filter((o) =>
      `${o.org_name || ''} ${o.contact_email || ''}`.toLowerCase().includes(q),
    )
  }, [orgs, search])

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>Appointment Manager</h1>
          <p>Customers with the appointments module — config, WA template, agent, and live pipeline for support.</p>
        </div>
        <div className="pageTopActions">
          <Link className="btn soft" to="/billing/products?tab=campaign">Products hub</Link>
          <button type="button" className="btn primary" onClick={() => load().catch((e) => setError(e?.message))}>
            Refresh
          </button>
        </div>
      </div>

      {error ? <div className="card" style={{ marginBottom: 16, borderColor: '#fecaca' }}><div className="cardBody" style={{ color: '#b91c1c' }}>{error}</div></div> : null}

      {overview ? (
        <div className="grid4" style={{ marginBottom: 16 }}>
          <StatCard label="Active customers" value={overview.active_orgs ?? 0} />
          <StatCard label="Total appointments" value={overview.total_appointments ?? 0} />
          <StatCard label="At risk (24h)" value={overview.at_risk_24h ?? 0} hint="Unconfirmed soon" />
          <StatCard label="Customers with issues" value={overview.orgs_with_issues ?? 0} hint="Config / CRM / agent" />
        </div>
      ) : null}

      <div className="runningSurveyLayout">
        <div className="card runningSurveyList">
          <div className="cardHead">
            <h3>Customers</h3>
            <input
              className="input"
              placeholder="Search org…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ maxWidth: 220 }}
            />
          </div>
          <div className="cardBody" style={{ padding: 0 }}>
            {loading ? <div className="note" style={{ padding: 16 }}>Loading…</div> : null}
            {!loading && !filtered.length ? <div className="note" style={{ padding: 16 }}>No customers with appointments enabled.</div> : null}
            <table className="table compact">
              <thead>
                <tr>
                  <th>Organisation</th>
                  <th>Appts</th>
                  <th>Risk</th>
                  <th>Issues</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((o) => (
                  <tr
                    key={o.org_id}
                    className={selectedId === o.org_id ? 'isSelected' : ''}
                    style={{ cursor: 'pointer' }}
                    onClick={() => setSelectedId(o.org_id)}
                  >
                    <td>
                      <strong>{o.org_name}</strong>
                      <div className="muted" style={{ fontSize: 12 }}>{o.contact_email}</div>
                    </td>
                    <td>{o.appointment_count}</td>
                    <td>{o.at_risk_24h > 0 ? <span className="leadPill leadPillHold">{o.at_risk_24h}</span> : '—'}</td>
                    <td>{o.issue_count > 0 ? <span className="leadPill leadPillDecline">{o.issue_count}</span> : 'OK'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card runningSurveyDetail">
          {!detail ? (
            <div className="cardBody note">Select a customer to view configuration and appointment processes.</div>
          ) : (
            <>
              <div className="cardHead">
                <h3>{detail.org?.name}</h3>
                <Link className="btn soft" to={`/organisations/${detail.org?.id}`}>Open org</Link>
              </div>
              <div className="cardBody" style={{ display: 'grid', gap: 16 }}>
                {detail.issues?.length ? (
                  <div>
                    <strong>Support flags</strong>
                    <ul style={{ margin: '8px 0 0', paddingLeft: 18 }}>
                      {detail.issues.map((i) => (
                        <li key={i.code}><span className={issuePill(i.level)} style={{ marginRight: 8 }}>{i.level}</span>{i.message}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                <div className="grid2">
                  <div>
                    <label className="muted">WA template</label>
                    <div>{detail.config?.wa_template_name || '—'} {detail.config?.wa_enabled ? '(on)' : '(off)'}</div>
                  </div>
                  <div>
                    <label className="muted">AI agent</label>
                    <div>{detail.agent?.voice_label || detail.agent?.name || '—'} {detail.config?.call_enabled ? '(calls on)' : '(calls off)'}</div>
                  </div>
                  <div>
                    <label className="muted">Outreach window</label>
                    <div>{detail.config?.outreach_window_start || '09:00'} – {detail.config?.outreach_window_end || '16:00'}</div>
                  </div>
                  <div>
                    <label className="muted">CRM</label>
                    <div>{detail.config?.crm_provider || '—'} · sync every {detail.config?.sync_interval_minutes || 60}m</div>
                  </div>
                </div>

                <div>
                  <strong>Appointment processes</strong>
                  <table className="table compact" style={{ marginTop: 8 }}>
                    <thead>
                      <tr>
                        <th>Contact</th>
                        <th>When</th>
                        <th>Status</th>
                        <th>Flags</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(detail.appointments || []).map((a) => (
                        <tr key={a.id}>
                          <td>{a.contact_name}<div className="muted" style={{ fontSize: 11 }}>{a.contact_phone}</div></td>
                          <td style={{ fontSize: 12 }}>{a.appointment_datetime ? new Date(a.appointment_datetime).toLocaleString() : '—'}</td>
                          <td>{a.status}</td>
                          <td>
                            {(a.flags || []).map((f) => (
                              <span key={f} className="leadPill leadPillHold" style={{ marginRight: 4, fontSize: 10 }}>{f}</span>
                            ))}
                            {!a.flags?.length ? '—' : null}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  )
}
