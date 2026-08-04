import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from 'recharts'
import { Activity, CreditCard, Phone, RefreshCw, Sparkles, Wallet } from 'lucide-react'
import { apiFetch } from '../../lib/api'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { KpiCard } from '@/components/ui/KpiCard'

const money = (amount, currency = 'USD') => {
  const value = Number(amount || 0)
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: currency || 'USD' }).format(value)
  } catch {
    return `$${value.toFixed(2)}`
  }
}

const FILL_COST = 'oklch(0.62 0.13 65)'
const FILL_REV = 'oklch(0.55 0.14 150)'

export default function CostRevenue() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [billing, setBilling] = useState(null)
  const [callCosts, setCallCosts] = useState(null)
  const [balances, setBalances] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [billingRes, costsRes, balancesRes] = await Promise.all([
        apiFetch('/admin/billing/overview').catch(() => null),
        apiFetch('/admin/billing/calls-cost?date_range=last_30_days&page_size=1').catch(() => null),
        apiFetch('/admin/dashboard/provider-balances').catch(() => null),
      ])
      setBilling(billingRes)
      setCallCosts(costsRes)
      setBalances(balancesRes)
    } catch (e) {
      setError(e?.message || 'Could not load cost vs revenue')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const summary = callCosts?.summary || {}
  const currency = summary.currency || 'USD'
  const telnyxSpend = Number(summary.total_cost || 0)
  const activeSubs = Number(billing?.subscriptions_active || 0)

  const chartRows = useMemo(
    () => [
      { name: 'Voice/AI cost (30d)', cost: telnyxSpend, revenue: 0 },
      { name: 'Active subs (proxy)', cost: 0, revenue: activeSubs },
    ],
    [telnyxSpend, activeSubs],
  )

  const kpis = [
    {
      label: 'Telnyx spend (30d)',
      value: loading ? '…' : money(telnyxSpend, currency),
      hint: `${summary.total_calls ?? 0} calls`,
      icon: Phone,
      tone: 'warning',
      href: '/billing/calls-cost',
    },
    {
      label: 'Avg cost / call',
      value: loading ? '…' : money(summary.avg_cost, currency),
      hint: 'AI voice assistant',
      icon: Activity,
      href: '/billing/calls-cost',
    },
    {
      label: 'Active subscriptions',
      value: loading ? '…' : String(activeSubs),
      hint: `${billing?.subscriptions_trial ?? 0} trial`,
      icon: CreditCard,
      tone: 'success',
      href: '/billing/subscriptions',
    },
    {
      label: 'Past due',
      value: loading ? '…' : String(billing?.subscriptions_past_due ?? 0),
      hint: 'needs billing action',
      icon: Activity,
      tone: 'warning',
      href: '/billing/subscriptions',
    },
    {
      label: 'Telnyx balance',
      value: loading
        ? '…'
        : balances?.telnyx?.ok
          ? money(balances.telnyx.amount, balances.telnyx.currency)
          : 'Not configured',
      hint: 'prepaid credit',
      icon: Wallet,
      href: '/integrations/telnyx',
    },
    {
      label: 'ElevenLabs quota',
      value: loading
        ? '…'
        : balances?.elevenlabs?.ok
          ? `${balances.elevenlabs.characters_remaining?.toLocaleString()} chars`
          : 'Not configured',
      hint: balances?.elevenlabs?.tier || 'TTS',
      icon: Sparkles,
      tone: 'info',
      href: '/integrations/elevenlabs',
    },
  ]

  return (
    <div className="ds-scope space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0">
          <h1 className="text-[15px] font-semibold leading-tight text-foreground">Cost vs revenue</h1>
          <p className="text-[11px] leading-tight text-muted-foreground">
            Telnyx call spend (last 30 days) compared with subscription volume. Full revenue lives in Billing → Reports.
          </p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" className="h-7 gap-1.5 text-[11px]" onClick={load} disabled={loading}>
            <RefreshCw className={loading ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} />
            {loading ? 'Refreshing…' : 'Refresh'}
          </Button>
          <Button asChild size="sm" variant="outline" className="h-7 text-[11px]">
            <Link to="/billing/calls-cost">Call cost detail</Link>
          </Button>
          <Button asChild size="sm" className="h-7 text-[11px]">
            <Link to="/analytics/kpis">Platform KPIs</Link>
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-[12px] text-destructive">
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
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

      <Panel
        title="Cost vs subscription volume"
        description="Revenue proxy = active paid subscriptions count (see Billing → Revenue reports for GBP totals)."
      >
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartRows}>
              <CartesianGrid stroke="oklch(0.9 0.012 85)" strokeDasharray="3 3" />
              <XAxis dataKey="name" tick={{ fill: 'oklch(0.5 0.02 260)', fontSize: 11 }} />
              <YAxis tick={{ fill: 'oklch(0.5 0.02 260)', fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Bar dataKey="cost" name="Cost (USD)" fill={FILL_COST} radius={[8, 8, 0, 0]} />
              <Bar dataKey="revenue" name="Active subs" fill={FILL_REV} radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Panel>
    </div>
  )
}
