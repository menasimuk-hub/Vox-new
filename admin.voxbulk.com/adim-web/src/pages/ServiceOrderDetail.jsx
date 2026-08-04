import React, { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import {
  formatDurationSeconds,
  interviewFormatLabel,
  orderDeliveryLabel,
  orderEstimatedDurationMin,
  recipientSessionChannel,
} from '../lib/serviceOrderAdmin'
import OrderAdminBillingPanel from '../components/OrderAdminBillingPanel'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Pill } from '@/components/ui/Badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs'
import {
  StripeTable,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table'
import '../components/orderAdminBilling.css'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'calls', label: 'Calls & costs' },
  { id: 'activity', label: 'Activity' },
  { id: 'contacts', label: 'Contacts' },
  { id: 'audit', label: 'Audit' },
]

function fmtWhen(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

function statusTone(status) {
  const s = String(status || '').toLowerCase()
  if (['running', 'approved', 'paid', 'completed'].includes(s)) {
    if (s === 'running') return 'info'
    if (s === 'completed') return 'neutral'
    return 'success'
  }
  if (['paused', 'pending'].includes(s)) return 'warning'
  if (['failed', 'rejected'].includes(s)) return 'danger'
  return 'neutral'
}

function InfoRow({ label, value }) {
  return (
    <div className="flex justify-between gap-3 border-b border-border/60 py-1.5 text-[12px] last:border-0">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="text-right text-foreground">{value}</span>
    </div>
  )
}

function ActivityTimeline({ events }) {
  if (!events?.length) {
    return <div className="py-4 text-center text-sm text-muted-foreground">No activity events yet.</div>
  }
  return (
    <ul className="order-activity-timeline">
      {events.map((ev, i) => (
        <li key={`${ev.at}-${ev.code}-${i}`}>
          <span className="order-activity-time tabular-nums">{fmtWhen(ev.at)}</span>
          <span>
            <strong className="text-foreground">{ev.label || ev.code}</strong>
            {ev.detail ? <span className="text-muted-foreground"> — {ev.detail}</span> : null}
          </span>
        </li>
      ))}
    </ul>
  )
}

export default function ServiceOrderDetail() {
  const { orderId } = useParams()
  const navigate = useNavigate()
  const [order, setOrder] = useState(null)
  const [audit, setAudit] = useState([])
  const [tab, setTab] = useState('overview')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refSearch, setRefSearch] = useState('')
  const [activityByRecipient, setActivityByRecipient] = useState({})
  const [activityLoading, setActivityLoading] = useState(false)
  const [expandedActivityId, setExpandedActivityId] = useState('')

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

  const loadInterviewActivity = useCallback(async () => {
    if (!order?.id || order.service_code !== 'interview') return
    const recipients = Array.isArray(order.recipients) ? order.recipients : []
    if (!recipients.length) return
    setActivityLoading(true)
    try {
      const entries = await Promise.all(
        recipients.map(async (r) => {
          try {
            const data = await apiFetch(
              `/admin/platform-services/orders/${encodeURIComponent(order.id)}/recipients/${encodeURIComponent(r.id)}/activity`,
            )
            return [r.id, data]
          } catch {
            return [r.id, null]
          }
        }),
      )
      setActivityByRecipient(Object.fromEntries(entries))
    } finally {
      setActivityLoading(false)
    }
  }, [order])

  useEffect(() => {
    if (tab !== 'activity' || order?.service_code !== 'interview') return
    void loadInterviewActivity()
  }, [tab, order, loadInterviewActivity])

  const onRefSearch = async (e) => {
    e.preventDefault()
    const ref = refSearch.trim()
    if (!ref) return
    setError('')
    try {
      navigate(`/operations/orders/${encodeURIComponent(ref)}`)
    } catch (err) {
      setError(err?.message || 'Order not found')
    }
  }

  const recipients = order?.recipients || []
  const cfg = order?.config || {}
  const isWa = String(cfg.survey_channel || cfg.channel || '').toLowerCase() === 'whatsapp'
  const isInterview = order?.service_code === 'interview'
  const estMin = order ? orderEstimatedDurationMin(order) : null

  return (
    <div className="ds-scope mx-auto max-w-[1440px] space-y-4 px-1 pb-12 text-sm leading-relaxed">
      {error ? (
        <Panel className="border-destructive/40" bodyClassName="py-3">
          <p className="text-sm text-destructive">{error}</p>
        </Panel>
      ) : null}

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading order…</p>
      ) : null}

      {!loading && order ? (
        <Panel
          title={order.title || 'Service order'}
          subtitle={`${order.campaign_id || order.reference_id || order.id} · ${order.org_name || '—'} · ${order.recipient_count ?? recipients.length} contacts`}
          action={
            <div className="flex flex-wrap items-center gap-2">
              <Pill tone={statusTone(order.status_label || order.status)}>
                {order.status_label || order.status || '—'}
              </Pill>
              <Pill tone="neutral">{order.service_code || 'order'}</Pill>
            </div>
          }
          bodyClassName="space-y-4"
        >
          <form className="flex flex-wrap items-center gap-2" onSubmit={onRefSearch}>
            <Input
              className="h-8 max-w-sm flex-1"
              type="text"
              placeholder="Open by VB-CMP-… or order UUID"
              value={refSearch}
              onChange={(e) => setRefSearch(e.target.value)}
            />
            <Button type="submit" size="sm" className="h-8">
              Go
            </Button>
          </form>

          <OrderAdminBillingPanel order={order} showCallTable={false} />

          <Tabs value={tab} onValueChange={setTab}>
            <TabsList className="h-auto flex-wrap">
              {TABS.map((t) => (
                <TabsTrigger key={t.id} value={t.id} className="text-[12px]">
                  {t.label}
                </TabsTrigger>
              ))}
            </TabsList>

            <TabsContent value="overview" className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-lg border border-border bg-surface-muted/30 p-3">
                  <div className="mb-2 text-[12px] font-semibold text-foreground">Order</div>
                  <InfoRow label="Reference" value={order.reference_id || '—'} />
                  <InfoRow label="Campaign ID" value={order.campaign_id || '—'} />
                  <InfoRow
                    label="Delivery"
                    value={
                      order.service_code === 'interview'
                        ? interviewFormatLabel(order)
                        : orderDeliveryLabel(order)
                    }
                  />
                  {order.interview_sessions ? (
                    <InfoRow
                      label="Sessions"
                      value={`${order.interview_sessions.interview_format_label || '—'} — ${order.interview_sessions.web_sessions || 0} web, ${order.interview_sessions.phone_sessions || 0} phone, ${order.interview_sessions.total_billable_minutes || 0} billable min`}
                    />
                  ) : null}
                  <InfoRow
                    label="Channel"
                    value={cfg.delivery || cfg.survey_channel || cfg.channel || order.quote_survey_channel || '—'}
                  />
                  <InfoRow label="Est. minutes" value={estMin != null ? `${estMin} min` : '—'} />
                  <InfoRow label="Created" value={fmtWhen(order.created_at)} />
                  <InfoRow label="Started" value={fmtWhen(order.started_at)} />
                  <InfoRow label="Completed" value={fmtWhen(order.completed_at)} />
                </div>
                <div className="rounded-lg border border-border bg-surface-muted/30 p-3">
                  <div className="mb-2 text-[12px] font-semibold text-foreground">Customer</div>
                  <InfoRow label="Organisation" value={order.org_name || '—'} />
                  <InfoRow label="Owner" value={order.owner_email || '—'} />
                  {(cfg.wa_template_name || cfg.template_name) ? (
                    <InfoRow label="WA template" value={cfg.wa_template_name || cfg.template_name} />
                  ) : null}
                  {cfg.goal ? <InfoRow label="Goal" value={cfg.goal} /> : null}
                </div>
              </div>
              <OrderAdminBillingPanel order={order} showMetrics={false} showFootnote />
            </TabsContent>

            <TabsContent value="calls">
              <div className="overflow-x-auto">
                <StripeTable>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Contact</TableHead>
                      <TableHead>Phone</TableHead>
                      <TableHead>Email</TableHead>
                      <TableHead>Channel</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Duration</TableHead>
                      <TableHead>Min</TableHead>
                      <TableHead>R.cost</TableHead>
                      <TableHead>O.cost</TableHead>
                      <TableHead>Margin</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {!recipients.length ? (
                      <TableEmpty colSpan={11}>No contacts.</TableEmpty>
                    ) : (
                      recipients.map((r) => (
                        <TableRow key={r.id}>
                          <TableCell>{r.name || '—'}</TableCell>
                          <TableCell className="font-mono text-[12px]">{r.phone || '—'}</TableCell>
                          <TableCell>{r.email || '—'}</TableCell>
                          <TableCell>{recipientSessionChannel(r, order)}</TableCell>
                          <TableCell>{r.call_type || '—'}</TableCell>
                          <TableCell>{formatDurationSeconds(r.duration_seconds)}</TableCell>
                          <TableCell className="font-mono text-[12px]">{r.billable_minutes ?? '—'}</TableCell>
                          <TableCell className="font-mono text-[12px]">{r.retail_cost_display || '—'}</TableCell>
                          <TableCell className="font-mono text-[12px]">{r.operator_cost_display || '—'}</TableCell>
                          <TableCell className="font-mono text-[12px]">{r.margin_display || '—'}</TableCell>
                          <TableCell>{r.status || '—'}</TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </StripeTable>
              </div>
              <p className="mt-2 text-[11px] text-muted-foreground">
                R.cost = retail (billable min × rate + connection). O.cost = Telnyx operator (USD). Margin is not FX-adjusted.
              </p>
            </TabsContent>

            <TabsContent value="activity" className="space-y-3">
              <div className="rounded-lg border border-border bg-surface-muted/30 p-3">
                <div className="mb-2 text-[12px] font-semibold text-foreground">Campaign timeline (order audit)</div>
                <ActivityTimeline events={audit} />
              </div>
              {isInterview ? (
                <>
                  <div className="text-[12px] font-semibold text-foreground">Per-candidate activity</div>
                  {activityLoading ? (
                    <div className="py-4 text-center text-sm text-muted-foreground">Loading candidate timelines…</div>
                  ) : null}
                  {!activityLoading && !recipients.length ? (
                    <div className="py-4 text-center text-sm text-muted-foreground">No contacts.</div>
                  ) : null}
                  {recipients.map((r) => {
                    const activity = activityByRecipient[r.id]
                    const open = expandedActivityId === r.id
                    return (
                      <div key={r.id} className="rounded-lg border border-border bg-surface-muted/30 p-3">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-8"
                          onClick={() => setExpandedActivityId(open ? '' : r.id)}
                        >
                          {open ? '▼' : '▶'} {r.name || r.email || r.phone || r.id}
                          {activity?.activity_status ? (
                            <Pill tone="neutral" className="ml-2">
                              {activity.activity_status}
                            </Pill>
                          ) : null}
                        </Button>
                        {open ? (
                          <div className="mt-2">
                            <ActivityTimeline events={activity?.events || []} />
                          </div>
                        ) : null}
                      </div>
                    )
                  })}
                </>
              ) : (
                <p className="text-[11px] text-muted-foreground">
                  Per-candidate timelines are available for interview orders.
                </p>
              )}
            </TabsContent>

            <TabsContent value="contacts">
              <div className="overflow-x-auto">
                <StripeTable>
                  <TableHeader>
                    <TableRow>
                      <TableHead>#</TableHead>
                      <TableHead>Name</TableHead>
                      <TableHead>Phone</TableHead>
                      <TableHead>Email</TableHead>
                      {!isWa ? <TableHead>Channel</TableHead> : null}
                      {!isWa ? <TableHead>Duration</TableHead> : null}
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {recipients.map((r) => (
                      <TableRow key={r.id}>
                        <TableCell>{r.row_number}</TableCell>
                        <TableCell>{r.name}</TableCell>
                        <TableCell>{r.phone || '—'}</TableCell>
                        <TableCell>{r.email || '—'}</TableCell>
                        {!isWa ? <TableCell>{recipientSessionChannel(r, order)}</TableCell> : null}
                        {!isWa ? <TableCell>{formatDurationSeconds(r.duration_seconds)}</TableCell> : null}
                        <TableCell>{r.status || '—'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </StripeTable>
              </div>
            </TabsContent>

            <TabsContent value="audit">
              {!audit.length ? (
                <div className="py-4 text-center text-sm text-muted-foreground">No audit events.</div>
              ) : (
                <div className="overflow-x-auto">
                  <StripeTable>
                    <TableHeader>
                      <TableRow>
                        <TableHead>When</TableHead>
                        <TableHead>Event</TableHead>
                        <TableHead>Detail</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {audit.map((ev, i) => (
                        <TableRow key={`${ev.at}-${i}`}>
                          <TableCell className="text-[12px] text-muted-foreground">{fmtWhen(ev.at)}</TableCell>
                          <TableCell>{ev.label || ev.kind}</TableCell>
                          <TableCell>{ev.detail || '—'}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </StripeTable>
                </div>
              )}
            </TabsContent>
          </Tabs>

          <div className="flex flex-wrap gap-2 border-t border-border pt-3">
            <Button asChild variant="outline" size="sm" className="h-8">
              <Link to="/organisations/all-users">← Control Center</Link>
            </Button>
            {order.org_id ? (
              <Button asChild variant="outline" size="sm" className="h-8">
                <Link to={`/organisations/${order.org_id}`}>Organisation</Link>
              </Button>
            ) : null}
            {order.service_code === 'survey' ? (
              <Button asChild size="sm" className="h-8">
                <Link to={`/operations/running-surveys?order=${encodeURIComponent(orderId)}`}>
                  Manage survey
                </Link>
              </Button>
            ) : null}
            {order.service_code === 'interview' ? (
              <Button asChild size="sm" className="h-8">
                <Link to={`/operations/running-interviews?order=${encodeURIComponent(orderId)}`}>
                  Manage interview
                </Link>
              </Button>
            ) : null}
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8"
              onClick={() => load().catch((e) => setError(e?.message))}
            >
              Refresh
            </Button>
          </div>
        </Panel>
      ) : null}
    </div>
  )
}
