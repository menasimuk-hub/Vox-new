import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ResponsiveContainer, BarChart, Bar, XAxis, Tooltip, Cell } from 'recharts'
import {
  Activity,
  Bot,
  Building2,
  CreditCard,
  LifeBuoy,
  MessageSquare,
  RefreshCw,
  Settings2,
  Wallet,
} from 'lucide-react'
import { apiFetch } from '../../lib/api'
import { INTEGRATION_PROVIDERS, isIntegrationConnected } from '../../lib/integrationsCatalog'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { KpiCard } from '@/components/ui/KpiCard'

const n = (v) => Number(v || 0).toLocaleString()
const fmt = (v) => {
  if (!v) return '—'
  try {
    return new Date(v).toLocaleString()
  } catch {
    return String(v)
  }
}

/** Chart fills from DESIGN_SYSTEM tokens only (info / primary). */
const CHART_FILLS = [
  'oklch(0.52 0.1 250)',
  'oklch(0.45 0.1 250)',
  'oklch(0.27 0.04 265)',
  'oklch(0.4 0.06 265)',
]

export default function PlatformKpis() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [billing, setBilling] = useState(null)
  const [support, setSupport] = useState(null)
  const [surveys, setSurveys] = useState(null)
  const [interviews, setInterviews] = useState(null)
  const [orgs, setOrgs] = useState([])
  const [integrations, setIntegrations] = useState({})
  const [balances, setBalances] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [billingRes, supportRes, surveysRes, interviewsRes, orgsRes, balancesRes] = await Promise.all([
        apiFetch('/admin/billing/overview').catch(() => null),
        apiFetch('/admin/support/kpis').catch(() => null),
        apiFetch('/admin/platform-services/surveys/overview').catch(() => null),
        apiFetch('/admin/platform-services/interviews/overview').catch(() => null),
        apiFetch('/admin/organisations?limit=500').catch(() => []),
        apiFetch('/admin/dashboard/provider-balances').catch(() => null),
      ])
      setBilling(billingRes)
      setSupport(supportRes)
      setSurveys(surveysRes)
      setInterviews(interviewsRes)
      setOrgs(Array.isArray(orgsRes) ? orgsRes : [])
      setBalances(balancesRes)

      const integ = {}
      await Promise.all(
        INTEGRATION_PROVIDERS.map(async (p) => {
          try {
            integ[p.key] = await apiFetch(`/admin/integrations/${p.key}`)
          } catch {
            integ[p.key] = { error: true }
          }
        }),
      )
      setIntegrations(integ)
    } catch (e) {
      setError(e?.message || 'Could not load platform KPIs')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const connectedIntegrations = INTEGRATION_PROVIDERS.filter((p) => isIntegrationConnected(integrations[p.key])).length
  const activeOrgs = orgs.filter((o) => !o.is_suspended).length

  const serviceChart = [
    { name: 'WA live', v: surveys?.live ?? 0 },
    { name: 'WA running', v: surveys?.running ?? 0 },
    { name: 'Interview live', v: interviews?.live ?? 0 },
    { name: 'Interview running', v: interviews?.running ?? 0 },
  ]

  const kpis = [
    {
      label: 'Organisations',
      value: loading ? '…' : n(orgs.length),
      hint: `${n(activeOrgs)} active`,
      icon: Building2,
      href: '/organisations',
    },
    {
      label: 'Active subscriptions',
      value: loading ? '…' : n(billing?.subscriptions_active),
      hint: `${n(billing?.subscriptions_trial)} trial`,
      icon: CreditCard,
      tone: 'success',
      href: '/billing/subscriptions',
    },
    {
      label: 'Past due',
      value: loading ? '…' : n(billing?.subscriptions_past_due),
      hint: `${n(billing?.subscriptions_pending_payment)} pending payment`,
      icon: Activity,
      tone: 'warning',
      href: '/billing/subscriptions',
    },
    {
      label: 'Open tickets',
      value: loading ? '…' : n(support?.total_open ?? support?.open ?? 0),
      hint: `${n(support?.unassigned ?? 0)} unassigned`,
      icon: LifeBuoy,
      tone: 'info',
      href: '/support/inbox',
    },
    {
      label: 'WA surveys live',
      value: loading ? '…' : n(surveys?.live ?? 0),
      hint: `${n(surveys?.total ?? 0)} total campaigns`,
      icon: MessageSquare,
      href: '/operations/running-surveys',
    },
    {
      label: 'AI interviews live',
      value: loading ? '…' : n(interviews?.live ?? 0),
      hint: `${n(interviews?.total ?? 0)} total campaigns`,
      icon: Bot,
      href: '/operations/running-interviews',
    },
    {
      label: 'Integrations OK',
      value: loading ? '…' : n(connectedIntegrations),
      hint: `of ${INTEGRATION_PROVIDERS.length} providers`,
      icon: Settings2,
      tone: 'success',
      href: '/integrations/kpi',
    },
    {
      label: 'Telnyx credit',
      value: loading
        ? '…'
        : balances?.telnyx?.ok
          ? `$${Number(balances.telnyx.amount || 0).toFixed(2)}`
          : '—',
      hint: balances?.telnyx?.currency || 'USD',
      icon: Wallet,
      tone: 'warning',
      href: '/integrations/telnyx',
    },
  ]

  return (
    <div className="ds-scope space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0">
          <h1 className="text-[15px] font-semibold leading-tight text-foreground">Platform KPIs</h1>
          <p className="text-[11px] leading-tight text-muted-foreground">
            Live counts from billing, organisations, campaigns, support, and integrations.
          </p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" className="h-7 gap-1.5 text-[11px]" onClick={load} disabled={loading}>
            <RefreshCw className={loading ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} />
            {loading ? 'Refreshing…' : 'Refresh'}
          </Button>
          <Button asChild size="sm" className="h-7 text-[11px]">
            <Link to="/analytics/cost-revenue">Cost vs revenue</Link>
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-[12px] text-destructive">
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-8">
        {kpis.map((k, i) => (
          <Link key={k.label} to={k.href} className="block no-underline">
            <KpiCard
              index={i}
              icon={k.icon}
              label={k.label}
              value={k.value}
              hint={k.hint}
              tone={k.tone || 'primary'}
              className="h-full"
            />
          </Link>
        ))}
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <Panel title="Active campaigns" description="WA Survey and AI Interview live volume." className="lg:col-span-2">
          <div className="h-56 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={serviceChart}>
                <XAxis dataKey="name" tick={{ fill: 'oklch(0.5 0.02 260)', fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="v" radius={[8, 8, 0, 0]}>
                  {serviceChart.map((_, i) => (
                    <Cell key={serviceChart[i].name} fill={CHART_FILLS[i % CHART_FILLS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title="Latest activity" description="Recent platform signals.">
          <ul className="space-y-2 text-[12px] text-muted-foreground">
            {[
              ['Latest subscription', fmt(billing?.latest_subscription_created_at)],
              ['WA completed', n(surveys?.completed ?? 0)],
              ['Interviews completed', n(interviews?.completed ?? 0)],
              [
                'ElevenLabs chars left',
                balances?.elevenlabs?.ok ? n(balances.elevenlabs.characters_remaining) : '—',
              ],
            ].map(([label, value]) => (
              <li key={label} className="flex items-center justify-between gap-2 border-b border-border/60 py-1.5 last:border-0">
                <span>{label}</span>
                <strong className="tabular-nums text-foreground">{value}</strong>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  )
}
