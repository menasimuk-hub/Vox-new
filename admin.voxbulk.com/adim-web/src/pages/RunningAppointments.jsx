import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'

function StatCard({ label, value, hint }) {
  return (
    <div className="runningSurveyStatCompact">
      <span className="runningSurveyStatCompactLabel">{label}</span>
      <span className="runningSurveyStatCompactValue">{value}</span>
      {hint ? <span className="runningSurveyStatCompactHint">{hint}</span> : null}
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
  const [templates, setTemplates] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')

  const [orgsError, setOrgsError] = useState('')

  const load = useCallback(async () => {
    setError('')
    setOrgsError('')
    const [ovRes, listRes, tplRes] = await Promise.allSettled([
      apiFetch('/admin/platform-services/appointments/overview'),
      apiFetch('/admin/platform-services/appointments/organisations'),
      apiFetch('/admin/wa-appointment/templates'),
    ])
    if (ovRes.status === 'fulfilled') {
      setOverview(ovRes.value || null)
    } else {
      setOverview(null)
      setError(ovRes.reason?.message || 'Could not load appointment overview')
    }
    if (listRes.status === 'fulfilled') {
      setOrgs(Array.isArray(listRes.value?.organisations) ? listRes.value.organisations : [])
    } else {
      setOrgs([])
      setOrgsError(listRes.reason?.message || 'Could not load customers')
    }
    if (tplRes.status === 'fulfilled') {
      setTemplates(Array.isArray(tplRes.value?.templates) ? tplRes.value.templates : [])
    } else {
      setTemplates([])
    }
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
          <p>Customers with the appointments module — setup status, WA templates, agents, and live pipeline.</p>
        </div>
        <div className="pageTopActions">
          <Link className="btn soft" to="/settings/wa-appointment">WA templates</Link>
          <Link className="btn soft" to="/onboarding/services">Dashboard modules</Link>
          <button type="button" className="btn primary" onClick={() => load().catch((e) => setError(e?.message))}>
            Refresh
          </button>
        </div>
      </div>

      {error ? <div className="card runningSurveyError"><div className="cardBody" style={{ color: '#b91c1c' }}>{error}</div></div> : null}
      {orgsError ? <div className="card runningSurveyError"><div className="cardBody" style={{ color: '#b91c1c' }}>{orgsError}</div></div> : null}

      {overview || loading ? (
        <div className="runningSurveyStatsCompactRow">
          <StatCard label="Active customers" value={overview.active_orgs ?? 0} />
          <StatCard label="Total appointments" value={overview.total_appointments ?? 0} />
          <StatCard label="At risk (24h)" value={overview.at_risk_24h ?? 0} hint="Unconfirmed soon" />
          <StatCard label="Customers with issues" value={overview.orgs_with_issues ?? 0} hint="Setup / CRM / agent" />
        </div>
      ) : null}

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="cardHead runningSurveyListHead">
          <h3>Platform WA templates</h3>
          <Link className="btn soft" to="/settings/wa-appointment">Manage templates</Link>
        </div>
        <div className="cardBody runningSurveyStatsCompactRow">
          {(templates.length ? templates : [{ label: '—', name: 'Run deploy to seed 4 templates' }]).map((t) => (
            <div key={t.id || t.name} className="runningSurveyStatCompact">
              <span className="runningSurveyStatCompactLabel">{t.display_name || t.label}</span>
              <span className="runningSurveyStatCompactValue">{t.name}</span>
              {t.active_for_appointment === false ? (
                <span className="runningSurveyStatCompactHint">Hidden</span>
              ) : null}
              {t.id ? (
                <Link className="btn soft" style={{ marginTop: 6, fontSize: 11, padding: '2px 8px' }} to={`/settings/wa-appointment?edit=${t.id}`}>
                  Edit
                </Link>
              ) : null}
            </div>
          ))}
        </div>
      </div>

      <div className="runningSurveyLayout">
        <div className="card runningSurveyList">
          <div className="cardHead runningSurveyListHead">
            <h3>Customers</h3>
            <input
              className="input runningSurveySearch"
              placeholder="Search org…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="cardBody" style={{ padding: 0 }}>
            {loading ? <div className="note" style={{ padding: 16 }}>Loading…</div> : null}
            {!loading && !filtered.length ? <div className="note" style={{ padding: 16 }}>No customers with appointments enabled. Grant the module in Dashboard modules first.</div> : null}
            <table className="table compact">
              <thead>
                <tr>
                  <th>Organisation</th>
                  <th>Setup</th>
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
                    <td>
                      {o.setup_complete ? (
                        <span className="leadPill leadPillAdvance">Live</span>
                      ) : (
                        <span className="leadPill leadPillHold">Setup pending</span>
                      )}
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
                {!detail.config?.setup_complete ? (
                  <div className="note" style={{ borderColor: '#fcd34d', background: '#fffbeb' }}>
                    Customer has not completed the dashboard setup wizard yet.
                  </div>
                ) : null}

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

                <div className="runningSurveyStatsCompactRow">
                  <StatCard label="WA template" value={detail.config?.wa_template_name || '—'} />
                  <StatCard label="WhatsApp" value={detail.config?.wa_enabled ? 'On' : 'Off'} />
                  <StatCard label="AI calls" value={detail.config?.call_enabled ? 'On' : 'Off'} />
                  <StatCard label="CRM" value={detail.config?.crm_provider || '—'} />
                </div>

                <div className="grid2">
                  <div>
                    <label className="muted">Outreach window</label>
                    <div>{detail.config?.outreach_window_start || '09:00'} – {detail.config?.outreach_window_end || '16:00'}</div>
                  </div>
                  <div>
                    <label className="muted">AI agent</label>
                    <div>{detail.agent?.voice_label || detail.agent?.name || '—'}</div>
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
