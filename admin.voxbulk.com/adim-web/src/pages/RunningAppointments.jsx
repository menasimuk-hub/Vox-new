import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Building2, CalendarClock, RefreshCw, Users } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Pill } from '@/components/ui/Badge'
import { KpiCard } from '@/components/ui/KpiCard'
import {
  StripeTable,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableLoading,
  TableRow,
} from '@/components/ui/Table'

function issueTone(level) {
  if (level === 'error') return 'danger'
  return 'warning'
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
  const [templatesError, setTemplatesError] = useState('')

  const load = useCallback(async () => {
    setError('')
    setOrgsError('')
    setTemplatesError('')
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
      const msg = listRes.reason?.message || 'Could not load customers'
      setOrgsError(msg)
      if (/display_name/i.test(msg)) {
        setOrgsError(
          `${msg} — Production API is stale. On the VPS run: git pull origin main && ./deploy-vps.sh (do not use VOX_SKIP_BUILD=1), then hard-refresh this page.`,
        )
      }
    }
    if (tplRes.status === 'fulfilled') {
      setTemplates(Array.isArray(tplRes.value?.templates) ? tplRes.value.templates : [])
    } else {
      setTemplates([])
      setTemplatesError(tplRes.reason?.message || 'Could not load WA appointment templates')
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

  const kpiLoading = loading && !overview

  return (
    <div className="ds-scope space-y-4">
      <div className="pageTop">
        <div>
          <h1>Appointment Manager</h1>
          <p>Customers with the appointments module — setup status, WA templates, agents, and live pipeline.</p>
        </div>
        <div className="actions">
          <Button asChild variant="outline" size="sm" className="h-8">
            <Link to="/ai/agents">Appointment agents</Link>
          </Button>
          <Button asChild variant="outline" size="sm" className="h-8">
            <Link to="/settings/wa-appointment">WA templates</Link>
          </Button>
          <Button asChild variant="outline" size="sm" className="h-8">
            <Link to="/onboarding/services">Dashboard modules</Link>
          </Button>
          <Button
            type="button"
            size="sm"
            className="h-8"
            onClick={() => load().catch((e) => setError(e?.message))}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}
      {orgsError ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {orgsError}
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          label="Active customers"
          value={kpiLoading ? '…' : (overview?.active_orgs ?? 0)}
          icon={Building2}
          tone="info"
        />
        <KpiCard
          label="Total appointments"
          value={kpiLoading ? '…' : (overview?.total_appointments ?? 0)}
          icon={CalendarClock}
          tone="primary"
        />
        <KpiCard
          label="At risk (24h)"
          value={kpiLoading ? '…' : (overview?.at_risk_24h ?? 0)}
          hint="Unconfirmed soon"
          icon={AlertTriangle}
          tone="warning"
        />
        <KpiCard
          label="Customers with issues"
          value={kpiLoading ? '…' : (overview?.orgs_with_issues ?? 0)}
          hint="Setup / CRM / agent"
          icon={Users}
          tone="danger"
        />
      </div>

      <Panel
        title="Appointment AI agents"
        action={
          <Button asChild variant="outline" size="sm" className="h-7 text-[11px]">
            <Link to="/ai/agents">Manage agents</Link>
          </Button>
        }
        bodyClassName="space-y-3"
      >
        {(overview?.appointment_agents || []).length ? (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {overview.appointment_agents.map((a) => (
              <div key={a.id} className="rounded-lg border border-border bg-surface-muted/40 p-2.5">
                <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  {a.voice_label || a.name}
                </div>
                <div className="text-sm font-medium text-foreground">{a.name}</div>
                {a.is_default ? (
                  <div className="mt-0.5 text-[11px] text-muted-foreground">Platform default</div>
                ) : null}
                <Button asChild variant="outline" size="sm" className="mt-2 h-7 text-[11px]">
                  <Link to={`/ai/agents/${a.id}`}>Edit agent</Link>
                </Button>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-md border border-border bg-surface-muted/40 px-3 py-2 text-sm text-muted-foreground">
            No appointment agents yet. Open <Link to="/ai/agents" className="text-primary underline-offset-4 hover:underline">AI → Agents</Link>, edit an agent, enable <strong className="text-foreground">Appointments</strong> under Service assignment, and mark one as <strong className="text-foreground">Default</strong>. Customers pick the agent in their dashboard setup wizard when AI calls are on.
          </div>
        )}
      </Panel>

      <Panel
        title="Platform WA templates"
        action={
          <Button asChild variant="outline" size="sm" className="h-7 text-[11px]">
            <Link to="/settings/wa-appointment">Manage templates</Link>
          </Button>
        }
        bodyClassName="space-y-3"
      >
        {templatesError ? (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {templatesError}
          </div>
        ) : null}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {(templates.length ? templates : [
            { label: 'Appointment confirmation', name: 'appt_confirm_v1' },
            { label: 'Friendly confirmation', name: 'appt_confirm_v2' },
            { label: 'Appointment reminder', name: 'appt_reminder_v1' },
            { label: 'Clinic reminder', name: 'appt_reminder_v2' },
          ]).map((t) => (
            <div key={t.id || t.name} className="rounded-lg border border-border bg-surface-muted/40 p-2.5">
              <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
                {t.display_name || t.label}
              </div>
              <div className="text-sm font-medium text-foreground">{t.name}</div>
              {t.active_for_appointment === false ? (
                <div className="mt-0.5 text-[11px] text-muted-foreground">Hidden</div>
              ) : null}
              <Button asChild variant="outline" size="sm" className="mt-2 h-7 text-[11px]">
                <Link to={t.id ? `/settings/wa-appointment?edit=${t.id}` : '/settings/wa-appointment'}>
                  {t.id ? 'Edit' : 'Open editor'}
                </Link>
              </Button>
            </div>
          ))}
        </div>
        {!templates.length && !loading ? (
          <p className="text-[12px] text-muted-foreground">
            Templates seed on first API load after migration <code>0130</code>. If this persists after deploy, open Manage templates and click Refresh.
          </p>
        ) : null}
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel
          title="Customers"
          action={
            <Input
              className="h-8 w-[180px]"
              placeholder="Search org…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          }
          bodyClassName="p-0"
        >
          <StripeTable>
            <TableHeader>
              <TableRow>
                <TableHead>Organisation</TableHead>
                <TableHead>Setup</TableHead>
                <TableHead>Appts</TableHead>
                <TableHead>Risk</TableHead>
                <TableHead>Issues</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableLoading colSpan={5} />
              ) : !filtered.length ? (
                <TableEmpty colSpan={5}>
                  No customers with appointments enabled. Grant the module in Dashboard modules first.
                </TableEmpty>
              ) : (
                filtered.map((o) => (
                  <TableRow
                    key={o.org_id}
                    data-state={selectedId === o.org_id ? 'selected' : undefined}
                    className="cursor-pointer"
                    onClick={() => setSelectedId(o.org_id)}
                  >
                    <TableCell>
                      <strong className="text-foreground">{o.org_name}</strong>
                      <div className="text-[12px] text-muted-foreground">{o.contact_email}</div>
                    </TableCell>
                    <TableCell>
                      {o.setup_complete ? (
                        <Pill tone="success">Live</Pill>
                      ) : (
                        <Pill tone="warning">Setup pending</Pill>
                      )}
                    </TableCell>
                    <TableCell>{o.appointment_count}</TableCell>
                    <TableCell>
                      {o.at_risk_24h > 0 ? <Pill tone="warning">{o.at_risk_24h}</Pill> : '—'}
                    </TableCell>
                    <TableCell>
                      {o.issue_count > 0 ? <Pill tone="danger">{o.issue_count}</Pill> : 'OK'}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </StripeTable>
        </Panel>

        <Panel
          title={detail?.org?.name || 'Customer detail'}
          action={
            detail?.org?.id ? (
              <Button asChild variant="outline" size="sm" className="h-7 text-[11px]">
                <Link to={`/organisations/${detail.org.id}`}>Open org</Link>
              </Button>
            ) : null
          }
          bodyClassName="space-y-4"
        >
          {!detail ? (
            <p className="text-sm text-muted-foreground">Select a customer to view configuration and appointment processes.</p>
          ) : (
            <>
              {!detail.config?.setup_complete ? (
                <div className="rounded-md border border-warning/40 bg-warning-soft px-3 py-2 text-sm text-warning">
                  Customer has not completed the dashboard setup wizard yet.
                </div>
              ) : null}

              {detail.issues?.length ? (
                <div>
                  <strong className="text-sm text-foreground">Support flags</strong>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
                    {detail.issues.map((i) => (
                      <li key={i.code}>
                        <Pill tone={issueTone(i.level)} className="mr-2">
                          {i.level}
                        </Pill>
                        {i.message}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <div className="grid grid-cols-2 gap-2">
                <KpiCard label="WA template" value={detail.config?.wa_template_name || '—'} tone="info" />
                <KpiCard label="WhatsApp" value={detail.config?.wa_enabled ? 'On' : 'Off'} tone="primary" />
                <KpiCard label="AI calls" value={detail.config?.call_enabled ? 'On' : 'Off'} tone="primary" />
                <KpiCard label="CRM" value={detail.config?.crm_provider || '—'} tone="info" />
              </div>

              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <div className="text-[11px] text-muted-foreground">Outreach window</div>
                  <div className="text-foreground">
                    {detail.config?.outreach_window_start || '09:00'} – {detail.config?.outreach_window_end || '16:00'}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] text-muted-foreground">AI agent</div>
                  <div className="text-foreground">{detail.agent?.voice_label || detail.agent?.name || '—'}</div>
                </div>
              </div>

              <div>
                <strong className="text-sm text-foreground">Appointment processes</strong>
                <div className="mt-2 overflow-x-auto">
                  <StripeTable>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Contact</TableHead>
                        <TableHead>When</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Flags</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(detail.appointments || []).length === 0 ? (
                        <TableEmpty colSpan={4}>No appointments.</TableEmpty>
                      ) : (
                        (detail.appointments || []).map((a) => (
                          <TableRow key={a.id}>
                            <TableCell>
                              {a.contact_name}
                              <div className="text-[11px] text-muted-foreground">{a.contact_phone}</div>
                            </TableCell>
                            <TableCell className="text-[12px]">
                              {a.appointment_datetime ? new Date(a.appointment_datetime).toLocaleString() : '—'}
                            </TableCell>
                            <TableCell>{a.status}</TableCell>
                            <TableCell>
                              {(a.flags || []).map((f) => (
                                <Pill key={f} tone="warning" className="mr-1">
                                  {f}
                                </Pill>
                              ))}
                              {!a.flags?.length ? '—' : null}
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </StripeTable>
                </div>
              </div>
            </>
          )}
        </Panel>
      </div>
    </div>
  )
}
