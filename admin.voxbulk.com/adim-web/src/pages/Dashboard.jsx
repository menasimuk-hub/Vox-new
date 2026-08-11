import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  Bot,
  Building2,
  CheckCircle2,
  CircleDollarSign,
  CreditCard,
  Database,
  Inbox,
  LifeBuoy,
  Megaphone,
  MessageSquare,
  QrCode,
  RefreshCw,
  Server,
  Settings2,
  Sparkles,
  Timer,
  UserPlus,
  Wallet,
  Zap,
} from 'lucide-react'
import { apiFetch } from '../lib/api'
import { normalizeAdminRole } from '../lib/adminPaths'
import { useAdminProfile } from '../context/AdminProfileContext'
import {
  INTEGRATION_PROVIDERS,
  integrationCardStatus,
} from '../lib/integrationsCatalog'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { KpiCard } from '@/components/ui/KpiCard'
import { Progress } from '@/components/ui/Progress'
import { Separator } from '@/components/ui/Separator'
import { Switch } from '@/components/ui/Switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/Sheet'
import { Sparkline, StatusDot, spark } from '@/components/ui/Sparkline'

function deferNonCritical(task) {
  const run = window.requestIdleCallback || ((fn) => window.setTimeout(fn, 250))
  return run(task)
}

const n = (value) => Number(value || 0).toLocaleString()
const money = (amount, currency = 'USD') => {
  const value = Number(amount)
  if (!Number.isFinite(value)) return '—'
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: currency || 'USD' }).format(value)
  } catch {
    return `${currency || 'USD'} ${value.toFixed(2)}`
  }
}
const fmt = (value) => {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return String(value)
  }
}

const HEALTH_BALANCE_KEYS = {
  telnyx: 'telnyx',
  elevenlabs: 'elevenlabs',
}

function balanceDetail(key, balances) {
  if (key === 'telnyx') {
    const row = balances?.telnyx
    if (!row?.ok) return row?.message || 'Not configured'
    return `${money(row.amount, row.currency)} credit${row.pending > 0 ? ` · ${money(row.pending, row.currency)} pending` : ''}`
  }
  if (key === 'elevenlabs') {
    const row = balances?.elevenlabs
    if (!row?.ok) return row?.message || 'Not configured'
    return `${n(row.characters_remaining)} chars left · ${row.tier || 'tier'}`
  }
  return 'Configured'
}

function integrationMetaLine(key, summary, balances) {
  if (HEALTH_BALANCE_KEYS[key]) return balanceDetail(key, balances)
  if (summary?.updated_at) return `Updated ${fmt(summary.updated_at)}`
  return 'Running · credentials configured'
}

function toneFromCount(count, { warnAt = 1, badAt = null } = {}) {
  const v = Number(count || 0)
  if (badAt != null && v >= badAt) return 'bad'
  if (v >= warnAt) return 'warn'
  return 'ok'
}

export default function Dashboard() {
  const navigate = useNavigate()
  const { adminRole } = useAdminProfile()
  const isSuper = normalizeAdminRole(adminRole) === 'superadmin'

  const [loading, setLoading] = useState(true)
  const [integrationsLoading, setIntegrationsLoading] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [health, setHealth] = useState({})
  const [providerBalances, setProviderBalances] = useState({ telnyx: null, elevenlabs: null })
  const [billing, setBilling] = useState(null)
  const [operations, setOperations] = useState(null)
  const [support, setSupport] = useState(null)
  const [orgSummary, setOrgSummary] = useState({ total: 0, active: 0 })
  const [pending, setPending] = useState([])
  const [accountDeletions, setAccountDeletions] = useState({ items: [], pending_count: 0 })
  const [tickets, setTickets] = useState([])
  const [surveys, setSurveys] = useState(null)
  const [interviews, setInterviews] = useState(null)
  const [celery, setCelery] = useState(null)
  const [celeryRestarting, setCeleryRestarting] = useState(false)
  const [celeryMsg, setCeleryMsg] = useState('')
  const [error, setError] = useState('')
  const [activeKpi, setActiveKpi] = useState(null)
  const [productTab, setProductTab] = useState('wa')
  const [integrationQuery, setIntegrationQuery] = useState('')
  const [onlineOnly, setOnlineOnly] = useState(false)
  const [stats, setStats] = useState({ pending_approval: 0 })

  const loadIntegrations = useCallback(async () => {
    if (!isSuper) {
      setHealth({})
      return
    }
    setIntegrationsLoading(true)
    try {
      const next = {}
      const providers = INTEGRATION_PROVIDERS
      for (let i = 0; i < providers.length; i += 3) {
        const chunk = providers.slice(i, i + 3)
        await Promise.all(
          chunk.map(async (p) => {
            try {
              next[p.key] = await apiFetch(`/admin/integrations/${p.key}`, { timeoutMs: 45000 })
            } catch {
              next[p.key] = { error: true }
            }
          }),
        )
      }
      setHealth(next)
    } finally {
      setIntegrationsLoading(false)
    }
  }, [isSuper])

  const loadAll = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [
        billingRes,
        operationsRes,
        supportRes,
        orgSummaryRes,
        pendingRes,
        deletionsRes,
        ticketsRes,
        balancesRes,
        surveysRes,
        interviewsRes,
        opsPendingRes,
      ] = await Promise.all([
        apiFetch('/admin/billing/overview').catch(() => null),
        apiFetch('/admin/operations/overview').catch(() => null),
        apiFetch('/admin/support/kpis').catch(() => null),
        apiFetch('/admin/organisations/summary').catch(() => ({ total: 0, active: 0 })),
        apiFetch('/admin/onboarding/requests?status_filter=pending').catch(() => []),
        apiFetch('/admin/account-deletions?status_filter=pending&limit=20').catch(() => ({ items: [], pending_count: 0 })),
        apiFetch('/admin/support/tickets?limit=12&status_filter=open').catch(() => []),
        apiFetch('/admin/dashboard/provider-balances').catch(() => null),
        apiFetch('/admin/platform-services/surveys/overview').catch(() => null),
        apiFetch('/admin/platform-services/interviews/overview').catch(() => null),
        apiFetch('/admin/ops-pending').catch(() => ({ pending_approval: 0, offer_queue_ready: 0, demo_requests: 0 })),
      ])

      setBilling(billingRes)
      setOperations(operationsRes)
      setSupport(supportRes)
      setStats(opsPendingRes || { pending_approval: 0, offer_queue_ready: 0, demo_requests: 0 })
      setOrgSummary(
        orgSummaryRes && typeof orgSummaryRes === 'object'
          ? {
              total: Number(orgSummaryRes.total || 0),
              active: Number(orgSummaryRes.active || 0),
            }
          : { total: 0, active: 0 },
      )
      setPending(Array.isArray(pendingRes) ? pendingRes : [])
      setAccountDeletions(
        deletionsRes && typeof deletionsRes === 'object'
          ? {
              items: Array.isArray(deletionsRes.items) ? deletionsRes.items : [],
              pending_count: Number(deletionsRes.pending_count || 0),
            }
          : { items: [], pending_count: 0 },
      )
      setTickets(Array.isArray(ticketsRes) ? ticketsRes : [])
      setProviderBalances(balancesRes || { telnyx: null, elevenlabs: null })
      setSurveys(surveysRes)
      setInterviews(interviewsRes)
      setCeleryMsg('')
    } catch (e) {
      setError(e?.message || 'Could not load dashboard')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadCelery = useCallback(async () => {
    if (!isSuper) {
      setCelery(null)
      return
    }
    try {
      const res = await apiFetch('/admin/operations/celery', { timeoutMs: 20000 })
      setCelery(res || null)
    } catch {
      setCelery({ ok: false, issues: ['Could not load Celery status'] })
    }
  }, [isSuper])

  const restartCelery = async () => {
    if (!isSuper) return
    if (!window.confirm('Restart Celery worker and beat on the server? Deferred jobs and schedules will resume after a few seconds.')) {
      return
    }
    setCeleryRestarting(true)
    setCeleryMsg('')
    try {
      const res = await apiFetch('/admin/operations/celery/restart', { method: 'POST', body: JSON.stringify({}) })
      setCelery(res?.status || res || null)
      setCeleryMsg(res?.ok ? 'Celery restarted successfully.' : res?.detail || 'Restart finished with issues — check status below.')
    } catch (e) {
      setCeleryMsg(e?.message || 'Celery restart failed')
      await loadCelery()
    } finally {
      setCeleryRestarting(false)
    }
  }

  useEffect(() => {
    void loadAll()
  }, [loadAll, refreshKey])

  useEffect(() => {
    if (!isSuper) return undefined
    let cancelled = false
    const idleId = deferNonCritical(() => {
      if (!cancelled) void loadCelery()
    })
    return () => {
      cancelled = true
      if (window.cancelIdleCallback && typeof idleId === 'number') {
        window.cancelIdleCallback(idleId)
      }
    }
  }, [isSuper, loadCelery, refreshKey])

  useEffect(() => {
    if (!isSuper) return undefined
    let cancelled = false
    const idleId = deferNonCritical(() => {
      if (!cancelled) void loadIntegrations()
    })
    return () => {
      cancelled = true
      if (window.cancelIdleCallback && typeof idleId === 'number') {
        window.cancelIdleCallback(idleId)
      }
    }
  }, [isSuper, loadIntegrations, refreshKey])

  const webhooks = operations?.webhooks || {}
  const orgTotal = orgSummary.total
  const activeOrgs = orgSummary.active
  const telnyxBalance = providerBalances?.telnyx
  const elevenBalance = providerBalances?.elevenlabs
  const openTickets = support?.total_open ?? support?.open ?? 0
  const pastDue = billing?.subscriptions_past_due ?? 0
  const failedHooks = webhooks.failed || 0

  const enabledIntegrations = useMemo(() => {
    const q = integrationQuery.trim().toLowerCase()
    return INTEGRATION_PROVIDERS.filter((p) => {
      const s = health[p.key]
      const online = Boolean(s && s.is_enabled && s.configured && !s.error)
      if (!online && !s) return false
      if (!s || !s.is_enabled || !s.configured || s.error) {
        if (onlineOnly) return false
        // Still show only enabled+configured in the grid (same as before)
        return false
      }
      if (onlineOnly && !online) return false
      if (!q) return true
      return (
        p.label.toLowerCase().includes(q) ||
        (p.group || '').toLowerCase().includes(q) ||
        (p.blurb || '').toLowerCase().includes(q)
      )
    })
  }, [health, integrationQuery, onlineOnly])

  const overviewKpis = useMemo(() => {
    const dash = loading ? '…' : null
    return [
      {
        id: 'orgs',
        label: 'Organisations',
        value: dash ?? n(orgTotal),
        sub: `${n(activeOrgs)} active`,
        icon: Building2,
        valueTone: 'default',
        href: '/organisations',
        detail: [`${n(activeOrgs)} active of ${n(orgTotal)} total`, 'Open Organisations to manage tenants'],
        spark: spark(3),
      },
      {
        id: 'subs',
        label: 'Active subscriptions',
        value: dash ?? n(billing?.subscriptions_active),
        sub: `${n(billing?.subscriptions_trial)} trial`,
        icon: CreditCard,
        valueTone: 'ok',
        href: '/billing/subscriptions',
        detail: [
          `${n(billing?.subscriptions_active)} paying · ${n(billing?.subscriptions_trial)} trial`,
          `Latest: ${fmt(billing?.latest_subscription_created_at)}`,
        ],
        spark: spark(4),
      },
      {
        id: 'pastdue',
        label: 'Past due',
        value: dash ?? n(pastDue),
        sub: `${n(billing?.subscriptions_pending_payment)} pending pay`,
        icon: AlertTriangle,
        valueTone: toneFromCount(pastDue),
        href: '/billing/subscriptions',
        detail: [`${n(pastDue)} past due`, `${n(billing?.subscriptions_pending_payment)} pending payment`],
        spark: spark(5),
      },
      {
        id: 'tickets',
        label: 'Open tickets',
        value: dash ?? n(openTickets),
        sub: `${n(support?.unassigned ?? 0)} unassigned`,
        icon: LifeBuoy,
        valueTone: toneFromCount(openTickets),
        href: '/support/inbox',
        detail: [`${n(openTickets)} open`, `${n(support?.unassigned ?? 0)} unassigned`],
        spark: spark(6),
      },
      {
        id: 'wa',
        label: 'WA surveys live',
        value: dash ?? n(surveys?.live ?? 0),
        sub: `${n(surveys?.total ?? 0)} total`,
        icon: MessageSquare,
        valueTone: 'default',
        href: '/operations/running-surveys',
        detail: [
          `${n(surveys?.running ?? surveys?.live ?? 0)} running · ${n(surveys?.scheduled ?? 0)} scheduled · ${n(surveys?.completed ?? 0)} completed · ${n(surveys?.paused ?? 0)} paused`,
        ],
        spark: spark(7),
      },
      {
        id: 'ai',
        label: 'AI interviews live',
        value: dash ?? n(interviews?.live ?? 0),
        sub: `${n(interviews?.total ?? 0)} total`,
        icon: Bot,
        valueTone: 'default',
        href: '/operations/running-interviews',
        detail: [
          `${n(interviews?.running ?? interviews?.live ?? 0)} running · ${n(interviews?.scheduled ?? 0)} scheduled · ${n(interviews?.completed ?? 0)} completed · ${n(interviews?.drafts ?? 0)} drafts`,
        ],
        spark: spark(8),
      },
      {
        id: 'hooks',
        label: 'Failed webhooks',
        value: dash ?? n(failedHooks),
        sub: 'recent delivery errors',
        icon: Zap,
        valueTone: toneFromCount(failedHooks),
        href: '/integrations/webhooks',
        detail: [`${n(failedHooks)} recent failures`, `Latest: ${fmt(webhooks.latest_received_at)}`],
        spark: spark(9),
      },
      {
        id: 'credit',
        label: 'Telnyx credit',
        value: dash ?? (telnyxBalance?.ok ? money(telnyxBalance.amount, telnyxBalance.currency) : '—'),
        sub: 'voice / SMS balance',
        icon: Wallet,
        valueTone: telnyxBalance?.ok && Number(telnyxBalance.amount) < 20 ? 'warn' : telnyxBalance?.ok ? 'ok' : 'warn',
        href: '/integrations/telnyx',
        detail: [telnyxBalance?.ok ? money(telnyxBalance.amount, telnyxBalance.currency) : telnyxBalance?.message || 'Not configured'],
        spark: spark(10),
      },
    ]
  }, [
    loading,
    orgTotal,
    activeOrgs,
    billing,
    pastDue,
    openTickets,
    support,
    surveys,
    interviews,
    failedHooks,
    webhooks.latest_received_at,
    telnyxBalance,
  ])

  const productTabs = useMemo(
    () => [
      {
        id: 'wa',
        label: 'WA Survey',
        live: surveys?.live ?? 0,
        total: surveys?.total ?? 0,
        icon: MessageSquare,
        href: '/operations/running-surveys',
        breakdown: [
          { label: 'Running', value: surveys?.running ?? surveys?.live ?? 0 },
          { label: 'Scheduled', value: surveys?.scheduled ?? 0 },
          { label: 'Completed', value: surveys?.completed ?? 0 },
          { label: 'Paused', value: surveys?.paused ?? 0 },
        ],
      },
      {
        id: 'ai',
        label: 'AI Interview',
        live: interviews?.live ?? 0,
        total: interviews?.total ?? 0,
        icon: Bot,
        href: '/operations/running-interviews',
        breakdown: [
          { label: 'Running', value: interviews?.running ?? interviews?.live ?? 0 },
          { label: 'Scheduled', value: interviews?.scheduled ?? 0 },
          { label: 'Completed', value: interviews?.completed ?? 0 },
          { label: 'Drafts', value: interviews?.drafts ?? 0 },
        ],
      },
      {
        id: 'campaigns',
        label: 'Campaigns',
        live: null,
        total: null,
        icon: Megaphone,
        href: '/campaigns',
        breakdown: [
          { label: 'Hub', value: '—', note: 'Template library' },
          { label: 'Broadcast', value: '—', note: 'Outbound' },
        ],
      },
      {
        id: 'feedback',
        label: 'Feedback',
        live: null,
        total: null,
        icon: Sparkles,
        href: '/customer-feedback/industries',
        breakdown: [
          { label: 'Catalog', value: '—', note: 'Industries' },
          { label: 'Results', value: '—', note: 'WA feedback' },
        ],
      },
    ],
    [surveys, interviews],
  )

  const celeryStats = useMemo(() => {
    const workerOk = Boolean(celery?.worker?.ping?.ok || celery?.worker?.process_running)
    const beatOk = Boolean(celery?.beat?.schedule?.ok || celery?.beat?.process_running)
    const redisOk = Boolean(celery?.redis?.ok)
    const criticalHave = (celery?.worker?.tasks?.has_critical || []).length
    const criticalNeed = (celery?.critical_tasks || []).length || 4
    const criticalOk = criticalHave >= criticalNeed && !celery?.worker?.tasks?.missing_critical?.length
    return [
      {
        label: 'Worker',
        value: loading ? '…' : celery?.worker?.supervisor?.state || (celery?.worker?.process_running ? 'PROCESS' : '—'),
        note: `ping ${celery?.worker?.ping?.ok ? 'ok' : 'fail'}${celery?.worker?.ping?.nodes?.length ? ` · ${celery.worker.ping.nodes.length} node(s)` : ''}`,
        tone: workerOk ? 'ok' : 'bad',
      },
      {
        label: 'Beat',
        value: loading ? '…' : celery?.beat?.supervisor?.state || (celery?.beat?.process_running ? 'PROCESS' : '—'),
        note: `schedule ${celery?.beat?.schedule?.ok ? 'ok' : 'check needed'}`,
        tone: beatOk ? 'ok' : 'warn',
      },
      {
        label: 'Redis',
        value: loading ? '…' : celery?.redis?.ok ? 'OK' : 'DOWN',
        note: celery?.redis?.detail || 'broker',
        tone: redisOk ? 'ok' : 'bad',
      },
      {
        label: 'Critical tasks',
        value: loading ? '…' : `${criticalHave}/${criticalNeed}`,
        note: celery?.stale_code
          ? 'Restart needed after deploy'
          : celery?.worker?.tasks?.missing_critical?.length
            ? `Missing: ${celery.worker.tasks.missing_critical.join(', ')}`
            : 'registered on worker',
        tone: criticalOk ? 'ok' : 'warn',
      },
    ]
  }, [celery, loading])

  const systemsOk = celery?.ok !== false && Number(failedHooks) === 0

  const decideSignup = async (id, action) => {
    try {
      await apiFetch(`/admin/onboarding/requests/${id}/${action}`, { method: 'POST', body: JSON.stringify({}) })
      setRefreshKey((k) => k + 1)
    } catch (e) {
      window.alert(e?.message || 'Action failed')
    }
  }

  const openOrgUsers = (organisationId) => {
    localStorage.setItem('voxbulk_admin_selected_org_id', organisationId)
    navigate('/organisations/profile?tab=users')
  }

  return (
    <div className="space-y-3">
      <div className="sticky top-0 z-20 -mx-4 border-b border-border/70 bg-background/85 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/70 sm:-mx-0 sm:rounded-none">
        <div className="flex flex-wrap items-center gap-3 py-2.5">
          <div className="min-w-0">
            <h1 className="text-[15px] font-semibold leading-tight text-foreground">Platform overview</h1>
            <p className="text-[11px] leading-tight text-muted-foreground">
              Compact KPIs with mini charts — click a card for detail.
            </p>
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="gap-1.5 rounded-full text-[10px]">
              <StatusDot tone={systemsOk ? 'ok' : 'warn'} />
              {systemsOk ? 'All systems operational' : 'Attention needed'}
            </Badge>
            <span className="hidden text-[11px] text-muted-foreground sm:inline">
              Checked {celery?.checked_at ? fmt(celery.checked_at) : loading ? '…' : '—'}
            </span>
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1.5 text-[11px]"
              onClick={() => setRefreshKey((k) => k + 1)}
              disabled={loading}
            >
              <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
              {loading ? 'Refreshing…' : 'Refresh'}
            </Button>
            <Button asChild size="sm" variant="outline" className="h-7 text-[11px]">
              <Link to="/analytics/kpis">Analytics</Link>
            </Button>
            <Button asChild size="sm" className="h-7 text-[11px]">
              <Link to="/onboarding/add-customer">Add customer</Link>
            </Button>
          </div>
        </div>
      </div>

      {error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-[12px] text-destructive">
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-8">
        {overviewKpis.map((kpi, i) => (
          <KpiCard
            key={kpi.id}
            variant="dashboard"
            index={i}
            icon={kpi.icon}
            label={kpi.label}
            value={kpi.value}
            sub={kpi.sub}
            valueTone={kpi.valueTone}
            spark={kpi.spark}
            onClick={() => setActiveKpi(kpi)}
          />
        ))}
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <Panel
          title="Celery / background jobs"
          description="Worker + beat health for deferred WA surveys, billing, and voice notes."
          icon={Server}
          action={
            isSuper ? (
              <Button
                size="sm"
                variant="outline"
                className="h-7 gap-1.5 text-[11px]"
                onClick={() => void restartCelery()}
                disabled={celeryRestarting || loading}
              >
                <RefreshCw className={cn('h-3.5 w-3.5', celeryRestarting && 'animate-spin')} />
                {celeryRestarting ? 'Restarting…' : 'Restart Celery'}
              </Button>
            ) : null
          }
        >
          {!isSuper ? (
            <p className="text-[12px] text-muted-foreground">Celery controls are visible to superadmin only.</p>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-2">
                {celeryStats.map((s) => (
                  <div key={s.label} className="rounded-lg border border-border bg-surface-muted/60 p-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{s.label}</span>
                      <StatusDot tone={s.tone} />
                    </div>
                    <p className="mt-0.5 text-[13px] font-semibold text-foreground">{s.value}</p>
                    <p className="text-[10px] text-muted-foreground">{s.note}</p>
                  </div>
                ))}
              </div>
              {celery?.issues?.length ? (
                <ul className="mt-2 space-y-1 rounded-lg border border-warning/30 bg-warning-soft/60 px-2 py-1.5 text-[11px] text-foreground">
                  {celery.issues.map((issue) => (
                    <li key={issue} className="flex items-start gap-1.5">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
                      {issue}
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="mt-2 flex items-center gap-1.5 rounded-lg border border-success/30 bg-success-soft/60 px-2 py-1.5 text-[11px] text-foreground">
                  <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                  Healthy — deferred WA starts and billing schedules can run.
                </div>
              )}
              {celeryMsg ? <p className="mt-2 text-[11px] text-muted-foreground">{celeryMsg}</p> : null}
              <div className="mt-2 space-y-1.5">
                {[
                  { label: 'Queue depth', value: Number(celery?.queue_depth ?? 0), max: 100 },
                  {
                    label: 'Task success (24h)',
                    value: Number(celery?.task_success_pct ?? (celery?.ok ? 99 : 0)),
                    max: 100,
                  },
                ].map((q) => (
                  <div key={q.label}>
                    <div className="flex justify-between text-[10px] text-muted-foreground">
                      <span>{q.label}</span>
                      <span className="tabular-nums">{q.value}</span>
                    </div>
                    <Progress value={(q.value / q.max) * 100} className="h-1" />
                  </div>
                ))}
              </div>
            </>
          )}
        </Panel>

        <Panel
          title="Products"
          description="WA Survey, AI Interview, campaigns and feedback — compact volume."
          icon={Activity}
          className="lg:col-span-2"
        >
          <Tabs value={productTab} onValueChange={setProductTab}>
            <TabsList className="h-8 w-full justify-start gap-1 bg-secondary p-0.5">
              {productTabs.map((p) => (
                <TabsTrigger key={p.id} value={p.id} className="h-7 gap-1.5 text-[11px]">
                  <p.icon className="h-3.5 w-3.5" />
                  {p.label}
                </TabsTrigger>
              ))}
            </TabsList>
            {productTabs.map((p, pi) => (
              <TabsContent key={p.id} value={p.id} className="mt-2.5">
                <div className="grid gap-2.5 sm:grid-cols-[auto_1fr]">
                  <button
                    type="button"
                    onClick={() => navigate(p.href)}
                    className="rounded-lg border border-border bg-surface-muted/60 p-2.5 text-left transition-colors hover:border-ring/40 sm:w-40"
                  >
                    <p className="text-2xl font-semibold leading-none tabular-nums text-foreground">
                      {p.live == null ? '—' : loading ? '…' : n(p.live)}
                    </p>
                    <p className="text-[11px] text-muted-foreground">live now</p>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      {p.total == null ? 'Open hub' : `${n(p.total)} total`}
                    </p>
                    <div className="mt-1 text-primary">
                      <Sparkline data={spark(pi + 11)} />
                    </div>
                  </button>
                  <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
                    {p.breakdown.map((b) => {
                      const numeric = typeof b.value === 'number'
                      const pct = numeric && p.total ? Math.round((b.value / Math.max(p.total, 1)) * 100) : 0
                      return (
                        <div key={b.label} className="rounded-lg border border-border bg-card p-2">
                          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{b.label}</p>
                          <p className="text-base font-semibold tabular-nums text-foreground">
                            {numeric ? (loading ? '…' : n(b.value)) : b.value}
                          </p>
                          {b.note ? <p className="text-[10px] text-muted-foreground">{b.note}</p> : null}
                          {numeric ? <Progress value={pct} className="mt-1 h-1" /> : null}
                        </div>
                      )
                    })}
                  </div>
                </div>
              </TabsContent>
            ))}
          </Tabs>

          <Separator className="my-3" />

          <div className="grid gap-2 sm:grid-cols-3">
            {[
              {
                title: 'Campaigns',
                desc: 'Broadcast templates and outbound hub.',
                cta: 'Template library',
                to: '/campaigns',
                icon: Megaphone,
              },
              {
                title: 'Customer feedback',
                desc: 'Industries, packages, locations, results.',
                cta: 'Feedback catalog',
                to: '/customer-feedback/industries',
                icon: Sparkles,
              },
              {
                title: 'Smart card QR',
                desc: 'QR profiles, scans and redirect targets.',
                cta: 'QR studio',
                to: '/operations/smart-card-insights',
                icon: QrCode,
              },
            ].map((c) => (
              <Link
                key={c.title}
                to={c.to}
                className="group rounded-lg border border-border bg-card p-2.5 transition-all hover:-translate-y-0.5 hover:border-ring/40 hover:shadow-md"
              >
                <div className="flex items-center gap-1.5 text-[12px] font-semibold text-foreground">
                  <c.icon className="h-3.5 w-3.5" /> {c.title}
                </div>
                <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{c.desc}</p>
                <span className="mt-1.5 inline-flex items-center gap-1 text-[11px] font-medium text-foreground">
                  {c.cta}
                  <ArrowUpRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                </span>
              </Link>
            ))}
          </div>
        </Panel>
      </div>

      <Panel
        title="Platform APIs"
        description="Enabled integrations only — click a card to open API settings."
        icon={Settings2}
        action={
          isSuper ? (
            <div className="flex flex-wrap items-center gap-2">
              <Input
                value={integrationQuery}
                onChange={(e) => setIntegrationQuery(e.target.value)}
                placeholder="Search integrations…"
                className="h-7 w-40 text-[11px]"
              />
              <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                <Switch
                  checked={onlineOnly}
                  onCheckedChange={setOnlineOnly}
                  className="data-[state=checked]:bg-success"
                />
                Online only
              </label>
              <Button asChild size="sm" variant="outline" className="h-7 text-[11px]">
                <Link to="/integrations/kpi">All integrations</Link>
              </Button>
            </div>
          ) : null
        }
      >
        {!isSuper ? (
          <p className="text-[12px] text-muted-foreground">Enabled API status is visible to superadmin only.</p>
        ) : integrationsLoading ? (
          <p className="text-[12px] text-muted-foreground">Loading integration status…</p>
        ) : enabledIntegrations.length === 0 ? (
          <p className="py-6 text-center text-[12px] text-muted-foreground">
            {integrationQuery
              ? `No integrations match “${integrationQuery}”.`
              : 'No enabled integrations — turn providers on in Integrations.'}
          </p>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {enabledIntegrations.map((p, idx) => {
                const status = integrationCardStatus(health[p.key])
                const detail = integrationMetaLine(p.key, health[p.key], providerBalances)
                return (
                  <button
                    key={p.key}
                    type="button"
                    onClick={() => navigate(`/integrations/${p.key}`)}
                    style={{ animationDelay: `${idx * 20}ms` }}
                    className="group animate-in fade-in-50 rounded-lg border border-border bg-card p-2.5 text-left transition-all hover:-translate-y-0.5 hover:border-ring/40 hover:shadow-md"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-[12px] font-semibold text-foreground">{p.label}</p>
                        <p className="line-clamp-2 text-[11px] leading-snug text-muted-foreground">{p.blurb}</p>
                      </div>
                      <Badge
                        variant="outline"
                        className={cn(
                          'shrink-0 gap-1 rounded-full px-1.5 text-[9px]',
                          status.connected
                            ? 'border-success/40 text-success'
                            : 'border-border text-muted-foreground',
                        )}
                      >
                        <span
                          className={cn(
                            'h-1.5 w-1.5 rounded-full',
                            status.connected ? 'bg-success' : 'bg-muted-foreground',
                          )}
                        />
                        {status.label}
                      </Badge>
                    </div>
                    <div className="mt-2 flex items-center justify-between gap-2">
                      <span className="truncate text-[10px] text-muted-foreground">{detail}</span>
                      <span className="inline-flex shrink-0 items-center gap-1 text-[10px] font-medium text-foreground opacity-70 group-hover:opacity-100">
                        Settings <ArrowUpRight className="h-3 w-3" />
                      </span>
                    </div>
                  </button>
                )
              })}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-3 rounded-lg border border-border bg-surface-muted/50 px-2.5 py-2 text-[11px]">
              <span>
                Webhooks failed: <strong className="tabular-nums">{n(failedHooks)}</strong>
              </span>
              <span className="text-muted-foreground">Latest: {fmt(webhooks.latest_received_at)}</span>
              <Button asChild size="sm" variant="outline" className="ml-auto h-7 text-[11px]">
                <Link to="/integrations/webhooks">Webhook settings</Link>
              </Button>
            </div>
          </>
        )}
      </Panel>

      <div className="grid gap-3 lg:grid-cols-3">
        {/* Three pending cards */}
        <Link
          to="/marketing/lead-sales?status=pending"
          className="group rounded-lg border border-border bg-card p-3 transition-all hover:-translate-y-0.5 hover:border-ring/40 hover:shadow-md"
        >
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 text-[12px] font-semibold text-foreground">
              <Phone className="h-3.5 w-3.5" /> Pending sales approval
            </span>
            <Badge variant="outline" className="gap-1.5 rounded-full text-[10px]">
              <StatusDot tone="warn" />
              {stats.pending_approval || 0}
            </Badge>
          </div>
          <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
            Sales tasks awaiting admin approval before dialing.
          </p>
          <span className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-foreground">
            Review queue
            <ArrowUpRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
          </span>
        </Link>

        <Link
          to="/marketing/send-offer"
          className="group rounded-lg border border-border bg-card p-3 transition-all hover:-translate-y-0.5 hover:border-ring/40 hover:shadow-md"
        >
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 text-[12px] font-semibold text-foreground">
              <Send className="h-3.5 w-3.5" /> Offers ready to send
            </span>
            <Badge variant="outline" className="gap-1.5 rounded-full text-[10px]">
              <StatusDot tone="ok" />
              {operations?.offer_queue_ready || 0}
            </Badge>
          </div>
          <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
            Post-call service offers awaiting delivery.
          </p>
          <span className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-foreground">
            Send offers
            <ArrowUpRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
          </span>
        </Link>

        <Link
          to="/marketing/ai-demos"
          className="group rounded-lg border border-border bg-card p-3 transition-all hover:-translate-y-0.5 hover:border-ring/40 hover:shadow-md"
        >
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 text-[12px] font-semibold text-foreground">
              <Bot className="h-3.5 w-3.5" /> AI demos requested
            </span>
            <Badge variant="outline" className="gap-1.5 rounded-full text-[10px]">
              <StatusDot tone={support?.demo_requests > 0 ? 'warn' : 'ok'} />
              {support?.demo_requests || 0}
            </Badge>
          </div>
          <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
            Website visitors requesting product demos.
          </p>
          <span className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-foreground">
            View demos
            <ArrowUpRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
          </span>
        </Link>
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <Panel
          title="Queues & operations"
          description="Support, compliance, and onboarding."
          icon={Inbox}
          className="lg:col-span-2"
          action={
            <Button asChild size="sm" variant="outline" className="h-7 text-[11px]">
              <Link to="/support/inbox">View inbox</Link>
            </Button>
          }
        >
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-[11px]">
              <thead className="bg-surface-muted/70 text-muted-foreground">
                <tr>
                  {['Subject', 'Category', 'Status', 'Updated'].map((h) => (
                    <th key={h} className="px-2.5 py-1.5 text-left font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tickets.length ? (
                  tickets.map((t) => (
                    <tr
                      key={t.id}
                      className="cursor-pointer border-t border-border/70 hover:bg-muted/50"
                      onClick={() => navigate(`/support/tickets/${t.id}`)}
                    >
                      <td className="px-2.5 py-1.5 font-medium text-foreground">{t.subject}</td>
                      <td className="px-2.5 py-1.5 text-muted-foreground">{t.category || '—'}</td>
                      <td className="px-2.5 py-1.5">
                        <Badge
                          variant="outline"
                          className="rounded-full border-warning/40 px-1.5 text-[9px] text-warning"
                        >
                          {t.status}
                        </Badge>
                      </td>
                      <td className="px-2.5 py-1.5 tabular-nums text-muted-foreground">
                        {fmt(t.updated_at || t.last_message_at)}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} className="px-2.5 py-6 text-center text-muted-foreground">
                      No open tickets.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            <div className="rounded-lg border border-border bg-surface-muted/50 p-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-1.5 text-[12px] font-semibold text-foreground">
                  <Database className="h-3.5 w-3.5" /> Pending account deletions
                </span>
                <span className="text-[10px] text-muted-foreground">
                  {n(accountDeletions.pending_count || accountDeletions.items.length)} awaiting
                </span>
              </div>
              {accountDeletions.items.length ? (
                <ul className="mt-1.5 space-y-1">
                  {accountDeletions.items.slice(0, 4).map((row) => (
                    <li key={row.id} className="truncate text-[11px] text-muted-foreground">
                      {row.requested_by_email || '—'} · {row.org_name || '—'}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-[11px] text-muted-foreground">No pending account deletion requests.</p>
              )}
              <Button asChild size="sm" variant="ghost" className="mt-1 h-6 px-1.5 text-[11px]">
                <Link to="/compliance/account-deletions">View queue</Link>
              </Button>
            </div>

            <div className="rounded-lg border border-border bg-surface-muted/50 p-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-1.5 text-[12px] font-semibold text-foreground">
                  <UserPlus className="h-3.5 w-3.5" /> Pending signups
                </span>
                <span className="text-[10px] text-muted-foreground">{n(pending.length)} awaiting</span>
              </div>
              {pending.length ? (
                <ul className="mt-1.5 space-y-1.5">
                  {pending.slice(0, 4).map((row) => (
                    <li key={row.id} className="flex items-center justify-between gap-2">
                      <span className="min-w-0 truncate text-[11px] text-muted-foreground">
                        {row.email || row.contact_email || '—'}
                      </span>
                      <span className="flex shrink-0 gap-1">
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="h-6 px-1.5 text-[10px]"
                          onClick={() => void decideSignup(row.id, 'approve')}
                        >
                          Approve
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          className="h-6 px-1.5 text-[10px]"
                          onClick={() => void decideSignup(row.id, 'reject')}
                        >
                          Reject
                        </Button>
                        {row.organisation_id ? (
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            className="h-6 px-1.5 text-[10px]"
                            onClick={() => openOrgUsers(row.organisation_id)}
                          >
                            Users
                          </Button>
                        ) : null}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-[11px] text-muted-foreground">No pending onboarding requests.</p>
              )}
              <Button asChild size="sm" variant="ghost" className="mt-1 h-6 px-1.5 text-[11px]">
                <Link to="/onboarding/add-customer">View queue</Link>
              </Button>
            </div>
          </div>
        </Panel>

        <Panel
          title="Needs attention"
          description="Live signals across billing, delivery and support."
          icon={AlertTriangle}
          action={
            <Badge variant="outline" className="gap-1.5 rounded-full text-[10px]">
              <StatusDot tone="ok" /> Live
            </Badge>
          }
        >
          <div className="space-y-1.5">
            {[
              {
                label: 'Failed webhooks',
                value: `${n(failedHooks)} recent`,
                tone: toneFromCount(failedHooks),
                icon: Zap,
                href: '/integrations/webhooks',
              },
              {
                label: 'Past-due subscriptions',
                value: `${n(pastDue)} subs`,
                tone: toneFromCount(pastDue),
                icon: CircleDollarSign,
                href: '/billing/subscriptions',
              },
              {
                label: 'Pending signups',
                value: `${n(pending.length)} to review`,
                tone: toneFromCount(pending.length),
                icon: UserPlus,
                href: '/onboarding/add-customer',
              },
              {
                label: 'Open tickets',
                value: `${n(openTickets)} open`,
                tone: toneFromCount(openTickets),
                icon: LifeBuoy,
                href: '/support/inbox',
              },
              {
                label: 'Telnyx credit',
                value: telnyxBalance?.ok ? money(telnyxBalance.amount, telnyxBalance.currency) : '—',
                tone: telnyxBalance?.ok && Number(telnyxBalance.amount) < 20 ? 'warn' : 'ok',
                icon: Wallet,
                href: '/integrations/telnyx',
              },
            ].map((a) => (
              <button
                key={a.label}
                type="button"
                onClick={() => navigate(a.href)}
                className="flex w-full items-center justify-between rounded-lg border border-border bg-card px-2.5 py-1.5 text-left transition-colors hover:bg-muted/40"
              >
                <span className="flex items-center gap-1.5 text-[11px] text-foreground">
                  <a.icon className="h-3.5 w-3.5 text-muted-foreground" />
                  {a.label}
                </span>
                <span
                  className={cn(
                    'flex items-center gap-1.5 text-[11px] tabular-nums',
                    a.tone === 'ok' ? 'text-muted-foreground' : 'text-warning',
                  )}
                >
                  <StatusDot tone={a.tone} />
                  {a.value}
                </span>
              </button>
            ))}
          </div>

          <Separator className="my-2.5" />

          <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold text-foreground">
            <Timer className="h-3.5 w-3.5" /> Latest activity
          </p>
          <ul className="space-y-1 text-[11px] text-muted-foreground">
            {[
              { icon: CreditCard, t: 'Latest subscription', v: fmt(billing?.latest_subscription_created_at) },
              { icon: MessageSquare, t: 'WA surveys live', v: n(surveys?.live ?? 0) },
              { icon: Bot, t: 'AI interviews live', v: n(interviews?.live ?? 0) },
              {
                icon: Sparkles,
                t: 'ElevenLabs chars',
                v: elevenBalance?.ok ? n(elevenBalance.characters_remaining) : '—',
              },
            ].map((r) => (
              <li key={r.t} className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-1.5">
                  <r.icon className="h-3 w-3" />
                  {r.t}
                </span>
                <span className="tabular-nums text-foreground">{r.v}</span>
              </li>
            ))}
          </ul>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Button asChild size="sm" variant="outline" className="h-7 text-[11px]">
              <Link to="/operations/running-surveys">WA Survey</Link>
            </Button>
            <Button asChild size="sm" variant="outline" className="h-7 text-[11px]">
              <Link to="/operations/running-interviews">AI Interview</Link>
            </Button>
            <Button asChild size="sm" variant="outline" className="h-7 text-[11px]">
              <Link to="/campaigns">Campaigns</Link>
            </Button>
          </div>
        </Panel>
      </div>

      <Sheet open={!!activeKpi} onOpenChange={(o) => !o && setActiveKpi(null)}>
        <SheetContent className="w-full sm:max-w-md">
          {activeKpi ? (
            <>
              <SheetHeader>
                <SheetTitle className="flex items-center gap-2 text-sm">
                  {activeKpi.icon ? <activeKpi.icon className="h-4 w-4" /> : null}
                  {activeKpi.label}
                </SheetTitle>
                <SheetDescription className="text-[11px]">{activeKpi.sub}</SheetDescription>
              </SheetHeader>
              <div className="space-y-3 px-0 pb-4 pt-2">
                <div className="rounded-lg border border-border bg-surface-muted/60 p-3">
                  <p className="text-3xl font-semibold tabular-nums text-foreground">{activeKpi.value}</p>
                  <div className="mt-2 text-primary">
                    <Sparkline data={activeKpi.spark || spark(7)} className="h-14" />
                  </div>
                </div>
                <ul className="space-y-1.5">
                  {(activeKpi.detail || []).map((d) => (
                    <li
                      key={d}
                      className="rounded-md border border-border bg-card px-2.5 py-1.5 text-[11px] text-muted-foreground"
                    >
                      {d}
                    </li>
                  ))}
                </ul>
                <Button
                  size="sm"
                  className="w-full text-[11px]"
                  onClick={() => {
                    const href = activeKpi.href
                    setActiveKpi(null)
                    if (href) navigate(href)
                  }}
                >
                  Open full report
                </Button>
              </div>
            </>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  )
}
