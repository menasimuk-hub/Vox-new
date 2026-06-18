import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts'
import {
  Building2,
  DollarSign,
  BadgeCheck,
  BrainCircuit,
  PhoneCall,
  AlertTriangle,
  Activity,
  Wallet,
  Mic2,
  RefreshCw,
  MessageSquare,
  Users,
  PlayCircle,
} from 'lucide-react'
import { apiFetch } from '../lib/api'
import { normalizeAdminRole } from '../lib/adminPaths'
import { useAdminProfile } from '../context/AdminProfileContext'

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

const HEALTH_PROVIDERS = [
  ['Dentally', 'dentally'],
  ['Telnyx', 'telnyx'],
  ['Azure Speech', 'azure_speech'],
  ['OpenAI', 'openai'],
  ['DeepSeek', 'deepseek'],
  ['Groq', 'groq'],
  ['Deepgram', 'deepgram'],
  ['Cartesia', 'cartesia'],
  ['ElevenLabs', 'elevenlabs'],
  ['Vapi', 'vapi'],
  ['GoCardless', 'gocardless'],
  ['Zoom', 'zoom'],
]

function StatCard({ label, value, delta, accent, icon: Icon, cls }) {
  return (
    <div className='card stat' style={{ '--accent': accent }}>
      <div className='statCardTop'>
        <div className='statCardIcon'>
          <Icon size={18} />
        </div>
        <span className={`pill ${cls}`}>{delta}</span>
      </div>
      <div className='statValue'>{value}</div>
      <div className='muted'>{label}</div>
    </div>
  )
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

function healthLabel(summary) {
  if (!summary) return { text: 'Loading', cls: 'p-amber' }
  if (summary.error) return { text: 'Error', cls: 'p-red' }
  if (!summary.exists) return { text: 'Not set', cls: 'p-amber' }
  if (!summary.is_enabled) return { text: 'Disabled', cls: 'p-amber' }
  if (summary.configured) return { text: 'OK', cls: 'p-green' }
  return { text: 'Incomplete', cls: 'p-amber' }
}

export default function Dashboard() {
  const navigate = useNavigate()
  const { adminRole } = useAdminProfile()
  const isSuper = normalizeAdminRole(adminRole) === 'superadmin'

  const [loading, setLoading] = useState(true)
  const [refreshKey, setRefreshKey] = useState(0)
  const [health, setHealth] = useState({})
  const [providerBalances, setProviderBalances] = useState({ telnyx: null, elevenlabs: null })
  const [billing, setBilling] = useState(null)
  const [operations, setOperations] = useState(null)
  const [support, setSupport] = useState(null)
  const [orgs, setOrgs] = useState([])
  const [pending, setPending] = useState([])
  const [accountDeletions, setAccountDeletions] = useState({ items: [], pending_count: 0 })
  const [tickets, setTickets] = useState([])
  const [surveys, setSurveys] = useState(null)
  const [interviews, setInterviews] = useState(null)
  const [error, setError] = useState('')
  const [showMoreStats, setShowMoreStats] = useState(false)

  const loadAll = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [
        billingRes,
        operationsRes,
        supportRes,
        orgsRes,
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
        apiFetch('/admin/organisations?limit=200').catch(() => []),
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
      setOrgs(Array.isArray(orgsRes) ? orgsRes : [])
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

      if (isSuper) {
        const next = {}
        await Promise.all(
          HEALTH_PROVIDERS.map(async ([, key]) => {
            try {
              next[key] = await apiFetch(`/admin/integrations/${key}`)
            } catch {
              next[key] = { error: true }
            }
          }),
        )
        setHealth(next)
      } else {
        setHealth({})
      }
    } catch (e) {
      setError(e?.message || 'Could not load dashboard')
    } finally {
      setLoading(false)
    }
  }, [isSuper])

  useEffect(() => {
    loadAll()
  }, [loadAll, refreshKey])

  const recovery = operations?.recovery_jobs || {}
  const webhooks = operations?.webhooks || {}
  const activeOrgs = orgs.filter((o) => !o.is_suspended).length
  const telnyxBalance = providerBalances?.telnyx
  const elevenBalance = providerBalances?.elevenlabs

  const workflowRows = useMemo(
    () => [
      { n: 'Queued', v: recovery.queued || 0 },
      { n: 'Calling', v: recovery.calling || 0 },
      { n: 'Messaged', v: recovery.messaged || 0 },
      { n: 'Recovered', v: recovery.recovered || 0 },
      { n: 'Failed', v: recovery.failed || 0 },
    ],
    [recovery],
  )

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

  const primaryStats = (
    <>
      <StatCard
        label='Organisations'
        value={n(orgs.length)}
        delta={`${n(activeOrgs)} active`}
        accent='#0891b2'
        icon={Building2}
        cls='p-cyan'
      />
      <StatCard
        label='Active subscriptions'
        value={n(billing?.subscriptions_active)}
        delta={`${n(billing?.subscriptions_trial)} trial · ${n(billing?.subscriptions_past_due)} past due`}
        accent='#0f766e'
        icon={DollarSign}
        cls='p-green'
      />
      <StatCard
        label='Open support tickets'
        value={n(support?.total_open ?? support?.open ?? 0)}
        delta={`${n(support?.total_pending ?? support?.pending ?? 0)} pending · ${n(support?.unassigned ?? 0)} unassigned`}
        accent='#7c3aed'
        icon={BadgeCheck}
        cls='p-violet'
      />
      <StatCard
        label='Failed operations'
        value={n((recovery.failed || 0) + (webhooks.failed || 0))}
        delta={`${n(recovery.failed || 0)} jobs · ${n(webhooks.failed || 0)} webhooks`}
        accent='#d97706'
        icon={BrainCircuit}
        cls='p-amber'
      />
    </>
  )

  const secondaryStats = (
    <>
      <StatCard
        label='Live surveys'
        value={n(surveys?.live ?? surveys?.running ?? 0)}
        delta={`${n(surveys?.running ?? 0)} running · ${n(surveys?.drafts ?? 0)} drafts`}
        accent='#2563eb'
        icon={PlayCircle}
        cls='p-cyan'
      />
      <StatCard
        label='Live interviews'
        value={n(interviews?.live ?? interviews?.running ?? 0)}
        delta={`${n(interviews?.running ?? 0)} running · ${n(interviews?.drafts ?? 0)} drafts`}
        accent='#9333ea'
        icon={Users}
        cls='p-violet'
      />
      <StatCard
        label='Telnyx balance'
        value={
          telnyxBalance?.ok
            ? money(telnyxBalance.amount, telnyxBalance.currency)
            : telnyxBalance?.configured === false
              ? 'Not configured'
              : '—'
        }
        delta={
          telnyxBalance?.ok && telnyxBalance.pending > 0
            ? `${money(telnyxBalance.pending, telnyxBalance.currency)} pending`
            : 'Voice / SMS credit'
        }
        accent='#14b8a6'
        icon={Wallet}
        cls='p-green'
      />
      <StatCard
        label='ElevenLabs characters'
        value={elevenBalance?.ok ? n(elevenBalance.characters_remaining) : elevenBalance?.configured === false ? 'Not set' : '—'}
        delta={
          elevenBalance?.ok
            ? `${n(elevenBalance.character_count)} used · ${elevenBalance.tier || 'tier'}`
            : 'TTS quota'
        }
        accent='#6366f1'
        icon={Mic2}
        cls='p-violet'
      />
    </>
  )

  return (
    <div className='pageShell dashboardPage'>
      <div className='pageTop'>
        <div>
          <h1>Dashboard</h1>
          <p>Live platform overview — organisations, billing, support, operations, and integrations.</p>
        </div>
        <div className='actions'>
          <button type='button' className='btn soft' onClick={() => setRefreshKey((k) => k + 1)} disabled={loading}>
            <RefreshCw size={16} className='btnIconLeading' />
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
          <Link to='/onboarding/add-customer' className='btn primary'>
            Add customer
          </Link>
        </div>
      </div>

      {error ? <div className='note dashboardErrorNote'>{error}</div> : null}

      <DashboardSection
        title='Platform overview'
        description='Customers, billing, support load, and operational failures.'
        action={
          <button type='button' className='btn soft' onClick={() => setShowMoreStats((v) => !v)}>
            {showMoreStats ? 'Hide extra metrics' : 'Show 4 more metrics'}
          </button>
        }
      >
        <div className='grid-4'>{primaryStats}</div>
        {showMoreStats ? <div className='grid-4'>{secondaryStats}</div> : null}
      </DashboardSection>

      <DashboardSection title='Queues & operations' description='Support, compliance, onboarding, and recovery activity.'>
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

          <div className='card'>
            <div className='cardHead'>
              <h3>Recovery workflow volume</h3>
              <Link to='/operations/recovery-events' className='btn soft'>
                Recovery events
              </Link>
            </div>
            <div className='cardBody dashboardChartBody'>
              <ResponsiveContainer width='100%' height='100%'>
                <BarChart data={workflowRows}>
                  <CartesianGrid stroke='var(--line)' strokeDasharray='3 3' />
                  <XAxis dataKey='n' tick={{ fill: 'var(--muted)', fontSize: 12 }} />
                  <YAxis tick={{ fill: 'var(--muted)', fontSize: 12 }} allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey='v' fill='#0f766e' radius={[10, 10, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        <div className='span-4'>
          <DashboardSection title='Status & health' description='Integrations, alerts, and recent platform activity.'>
          <div className='stack'>
          <div className='card'>
            <div className='cardHead'>
              <h3>System health</h3>
              <Link to='/integrations/kpi' className='btn soft'>
                Integrations
              </Link>
            </div>
            <div className='cardBody'>
              <div className='list'>
                {isSuper ? (
                  HEALTH_PROVIDERS.map(([label, key]) => {
                    const pill = healthLabel(health[key])
                    return (
                      <div className='listRow' key={key}>
                        <span>{label}</span>
                        <span className={`pill ${pill.cls}`}>{pill.text}</span>
                      </div>
                    )
                  })
                ) : (
                  <p className='muted dashboardHint'>Integration health is visible to superadmin only.</p>
                )}
                <div className='listRow'>
                  <span>Webhooks (recent failed)</span>
                  <strong>{n(webhooks.failed || 0)}</strong>
                </div>
                <div className='listRow'>
                  <span>Latest webhook</span>
                  <strong className='dashboardMetaStrong'>{fmt(webhooks.latest_received_at)}</strong>
                </div>
              </div>
            </div>
          </div>

          <div className='card'>
            <div className='cardHead'>
              <h3>Needs attention</h3>
              <span className='pill p-red'>Live</span>
            </div>
            <div className='cardBody'>
              <div className='timeline'>
                {[
                  ['Failed recovery jobs', `${n(recovery.failed)} recent`, '/operations/failed-jobs', PhoneCall],
                  ['Failed webhooks', `${n(webhooks.failed)} recent`, '/operations/recovery-events', AlertTriangle],
                  ['Past-due subscriptions', `${n(billing?.subscriptions_past_due)} subs`, '/billing/subscriptions', Activity],
                  ['Pending signups', `${n(pending.length)} to review`, '/dashboard', MessageSquare],
                ].map(([title, detail, href, Icon]) => (
                  <div className='timelineItem' key={title} onClick={() => navigate(href)} role='button' tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter') navigate(href) }}>
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
                  <span>Latest recovery job</span>
                  <strong className='dashboardMetaStrong'>{fmt(recovery.latest_created_at)}</strong>
                </div>
                <div className='listRow'>
                  <span>Survey campaigns live</span>
                  <strong>{n(surveys?.live ?? 0)}</strong>
                </div>
                <div className='listRow'>
                  <span>Interview campaigns live</span>
                  <strong>{n(interviews?.live ?? 0)}</strong>
                </div>
              </div>
              <div className='actions dashboardCardActions'>
                <Link to='/operations/running-surveys' className='btn soft'>
                  Surveys
                </Link>
                <Link to='/operations/running-interviews' className='btn soft'>
                  Interviews
                </Link>
                <Link to='/organisations' className='btn soft'>
                  Organisations
                </Link>
              </div>
            </div>
          </div>
          </div>
          </DashboardSection>
        </div>
      </div>
      </DashboardSection>
    </div>
  )
}
