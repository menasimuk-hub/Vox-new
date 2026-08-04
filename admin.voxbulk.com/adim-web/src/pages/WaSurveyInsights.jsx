import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { BarChart3, CheckCircle2, MessageCircle, RefreshCw, TriangleAlert, Bot } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { deliveryOkBadge, waSessionStatusPill } from '../lib/waSurveyOps'
import WaSurveySessionPanel from '../components/WaSurveySessionPanel'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { KpiCard } from '@/components/ui/KpiCard'
import '../styles/ops-theme.css'

function fmtWhen(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
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
    <div className="opsTheme ds-scope space-y-4">
      <div className="pageTop">
        <div>
          <h1 className="flex items-center gap-2">
            <MessageCircle className="h-5 w-5 text-muted-foreground" />
            WA Survey insights
          </h1>
          <p>
            Platform-wide WhatsApp adaptive survey sessions: delivery health, picker usage, and branch rules.
            Configure types and flows under{' '}
            <Link to="/settings/wa-survey" className="text-primary underline-offset-4 hover:underline">
              WA Survey settings
            </Link>
            .
          </p>
        </div>
        <div className="actions flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
            <span>Days</span>
            <select
              className="h-8 rounded-md border border-input bg-transparent px-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
              value={sinceDays}
              onChange={(e) => setSinceDays(Number(e.target.value))}
            >
              <option value={1}>1</option>
              <option value={7}>7</option>
              <option value={14}>14</option>
              <option value={30}>30</option>
            </select>
          </label>
          <Input
            className="h-8 w-[200px]"
            placeholder="Filter by order ID…"
            value={orderId}
            onChange={(e) => setOrderId(e.target.value)}
          />
          <Button type="button" variant="outline" size="sm" className="h-8" onClick={load} disabled={loading}>
            <RefreshCw className={loading ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} />
            Refresh
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="rounded-lg border border-border bg-surface-muted/50 px-3 py-2 text-[12px] text-muted-foreground">
        <strong className="text-foreground">AI picker</strong> — platform: {picker.platform_enabled ? 'enabled' : 'disabled'}
        {' · '}
        kill switch: {picker.kill_switch ? 'ON (blocked)' : 'off'}
        {' · '}
        max calls/session: {picker.max_calls_per_session ?? '—'}
        {' · '}
        <Link to="/settings/wa-survey/simulator" className="text-primary underline-offset-4 hover:underline">
          Open simulator
        </Link>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {metrics.map((m, i) => (
          <KpiCard key={m.label} icon={m.icon} label={m.label} value={m.value} hint={m.hint} tone={m.tone} index={i} />
        ))}
      </div>

      <div className="waSurveyInsightSplit grid gap-4 lg:grid-cols-2">
        <Panel title="Recent sessions" icon={BarChart3} bodyClassName="space-y-2">
          {loading ? <div className="text-sm text-muted-foreground">Loading…</div> : null}
          {!loading && !sessions.length ? <div className="text-sm text-muted-foreground">No sessions in this window.</div> : null}
          {!loading && sessions.length ? (
            <div className="tableWrap overflow-x-auto">
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
                        <td className="text-[11px] text-muted-foreground">{s.order_id?.slice(0, 8)}…</td>
                        <td>
                          <Button type="button" variant="outline" size="sm" className="h-7 text-[11px]" onClick={() => openSession(s.id)}>
                            Detail
                          </Button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : null}
        </Panel>

        <Panel title="Session detail" bodyClassName="space-y-3">
          {detailLoading ? <div className="text-sm text-muted-foreground">Loading session…</div> : null}
          {!detailLoading && !sessionDetail ? (
            <div className="text-sm text-muted-foreground">Select a session to inspect answers, branches, and delivery.</div>
          ) : null}
          {!detailLoading && sessionDetail ? (
            <>
              {sessionDetail.order?.id ? (
                <div className="rounded-md border border-border bg-surface-muted/40 px-3 py-2 text-[12px]">
                  Order:{' '}
                  <Link
                    to="/operations/running-surveys"
                    className="text-primary underline-offset-4 hover:underline"
                  >
                    {sessionDetail.order.title || sessionDetail.order.id}
                  </Link>
                </div>
              ) : null}
              <WaSurveySessionPanel data={sessionDetail} />
            </>
          ) : null}
        </Panel>
      </div>

      {overview?.top_branch_rule_keys?.length ? (
        <Panel title="Top branch rules">
          <ul className="waSurveySessionList space-y-1 text-sm">
            {overview.top_branch_rule_keys.map((row) => (
              <li key={row.rule_key}>
                <code>{row.rule_key}</code> — {row.count}
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      {(overview?.outcome_counts && Object.keys(overview.outcome_counts).length) ? (
        <Panel title="Outcomes" bodyClassName="waSurveyInsightOutcomes flex flex-wrap gap-2">
          {Object.entries(overview.outcome_counts).map(([key, count]) => (
            <div
              key={key}
              className="waSurveyInsightOutcomeChip flex items-center gap-2 rounded-md border border-border bg-surface-muted/40 px-2.5 py-1.5 text-[12px]"
            >
              <strong className="text-foreground">{key}</strong>
              <span className="text-muted-foreground">{count}</span>
            </div>
          ))}
        </Panel>
      ) : null}
    </div>
  )
}
