import React, { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  BadgeCheck,
  AlertTriangle,
  Activity,
  RefreshCw,
  MessageSquare,
} from 'lucide-react'
import { apiFetch } from '../lib/api'
import { normalizeAdminRole } from '../lib/adminPaths'
import { useAdminProfile } from '../context/AdminProfileContext'
import {
  INTEGRATION_PROVIDERS,
  integrationCardStatus,
} from '../lib/integrationsCatalog'

const DashboardProductChart = lazy(() => import('../components/DashboardProductChart'))
const DashboardKpiSpark = lazy(() => import('../components/DashboardKpiSpark'))

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

function DashboardSection({ title, description, action, children }) {
  return (
    <section className='dashboardSection'>
      <div className='dashboardSectionHead'>
        <div>
          <h2>{title}</h2>
          {description ? <p>{description}</p> : null}
        </div>
        {action || null}
      </div>
      {children}
    </section>
  )
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

function DashboardApiCard({ provider, summary, balances, onOpen }) {
  const status = integrationCardStatus(summary)
  const detail = integrationMetaLine(provider.key, summary, balances)
  return (
    <button
      type='button'
      className={`dashApiCard integrationKpiCard ${status.cardClass}`}
      onClick={onOpen}
      title={`Open ${provider.label} settings`}
    >
      <div className='integrationKpiCardTop'>
        <span className='integrationKpiIcon'>
          <i className={`ti ${provider.icon}`} />
        </span>
        <span className={`integrationKpiDot ${status.connected ? 'isOn' : 'isOff'}`} title={status.label} />
      </div>
      <strong className='integrationKpiTitle'>{provider.label}</strong>
      <p className='integrationKpiBlurb'>{provider.blurb}</p>
      <p className='dashApiCardDetail'>{detail}</p>
      <div className='integrationKpiFoot'>
        <span className={`pill ${status.pillClass}`}>{status.label}</span>
        <span className='integrationKpiOpen'>
          Settings <i className='ti ti-chevron-right' />
        </span>
      </div>
    </button>
  )
}

function ProductMiniChart(props) {
  return (
    <Suspense
      fallback={
        <div className="dashProductCard">
          <div className="dashProductCardHead">
            <strong>{props.title}</strong>
          </div>
          <span className="dashProductCardSub muted">Loading chart…</span>
        </div>
      }
    >
      <DashboardProductChart {...props} />
    </Suspense>
  )
}

function KpiSpark({ rows }) {
  if (!rows?.length) return null
  return (
    <Suspense fallback={<div className="dashKpiSpark muted" style={{ fontSize: 11 }}>…</div>}>
      <DashboardKpiSpark rows={rows} />
    </Suspense>
  )
}

function ProductHubCard({ title, description, href, icon, stat }) {
  return (
    <Link to={href} className='dashProductCard dashProductCardLink dashProductHubCard'>
      <div className='dashProductHubIcon'>
        <i className={`ti ${icon}`} />
      </div>
      <strong>{title}</strong>
      <p className='dashProductCardSub'>{description}</p>
      {stat ? <span className='dashProductHubStat'>{stat}</span> : null}
      <span className='dashProductHubOpen'>
        Open <i className='ti ti-chevron-right' />
      </span>
    </Link>
  )
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
  const [error, setError] = useState('')

  const loadIntegrations = useCallback(async () => {
    if (!isSuper) {
      setHealth({})
      return
    }
    setIntegrationsLoading(true)
    try {
      const next = {}
      await Promise.all(
        INTEGRATION_PROVIDERS.map(async (p) => {
          try {
            next[p.key] = await apiFetch(`/admin/integrations/${p.key}`)
          } catch {
            next[p.key] = { error: true }
          }
        }),
      )
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
      ])

      setBilling(billingRes)
      setOperations(operationsRes)
      setSupport(supportRes)
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
    } catch (e) {
      setError(e?.message || 'Could not load dashboard')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadAll()
  }, [loadAll, refreshKey])

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

  const enabledIntegrations = useMemo(
    () =>
      INTEGRATION_PROVIDERS.filter((p) => {
        const s = health[p.key]
        return s && s.is_enabled && s.configured && !s.error
      }),
    [health],
  )

  const surveyChartRows = useMemo(
    () => [
      { n: 'Live', v: surveys?.live ?? 0, fill: '#0891b2' },
      { n: 'Running', v: surveys?.running ?? 0, fill: '#06b6d4' },
      { n: 'Scheduled', v: surveys?.scheduled ?? 0, fill: '#22d3ee' },
      { n: 'Completed', v: surveys?.completed ?? 0, fill: '#0e7490' },
      { n: 'Paused', v: surveys?.paused ?? 0, fill: '#94a3b8' },
    ],
    [surveys],
  )

  const interviewChartRows = useMemo(
    () => [
      { n: 'Live', v: interviews?.live ?? 0, fill: '#7c3aed' },
      { n: 'Running', v: interviews?.running ?? 0, fill: '#a855f7' },
      { n: 'Scheduled', v: interviews?.scheduled ?? 0, fill: '#c084fc' },
      { n: 'Completed', v: interviews?.completed ?? 0, fill: '#6d28d9' },
      { n: 'Drafts', v: interviews?.drafts ?? 0, fill: '#a78bfa' },
    ],
    [interviews],
  )

  const overviewKpis = [
    { label: 'Organisations', value: n(orgTotal), sub: `${n(activeOrgs)} active`, href: '/organisations', spark: [{ v: orgTotal }] },
    { label: 'Active subscriptions', value: n(billing?.subscriptions_active), sub: `${n(billing?.subscriptions_trial)} trial`, href: '/billing/subscriptions' },
    { label: 'Past due', value: n(billing?.subscriptions_past_due), sub: `${n(billing?.subscriptions_pending_payment)} pending pay`, href: '/billing/subscriptions' },
    { label: 'Open tickets', value: n(support?.total_open ?? support?.open ?? 0), sub: `${n(support?.unassigned ?? 0)} unassigned`, href: '/support/inbox' },
    { label: 'WA surveys live', value: n(surveys?.live ?? 0), sub: `${n(surveys?.total ?? 0)} total`, href: '/operations/running-surveys', spark: surveyChartRows.slice(0, 3) },
    { label: 'AI interviews live', value: n(interviews?.live ?? 0), sub: `${n(interviews?.total ?? 0)} total`, href: '/operations/running-interviews', spark: interviewChartRows.slice(0, 3) },
    { label: 'Failed webhooks', value: n(webhooks.failed || 0), sub: 'recent delivery errors', href: '/integrations/webhooks' },
    { label: 'Telnyx credit', value: telnyxBalance?.ok ? money(telnyxBalance.amount, telnyxBalance.currency) : '—', sub: 'voice / SMS balance', href: '/integrations/telnyx' },
  ]

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
    <div className='pageShell dashboardPage'>
      <div className='pageTop'>
        <div>
          <h1>Dashboard</h1>
          <p>Live platform overview — products, enabled APIs, billing, and operations queues.</p>
        </div>
        <div className='actions'>
          <button type='button' className='btn soft' onClick={() => setRefreshKey((k) => k + 1)} disabled={loading}>
            <RefreshCw size={16} className='btnIconLeading' />
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
          <Link to='/analytics/kpis' className='btn soft'>
            Analytics
          </Link>
          <Link to='/onboarding/add-customer' className='btn primary'>
            Add customer
          </Link>
        </div>
      </div>

      {error ? <div className='note dashboardErrorNote'>{error}</div> : null}

      <DashboardSection title='Platform overview' description='Compact KPIs with mini charts — click a card for detail.'>
        <div className='dashKpiGrid'>
          {overviewKpis.map((kpi) => (
            <Link key={kpi.label} to={kpi.href} className='dashKpiCard dashKpiCardLink'>
              <span className='dashKpiLabel'>{kpi.label}</span>
              <strong className='dashKpiValue'>{loading ? '…' : kpi.value}</strong>
              <span className='dashKpiSub'>{kpi.sub}</span>
              {kpi.spark?.length ? (
                <KpiSpark rows={kpi.spark} />
              ) : null}
            </Link>
          ))}
        </div>
      </DashboardSection>

      <DashboardSection title='Products' description='WA Survey, AI Interview, campaigns, and customer feedback — compact volume charts.'>
        <div className='dashProductGrid'>
          <ProductMiniChart
            title='WA Survey'
            href='/operations/running-surveys'
            total={surveys?.total ?? 0}
            live={surveys?.live ?? 0}
            rows={surveyChartRows}
            accent='#0891b2'
          />
          <ProductMiniChart
            title='AI Interview'
            href='/operations/running-interviews'
            total={interviews?.total ?? 0}
            live={interviews?.live ?? 0}
            rows={interviewChartRows}
            accent='#7c3aed'
          />
          <ProductHubCard
            title='Campaigns'
            description='Broadcast templates and outbound campaign hub.'
            href='/campaigns'
            icon='ti-ad-2'
            stat='Template library'
          />
          <ProductHubCard
            title='Customer feedback'
            description='Industries, packages, locations, and WhatsApp survey results.'
            href='/customer-feedback/industries'
            icon='ti-message-circle'
            stat='Feedback catalog'
          />
        </div>
      </DashboardSection>

      <DashboardSection
        title='Platform APIs'
        description='Enabled integrations only — click a card to open API settings.'
        action={
          isSuper ? (
            <Link to='/integrations/kpi' className='btn soft'>
              All integrations
            </Link>
          ) : null
        }
      >
        {!isSuper ? (
          <p className='muted dashboardHint'>Enabled API status is visible to superadmin only.</p>
        ) : integrationsLoading ? (
          <p className='muted dashboardHint'>Loading integration status…</p>
        ) : enabledIntegrations.length === 0 ? (
          <p className='muted dashboardHint'>No enabled integrations — turn providers on in Integrations.</p>
        ) : (
          <>
            <div className='dashApiGrid'>
              {enabledIntegrations.map((p) => (
                <DashboardApiCard
                  key={p.key}
                  provider={p}
                  summary={health[p.key]}
                  balances={providerBalances}
                  onOpen={() => navigate(`/integrations/${p.key}`)}
                />
              ))}
            </div>
            <div className='dashApiWebhookRow'>
              <span>
                Webhooks failed: <strong>{n(webhooks.failed || 0)}</strong>
              </span>
              <span className='muted'>Latest: {fmt(webhooks.latest_received_at)}</span>
              <Link to='/integrations/webhooks' className='btn soft sm'>
                Webhook settings
              </Link>
            </div>
          </>
        )}
      </DashboardSection>

      <DashboardSection title='Queues & operations' description='Support, compliance, and onboarding.'>
      <div className='grid-12'>
        <div className='span-8 stack'>
          <div className='card'>
            <div className='cardHead'>
              <h3>Open support tickets</h3>
              <Link to='/support/inbox' className='btn soft'>
                View inbox
              </Link>
            </div>
            <div className='cardBody'>
              {tickets.length ? (
                <div className='tableWrap'>
                  <table className='table'>
                    <thead>
                      <tr>
                        <th>Subject</th>
                        <th>Category</th>
                        <th>Status</th>
                        <th>Updated</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tickets.map((t) => (
                        <tr
                          key={t.id}
                          className='tableRowClickable'
                          onClick={() => navigate(`/support/tickets/${t.id}`)}
                        >
                          <td>{t.subject}</td>
                          <td>{t.category || '—'}</td>
                          <td>
                            <span className='pill p-cyan'>{t.status}</span>
                          </td>
                          <td className='muted'>{fmt(t.updated_at || t.last_message_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className='muted'>No open tickets.</p>
              )}
            </div>
          </div>

          <div className='card'>
            <div className='cardHead'>
              <h3>Pending account deletions</h3>
              <Link to='/compliance/account-deletions' className='btn soft'>
                View queue
              </Link>
            </div>
            <div className='cardBody'>
              <div className='dashboardInlineBadge'>
                <span className='pill p-amber'>{n(accountDeletions.pending_count || accountDeletions.items.length)} awaiting</span>
              </div>
              {accountDeletions.items.length ? (
                <div className='tableWrap'>
                  <table className='table'>
                    <thead>
                      <tr>
                        <th>User</th>
                        <th>Organisation</th>
                        <th>Requested</th>
                      </tr>
                    </thead>
                    <tbody>
                      {accountDeletions.items.slice(0, 8).map((row) => (
                        <tr
                          key={row.id}
                          className='tableRowClickable'
                          onClick={() => navigate('/compliance/account-deletions')}
                        >
                          <td>{row.requested_by_email || '—'}</td>
                          <td>{row.org_name || '—'}</td>
                          <td className='muted'>{fmt(row.requested_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className='muted'>No pending account deletion requests.</p>
              )}
            </div>
          </div>

          <div className='card'>
            <div className='cardHead'>
              <h3>Pending signups</h3>
              <span className='pill p-amber'>{n(pending.length)} awaiting</span>
            </div>
            <div className='cardBody'>
              {pending.length ? (
                <div className='tableWrap'>
                  <table className='table'>
                    <thead>
                      <tr>
                        <th>Email</th>
                        <th>Organisation</th>
                        <th>Requested</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {pending.slice(0, 10).map((row) => (
                        <tr key={row.id}>
                          <td>{row.email || row.contact_email || '—'}</td>
                          <td>{row.organisation_name || row.org_name || '—'}</td>
                          <td className='muted'>{fmt(row.created_at)}</td>
                          <td>
                            <div className='rowActionsCompact'>
                              <button type='button' className='btn soft sm' onClick={() => decideSignup(row.id, 'approve')}>
                                Approve
                              </button>
                              <button type='button' className='btn soft sm' onClick={() => decideSignup(row.id, 'reject')}>
                                Reject
                              </button>
                              {row.organisation_id ? (
                                <button type='button' className='btn soft sm' onClick={() => openOrgUsers(row.organisation_id)}>
                                  Users
                                </button>
                              ) : null}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className='muted'>No pending onboarding requests.</p>
              )}
            </div>
          </div>
        </div>

        <div className='span-4'>
          <div className='stack'>
            <div className='card'>
              <div className='cardHead'>
                <h3>Needs attention</h3>
                <span className='pill p-red'>Live</span>
              </div>
              <div className='cardBody'>
                <div className='timeline'>
                  {[
                    ['Failed webhooks', `${n(webhooks.failed)} recent`, '/integrations/webhooks', AlertTriangle],
                    ['Past-due subscriptions', `${n(billing?.subscriptions_past_due)} subs`, '/billing/subscriptions', Activity],
                    ['Pending signups', `${n(pending.length)} to review`, '/onboarding/add-customer', MessageSquare],
                    ['Open tickets', `${n(support?.total_open ?? 0)} open`, '/support/inbox', BadgeCheck],
                  ].map(([title, detail, href, Icon]) => (
                    <div
                      className='timelineItem'
                      key={title}
                      onClick={() => navigate(href)}
                      role='button'
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') navigate(href)
                      }}
                    >
                      <div className='timelineIcon'>
                        <Icon size={16} />
                      </div>
                      <div>
                        <div className='timelineTitle'>{title}</div>
                        <div className='muted'>{detail}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className='card'>
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
                    <span>WA surveys live</span>
                    <strong>{n(surveys?.live ?? 0)}</strong>
                  </div>
                  <div className='listRow'>
                    <span>AI interviews live</span>
                    <strong>{n(interviews?.live ?? 0)}</strong>
                  </div>
                  <div className='listRow'>
                    <span>ElevenLabs chars</span>
                    <strong>{elevenBalance?.ok ? n(elevenBalance.characters_remaining) : '—'}</strong>
                  </div>
                </div>
                <div className='actions dashboardCardActions'>
                  <Link to='/operations/running-surveys' className='btn soft'>WA Survey</Link>
                  <Link to='/operations/running-interviews' className='btn soft'>AI Interview</Link>
                  <Link to='/campaigns' className='btn soft'>Campaigns</Link>
                  <Link to='/customer-feedback/industries' className='btn soft'>Feedback</Link>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      </DashboardSection>
    </div>
  )
}
