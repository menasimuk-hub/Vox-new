import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { BarChart3, CheckCircle2, MessageCircle, RefreshCw, TriangleAlert, Bot } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { deliveryOkBadge, waSessionStatusPill } from '../lib/waSurveyOps'
import WaSurveySessionPanel from '../components/WaSurveySessionPanel'
import { KpiCard } from '@/components/ui/KpiCard'
import '../styles/ops-theme.css'

function fmtWhen(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
}

function MetricCard({ label, value, hint }) {
  return (
    <div className="card stat waSurveyInsightStat">
      <div className="statValue">{value}</div>
      <div className="muted">{label}</div>
      {hint ? <div className="muted waSurveyInsightStatHint">{hint}</div> : null}
    </div>
  )
}

export default function WaSurveyInsights() {
  const [sinceDays, setSinceDays] = useState(7)
  const [orderId, setOrderId] = useState('')
  const [overview, setOverview] = useState(null)
  const [sessions, setSessions] = useState([])
  const [selectedSessionId, setSelectedSessionId] = useState(null)
  const [sessionDetail, setSessionDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setError('')
    const qs = new URLSearchParams({ since_days: String(sinceDays) })
    if (orderId.trim()) qs.set('order_id', orderId.trim())
    const [ov, sess] = await Promise.all([
      apiFetch(`/admin/platform-services/surveys/wa-observability/overview?${qs}`),
      apiFetch(`/admin/platform-services/surveys/wa-sessions?${qs}&limit=100`),
    ])
    setOverview(ov || null)
    setSessions(sess?.sessions || [])
  }, [sinceDays, orderId])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load WA survey insights')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [load])

  const openSession = async (sessionId) => {
    setSelectedSessionId(sessionId)
    setSessionDetail(null)
    setDetailLoading(true)
    setError('')
    try {
      const detail = await apiFetch(
        `/admin/platform-services/surveys/wa-sessions/${encodeURIComponent(sessionId)}`,
      )
      setSessionDetail(detail)
    } catch (e) {
      setError(e?.message || 'Could not load session detail')
    } finally {
      setDetailLoading(false)
    }
  }

  const picker = overview?.picker || {}
  const metrics = useMemo(
    () => [
      {
        label: 'Sessions',
        value: overview?.session_count ?? '—',
        hint: overview?.since ? `Since ${fmtWhen(overview.since)}` : null,
        icon: MessageCircle,
        tone: 'info',
      },
      {
        label: 'Completed',
        value: overview?.sessions_by_status?.completed ?? 0,
        hint: `${overview?.sessions_by_status?.active ?? 0} active`,
        icon: CheckCircle2,
        tone: 'success',
      },
      {
        label: 'Delivery failures',
        value: overview?.delivery_failure_count ?? 0,
        hint: `${overview?.template_send_failure_count ?? 0} template failures`,
        icon: TriangleAlert,
        tone: 'danger',
      },
      {
        label: 'AI picker fallbacks',
        value: overview?.ai_picker_fallback_count ?? 0,
        hint: `${overview?.picker_invocation_count ?? 0} invocations`,
        icon: Bot,
        tone: 'warning',
      },
    ],
    [overview],
  )

  return (
    <div className="opsTheme">
      <div className="pageTop">
        <div>
          <h1><MessageCircle size={22} style={{ verticalAlign: 'middle', marginRight: 8 }} />WA Survey insights</h1>
          <p>
            Platform-wide WhatsApp adaptive survey sessions: delivery health, picker usage, and branch rules.
            Configure types and flows under{' '}
            <Link to="/settings/wa-survey" style={{ color: 'var(--grn)' }}>WA Survey settings</Link>.
          </p>
        </div>
        <div className="actions">
          <label className="waSurveyInsightFilter">
            <span className="muted">Days</span>
            <select className="input" value={sinceDays} onChange={(e) => setSinceDays(Number(e.target.value))}>
              <option value={1}>1</option>
              <option value={7}>7</option>
              <option value={14}>14</option>
              <option value={30}>30</option>
            </select>
          </label>
          <input
            className="input waSurveyInsightOrderFilter"
            placeholder="Filter by order ID…"
            value={orderId}
            onChange={(e) => setOrderId(e.target.value)}
          />
          <button type="button" className="btn soft" onClick={load} disabled={loading}>
            <RefreshCw size={15} />
            Refresh
          </button>
        </div>
      </div>

      {error ? <div className="note runningSurveyError">{error}</div> : null}

      <div className="note waSurveyInsightPickerNote">
        <strong>AI picker</strong> — platform: {picker.platform_enabled ? 'enabled' : 'disabled'}
        {' · '}
        kill switch: {picker.kill_switch ? 'ON (blocked)' : 'off'}
        {' · '}
        max calls/session: {picker.max_calls_per_session ?? '—'}
        {' · '}
        <Link to="/settings/wa-survey/simulator">Open simulator</Link>
      </div>

      <div className="ds-scope grid grid-cols-2 gap-3 lg:grid-cols-4">
        {metrics.map((m, i) => (
          <KpiCard key={m.label} icon={m.icon} label={m.label} value={m.value} hint={m.hint} tone={m.tone} index={i} />
        ))}
      </div>

      <div className="waSurveyInsightSplit">
        <div className="card waSurveyInsightListCard">
          <div className="cardHead">
            <h3><BarChart3 size={16} /> Recent sessions</h3>
          </div>
          <div className="cardBody">
            {loading ? <div className="muted">Loading…</div> : null}
            {!loading && !sessions.length ? <div className="muted">No sessions in this window.</div> : null}
            {!loading && sessions.length ? (
              <div className="tableWrap">
                <table className="table waSurveyInsightTable">
                  <thead>
                    <tr>
                      <th>Status</th>
                      <th>Flow</th>
                      <th>Outcome</th>
                      <th>Delivery</th>
                      <th>Order</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {sessions.map((s) => {
                      const del = deliveryOkBadge(s.outcome_delivery)
                      return (
                        <tr key={s.id} className={selectedSessionId === s.id ? 'isSelected' : ''}>
                          <td><span className={waSessionStatusPill(s.status)}>{s.status}</span></td>
                          <td>{s.flow_mode || '—'}</td>
                          <td>{s.outcome_key || '—'}</td>
                          <td><span className={del.className}>{del.label}</span></td>
                          <td className="muted" style={{ fontSize: '11px' }}>{s.order_id?.slice(0, 8)}…</td>
                          <td>
                            <button type="button" className="btn soft bsm" onClick={() => openSession(s.id)}>
                              Detail
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        </div>

        <div className="card waSurveyInsightDetailCard">
          <div className="cardHead">
            <h3>Session detail</h3>
          </div>
          <div className="cardBody">
            {detailLoading ? <div className="muted">Loading session…</div> : null}
            {!detailLoading && !sessionDetail ? (
              <div className="muted">Select a session to inspect answers, branches, and delivery.</div>
            ) : null}
            {!detailLoading && sessionDetail ? (
              <>
                {sessionDetail.order?.id ? (
                  <div className="note" style={{ marginBottom: 12 }}>
                    Order:{' '}
                    <Link to="/operations/running-surveys">{sessionDetail.order.title || sessionDetail.order.id}</Link>
                  </div>
                ) : null}
                <WaSurveySessionPanel data={sessionDetail} />
              </>
            ) : null}
          </div>
        </div>
      </div>

      {overview?.top_branch_rule_keys?.length ? (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="cardHead">
            <h3>Top branch rules</h3>
          </div>
          <div className="cardBody">
            <ul className="waSurveySessionList">
              {overview.top_branch_rule_keys.map((row) => (
                <li key={row.rule_key}>
                  <code>{row.rule_key}</code> — {row.count}
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}

      {(overview?.outcome_counts && Object.keys(overview.outcome_counts).length) ? (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="cardHead">
            <h3>Outcomes</h3>
          </div>
          <div className="cardBody waSurveyInsightOutcomes">
            {Object.entries(overview.outcome_counts).map(([key, count]) => (
              <div key={key} className="waSurveyInsightOutcomeChip">
                <strong>{key}</strong>
                <span className="muted">{count}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}
