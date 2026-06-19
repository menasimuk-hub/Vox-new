import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ResponsiveContainer, BarChart, Bar, XAxis, Tooltip } from 'recharts'
import { RefreshCw } from 'lucide-react'
import { apiFetch } from '../../lib/api'
import { INTEGRATION_PROVIDERS, isIntegrationConnected } from '../../lib/integrationsCatalog'

const n = (v) => Number(v || 0).toLocaleString()
const fmt = (v) => {
  if (!v) return '—'
  try {
    return new Date(v).toLocaleString()
  } catch {
    return String(v)
  }
}

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
    { name: 'WA live', v: surveys?.live ?? 0, fill: '#0891b2' },
    { name: 'WA running', v: surveys?.running ?? 0, fill: '#06b6d4' },
    { name: 'Interview live', v: interviews?.live ?? 0, fill: '#7c3aed' },
    { name: 'Interview running', v: interviews?.running ?? 0, fill: '#a855f7' },
  ]

  return (
    <div className='pageShell dashboardPage'>
      <div className='pageTop'>
        <div>
          <h1>Platform KPIs</h1>
          <p>Live counts from billing, organisations, campaigns, support, and integrations.</p>
        </div>
        <div className='actions'>
          <button type='button' className='btn soft' onClick={load} disabled={loading}>
            <RefreshCw size={16} className='btnIconLeading' />
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
          <Link to='/analytics/cost-revenue' className='btn primary'>
            Cost vs revenue
          </Link>
        </div>
      </div>

      {error ? <div className='note dashboardErrorNote'>{error}</div> : null}

      <div className='dashKpiGrid'>
        {[
          ['Organisations', n(orgs.length), `${n(activeOrgs)} active`, '/organisations'],
          ['Active subscriptions', n(billing?.subscriptions_active), `${n(billing?.subscriptions_trial)} trial`, '/billing/subscriptions'],
          ['Past due', n(billing?.subscriptions_past_due), `${n(billing?.subscriptions_pending_payment)} pending payment`, '/billing/subscriptions'],
          ['Open tickets', n(support?.total_open ?? support?.open ?? 0), `${n(support?.unassigned ?? 0)} unassigned`, '/support/inbox'],
          ['WA surveys live', n(surveys?.live ?? 0), `${n(surveys?.total ?? 0)} total campaigns`, '/operations/running-surveys'],
          ['AI interviews live', n(interviews?.live ?? 0), `${n(interviews?.total ?? 0)} total campaigns`, '/operations/running-interviews'],
          ['Integrations OK', n(connectedIntegrations), `of ${INTEGRATION_PROVIDERS.length} providers`, '/integrations/kpi'],
          ['Telnyx credit', balances?.telnyx?.ok ? `$${Number(balances.telnyx.amount || 0).toFixed(2)}` : '—', balances?.telnyx?.currency || 'USD', '/integrations/telnyx'],
        ].map(([label, value, sub, href]) => (
          <Link key={label} to={href} className='dashKpiCard dashKpiCardLink'>
            <span className='dashKpiLabel'>{label}</span>
            <strong className='dashKpiValue'>{loading ? '…' : value}</strong>
            <span className='dashKpiSub'>{sub}</span>
          </Link>
        ))}
      </div>

      <div className='grid-12'>
        <div className='span-8 card dashChartCard'>
          <div className='cardHead'>
            <h3>Active campaigns</h3>
          </div>
          <div className='cardBody dashboardChartBody'>
            <ResponsiveContainer width='100%' height='100%'>
              <BarChart data={serviceChart}>
                <XAxis dataKey='name' tick={{ fill: 'var(--muted)', fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey='v' radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className='span-4 card'>
          <div className='cardHead'>
            <h3>Latest activity</h3>
          </div>
          <div className='cardBody'>
            <div className='list'>
              <div className='listRow'>
                <span>Latest subscription</span>
                <strong className='dashboardMetaStrong'>{fmt(billing?.latest_subscription_created_at)}</strong>
              </div>
              <div className='listRow'>
                <span>WA completed</span>
                <strong>{n(surveys?.completed ?? 0)}</strong>
              </div>
              <div className='listRow'>
                <span>Interviews completed</span>
                <strong>{n(interviews?.completed ?? 0)}</strong>
              </div>
              <div className='listRow'>
                <span>ElevenLabs chars left</span>
                <strong>{balances?.elevenlabs?.ok ? n(balances.elevenlabs.characters_remaining) : '—'}</strong>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
