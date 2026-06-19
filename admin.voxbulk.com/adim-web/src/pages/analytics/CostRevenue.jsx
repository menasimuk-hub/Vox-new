import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from 'recharts'
import { RefreshCw } from 'lucide-react'
import { apiFetch } from '../../lib/api'

const money = (amount, currency = 'USD') => {
  const value = Number(amount || 0)
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: currency || 'USD' }).format(value)
  } catch {
    return `$${value.toFixed(2)}`
  }
}

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

  return (
    <div className='pageShell dashboardPage'>
      <div className='pageTop'>
        <div>
          <h1>Cost vs revenue</h1>
          <p>Telnyx call spend (last 30 days) compared with subscription volume. Full revenue lives in Billing → Reports.</p>
        </div>
        <div className='actions'>
          <button type='button' className='btn soft' onClick={load} disabled={loading}>
            <RefreshCw size={16} className='btnIconLeading' />
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
          <Link to='/billing/calls-cost' className='btn soft'>
            Call cost detail
          </Link>
          <Link to='/analytics/kpis' className='btn primary'>
            Platform KPIs
          </Link>
        </div>
      </div>

      {error ? <div className='note dashboardErrorNote'>{error}</div> : null}

      <div className='dashKpiGrid'>
        {[
          ['Telnyx spend (30d)', money(telnyxSpend, currency), `${summary.total_calls ?? 0} calls`, '/billing/calls-cost'],
          ['Avg cost / call', money(summary.avg_cost, currency), 'AI voice assistant', '/billing/calls-cost'],
          ['Active subscriptions', String(activeSubs), `${billing?.subscriptions_trial ?? 0} trial`, '/billing/subscriptions'],
          ['Past due', String(billing?.subscriptions_past_due ?? 0), 'needs billing action', '/billing/subscriptions'],
          ['Telnyx balance', balances?.telnyx?.ok ? money(balances.telnyx.amount, balances.telnyx.currency) : 'Not configured', 'prepaid credit', '/integrations/telnyx'],
          ['ElevenLabs quota', balances?.elevenlabs?.ok ? `${balances.elevenlabs.characters_remaining?.toLocaleString()} chars` : 'Not configured', balances?.elevenlabs?.tier || 'TTS', '/integrations/elevenlabs'],
        ].map(([label, value, sub, href]) => (
          <Link key={label} to={href} className='dashKpiCard dashKpiCardLink'>
            <span className='dashKpiLabel'>{label}</span>
            <strong className='dashKpiValue'>{loading ? '…' : value}</strong>
            <span className='dashKpiSub'>{sub}</span>
          </Link>
        ))}
      </div>

      <div className='card dashChartCard'>
        <div className='cardHead'>
          <h3>Cost vs subscription volume</h3>
          <span className='muted' style={{ fontSize: 12 }}>
            Revenue proxy = active paid subscriptions count (see Billing → Revenue reports for GBP totals).
          </span>
        </div>
        <div className='cardBody dashboardChartBody dashboardChartBodyLg'>
          <ResponsiveContainer width='100%' height='100%'>
            <BarChart data={chartRows}>
              <CartesianGrid stroke='var(--line)' strokeDasharray='3 3' />
              <XAxis dataKey='name' tick={{ fill: 'var(--muted)', fontSize: 11 }} />
              <YAxis tick={{ fill: 'var(--muted)', fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Bar dataKey='cost' name='Cost (USD)' fill='#f97316' radius={[8, 8, 0, 0]} />
              <Bar dataKey='revenue' name='Active subs' fill='#0f766e' radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}
