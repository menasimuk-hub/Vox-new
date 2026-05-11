import './authHandoff.js'
import React, { useEffect, useMemo, useRef, useState } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { ResponsiveContainer, AreaChart, Area, CartesianGrid, XAxis, YAxis, Tooltip, BarChart, Bar, PieChart, Pie, Cell } from 'recharts'
import './styles.css'
import logoUrl from './logo.svg'
import { apiFetch, getAccessToken, getApiBaseUrl, logoutDashboard } from './lib/api'

const icon = {
  queue: '◧', phone: '☎', chat: '✉', money: '£', check: '✓', chart: '△'
}

const trend = [{ day: 'Mon', value: 240 }, { day: 'Tue', value: 320 }, { day: 'Wed', value: 280 }, { day: 'Thu', value: 410 }, { day: 'Fri', value: 520 }, { day: 'Sat', value: 380 }, { day: 'Sun', value: 460 }]
const queueStats = [
  { label: 'Pending patients', value: 12, tone: 'blue', icon: icon.queue },
  { label: 'Currently calling', value: 4, tone: 'indigo', icon: icon.phone },
  { label: 'Contacted today', value: 9, tone: 'orange', icon: icon.chat },
  { label: 'Rebooked today', value: 6, tone: 'green', icon: icon.check },
  { label: 'Failed today', value: 2, tone: 'slate', icon: '×' },
  { label: 'Queue value', value: '£2,740', tone: 'blue', icon: icon.money },
  { label: 'Overdue follow-ups', value: 5, tone: 'orange', icon: '↺' },
]
const dashboardStats = [
  { label: 'Revenue recovered', value: '£3,240', tone: 'green', icon: icon.money },
  { label: 'Appointments recovered', value: '34', tone: 'blue', icon: icon.check },
  { label: 'Call costs', value: '£540', tone: 'orange', icon: icon.phone },
  { label: 'Branches live', value: '3', tone: 'slate', icon: icon.chart },
]
const queueRows = [
  { patient: 'Sarah Johnson', branch: 'Chelsea', treatment: 'Hygiene', value: '£95', status: 'Pending', next: 'Call at 3:00 PM', priority: 'High' },
  { patient: 'James Davies', branch: 'Soho', treatment: 'Whitening', value: '£180', status: 'Calling', next: 'Auto-dial in progress', priority: 'High' },
  { patient: 'Emma Wilson', branch: 'Canary Wharf', treatment: 'Check-up', value: '£75', status: 'Contacted', next: 'Await reply', priority: 'Medium' },
  { patient: 'Michael Brown', branch: 'Chelsea', treatment: 'Emergency', value: '£120', status: 'Recovered', next: 'Booked Thursday', priority: 'High' },
  { patient: 'Olivia Clark', branch: 'Soho', treatment: 'Implant consult', value: '£240', status: 'Failed', next: 'Escalate manually', priority: 'High' },
]
const callTasks = [
  { patient: 'James Davies', branch: 'Soho', queue: 'Recovery Queue', action: 'Auto-dial next patient', state: 'Running', script: 'Hello James, this is the VOXBULK assistant calling from Soho Dental. We noticed you still need to arrange your whitening visit. I can help you book the nearest available slot now.' },
  { patient: 'Sarah Johnson', branch: 'Chelsea', queue: 'No-show follow-up', action: 'Retry after SMS', state: 'Queued', script: 'Hello Sarah, we are following up on your missed appointment today. We can offer a nearby replacement slot and confirm it by text during this call.' },
  { patient: 'Olivia Clark', branch: 'Soho', queue: 'Emergency reschedule', action: 'Priority callback', state: 'Queued', script: 'Hello Olivia, we need to reschedule your appointment due to an emergency change in today’s clinic schedule. I can offer the earliest suitable appointment options now.' },
]
const callOutcomes = [
  { name: 'Booked', value: 12, color: '#16A34A' }, { name: 'Voicemail', value: 7, color: '#F97316' }, { name: 'No answer', value: 5, color: '#94A3B8' }, { name: 'Declined', value: 3, color: '#CBD5E1' },
]
const recordings = [
  { patient: 'Sarah Johnson', agent: 'Auto dialer', recording: '03:12', transcript: 'Confirmed and rebooked' },
  { patient: 'James Davies', agent: 'Auto dialer', recording: '01:18', transcript: 'Voicemail left' },
]
const whatsappRows = [
  { patient: 'Emma Wilson', conversation: 'Needs later slot', template: 'Rebooking reminder', delivery: 'Read', reply: 'Yes, after 5pm', optOut: 'No', message: 'Hi Emma, we noticed your appointment still needs rebooking. We can offer 5:20 PM tomorrow or 6:10 PM on Thursday. Reply with your preferred option.' },
  { patient: 'Liam Evans', conversation: 'Asked to reschedule', template: 'Nearest free slot', delivery: 'Delivered', reply: 'Please send options', optOut: 'No', message: 'Hi Liam, the nearest free appointments are Wednesday 11:40 AM and Thursday 2:15 PM. Reply with the best option and we will confirm it for you.' },
  { patient: 'Olivia Clark', conversation: 'Stopped responding', template: 'Final reminder', delivery: 'Failed', reply: '-', optOut: 'Yes', message: 'Hi Olivia, we are making one final attempt to help you rebook your appointment. Please reply if you still want us to hold the next available slot.' },
]
const noShowFlow = [
  { patient: 'Ava Green', missed: 'Today 11:00', message: 'Sent', callTask: 'Created', nearestSlot: 'Today 16:30', result: 'Recovered' },
  { patient: 'Noah Hall', missed: 'Yesterday 15:00', message: 'Sent', callTask: 'Created', nearestSlot: 'Tomorrow 09:00', result: 'Pending' },
  { patient: 'Sophia King', missed: 'Today 10:15', message: 'Sent', callTask: 'Created', nearestSlot: 'Today 14:10', result: 'Waiting' },
]
const reportData = [
  { branch: 'Chelsea', recovered: 1280, appointments: 14, callCost: 220 },
  { branch: 'Soho', recovered: 980, appointments: 10, callCost: 180 },
  { branch: 'Canary Wharf', recovered: 760, appointments: 8, callCost: 140 },
]
const invoiceRows = [
  { id: 'INV-2026-04', month: 'April 2026', total: '£349', status: 'Paid' }, { id: 'INV-2026-03', month: 'March 2026', total: '£349', status: 'Paid' }, { id: 'INV-2026-02', month: 'February 2026', total: '£299', status: 'Paid' },
]
const initialTickets = [
  { id: '#2041', subject: 'Caller ID update request', status: 'Open', priority: 'High', from: 'Reception team', body: 'Please review the requested caller ID update for the Soho branch and confirm rollout timing.', replies: ['Support reviewed the request and asked for branch confirmation.'], attachments: ['caller-id-request.pdf'] },
  { id: '#2037', subject: 'WhatsApp delivery review', status: 'Waiting on support', priority: 'Medium', from: 'Practice owner', body: 'Several delivered messages were not read in Soho. Please investigate template timing and delivery.', replies: ['Initial checks completed. Reviewing delivery window.'], attachments: ['delivery-screenshot.png'] },
  { id: '#1988', subject: 'Branch import completed', status: 'Closed', priority: 'Low', from: 'Manager', body: 'Branch import completed successfully.', replies: ['Resolved and confirmed.'], attachments: [] },
]

const wizardSteps = [
  { id: 1, title: 'Category', note: 'Choose one business category.' },
  { id: 2, title: 'Software', note: 'Choose one booking system.' },
  { id: 3, title: 'Setup wizard', note: 'Services, workflows and compliance.' },
  { id: 4, title: 'Preview & finish', note: 'Review generated workflow profiles.' },
]

const GOAL_OPTIONS = [
  { id: 'reduce_cancellations', label: 'Reduce cancellations' },
  { id: 'recover_revenue', label: 'Recover missed revenue' },
  { id: 'improve_fill_rate', label: 'Improve chair fill-rate' },
]
const CHANNEL_OPTIONS = [
  { id: 'voice', label: 'Voice calls' },
  { id: 'whatsapp', label: 'WhatsApp' },
]

const SETUP_PROFILE_KEY = 'retover_dashboard_setup_profile_v1'
const SETUP_COMPLETE_KEY = 'retover_dashboard_setup_complete_v1'

function goalLabel(id) {
  return GOAL_OPTIONS.find((g) => g.id === id)?.label || id
}
function channelLabel(id) {
  return CHANNEL_OPTIONS.find((c) => c.id === id)?.label || id
}

function normalizeWizardPrefs(initial) {
  let recoveryGoals = Array.isArray(initial.recoveryGoals) ? initial.recoveryGoals.filter(Boolean) : []
  if (!recoveryGoals.length && initial.mainGoal) recoveryGoals = [initial.mainGoal]
  if (!recoveryGoals.length) recoveryGoals = ['reduce_cancellations']

  let contactChannels = Array.isArray(initial.contactChannels) ? initial.contactChannels.filter(Boolean) : []
  if (!contactChannels.length && initial.preferredChannels && typeof initial.preferredChannels === 'object') {
    const pc = initial.preferredChannels
    if (pc.voice) contactChannels.push('voice')
    if (pc.whatsapp) contactChannels.push('whatsapp')
  }
  if (!contactChannels.length) contactChannels = ['voice', 'whatsapp']

  return { recoveryGoals, contactChannels }
}

function toggleInList(list, id) {
  return list.includes(id) ? list.filter((x) => x !== id) : [...list, id]
}

function DashboardUserMenu() {
  const wrapRef = useRef(null)
  const [open, setOpen] = useState(false)
  const [line1, setLine1] = useState('Clinic user')
  const [line2, setLine2] = useState('')

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [me, org] = await Promise.all([apiFetch('/auth/me'), apiFetch('/organisations/me').catch(() => null)])
        if (cancelled) return
        setLine1(me?.email || (me?.role ? String(me.role).replace(/_/g, ' ') : 'Clinic user'))
        setLine2(org?.name || (me?.org_id ? `Organisation ${String(me.org_id).slice(0, 8)}…` : ''))
      } catch {
        if (!cancelled) {
          setLine1('Clinic user')
          setLine2('')
        }
      }
    })()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!open) return
    const onDoc = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('click', onDoc)
    return () => document.removeEventListener('click', onDoc)
  }, [open])

  const initials = (line1 || 'U').split(/\s+/).map((s) => s[0]).join('').slice(0, 2).toUpperCase() || 'U'

  return (
    <div className="user-menu-wrap" ref={wrapRef}>
      <button
        type="button"
        className="topbar-user user-menu-trigger"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="true"
      >
        <span className="user-avatar">{initials}</span>
        <div style={{ textAlign: 'left' }}>
          <strong>{line1}</strong>
          <p>{line2 || 'Signed in'}</p>
        </div>
        <span className="user-menu-caret" aria-hidden>▾</span>
      </button>
      {open && (
        <div className="user-menu-dropdown" role="menu">
          <button type="button" className="user-menu-item" role="menuitem" onClick={() => logoutDashboard()}>
            Log out
          </button>
        </div>
      )}
    </div>
  )
}

const emptyMetrics = {
  total_patients: 0,
  total_appointments: 0,
  total_call_logs: 0,
  total_whatsapp_logs: 0,
  appointment_status_counts: {},
}

const emptyModuleData = {
  recoveryJobs: [],
  calls: [],
  whatsapp: [],
  appointments: [],
  branches: [],
}

function moneyFromPence(pence) {
  return `£${(Number(pence || 0) / 100).toFixed(2)}`
}

function shortDateTime(v) {
  if (!v) return '—'
  try {
    return new Date(v).toLocaleString()
  } catch {
    return String(v)
  }
}

function tenantTicketKey(orgId) {
  return `retover_dashboard_support_tickets_${orgId || 'anonymous'}`
}

function settingsFromTenant(prev, tenant) {
  const org = tenant?.org || {}
  const me = tenant?.me || {}
  const plan = tenant?.plan || tenant?.subscription?.plan
  return {
    ...prev,
    organisation: org.name || prev.organisation || 'Your organisation',
    branches: org.city || org.postcode ? [org.city, org.postcode].filter(Boolean).join(', ') : 'No branches imported yet',
    integrations: 'Dentally API not connected yet',
    team: me.role ? `${String(me.role).replace(/_/g, ' ')} account` : 'Clinic account',
    notifications: 'Email notifications enabled',
    email: org.contact_email || me.email || prev.email || '',
    phone: me.phone?.phone_e164 || org.contact_phone || prev.phone || '',
    plan: plan?.name || prev.plan || 'Starter',
  }
}

function App() {
  const [settings, setSettings] = useState({ organisation: 'VOXBULK AI Ltd', branches: 'Chelsea, Soho, Canary Wharf', integrations: 'Dentally API connected', team: 'Practice owner, receptionist, treatment coordinator, managers', notifications: 'Email + WhatsApp alerts enabled', email: 'hello@voxbulk.com', phone: '+44 20 7946 0958', paymentMethod: 'Visa ending 4242', plan: 'Growth' })
  const [emergency, setEmergency] = useState({ dentist: 'Dr. Williams', day: 'Thursday', from: '09:00', to: '17:00', wholeDay: true, reason: 'Emergency leave' })
  const [ticketForm, setTicketForm] = useState({ subject: '', message: '', category: 'technical' })
  const [tickets, setTickets] = useState([])
  const [notificationCount, setNotificationCount] = useState(0)
  const [tenant, setTenant] = useState({ me: null, org: null, metrics: emptyMetrics, subscription: null, plan: null, loading: true, error: '' })
  const [moduleData, setModuleData] = useState(emptyModuleData)
  const nav = useMemo(() => [
    { label: 'Dashboard', to: '/', end: true, icon: '◫' },
    { label: 'Recovery Queue', to: '/recovery-queue', icon: '◧' },
    { label: 'Calls', to: '/calls', icon: '☎' },
    { label: 'WhatsApp', to: '/whatsapp', icon: '✉' },
    { label: 'No-Show Follow-Up', to: '/no-show-follow-up', icon: '↺' },
    { label: 'Emergency Reschedule', to: '/emergency-reschedule', icon: '!' },
    { label: 'Reports', to: '/reports', icon: '△' },
    { label: 'Profile Settings', to: '/settings/profile', icon: '⚙' },
    { label: 'API Settings', to: '/settings/api', icon: '⌁' },
    { label: 'AI / Workflow Settings', to: '/settings/ai-workflows', icon: '✦' },
    { label: 'Packages', to: '/packages', icon: '◇' },
    { label: 'Billing', to: '/billing', icon: '£' },
    { label: 'Support', to: '/support', icon: '⌘' },
  ], [])

  const reloadTenant = async () => {
    const [me, org, metrics, billing, recoveryJobs, calls, whatsapp, appointments, branches] = await Promise.all([
      apiFetch('/auth/me'),
      apiFetch('/organisations/me'),
      apiFetch('/dashboard/metrics').catch(() => emptyMetrics),
      apiFetch('/billing/subscription').catch(() => ({ subscription: null, plan: null })),
      apiFetch('/calls/recovery/jobs').catch(() => []),
      apiFetch('/calls').catch(() => []),
      apiFetch('/whatsapp').catch(() => []),
      apiFetch('/appointments').catch(() => []),
      apiFetch('/branches').catch(() => []),
    ])
    const next = {
      me,
      org,
      metrics: metrics || emptyMetrics,
      subscription: billing?.subscription || null,
      plan: billing?.plan || null,
      loading: false,
      error: '',
    }
    setTenant(next)
    setModuleData({
      recoveryJobs: Array.isArray(recoveryJobs) ? recoveryJobs : [],
      calls: Array.isArray(calls) ? calls : [],
      whatsapp: Array.isArray(whatsapp) ? whatsapp : [],
      appointments: Array.isArray(appointments) ? appointments : [],
      branches: Array.isArray(branches) ? branches : [],
    })
    setSettings((prev) => settingsFromTenant(prev, next))
    return next
  }

  const reloadSupportNotifications = async () => {
    try {
      const res = await apiFetch('/notifications/unread-count')
      setNotificationCount(Number(res?.count || 0))
    } catch {
      setNotificationCount(0)
    }
  }

  useEffect(() => {
    if (!getAccessToken()) return
    let cancelled = false
    ;(async () => {
      try {
        const next = await reloadTenant()
        if (cancelled) return
        await reloadSupportNotifications()
        try {
          const raw = localStorage.getItem(tenantTicketKey(next.org?.id))
          setTickets(raw ? JSON.parse(raw) : [])
        } catch {
          setTickets([])
        }
      } catch (e) {
        if (!cancelled) setTenant((t) => ({ ...t, loading: false, error: e?.message || 'Could not load account' }))
      }
    })()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!tenant.org?.id) return
    try {
      localStorage.setItem(tenantTicketKey(tenant.org.id), JSON.stringify(tickets))
    } catch {
      /* ignore */
    }
  }, [tenant.org?.id, tickets])

  return (
    <BrowserRouter>
      <div className="layout-root">
        <header className="topbar">
          <div className="topbar-left">
            <img src={logoUrl} alt="VOXBULK logo" className="topbar-logo" />
          </div>
          <div className="topbar-center">
            <div className="topbar-search"><span className="search-icon">⌕</span><input aria-label="Global search" placeholder="Search patients, calls, reports..." /></div>
          </div>
          <div className="topbar-right">
            <NavLink className="topbar-icon notificationBell" aria-label="Notifications" to="/support">🔔{notificationCount ? <span>{notificationCount}</span> : null}</NavLink>
            <button className="topbar-icon" aria-label="Alerts">⚠</button>
            <DashboardUserMenu />
          </div>
        </header>

        <div className="app-shell">
          <aside className="sidebar">
            <div className="nav-group">
              <p className="nav-label">{tenant.org?.name || 'User Dashboard'}</p>
              <nav className="nav">
                {nav.map(item => <NavLink key={item.label} to={item.to} end={item.end} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}><span className="nav-icon">{item.icon}</span><span>{item.label}</span></NavLink>)}
              </nav>
            </div>
            <button type="button" className="logout-btn" onClick={() => logoutDashboard()}>Log out</button>
          </aside>

          <main className="main-panel">
            <AuthGate />
            <Routes>
              <Route path="/" element={<DashboardPage tenant={tenant} />} />
              <Route path="/setup" element={<SimpleOnboardingPage />} />
              <Route path="/new-user-wizard" element={<SimpleOnboardingPage />} />
              <Route path="/recovery-queue" element={<RecoveryQueuePage tenant={tenant} moduleData={moduleData} />} />
              <Route path="/calls" element={<CallsPage tenant={tenant} moduleData={moduleData} />} />
              <Route path="/whatsapp" element={<WhatsAppPage tenant={tenant} moduleData={moduleData} />} />
              <Route path="/no-show-follow-up" element={<NoShowPage tenant={tenant} moduleData={moduleData} />} />
              <Route path="/emergency-reschedule" element={<EmergencyPage emergency={emergency} setEmergency={setEmergency} tenant={tenant} moduleData={moduleData} />} />
              <Route path="/reports" element={<ReportsPage tenant={tenant} moduleData={moduleData} />} />
              <Route path="/settings" element={<SettingsPage settings={settings} setSettings={setSettings} tenant={tenant} reloadTenant={reloadTenant} />} />
              <Route path="/settings/profile" element={<SettingsPage settings={settings} setSettings={setSettings} tenant={tenant} reloadTenant={reloadTenant} />} />
              <Route path="/settings/api" element={<ApiSettingsPage />} />
              <Route path="/settings/ai-workflows" element={<AIWorkflowSettingsPage />} />
              <Route path="/packages" element={<PackagesPage onPlanChanged={reloadTenant} />} />
              <Route path="/billing" element={<BillingPage settings={settings} tenant={tenant} />} />
              <Route path="/support" element={<SupportPage ticketForm={ticketForm} setTicketForm={setTicketForm} tenant={tenant} onNotificationsChange={reloadSupportNotifications} />} />
              <Route path="/faq" element={<FAQPage tenant={tenant} />} />
            </Routes>
          </main>
        </div>
      </div>
    </BrowserRouter>
  )
}

function readSetupProfile() {
  try {
    const raw = localStorage.getItem(SETUP_PROFILE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function writeSetupProfile(next) {
  localStorage.setItem(SETUP_PROFILE_KEY, JSON.stringify(next))
}

function isSetupCompleteLocal() {
  return localStorage.getItem(SETUP_COMPLETE_KEY) === '1'
}

function setSetupCompleteLocal() {
  localStorage.setItem(SETUP_COMPLETE_KEY, '1')
}

function AuthGate() {
  const nav = useNavigate()
  const loc = useLocation()

  useEffect(() => {
    const token = getAccessToken()
    if (!token) return

    let cancelled = false
    ;(async () => {
      try {
        const onboarding = await apiFetch('/onboarding/status')
        if (cancelled) return

        const inSetup = loc.pathname === '/setup' || loc.pathname === '/new-user-wizard'
        const needsWizard = !Boolean(onboarding?.onboarding_complete)
        if (needsWizard && !inSetup) {
          nav('/setup', { replace: true })
        }
        if (!needsWizard && inSetup) {
          nav('/', { replace: true })
        }
      } catch {
        // If the API call fails, don't hard-block the app.
      }
    })()

    return () => { cancelled = true }
  }, [nav, loc.pathname])

  return null
}

function PageHeader({ title, description, action }) {
  return <header className="page-header compact"><div className="page-header-row"><div><h1>{title}</h1><p className="page-description">{description}</p></div>{action ? <div className="page-actions">{action}</div> : null}</div></header>
}

function ColorStats({ items, columns='four' }) { return <section className={`metric-grid ${columns}`}>{items.map(item => <article className={`card stat-card tone-${item.tone}`} key={item.label}><div className="stat-top"><span className="stat-icon">{item.icon}</span><span className="kpi-label">{item.label}</span></div><h2>{item.value}</h2></article>)}</section> }

function DashboardPage({ tenant }) {
  const m = tenant.metrics || emptyMetrics
  const recovered = Number(m.appointment_status_counts?.recovered || m.appointment_status_counts?.booked || 0)
  const stats = [
    { label: 'Patients', value: m.total_patients || 0, tone: 'blue', icon: icon.queue },
    { label: 'Appointments', value: m.total_appointments || 0, tone: 'indigo', icon: icon.check },
    { label: 'Calls logged', value: m.total_call_logs || 0, tone: 'orange', icon: icon.phone },
    { label: 'WhatsApp logs', value: m.total_whatsapp_logs || 0, tone: 'green', icon: icon.chat },
  ]
  const userName = tenant.me?.email || 'your account'
  const orgName = tenant.org?.name || 'your organisation'
  return (
    <>
      <PageHeader
        title={`Dashboard — ${orgName}`}
        description={`Signed in as ${userName}. All figures below are scoped to this organisation only.`}
      />
      {tenant.error ? <article className="card"><div className="panel-body" style={{ color: '#b91c1c' }}>{tenant.error}</div></article> : null}
      <ColorStats items={stats} columns="four" />
      <section className="dashboard-grid">
        <article className="card">
          <div className="card-head"><h3>Tenant activity</h3></div>
          <div className="chart-box">
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={[{ day: 'Patients', value: m.total_patients || 0 }, { day: 'Appts', value: m.total_appointments || 0 }, { day: 'Calls', value: m.total_call_logs || 0 }, { day: 'WA', value: m.total_whatsapp_logs || 0 }]}>
                <defs><linearGradient id="blueFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2563EB" stopOpacity={0.24} /><stop offset="100%" stopColor="#2563EB" stopOpacity={0.04} /></linearGradient></defs>
                <CartesianGrid stroke="#E2E8F0" vertical={false} />
                <XAxis dataKey="day" tickLine={false} axisLine={false} stroke="#94A3B8" />
                <YAxis tickLine={false} axisLine={false} stroke="#94A3B8" allowDecimals={false} />
                <Tooltip />
                <Area type="monotone" dataKey="value" stroke="#2563EB" strokeWidth={2.5} fill="url(#blueFill)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </article>
        <article className="card">
          <div className="card-head"><h3>Account status</h3></div>
          <div className="list-stack">
            <div className="list-row">Organisation: <strong>{orgName}</strong></div>
            <div className="list-row">Role: <strong>{tenant.me?.role || 'Not set'}</strong></div>
            <div className="list-row">Current package: <strong>{tenant.plan?.name || 'No active package'}</strong></div>
            <div className="list-row">Recovered appointment count: <strong>{recovered}</strong></div>
          </div>
        </article>
      </section>
    </>
  )
}
function RecoveryQueuePage({ tenant, moduleData }) {
  const jobs = moduleData.recoveryJobs || []
  const queued = jobs.filter((j) => j.state === 'queued').length
  const failed = jobs.filter((j) => j.state === 'failed').length
  const recovered = jobs.filter((j) => j.state === 'recovered').length
  return (
    <>
      <PageHeader title="Recovery Queue" description={`Recovery jobs for ${tenant.org?.name || 'this organisation'}.`} />
      <ColorStats items={[
        { label: 'Total jobs', value: jobs.length, tone: 'blue', icon: icon.queue },
        { label: 'Queued', value: queued, tone: 'indigo', icon: '↺' },
        { label: 'Recovered', value: recovered, tone: 'green', icon: icon.check },
        { label: 'Failed', value: failed, tone: 'orange', icon: '!' },
      ]} columns="four" />
      <article className="card">
        <div className="table-wrap"><table><thead><tr><th>Patient</th><th>Branch</th><th>Treatment</th><th>Value</th><th>Status</th><th>Created</th></tr></thead><tbody>
          {jobs.length ? jobs.map((row) => <tr key={row.job_id}><td>{row.patient_name || '—'}</td><td>{row.branch_name || '—'}</td><td>{row.treatment_label || '—'}</td><td>{moneyFromPence(row.appointment_value_gbp_pence)}</td><td><span className={`status-badge ${String(row.state || 'pending').toLowerCase().replace(/\s/g, '-')}`}>{row.state || 'queued'}</span></td><td>{shortDateTime(row.created_at)}</td></tr>) : <tr><td colSpan="6">No recovery jobs for this organisation yet.</td></tr>}
        </tbody></table></div>
      </article>
    </>
  )
}

function CallsPage({ tenant, moduleData }) {
  const calls = moduleData.calls || []
  const [selectedId, setSelectedId] = useState(null)
  const [toNumber, setToNumber] = useState('')
  const [actionMsg, setActionMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const selected = calls.find((c) => c.id === selectedId) || calls[0]
  const startCall = async () => {
    setBusy(true)
    setActionMsg('')
    try {
      const res = await apiFetch('/calls/start', {
        method: 'POST',
        body: JSON.stringify({ to_number: toNumber }),
      })
      setActionMsg(res?.ok ? 'Telnyx voice-agent call queued.' : `Telnyx call failed: ${res?.log?.raw_payload || 'check Telnyx settings'}`)
      setToNumber('')
    } catch (e) {
      setActionMsg(e?.message || 'Could not start Telnyx call')
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <PageHeader title="Calls" description={`Call logs for ${tenant.org?.name || 'this organisation'}.`} />
      <article className="card" style={{ marginBottom: 16 }}>
        <div className="panel-body form-stack">
          <label><span>Test voice number</span><input value={toNumber} onChange={(e) => setToNumber(e.target.value)} placeholder="+447..." /></label>
          <div className="actions"><button className="btn btn-primary" disabled={busy || !toNumber.trim()} onClick={startCall}>{busy ? 'Starting…' : 'Start Telnyx voice-agent call'}</button></div>
          {actionMsg ? <p className="thread-meta">{actionMsg}</p> : null}
        </div>
      </article>
      <section className="metric-grid three">
        <article className="card feature-card"><h3>Total calls</h3><p>{calls.length}</p></article>
        <article className="card feature-card"><h3>Outbound</h3><p>{calls.filter((c) => c.direction === 'outbound').length}</p></article>
        <article className="card feature-card"><h3>Latest status</h3><p>{calls[0]?.status || 'No calls yet'}</p></article>
      </section>
      <section className="dashboard-grid support-grid">
        <article className="card"><div className="card-head"><h3>Call log</h3></div><div className="table-wrap"><table><thead><tr><th>Patient</th><th>Branch</th><th>Direction</th><th>Status</th><th>Number</th><th>Open</th></tr></thead><tbody>{calls.length ? calls.map(row => <tr key={row.id}><td>{row.patient_name || row.patient_id || '—'}</td><td>{row.branch_name || '—'}</td><td>{row.direction}</td><td>{row.status}</td><td>{row.to_number || '—'}</td><td><button className="table-link" onClick={() => setSelectedId(row.id)}>Open</button></td></tr>) : <tr><td colSpan="6">No call logs for this tenant yet.</td></tr>}</tbody></table></div></article>
        <article className="card"><div className="card-head"><h3>Selected call</h3></div><div className="panel-body">{selected ? <><p className="thread-title">{selected.patient_name || selected.to_number || `Call #${selected.id}`}</p><p className="thread-meta">{selected.provider} · {selected.status} · {shortDateTime(selected.created_at)}</p><div className="thread-message">{selected.transcript_text || selected.llm_response || selected.raw_payload || 'No transcript/payload stored yet.'}</div></> : 'Select a call.'}</div></article>
      </section>
    </>
  )
}

function WhatsAppPage({ tenant, moduleData }) {
  const rows = moduleData.whatsapp || []
  const [selectedId, setSelectedId] = useState(null)
  const [toNumber, setToNumber] = useState('')
  const [body, setBody] = useState('VOXBULK test WhatsApp sandbox message.')
  const [mediaUrl, setMediaUrl] = useState('')
  const [actionMsg, setActionMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const selected = rows.find((r) => r.id === selectedId) || rows[0]
  const sendMessage = async () => {
    setBusy(true)
    setActionMsg('')
    try {
      const media_urls = mediaUrl.trim() ? [mediaUrl.trim()] : []
      const res = await apiFetch('/whatsapp/send', {
        method: 'POST',
        body: JSON.stringify({ to_number: toNumber, body, media_urls }),
      })
      setActionMsg(res?.ok ? 'Twilio WhatsApp sandbox message queued.' : `Twilio WhatsApp failed: ${res?.log?.raw_payload || 'check sandbox settings'}`)
      setToNumber('')
      setMediaUrl('')
    } catch (e) {
      setActionMsg(e?.message || 'Could not send WhatsApp message')
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <PageHeader title="WhatsApp" description={`WhatsApp logs for ${tenant.org?.name || 'this organisation'}.`} />
      <article className="card" style={{ marginBottom: 16 }}>
        <div className="panel-body form-stack">
          <label><span>Sandbox-joined WhatsApp number</span><input value={toNumber} onChange={(e) => setToNumber(e.target.value)} placeholder="+447..." /></label>
          <label><span>Message</span><input value={body} onChange={(e) => setBody(e.target.value)} /></label>
          <label><span>Optional media URL</span><input value={mediaUrl} onChange={(e) => setMediaUrl(e.target.value)} placeholder="https://... image or PDF" /></label>
          <div className="actions"><button className="btn btn-primary" disabled={busy || !toNumber.trim() || !body.trim()} onClick={sendMessage}>{busy ? 'Sending…' : 'Send WhatsApp sandbox message'}</button></div>
          {actionMsg ? <p className="thread-meta">{actionMsg}</p> : null}
        </div>
      </article>
      <ColorStats items={[
        { label: 'Messages', value: rows.length, tone: 'blue', icon: icon.chat },
        { label: 'Delivered/sent', value: rows.filter((r) => ['sent', 'delivered'].includes(String(r.status).toLowerCase())).length, tone: 'green', icon: icon.check },
        { label: 'Queued', value: rows.filter((r) => String(r.status).toLowerCase() === 'queued').length, tone: 'indigo', icon: '↺' },
        { label: 'Failed', value: rows.filter((r) => String(r.status).toLowerCase() === 'failed').length, tone: 'orange', icon: '!' },
      ]} columns="four" />
      <section className="dashboard-grid support-grid"><article className="card"><div className="table-wrap"><table><thead><tr><th>Patient</th><th>Branch</th><th>Status</th><th>Number</th><th>Created</th><th>Open</th></tr></thead><tbody>{rows.length ? rows.map(row => <tr key={row.id}><td>{row.patient_name || row.patient_id || '—'}</td><td>{row.branch_name || '—'}</td><td>{row.status}</td><td>{row.to_number || '—'}</td><td>{shortDateTime(row.created_at)}</td><td><button className="table-link" onClick={() => setSelectedId(row.id)}>Open</button></td></tr>) : <tr><td colSpan="6">No WhatsApp logs for this tenant yet.</td></tr>}</tbody></table></div></article><article className="card"><div className="card-head"><h3>Selected message</h3></div><div className="panel-body">{selected ? <><p className="thread-title">{selected.patient_name || selected.to_number || `Message #${selected.id}`}</p><p className="thread-meta">{selected.provider} · {selected.status}</p><div className="thread-message">{selected.raw_payload || 'No message payload stored yet.'}</div></> : 'Select a message.'}</div></article></section>
    </>
  )
}

function NoShowPage({ tenant, moduleData }) {
  const noShows = (moduleData.appointments || []).filter((a) => ['no_show', 'noshow', 'missed'].includes(String(a.status || '').toLowerCase()))
  return <><PageHeader title="No-Show Follow-Up" description={`Missed appointment follow-up for ${tenant.org?.name || 'this organisation'}.`} /><ColorStats items={[{ label: 'Missed appointments', value: noShows.length, tone: 'orange', icon: '!' }, { label: 'Recovery jobs', value: (moduleData.recoveryJobs || []).length, tone: 'blue', icon: icon.queue }, { label: 'Call logs', value: (moduleData.calls || []).length, tone: 'indigo', icon: icon.phone }, { label: 'WhatsApp logs', value: (moduleData.whatsapp || []).length, tone: 'green', icon: icon.chat }]} columns="four" /><article className="card"><div className="table-wrap"><table><thead><tr><th>Appointment</th><th>Treatment</th><th>Value</th><th>Status</th><th>Scheduled</th></tr></thead><tbody>{noShows.length ? noShows.map(row => <tr key={row.id}><td>{row.id.slice(0, 8)}…</td><td>{row.treatment_label || '—'}</td><td>{moneyFromPence(row.value_gbp_pence)}</td><td>{row.status}</td><td>{shortDateTime(row.scheduled_start)}</td></tr>) : <tr><td colSpan="5">No no-show appointments for this tenant yet.</td></tr>}</tbody></table></div></article></>
}

function EmergencyPage({ emergency, setEmergency, tenant, moduleData }) {
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const prepareWorkflow = async () => {
    const appt = (moduleData.appointments || [])[0]
    if (!appt?.id) {
      setMsg('No tenant appointment is available to start a recovery workflow.')
      return
    }
    setBusy(true)
    setMsg('')
    try {
      const res = await apiFetch(`/appointments/${appt.id}/recovery`, { method: 'POST' })
      setMsg(`Recovery workflow queued for appointment ${appt.id.slice(0, 8)}… Job ${String(res?.job_id || '').slice(0, 8)}…`)
    } catch (e) {
      setMsg(e?.message || 'Could not prepare emergency workflow')
    } finally {
      setBusy(false)
    }
  }
  return <><PageHeader title="Emergency Reschedule" description={`Emergency handling for ${tenant.org?.name || 'this organisation'}.`} action={<button className="btn btn-primary" disabled={busy} onClick={prepareWorkflow}>{busy ? 'Preparing…' : 'Prepare workflow'}</button>} />{msg ? <article className="card" style={{ marginBottom: 16 }}><div className="panel-body">{msg}</div></article> : null}<ColorStats items={[{ label: 'Branches', value: (moduleData.branches || []).length, tone: 'blue', icon: icon.chart }, { label: 'Appointments', value: (moduleData.appointments || []).length, tone: 'indigo', icon: icon.check }, { label: 'Recovery jobs', value: (moduleData.recoveryJobs || []).length, tone: 'orange', icon: icon.queue }, { label: 'Messages', value: (moduleData.whatsapp || []).length, tone: 'green', icon: icon.chat }]} columns="four" /><section className="dashboard-grid"><article className="card"><div className="card-head"><h3>Reschedule setup</h3></div><div className="panel-body form-stack"><label><span>Dentist / staff member</span><input value={emergency.dentist} onChange={e => setEmergency({ ...emergency, dentist: e.target.value })} /></label><label><span>Selected day</span><input value={emergency.day} onChange={e => setEmergency({ ...emergency, day: e.target.value })} /></label><label className="checkbox-row"><input type="checkbox" checked={emergency.wholeDay} onChange={e => setEmergency({ ...emergency, wholeDay: e.target.checked })} /><span>Whole day</span></label><div className="time-row"><label><span>From</span><input value={emergency.from} onChange={e => setEmergency({ ...emergency, from: e.target.value })} disabled={emergency.wholeDay} /></label><label><span>To</span><input value={emergency.to} onChange={e => setEmergency({ ...emergency, to: e.target.value })} disabled={emergency.wholeDay} /></label></div><label><span>Reason</span><input value={emergency.reason} onChange={e => setEmergency({ ...emergency, reason: e.target.value })} /></label></div></article><article className="card"><div className="card-head"><h3>Tenant branches</h3></div><div className="list-stack">{(moduleData.branches || []).length ? moduleData.branches.map((b) => <div className="list-row" key={b.id}>{b.name} {b.city ? `· ${b.city}` : ''}</div>) : <div className="list-row">No branches imported for this tenant yet.</div>}</div></article></section></>
}
function ReportsPage({ tenant }) {
  const m = tenant.metrics || emptyMetrics
  const rows = [
    { name: 'Patients', value: m.total_patients || 0 },
    { name: 'Appointments', value: m.total_appointments || 0 },
    { name: 'Calls', value: m.total_call_logs || 0 },
    { name: 'WhatsApp', value: m.total_whatsapp_logs || 0 },
  ]
  return (
    <>
      <PageHeader title="Reports" description={`Reporting for ${tenant.org?.name || 'this organisation'}. Empty values mean no synced/imported tenant data yet.`} />
      <ColorStats items={[
        { label: 'Patients', value: m.total_patients || 0, tone: 'blue', icon: icon.queue },
        { label: 'Appointments', value: m.total_appointments || 0, tone: 'green', icon: icon.check },
        { label: 'Calls', value: m.total_call_logs || 0, tone: 'orange', icon: icon.phone },
      ]} columns="three" />
      <section className="dashboard-grid">
        <article className="card">
          <div className="card-head"><h3>Tenant data summary</h3></div>
          <div className="chart-box">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={rows}>
                <CartesianGrid stroke="#E2E8F0" vertical={false} />
                <XAxis dataKey="name" tickLine={false} axisLine={false} stroke="#94A3B8" />
                <YAxis tickLine={false} axisLine={false} stroke="#94A3B8" allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="value" fill="#2563EB" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </article>
        <article className="card">
          <div className="card-head"><h3>Appointment statuses</h3></div>
          <div className="list-stack">
            {Object.entries(m.appointment_status_counts || {}).length ? Object.entries(m.appointment_status_counts).map(([k, v]) => (
              <div className="list-row" key={k}>{k}: <strong>{v}</strong></div>
            )) : <div className="list-row">No appointment status data yet.</div>}
          </div>
        </article>
      </section>
    </>
  )
}
function SettingsPage({ settings, setSettings, tenant, reloadTenant }) {
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [phoneBusy, setPhoneBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const phoneStatus = tenant.me?.phone || {}

  const save = async () => {
    setSaving(true)
    setMsg('')
    try {
      await apiFetch('/organisations/me', {
        method: 'PATCH',
        body: JSON.stringify({
          name: settings.organisation,
          contact_email: settings.email,
          contact_phone: settings.phone,
        }),
      })
      await reloadTenant()
      setEditing(false)
      setMsg('Settings saved.')
    } catch (e) {
      setMsg(e?.message || 'Could not save settings')
    } finally {
      setSaving(false)
    }
  }

  const savePhone = async () => {
    setPhoneBusy(true)
    setMsg('')
    try {
      await apiFetch('/auth/me/phone', {
        method: 'PUT',
        body: JSON.stringify({ phone_number: settings.phone }),
      })
      await reloadTenant()
      setMsg('Phone number saved. You can now start Telnyx caller ID verification.')
    } catch (e) {
      setMsg(e?.message || 'Could not save phone number')
    } finally {
      setPhoneBusy(false)
    }
  }

  const verifyPhone = async () => {
    setPhoneBusy(true)
    setMsg('')
    try {
      const res = await apiFetch('/auth/me/phone/verify', { method: 'POST' })
      await reloadTenant()
      setMsg(res?.verification_code ? `Telnyx is verifying your number. Use this code if prompted: ${res.verification_code}` : 'Telnyx verification started. Complete the provider verification prompt.')
    } catch (e) {
      setMsg(e?.message || 'Could not start phone verification')
    } finally {
      setPhoneBusy(false)
    }
  }

  const refreshPhone = async () => {
    setPhoneBusy(true)
    setMsg('')
    try {
      await apiFetch('/auth/me/phone/refresh', { method: 'POST' })
      await reloadTenant()
      setMsg('Phone verification status refreshed.')
    } catch (e) {
      setMsg(e?.message || 'Could not refresh phone verification')
    } finally {
      setPhoneBusy(false)
    }
  }

  return (
    <>
      <PageHeader
        title="Settings"
        description="Your organisation and account information. These values are loaded from the logged-in tenant."
        action={<button className="btn btn-secondary" onClick={editing ? save : () => setEditing(true)} disabled={saving}>{saving ? 'Saving…' : editing ? 'Save changes' : 'Edit account details'}</button>}
      />
      <SettingsSubnav />
      {msg ? <article className="card"><div className="panel-body">{msg}</div></article> : null}
      <section className="form-grid">
        <EditableCard label="Organisation" value={settings.organisation} onChange={v => setSettings({ ...settings, organisation: v })} disabled={!editing} />
        <ReadOnlyCard label="Signed-in email" value={tenant.me?.email || '—'} />
        <ReadOnlyCard label="Role" value={tenant.me?.role || 'Not set'} />
        <ReadOnlyCard label="Organisation ID" value={tenant.org?.id || tenant.me?.org_id || '—'} />
        <ReadOnlyCard label="Current package" value={tenant.plan?.name || 'No active package'} />
        <EditableCard label="Phone number" value={settings.phone} onChange={v => setSettings({ ...settings, phone: v })} disabled={!editing} />
        <EditableCard label="Contact email" value={settings.email} onChange={v => setSettings({ ...settings, email: v })} disabled={!editing} />
        <ReadOnlyCard label="Tenant scope" value="Dashboard, billing, reports and support tickets are scoped to this organisation." wide />
      </section>
      <article className="card" style={{ marginTop: 16 }}>
        <div className="card-head"><h3>Verified caller ID</h3><span className="pill">{phoneStatus.verification_status || 'unverified'}</span></div>
        <div className="panel-body form-stack">
          <p className="thread-meta">This lets VOXBULK use your verified phone number as caller ID for outbound Telnyx voice-agent calls. Telnyx credentials stay in admin settings.</p>
          <label><span>Your phone number (E.164)</span><input value={settings.phone} onChange={e => setSettings({ ...settings, phone: e.target.value })} placeholder="+447700900123" /></label>
          <div className="actions">
            <button className="btn btn-secondary" disabled={phoneBusy || !settings.phone.trim()} onClick={savePhone}>{phoneBusy ? 'Working…' : 'Save phone'}</button>
            <button className="btn btn-primary" disabled={phoneBusy || !phoneStatus.phone_e164} onClick={verifyPhone}>Verify phone number</button>
            <button className="btn btn-ghost" disabled={phoneBusy || !phoneStatus.phone_e164} onClick={refreshPhone}>Refresh status</button>
          </div>
          <div className="list-stack">
            <div className="list-row">Normalized: <strong>{phoneStatus.phone_e164 || 'Not saved'}</strong></div>
            <div className="list-row">Status: <strong>{phoneStatus.verification_status || 'unverified'}</strong></div>
            <div className="list-row">Verified caller ID: <strong>{phoneStatus.telnyx_verified_number_id || 'Not verified yet'}</strong></div>
            {phoneStatus.last_error ? <div className="list-row">Last error: <strong>{phoneStatus.last_error}</strong></div> : null}
          </div>
        </div>
      </article>
    </>
  )
}

function SettingsSubnav() {
  return (
    <div className="chip-grid" style={{ marginBottom: 12 }}>
      <NavLink className={({ isActive }) => `choice-chip ${isActive ? 'on' : ''}`} to="/settings/profile">Profile Settings</NavLink>
      <NavLink className={({ isActive }) => `choice-chip ${isActive ? 'on' : ''}`} to="/settings/api">API Settings</NavLink>
      <NavLink className={({ isActive }) => `choice-chip ${isActive ? 'on' : ''}`} to="/settings/ai-workflows">AI / Workflow Settings</NavLink>
    </div>
  )
}

function ApiSettingsPage() {
  const [data, setData] = useState(null)
  const [form, setForm] = useState({})
  const [enabled, setEnabled] = useState(true)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  const load = async () => {
    setLoading(true)
    setMsg('')
    try {
      const res = await apiFetch('/organisations/me/service-api-settings')
      setData(res)
      setEnabled(Boolean(res?.connection?.is_enabled))
      const next = { ...(res?.connection?.config || {}) }
      for (const field of res?.required_fields || []) {
        if (field.secret) next[field.key] = ''
        else if (next[field.key] == null) next[field.key] = ''
      }
      setForm(next)
    } catch (e) {
      setMsg(e?.message || 'Could not load API settings')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const setField = (key, value) => setForm((prev) => ({ ...prev, [key]: value }))

  const save = async () => {
    setSaving(true)
    setMsg('')
    try {
      const res = await apiFetch('/organisations/me/service-api-settings', {
        method: 'PUT',
        body: JSON.stringify({ is_enabled: enabled, config: form }),
      })
      setData(res)
      setMsg('API settings saved.')
      await load()
    } catch (e) {
      setMsg(e?.message || 'Could not save API settings')
    } finally {
      setSaving(false)
    }
  }

  const test = async () => {
    setSaving(true)
    setMsg('')
    try {
      const res = await apiFetch('/organisations/me/service-api-settings/test', { method: 'POST' })
      setMsg(res?.message || (res?.ok ? 'Connection settings look complete.' : 'Connection settings are incomplete.'))
      await load()
    } catch (e) {
      setMsg(e?.message || 'Could not test connection')
    } finally {
      setSaving(false)
    }
  }

  const service = data?.service
  const connection = data?.connection || {}

  return (
    <>
      <PageHeader title="API Settings" description="Connect your selected booking or practice software after onboarding." action={<button className="btn btn-secondary" onClick={load} disabled={loading || saving}>Refresh</button>} />
      <SettingsSubnav />
      {msg ? <article className="card"><div className="panel-body">{msg}</div></article> : null}
      {loading ? <article className="card"><div className="panel-body">Loading API settings…</div></article> : null}
      {!loading && !service ? (
        <article className="card"><div className="panel-body">No booking/practice software selected yet. Complete onboarding first.</div></article>
      ) : null}
      {!loading && service ? (
        <section className="dashboard-grid">
          <article className="card">
            <div className="card-head"><h3>{service.display_name} connection</h3></div>
            <div className="panel-body form-stack">
              <div className="review-grid">
                <div><span>Category</span><strong>{service.category_slug}</strong></div>
                <div><span>Software</span><strong>{service.display_name}</strong></div>
                <div><span>Status</span><strong>{service.status}</strong></div>
                <div><span>Connection</span><strong>{connection.configured ? 'Configured' : 'Not configured'}</strong></div>
              </div>
              <p className="field-hint">{service.short_description || 'Enter the API details supplied by your software provider.'}</p>
              <label className="checkbox-row"><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} /> Enable this integration for my organisation</label>
              {(data?.required_fields || []).map((field) => (
                <label key={field.key}>
                  <span>{field.label}{field.secret && connection.secret_set?.[field.key] ? ' (saved, leave blank to keep)' : ''}</span>
                  <input
                    type={field.secret ? 'password' : 'text'}
                    value={form[field.key] || ''}
                    onChange={e => setField(field.key, e.target.value)}
                    placeholder={field.secret && connection.secret_set?.[field.key] ? 'Saved secret is hidden' : field.placeholder}
                  />
                </label>
              ))}
              <div className="actions">
                <button className="btn btn-primary" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save API settings'}</button>
                <button className="btn btn-secondary" onClick={test} disabled={saving || !connection.exists}>{saving ? 'Testing…' : 'Test connection'}</button>
              </div>
            </div>
          </article>
          <article className="card">
            <div className="card-head"><h3>Connection status</h3></div>
            <div className="panel-body form-stack">
              <div className="list-row">API setup: <strong>{connection.exists ? 'Saved' : 'Not saved'}</strong></div>
              <div className="list-row">Configured: <strong>{connection.configured ? 'Yes' : 'No'}</strong></div>
              <div className="list-row">Missing fields: <strong>{connection.missing_fields?.join(', ') || 'None'}</strong></div>
              {service.docs_text ? <div className="info-banner">{service.docs_text}</div> : null}
              <p className="field-hint">Sensitive fields are masked after save. Use the password input only when replacing the saved secret.</p>
            </div>
          </article>
        </section>
      ) : null}
    </>
  )
}

function AIWorkflowSettingsPage() {
  return (
    <>
      <PageHeader title="AI / Workflow Settings" description="Advanced assistant identity, workflow rules and generated prompt profiles will live here." />
      <SettingsSubnav />
      <article className="card">
        <div className="panel-body">
          Advanced settings are saved by onboarding defaults today. Editing screens for assistant identity, compliance wording, timing rules and workflow-specific prompt profiles can be added here next.
        </div>
      </article>
    </>
  )
}
function BillingPage({ settings, tenant }) {
  const plan = tenant.plan
  const sub = tenant.subscription
  return (
    <>
      <PageHeader title="Billing" description={`Billing for ${tenant.org?.name || 'your organisation'}. Use Packages to upgrade or downgrade.`} />
      <section className="billing-grid">
        <article className="card">
          <div className="card-head"><h3>Current plan</h3></div>
          <div className="panel-body">
            <p className="big-value">{plan?.name || settings.plan || 'No active plan'}</p>
            <p>Status: <strong>{sub?.status || 'none'}</strong></p>
            <p>Renewal: <strong>{sub?.current_period_end ? new Date(sub.current_period_end).toLocaleDateString() : '—'}</strong></p>
          </div>
        </article>
        <article className="card">
          <div className="card-head"><h3>Payment method</h3></div>
          <div className="panel-body">
            <p>Cash/manual payment is enabled for local testing and auto-approves package changes.</p>
            <NavLink className="btn btn-primary" to="/packages">Manage package</NavLink>
          </div>
        </article>
      </section>
      <article className="card">
        <div className="card-head"><h3>Invoices</h3></div>
        <div className="panel-body">No invoices have been generated for this tenant yet.</div>
      </article>
    </>
  )
}
function SupportPage({ ticketForm, setTicketForm, tenant, onNotificationsChange }) {
  const [tickets, setTickets] = useState([])
  const [detail, setDetail] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [reply, setReply] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [ticketOpen, setTicketOpen] = useState(false)
  const [notifications, setNotifications] = useState([])
  const [createFiles, setCreateFiles] = useState([])
  const [replyFiles, setReplyFiles] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const selected = detail?.ticket || tickets.find(t => t.id === selectedId)

  const pickFiles = (files, setter) => {
    const next = Array.from(files || [])
    const bad = next.find((f) => !(f.type === 'application/pdf' || f.type.startsWith('image/')) || f.size > 5 * 1024 * 1024)
    if (bad) {
      setError('Attachments must be image/PDF files and each file must be 5 MB or less.')
      setter([])
      return
    }
    setter(next)
  }

  const loadTickets = async () => {
    setLoading(true)
    setError('')
    try {
      const qs = statusFilter ? `?status_filter=${encodeURIComponent(statusFilter)}` : ''
      const rows = await apiFetch(`/support/tickets${qs}`)
      setTickets(Array.isArray(rows) ? rows : [])
    } catch (e) {
      setError(e?.message || 'Could not load tickets')
    } finally {
      setLoading(false)
    }
  }

  const loadNotifications = async () => {
    try {
      const rows = await apiFetch('/notifications?unread_only=true')
      setNotifications(Array.isArray(rows) ? rows : [])
    } catch {
      setNotifications([])
    }
  }

  useEffect(() => {
    loadTickets()
    loadNotifications()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter])

  const openTicket = async (id) => {
    setSelectedId(id)
    setError('')
    try {
      const d = await apiFetch(`/support/tickets/${id}`)
      setDetail(d)
      setTicketOpen(true)
      await loadNotifications()
      if (onNotificationsChange) await onNotificationsChange()
    } catch (e) {
      setError(e?.message || 'Could not open ticket')
    }
  }

  const openNotification = async (notification) => {
    try {
      if (notification?.id) {
        await apiFetch(`/notifications/${notification.id}/read`, { method: 'POST' }).catch(() => null)
      }
      if (notification?.ticket_id) {
        await openTicket(notification.ticket_id)
      } else if (notification?.action_url) {
        window.location.href = notification.action_url
      } else {
        await loadNotifications()
        if (onNotificationsChange) await onNotificationsChange()
      }
    } catch (e) {
      setError(e?.message || 'Could not open notification')
    }
  }

  const createTicket = async () => {
    if (!ticketForm.subject.trim() || !ticketForm.message.trim()) return
    setError('')
    try {
      const fd = new FormData()
      fd.append('category', ticketForm.category || 'technical')
      fd.append('subject', ticketForm.subject.trim())
      fd.append('message', ticketForm.message.trim())
      createFiles.forEach((file) => fd.append('attachments', file))
      const ticket = await apiFetch('/support/tickets/upload', {
        method: 'POST',
        body: fd,
      })
      setTicketForm({ subject: '', message: '', category: 'technical' })
      setCreateFiles([])
      setCreateOpen(false)
      await loadTickets()
      await loadNotifications()
      if (onNotificationsChange) await onNotificationsChange()
      await openTicket(ticket.id)
    } catch (e) {
      setError(e?.message || 'Could not create ticket')
    }
  }

  const addReply = async () => {
    if (!reply.trim() || !selected) return
    setError('')
    try {
      const fd = new FormData()
      fd.append('message', reply)
      replyFiles.forEach((file) => fd.append('attachments', file))
      await apiFetch(`/support/tickets/${selected.id}/reply-upload`, {
        method: 'POST',
        body: fd,
      })
      setReply('')
      setReplyFiles([])
      await loadTickets()
      await loadNotifications()
      if (onNotificationsChange) await onNotificationsChange()
      await openTicket(selected.id)
    } catch (e) {
      setError(e?.message || 'Could not send reply')
    }
  }

  const closeTicket = async () => {
    if (!selected || selected.status === 'closed') return
    setError('')
    try {
      await apiFetch(`/support/tickets/${selected.id}/close`, { method: 'POST' })
      await loadTickets()
      await loadNotifications()
      if (onNotificationsChange) await onNotificationsChange()
      await openTicket(selected.id)
    } catch (e) {
      setError(e?.message || 'Could not close ticket')
    }
  }

  const downloadAttachment = async (a) => {
    try {
      const res = await fetch(`${getApiBaseUrl()}/support/tickets/attachments/${a.id}`, {
        headers: { Authorization: `Bearer ${getAccessToken()}` },
      })
      if (!res.ok) throw new Error('Could not download attachment')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = a.filename
      link.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(e?.message || 'Could not download attachment')
    }
  }

  return (
    <>
      <PageHeader title="Support" description={`Support tickets for ${tenant.org?.name || 'this organisation'}.`} action={<div className="button-row"><select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}><option value="">All statuses</option><option value="open">Open</option><option value="pending">Pending</option><option value="closed">Closed</option></select><NavLink className="btn faqButton" to="/faq">FAQ</NavLink><button className="btn btn-primary" onClick={() => setCreateOpen(true)}>Create ticket</button></div>} />
      {error ? <article className="card"><div className="panel-body" style={{ color: '#b91c1c' }}>{error}</div></article> : null}
      <article className="card">
        <div className="card-head"><h3>All tickets</h3><span>{tickets.length}</span></div>
        <div className="ticket-list full-ticket-list">{loading ? <div className="list-row">Loading…</div> : tickets.length ? tickets.map(ticket => <button key={ticket.id} className={`ticket-item ${selectedId === ticket.id ? 'selected' : ''}`} onClick={() => openTicket(ticket.id)}><div><strong>{ticket.public_ref}</strong><p>{ticket.subject}</p><p>{ticket.category} · {shortDateTime(ticket.last_message_at)}</p></div><span>{ticket.status}</span></button>) : <div className="list-row">No tickets for this organisation yet.</div>}</div>
      </article>
      <article className="card">
        <div className="card-head"><h3>Notifications</h3><span>{notifications.length}</span></div>
        <div className="panel-body notification-list">
          {notifications.length ? notifications.map(n => <button type="button" className="notification-item" key={n.id} onClick={() => openNotification(n)}><strong>{n.title}</strong><p>{n.message}</p><small>{shortDateTime(n.created_at)}</small></button>) : <div className="list-row">No unread notifications yet.</div>}
        </div>
      </article>
      {ticketOpen && selected ? <div className="modalOverlay" role="dialog" aria-modal="true"><div className="supportTicketModal card"><div className="card-head"><div><h3>{selected.subject}</h3><p className="thread-meta">{selected.public_ref} · {selected.category} · {selected.status}</p></div><button className="modalCloseIcon" aria-label="Close popup" onClick={() => setTicketOpen(false)}>×</button></div><div className="panel-body thread-panel"><div className="reply-stack">{(detail?.messages || []).map((msg) => <div className={`reply-bubble ${msg.sender_type === 'admin' ? 'admin-reply' : ''}`} key={msg.id}><strong>{msg.sender_type === 'admin' ? 'VOXBULK support' : 'You'}</strong><p>{msg.body}</p>{(msg.attachments || []).length ? <div className="attachment-strip">{msg.attachments.map((a) => <button type="button" className="attachment-pill" onClick={() => downloadAttachment(a)} key={a.id}>{a.filename}</button>)}</div> : null}<small>{shortDateTime(msg.created_at)}</small></div>)}</div>{selected.status === 'closed' ? <div className="info-banner">Replying will reopen this closed ticket.</div> : null}<label><span>Reply</span><textarea rows={5} value={reply} onChange={e => setReply(e.target.value)} placeholder="Write a reply to this ticket" /></label><div className="upload-field"><span className="toolbar-label">Attachments</span><label className="upload-button"><input type="file" accept=".pdf,image/*" multiple onChange={e => pickFiles(e.target.files, setReplyFiles)} />Upload image/PDF (max 5 MB)</label>{replyFiles.length ? <p className="muted">{replyFiles.map(f => f.name).join(', ')}</p> : null}</div><div className="button-row supportTicketActions"><button className="btn btn-primary" onClick={addReply}>Send reply</button>{selected.status !== 'closed' ? <button className="btn closeTicketAction" onClick={closeTicket}>Close ticket</button> : null}<button className="btn cancelTicketAction" onClick={() => setTicketOpen(false)}>Cancel</button></div></div></div></div> : null}
      {createOpen ? <div className="modalOverlay" role="dialog" aria-modal="true"><div className="supportCreateModal card"><div className="card-head"><h3>Create ticket</h3><button className="modalCloseIcon" aria-label="Close create ticket" onClick={() => setCreateOpen(false)}>×</button></div><div className="panel-body form-stack"><label><span>Category</span><select value={ticketForm.category || 'technical'} onChange={e => setTicketForm({ ...ticketForm, category: e.target.value })}><option value="technical">Technical</option><option value="invoices">Invoices</option><option value="pre-sale">Pre-sale</option></select></label><label><span>Subject</span><input value={ticketForm.subject} onChange={e => setTicketForm({ ...ticketForm, subject: e.target.value })} placeholder="What do you need help with?" /></label><label><span>Message</span><textarea rows={5} value={ticketForm.message} onChange={e => setTicketForm({ ...ticketForm, message: e.target.value })} placeholder="Describe the issue clearly" /></label><div className="upload-field"><span className="toolbar-label">Attachments</span><label className="upload-button"><input type="file" accept=".pdf,image/*" multiple onChange={e => pickFiles(e.target.files, setCreateFiles)} />Upload image/PDF (max 5 MB)</label>{createFiles.length ? <p className="muted">{createFiles.map(f => f.name).join(', ')}</p> : null}</div><button className="btn btn-primary" onClick={createTicket}>Create ticket</button></div></div></div> : null}
    </>
  )
}

function FAQPage({ tenant }) {
  const [groups, setGroups] = useState([])
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState({})
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError('')
      try {
        const qs = search.trim() ? `?search=${encodeURIComponent(search.trim())}` : ''
        const rows = await apiFetch(`/faq${qs}`)
        if (!cancelled) setGroups(Array.isArray(rows) ? rows : [])
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load FAQs')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [search])

  const toggle = (id) => setOpen((s) => ({ ...s, [id]: !s[id] }))

  return (
    <>
      <PageHeader title="FAQ" description={`Answers for ${tenant.org?.name || 'your organisation'} support questions.`} action={<NavLink className="btn" to="/support">Back to support</NavLink>} />
      <article className="card faqHero">
        <div className="panel-body">
          <p className="package-code">Help centre</p>
          <h2>How can we help?</h2>
          <p>Search answers by question, feature, billing topic, or support workflow.</p>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search FAQs..." />
        </div>
      </article>
      {error ? <article className="card"><div className="panel-body" style={{ color: '#b91c1c' }}>{error}</div></article> : null}
      {loading ? <article className="card"><div className="panel-body">Loading FAQs...</div></article> : null}
      <section className="faqGroups">
        {groups.length ? groups.map((group) => (
          <article className="card faqGroup" key={group.slug || group.name}>
            <div className="card-head"><h3>{group.name}</h3><span>{group.items?.length || 0}</span></div>
            <div className="faqItems">
              {(group.items || []).map((item) => {
                const id = `${group.slug || 'group'}-${item.id}`
                const isOpen = !!open[id]
                return (
                  <div className={`faqAccordion ${isOpen ? 'open' : ''}`} key={id}>
                    <button type="button" onClick={() => toggle(id)}>
                      <span>{item.is_featured ? 'Featured · ' : ''}{item.question}</span>
                      <span className="faqChevron">⌄</span>
                    </button>
                    <div className="faqAnswer"><p>{item.answer}</p></div>
                  </div>
                )
              })}
            </div>
          </article>
        )) : !loading ? <article className="card"><div className="panel-body">No FAQ answers match your search.</div></article> : null}
      </section>
    </>
  )
}

function parseFeaturesJson(raw) {
  if (!raw) return []
  try {
    const j = JSON.parse(raw)
    return Array.isArray(j) ? j.map(String) : []
  } catch {
    return []
  }
}

function PackagesPage({ onPlanChanged }) {
  const location = useLocation()
  const nav = useNavigate()
  const [plans, setPlans] = useState([])
  const [currentPlan, setCurrentPlan] = useState(null)
  const [currentSubscription, setCurrentSubscription] = useState(null)
  const [testCashEnabled, setTestCashEnabled] = useState(false)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [plist, st] = await Promise.all([apiFetch('/billing/plans'), apiFetch('/billing/subscription')])
        if (cancelled) return
        setPlans(Array.isArray(plist) ? plist : [])
        setCurrentPlan(st?.plan || null)
        setCurrentSubscription(st?.subscription || null)
        setTestCashEnabled(Boolean(st?.test_cash_billing_enabled))
      } catch (e) {
        if (!cancelled) setErr(e?.message || 'Could not load packages')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const params = new URLSearchParams(location.search || '')
    const redirectFlowId = params.get('redirect_flow_id')
    if (!redirectFlowId) return
    let cancelled = false
    ;(async () => {
      setBusy('gocardless-complete')
      setErr('')
      setMsg('Completing GoCardless setup…')
      try {
        const res = await apiFetch('/billing/subscription/gocardless/complete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ redirect_flow_id: redirectFlowId }),
        })
        if (cancelled) return
        setCurrentPlan(res?.plan || null)
        setCurrentSubscription(res?.subscription || null)
        setMsg('GoCardless sandbox subscription completed successfully.')
        if (onPlanChanged) await onPlanChanged()
        nav('/packages?billing=success', { replace: true })
      } catch (e) {
        if (!cancelled) setErr(e?.message || 'Could not complete GoCardless setup')
      } finally {
        if (!cancelled) setBusy(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [location.search, nav, onPlanChanged])

  const selectPlan = async (plan, method = 'gocardless') => {
    setBusy(plan.id)
    setErr('')
    setMsg('')
    try {
      const useCash = method === 'cash'
      const endpoint = useCash ? '/billing/subscription/test-cash' : '/billing/subscription/gocardless/start'
      const res = await apiFetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan_id: plan.id }),
      })
      if (!useCash && res?.authorization_url) {
        window.location.href = res.authorization_url
        return
      }
      setCurrentPlan(res?.plan || null)
      setCurrentSubscription(res?.subscription || null)
      setMsg(res?.message || 'Package changed using test manual billing.')
      if (onPlanChanged) await onPlanChanged()
    } catch (e) {
      setErr(e?.message || 'Could not update plan')
    } finally {
      setBusy(null)
    }
  }

  const fmtMoney = (pence) => `£${(Number(pence || 0) / 100).toFixed(2)}`

  return (
    <>
      <PageHeader title="Packages" description={testCashEnabled ? "Choose, upgrade, or downgrade your package through GoCardless sandbox. Test manual cash remains available for local testing." : "Choose a package through the configured GoCardless billing flow."} />
      {err ? (
        <article className="card">
          <div className="panel-body" style={{ color: '#b91c1c' }}>
            {err}
          </div>
        </article>
      ) : null}
      {msg ? <article className="card"><div className="panel-body">{msg}</div></article> : null}
      <article className="card">
        <div className="panel-body">
          <strong>Billing mode:</strong> {testCashEnabled ? 'GoCardless sandbox + test manual cash' : 'GoCardless billing'}
          {currentSubscription?.payment_provider ? <span> · Provider: {currentSubscription.payment_provider}</span> : null}
          {currentSubscription?.payment_mode ? <span> · Mode: {currentSubscription.payment_mode}</span> : null}
        </div>
      </article>
      <section className="package-grid">
        {plans.map((p) => {
          const feats = parseFeaturesJson(p.features_json)
          const active = currentPlan?.id === p.id
          return (
            <article key={p.id} className={`card package-card ${active ? 'active' : ''}`}>
              <div className="package-card-head">
                <div>
                  <span className="package-code">{p.code}</span>
                  <h3>{p.name}</h3>
                </div>
                {active ? <span className="package-current">Current</span> : null}
              </div>
              <div className="package-card-body">
                <p className="package-price">
                  {fmtMoney(p.price_gbp_pence)}
                  <span>/{p.interval === 'monthly' ? 'mo' : p.interval}</span>
                </p>
                {p.description ? <p className="package-description">{p.description}</p> : null}
                <ul className="package-features">
                  {feats.map((f) => (
                    <li key={f}><span>✓</span>{f}</li>
                  ))}
                </ul>
                <div className="package-actions">
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={busy === p.id || active}
                    onClick={() => selectPlan(p, 'gocardless')}
                  >
                    {busy === p.id ? 'Saving…' : active ? 'Current plan' : 'Start GoCardless sandbox'}
                  </button>
                  {testCashEnabled && !active ? (
                    <button
                      type="button"
                      className="btn btn-ghost"
                      disabled={busy === p.id}
                      onClick={() => selectPlan(p, 'cash')}
                    >
                      Test cash/manual
                    </button>
                  ) : null}
                </div>
              </div>
            </article>
          )
        })}
      </section>
    </>
  )
}

function BackendOnboardingPage() {
  const nav = useNavigate()
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [status, setStatus] = useState(null)
  const [categories, setCategories] = useState([])
  const [softwareOptions, setSoftwareOptions] = useState([])
  const [template, setTemplate] = useState(null)
  const [preview, setPreview] = useState(null)
  const [categorySlug, setCategorySlug] = useState('')
  const [softwareSlug, setSoftwareSlug] = useState('')
  const [form, setForm] = useState({
    services: [],
    customServices: '',
    assistantName: 'VOXBULK Assistant',
    organisationName: '',
    tone: 'professional',
    humorLevel: 'none',
    terminologyLabel: 'patient',
    discloseAi: true,
    languages: 'en-GB',
    callStart: '09:00',
    callEnd: '18:00',
    whatsappStart: '09:00',
    whatsappEnd: '18:00',
    weekendAllowed: false,
    aiDisclosureWording: 'This is the VOXBULK AI assistant calling on behalf of the clinic.',
    optOutWording: 'Reply STOP or ask us not to contact you again.',
    escalationDestination: 'reception team',
    workflows: [],
  })

  const workflowTitle = (key) => String(key || '').split('_').map((s) => s.charAt(0).toUpperCase() + s.slice(1)).join(' ')
  const channelName = (id) => id === 'ai_call' ? 'AI call' : id === 'whatsapp' ? 'WhatsApp' : id
  const timingMeta = (key) => ({
    appointment_reminder: ['before_appointment.days', 'Reminder days before appointment'],
    cancellation_recovery: ['after_cancellation_minutes', 'Call/message minutes after cancellation'],
    no_show_follow_up: ['after_no_show_hours', 'Follow-up hours after no-show'],
    empty_slot_fill: ['empty_slot_window_hours', 'Empty slot window in hours'],
    recall_old_customers: ['inactivity_months', 'Inactive for months'],
    annual_review_recall: ['annual_recall_months', 'Annual recall threshold in months'],
    overdue_treatment_recall: ['overdue_days', 'Overdue after days'],
  }[key] || ['', 'Timing rule'])
  const stepFromStatus = (s) => {
    if (!s?.category_slug) return 1
    if (!s?.booking_software_slug) return 2
    return s?.onboarding_state === 'onboarding_completed' ? 4 : 3
  }

  const setField = (key, value) => setForm((prev) => ({ ...prev, [key]: value }))

  const getTimingValue = (workflow) => {
    const [path] = timingMeta(workflow.workflow_key)
    if (!path) return ''
    if (path.includes('.')) {
      const [parent, child] = path.split('.')
      return workflow.timing_rules?.[parent]?.[child] ?? ''
    }
    return workflow.timing_rules?.[path] ?? ''
  }

  const setTimingValue = (workflowKey, value) => {
    const [path] = timingMeta(workflowKey)
    if (!path) return
    setForm((prev) => ({
      ...prev,
      workflows: prev.workflows.map((w) => {
        if (w.workflow_key !== workflowKey) return w
        const nextRules = { ...(w.timing_rules || {}) }
        const num = Number(value)
        const nextValue = value === '' ? '' : Number.isNaN(num) ? value : num
        if (path.includes('.')) {
          const [parent, child] = path.split('.')
          nextRules[parent] = { ...(nextRules[parent] || {}), [child]: nextValue }
        } else {
          nextRules[path] = nextValue
        }
        return { ...w, timing_rules: nextRules }
      }),
    }))
  }

  const initialiseForm = (nextTemplate, config) => {
    if (!nextTemplate) return
    const existing = new Map((config?.workflows || []).map((w) => [w.workflow_key, w]))
    const workflows = Object.entries(nextTemplate.workflows || {}).map(([workflow_key, defaults]) => {
      const row = existing.get(workflow_key)
      return {
        workflow_key,
        enabled: row?.enabled ?? true,
        channels: row?.channels?.length ? row.channels : (defaults.channels || []),
        timing_rules: defaults.timing_rules || {},
        allowed_actions: row?.generated_profile?.allowed_actions || ['confirm_booking', 'offer_available_slots', 'send_whatsapp_follow_up'],
        forbidden_actions: row?.generated_profile?.forbidden_actions || ['clinical_advice', 'payment_disputes', 'medical_advice'],
        escalation_rules: row?.generated_profile?.escalation_behavior?.rules || ['complaint', 'payment', 'medical_question', 'uncertainty', 'human_requested'],
      }
    })
    setForm((prev) => ({
      ...prev,
      services: config?.services?.length ? config.services : (nextTemplate.default_services || []),
      assistantName: config?.ai_identity?.assistant_name || prev.assistantName,
      organisationName: config?.ai_identity?.organisation_name || prev.organisationName,
      tone: config?.ai_identity?.tone || nextTemplate.tone_options?.[0] || prev.tone,
      humorLevel: config?.ai_identity?.humor_level || prev.humorLevel,
      terminologyLabel: config?.ai_identity?.terminology_label || nextTemplate.default_terminology || prev.terminologyLabel,
      discloseAi: config?.ai_identity?.disclose_ai ?? prev.discloseAi,
      languages: (config?.ai_identity?.languages || ['en-GB']).join(', '),
      escalationDestination: config?.compliance?.escalation_destination || prev.escalationDestination,
      aiDisclosureWording: config?.compliance?.ai_disclosure_wording || prev.aiDisclosureWording,
      optOutWording: config?.compliance?.opt_out_wording || prev.optOutWording,
      weekendAllowed: config?.compliance?.weekend_allowed ?? prev.weekendAllowed,
      workflows,
    }))
    if (config?.workflows?.length) setPreview(config)
  }

  const loadCategoryContext = async (slug, selectedSoftware) => {
    const [templateRes, softwareRows, config] = await Promise.all([
      apiFetch(`/onboarding/category-template?category=${encodeURIComponent(slug)}`),
      apiFetch(`/onboarding/software-options?category=${encodeURIComponent(slug)}`),
      apiFetch('/onboarding/wizard').catch(() => null),
    ])
    setTemplate(templateRes)
    setSoftwareOptions(Array.isArray(softwareRows) ? softwareRows : [])
    if (selectedSoftware) setSoftwareSlug(selectedSoftware)
    initialiseForm(templateRes, config)
  }

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [statusRes, categoryRows] = await Promise.all([apiFetch('/onboarding/status'), apiFetch('/onboarding/categories')])
        if (cancelled) return
        setStatus(statusRes)
        setCategories(Array.isArray(categoryRows) ? categoryRows : [])
        setCategorySlug(statusRes?.category_slug || '')
        setSoftwareSlug(statusRes?.booking_software_slug || '')
        if (statusRes?.category_slug) await loadCategoryContext(statusRes.category_slug, statusRes.booking_software_slug)
        if (!cancelled) setStep(stepFromStatus(statusRes))
      } catch (e) {
        if (!cancelled) setMsg(e?.message || 'Could not load setup status')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [])

  const validate = () => {
    if (step === 1 && !categorySlug) return 'Select one category'
    if (step === 2 && !softwareSlug) return 'Select one booking/practice software'
    if (step === 3) {
      if (!form.services.length && !form.customServices.trim()) return 'Select or add at least one service'
      if (!form.workflows.some((w) => w.enabled)) return 'Enable at least one workflow'
      if (!form.assistantName.trim()) return 'Assistant name is required'
      if (!form.escalationDestination.trim()) return 'Human escalation destination is required'
    }
    return ''
  }

  const selectCategory = async () => {
    const err = validate()
    if (err) return window.alert(err)
    setSaving(true); setMsg('')
    try {
      const nextStatus = await apiFetch('/onboarding/select-category', { method: 'POST', body: JSON.stringify({ category_slug: categorySlug }) })
      setStatus(nextStatus)
      await loadCategoryContext(categorySlug, '')
      setSoftwareSlug('')
      setStep(2)
    } catch (e) {
      setMsg(e?.message || 'Could not save category')
    } finally {
      setSaving(false)
    }
  }

  const selectSoftware = async () => {
    const err = validate()
    if (err) return window.alert(err)
    setSaving(true); setMsg('')
    try {
      const nextStatus = await apiFetch('/onboarding/select-software', { method: 'POST', body: JSON.stringify({ software_slug: softwareSlug }) })
      setStatus(nextStatus)
      setStep(3)
    } catch (e) {
      setMsg(e?.message || 'Could not save software')
    } finally {
      setSaving(false)
    }
  }

  const buildPayload = () => ({
    step: step === 4 ? 'review' : 'wizard',
    services: form.services,
    custom_services: form.customServices.split(',').map((s) => s.trim()).filter(Boolean),
    ai_identity: {
      assistant_name: form.assistantName,
      organisation_name: form.organisationName || undefined,
      tone: form.tone,
      humor_level: form.humorLevel,
      languages: form.languages.split(',').map((s) => s.trim()).filter(Boolean),
      terminology_label: form.terminologyLabel,
      disclose_ai: form.discloseAi,
    },
    compliance: {
      outbound_call_windows: { weekdays: { start: form.callStart, end: form.callEnd } },
      whatsapp_windows: { weekdays: { start: form.whatsappStart, end: form.whatsappEnd } },
      weekend_allowed: form.weekendAllowed,
      ai_disclosure_wording: form.aiDisclosureWording,
      opt_out_wording: form.optOutWording,
      escalation_destination: form.escalationDestination,
      contact_preference_rules: { respect_do_not_contact: true, prefer_existing_customer_channel: true },
    },
    workflows: form.workflows,
  })

  const generatePreview = async () => {
    const err = validate()
    if (err) return window.alert(err)
    setSaving(true); setMsg('')
    try {
      const res = await apiFetch('/onboarding/wizard/generate-preview', { method: 'POST', body: JSON.stringify(buildPayload()) })
      setPreview(res)
      setStep(4)
    } catch (e) {
      setMsg(e?.message || 'Could not generate preview')
    } finally {
      setSaving(false)
    }
  }

  const complete = async () => {
    setSaving(true); setMsg('')
    try {
      await apiFetch('/onboarding/wizard/complete', { method: 'POST', body: JSON.stringify(buildPayload()) })
      nav('/', { replace: true })
    } catch (e) {
      setMsg(e?.message || 'Could not complete onboarding')
    } finally {
      setSaving(false)
    }
  }

  const updateWorkflow = (workflowKey, patch) => setForm((prev) => ({
    ...prev,
    workflows: prev.workflows.map((w) => w.workflow_key === workflowKey ? { ...w, ...patch } : w),
  }))
  const toggleWorkflowChannel = (workflow, channel) => updateWorkflow(workflow.workflow_key, { channels: toggleInList(workflow.channels || [], channel) })

  if (loading) return <article className="card"><div className="panel-body">Loading setup…</div></article>

  return (
    <>
      <PageHeader title="Complete VOXBULK setup" description="Choose your category, booking software and structured recovery workflows." action={<span className="pill">Step {step} / 4</span>} />
      {msg ? <article className="card"><div className="panel-body">{msg}</div></article> : null}
      <section className="wizard-shell">
        <aside className="card wizard-sidebar">
          <div className="card-head"><h3>Setup progress</h3></div>
          <div className="wizard-steps">
            {wizardSteps.map(item => (
              <button key={item.id} className={`wizard-step ${step === item.id ? 'active' : ''} ${step > item.id ? 'done' : ''}`} onClick={() => setStep(item.id)} type="button">
                <span className="wizard-step-index">{step > item.id ? '✓' : item.id}</span>
                <span><strong>{item.title}</strong><em>{item.note}</em></span>
              </button>
            ))}
          </div>
          <div className="wizard-progress"><div className="wizard-progress-bar"><span style={{ width: `${step * 25}%` }} /></div><p>{step} of 4</p></div>
        </aside>
        <section className="wizard-main">
          {step === 1 && (
            <article className="card wizard-card">
              <div className="card-head"><h3>Select one category</h3></div>
              <div className="panel-body form-stack">
                <p className="field-hint">This applies to the whole organisation.</p>
                <div className="chip-grid">
                  {categories.map((c) => <button key={c.slug} type="button" className={`choice-chip ${categorySlug === c.slug ? 'on' : ''}`} onClick={() => setCategorySlug(c.slug)}>{c.name}</button>)}
                </div>
                <div className="info-banner">Changing category later will require confirmation because templates, workflows and agent profiles may change.</div>
              </div>
            </article>
          )}
          {step === 2 && (
            <article className="card wizard-card">
              <div className="card-head"><h3>Select one booking/practice software</h3></div>
              <div className="panel-body form-stack">
                <p className="field-hint">VOXBULK uses this as the source of truth for appointments and customer context.</p>
                <div className="list-stack" style={{ padding: 0 }}>
                  {softwareOptions.map((s) => (
                    <button key={s.slug} type="button" className={`ticket-item ${softwareSlug === s.slug ? 'selected' : ''}`} onClick={() => setSoftwareSlug(s.slug)}>
                      <span><strong>{s.display_name}</strong><p>{s.short_description}</p></span>
                      <span><span className={`status-badge ${s.is_active ? 'recovered' : 'pending'}`}>{s.status}</span>{s.is_recommended ? <span className="status-badge contacted" style={{ marginLeft: 6 }}>recommended</span> : null}</span>
                    </button>
                  ))}
                </div>
              </div>
            </article>
          )}
          {step === 3 && (
            <article className="card wizard-card">
              <div className="card-head"><h3>Category-specific setup wizard</h3></div>
              <div className="panel-body form-stack">
                <div>
                  <span>Services offered</span>
                  <p className="field-hint">Choose defaults and add custom services separated by commas.</p>
                  <div className="chip-grid">{(template?.default_services || []).map((service) => <button key={service} type="button" className={`choice-chip ${form.services.includes(service) ? 'on' : ''}`} onClick={() => setField('services', toggleInList(form.services, service))}>{service}</button>)}</div>
                  <input style={{ marginTop: 10 }} value={form.customServices} onChange={e => setField('customServices', e.target.value)} placeholder="Custom services, comma separated" />
                </div>
                <div>
                  <span>AI identity and tone</span>
                  <div className="form-grid" style={{ marginTop: 8 }}>
                    <label><span>Assistant name</span><input value={form.assistantName} onChange={e => setField('assistantName', e.target.value)} /></label>
                    <label><span>Organisation/brand name</span><input value={form.organisationName} onChange={e => setField('organisationName', e.target.value)} placeholder="Use organisation name by default" /></label>
                    <label><span>Tone</span><select value={form.tone} onChange={e => setField('tone', e.target.value)}>{['professional', 'warm', 'premium', 'friendly'].map(v => <option key={v} value={v}>{v}</option>)}</select></label>
                    <label><span>Humor level</span><select value={form.humorLevel} onChange={e => setField('humorLevel', e.target.value)}><option value="none">none</option><option value="low">low</option></select></label>
                    <label><span>Terminology label</span><input value={form.terminologyLabel} onChange={e => setField('terminologyLabel', e.target.value)} /></label>
                    <label><span>Languages</span><input value={form.languages} onChange={e => setField('languages', e.target.value)} /></label>
                  </div>
                  <label className="checkbox-row"><input type="checkbox" checked={form.discloseAi} onChange={e => setField('discloseAi', e.target.checked)} /> Immediately disclose AI on calls/messages</label>
                </div>
                <div>
                  <span>Workflows and channels</span>
                  <p className="field-hint">Enable each workflow and choose WhatsApp, AI call, or both.</p>
                  <div className="list-stack" style={{ padding: 0 }}>
                    {form.workflows.map((w) => {
                      const [, timingLabelText] = timingMeta(w.workflow_key)
                      return (
                        <div key={w.workflow_key} className="list-row">
                          <div className="legend-row"><strong>{workflowTitle(w.workflow_key)}</strong><button type="button" className={`toggle ${w.enabled ? 'on' : ''}`} onClick={() => updateWorkflow(w.workflow_key, { enabled: !w.enabled })}>{w.enabled ? 'On' : 'Off'}</button></div>
                          <div className="chip-grid" style={{ marginTop: 10 }}>{['whatsapp', 'ai_call'].map((channel) => <button key={channel} type="button" className={`choice-chip ${w.channels?.includes(channel) ? 'on' : ''}`} onClick={() => toggleWorkflowChannel(w, channel)}>{channelName(channel)}</button>)}</div>
                          {timingMeta(w.workflow_key)[0] ? <label style={{ marginTop: 10 }}><span>{timingLabelText}</span><input value={getTimingValue(w)} onChange={e => setTimingValue(w.workflow_key, e.target.value)} /></label> : null}
                        </div>
                      )
                    })}
                  </div>
                </div>
                <div>
                  <span>Permissions and UK compliance</span>
                  <div className="form-grid" style={{ marginTop: 8 }}>
                    <label><span>Outbound call start</span><input value={form.callStart} onChange={e => setField('callStart', e.target.value)} /></label>
                    <label><span>Outbound call end</span><input value={form.callEnd} onChange={e => setField('callEnd', e.target.value)} /></label>
                    <label><span>WhatsApp start</span><input value={form.whatsappStart} onChange={e => setField('whatsappStart', e.target.value)} /></label>
                    <label><span>WhatsApp end</span><input value={form.whatsappEnd} onChange={e => setField('whatsappEnd', e.target.value)} /></label>
                    <label><span>Human escalation destination</span><input value={form.escalationDestination} onChange={e => setField('escalationDestination', e.target.value)} /></label>
                    <label><span>Weekend outreach</span><select value={form.weekendAllowed ? 'yes' : 'no'} onChange={e => setField('weekendAllowed', e.target.value === 'yes')}><option value="no">No</option><option value="yes">Yes</option></select></label>
                  </div>
                  <label style={{ marginTop: 10 }}><span>AI disclosure wording</span><textarea rows={2} value={form.aiDisclosureWording} onChange={e => setField('aiDisclosureWording', e.target.value)} /></label>
                  <label style={{ marginTop: 10 }}><span>Opt-out wording</span><textarea rows={2} value={form.optOutWording} onChange={e => setField('optOutWording', e.target.value)} /></label>
                  <div className="info-banner" style={{ marginTop: 10 }}>AI may confirm bookings, offer available slots and send WhatsApp follow-up. It must not provide clinical advice and must escalate complaints, payments, medical questions, uncertainty or human requests.</div>
                </div>
              </div>
            </article>
          )}
          {step === 4 && (
            <article className="card wizard-card">
              <div className="card-head"><h3>Review generated workflow preview</h3></div>
              <div className="panel-body wizard-review">
                <div className="review-grid">
                  <div><span>Category</span><strong>{status?.category_slug || categorySlug || '—'}</strong></div>
                  <div><span>Software</span><strong>{status?.booking_software_slug || softwareSlug || '—'}</strong></div>
                  <div><span>Assistant</span><strong>{form.assistantName}</strong></div>
                  <div><span>Services</span><strong>{[...form.services, ...form.customServices.split(',').map(s => s.trim()).filter(Boolean)].join(', ') || '—'}</strong></div>
                </div>
                {(preview?.workflows || []).map((workflow) => <div key={workflow.workflow_key} className="launch-panel"><h2>{workflowTitle(workflow.workflow_key)}</h2><p>{workflow.workflow_summary_preview}</p><textarea readOnly rows={8} value={workflow.generated_prompt_preview || ''} /></div>)}
                {!preview?.workflows?.length ? <div className="info-banner">Generate preview to see workflow summaries and prompt profiles.</div> : null}
                <div className="launch-panel"><h2>Ready to enter the dashboard</h2><p>Finishing setup stores this structured workflow configuration on your organisation and unlocks the normal dashboard.</p></div>
              </div>
            </article>
          )}
          <div className="wizard-footer-actions">
            <button className="btn btn-secondary" onClick={() => setStep(s => Math.max(1, s - 1))} disabled={step === 1 || saving} type="button">Back</button>
            {step === 1 ? <button className="btn btn-primary" onClick={selectCategory} disabled={saving} type="button">{saving ? 'Saving…' : 'Save category'}</button> : null}
            {step === 2 ? <button className="btn btn-primary" onClick={selectSoftware} disabled={saving} type="button">{saving ? 'Saving…' : 'Save software'}</button> : null}
            {step === 3 ? <button className="btn btn-primary" onClick={generatePreview} disabled={saving} type="button">{saving ? 'Generating…' : 'Generate preview'}</button> : null}
            {step === 4 ? <button className="btn btn-primary" onClick={complete} disabled={saving} type="button">{saving ? 'Saving…' : 'Finish setup'}</button> : null}
          </div>
        </section>
      </section>
    </>
  )
}

const SIMPLE_GOALS = [
  { key: 'appointment_reminder', label: 'Remind upcoming appointments' },
  { key: 'cancellation_recovery', label: 'Recover cancellations' },
  { key: 'no_show_follow_up', label: 'Follow up no-shows' },
  { key: 'empty_slot_fill', label: 'Fill empty slots' },
  { key: 'recall_old_customers', label: 'Recall old patients/clients/customers' },
]
const FALLBACK_CATEGORIES = [
  { id: 'dental', slug: 'dental', name: 'Dental', description: 'Dental clinics and hygiene recalls.' },
  { id: 'aesthetics', slug: 'aesthetics', name: 'Aesthetics / Beauty / Medspa / Anti-aging', description: 'Aesthetic, medspa and beauty clinics.' },
  { id: 'opticians', slug: 'opticians', name: 'Opticians', description: 'Opticians and optometry practices.' },
]
const FALLBACK_SOFTWARE = {
  dental: [
    { slug: 'dentally', display_name: 'Dentally', category_slug: 'dental', short_description: 'Dental practice management integration.', status: 'active', is_active: true, is_recommended: true },
    { slug: 'carestack', display_name: 'CareStack', category_slug: 'dental', short_description: 'Dental practice management integration for dental groups.', status: 'coming soon', is_active: false, is_recommended: false },
  ],
  aesthetics: [
    { slug: 'pabau', display_name: 'Pabau', category_slug: 'aesthetics', short_description: 'Aesthetics and medspa practice software integration.', status: 'coming soon', is_active: false, is_recommended: true },
    { slug: 'cliniko', display_name: 'Cliniko', category_slug: 'aesthetics', short_description: 'Clinic booking software integration.', status: 'coming soon', is_active: false, is_recommended: false },
  ],
  opticians: [
    { slug: 'optix', display_name: 'Optix', category_slug: 'opticians', short_description: 'Optician practice management integration.', status: 'coming soon', is_active: false, is_recommended: true },
    { slug: 'ocuco', display_name: 'Ocuco', category_slug: 'opticians', short_description: 'Optometry and optical retail software integration.', status: 'coming soon', is_active: false, is_recommended: false },
  ],
}
const FALLBACK_TEMPLATE = {
  dental: {
    default_services: ['check-up', 'hygiene', 'whitening', 'emergency', 'consultation', 'treatment follow-up'],
    workflows: {
      appointment_reminder: { timing_rules: { before_appointment: { days: 2 } } },
      cancellation_recovery: { timing_rules: { after_cancellation_minutes: 15 } },
      no_show_follow_up: { timing_rules: { after_no_show_hours: 2 } },
      empty_slot_fill: { timing_rules: { empty_slot_window_hours: 48 } },
      recall_old_customers: { timing_rules: { inactivity_months: 18 } },
    },
  },
  aesthetics: {
    default_services: ['consultation', 'Botox', 'fillers', 'facial', 'laser', 'anti-aging review', 'skin treatment'],
    workflows: {
      appointment_reminder: { timing_rules: { before_appointment: { days: 2 } } },
      cancellation_recovery: { timing_rules: { after_cancellation_minutes: 20 } },
      no_show_follow_up: { timing_rules: { after_no_show_hours: 3 } },
      empty_slot_fill: { timing_rules: { empty_slot_window_hours: 72 } },
      recall_old_customers: { timing_rules: { inactivity_months: 6 } },
    },
  },
  opticians: {
    default_services: ['eye test', 'contact lens check', 'contact lens renewal', 'annual recall', 'follow-up'],
    workflows: {
      appointment_reminder: { timing_rules: { before_appointment: { days: 2 } } },
      cancellation_recovery: { timing_rules: { after_cancellation_minutes: 20 } },
      no_show_follow_up: { timing_rules: { after_no_show_hours: 2 } },
      empty_slot_fill: { timing_rules: { empty_slot_window_hours: 48 } },
      recall_old_customers: { timing_rules: { inactivity_months: 18 } },
    },
  },
}

function SimpleOnboardingPage() {
  const nav = useNavigate()
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [status, setStatus] = useState(null)
  const [categories, setCategories] = useState([])
  const [softwareOptions, setSoftwareOptions] = useState([])
  const [template, setTemplate] = useState(null)
  const [categorySlug, setCategorySlug] = useState('')
  const [softwareSlug, setSoftwareSlug] = useState('')
  const [goals, setGoals] = useState(['appointment_reminder', 'cancellation_recovery'])
  const [channelChoice, setChannelChoice] = useState('both')

  const categoryLabel = (slug) => ({
    dental: 'Dental',
    aesthetics: 'Aesthetics / Beauty / Medspa / Anti-aging',
    opticians: 'Opticians',
  }[slug] || slug)
  const channelList = () => channelChoice === 'both' ? ['whatsapp', 'ai_call'] : [channelChoice]
  const channelSummary = () => channelChoice === 'both' ? 'WhatsApp and AI phone calls' : channelChoice === 'whatsapp' ? 'WhatsApp' : 'AI phone calls'
  const stepFromStatus = (s) => {
    if (!s?.category_slug) return 1
    if (!s?.booking_software_slug) return 2
    return 3
  }

  const loadCategoryContext = async (slug) => {
    const [templateRes, softwareRows] = await Promise.all([
      apiFetch(`/onboarding/category-template?category=${encodeURIComponent(slug)}`).catch(() => null),
      apiFetch(`/onboarding/software-options?category=${encodeURIComponent(slug)}`).catch(() => []),
    ])
    const nextTemplate = templateRes || FALLBACK_TEMPLATE[slug] || FALLBACK_TEMPLATE.dental
    const nextSoftware = Array.isArray(softwareRows) && softwareRows.length ? softwareRows : (FALLBACK_SOFTWARE[slug] || [])
    setTemplate(nextTemplate)
    setSoftwareOptions(nextSoftware)
    const defaults = Object.keys(nextTemplate?.workflows || {}).filter((key) => SIMPLE_GOALS.some((g) => g.key === key))
    if (defaults.length) setGoals(defaults.slice(0, 2))
  }

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [statusRes, categoryRows] = await Promise.all([apiFetch('/onboarding/status'), apiFetch('/onboarding/categories')])
        if (cancelled) return
        setStatus(statusRes)
        setCategories(Array.isArray(categoryRows) && categoryRows.length ? categoryRows : FALLBACK_CATEGORIES)
        setCategorySlug(statusRes?.category_slug || '')
        setSoftwareSlug(statusRes?.booking_software_slug || '')
        if (statusRes?.category_slug) await loadCategoryContext(statusRes.category_slug)
        if (!cancelled) setStep(stepFromStatus(statusRes))
      } catch (e) {
        if (!cancelled) {
          setCategories(FALLBACK_CATEGORIES)
          setMsg(e?.message || 'Could not load onboarding setup')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [])

  const saveCategory = async () => {
    if (!categorySlug) return window.alert('Select one category')
    setSaving(true); setMsg('')
    try {
      await loadCategoryContext(categorySlug)
      setSoftwareSlug('')
      setStep(2)
      const next = await apiFetch('/onboarding/select-category', { method: 'POST', body: JSON.stringify({ category_slug: categorySlug, confirm_change: true }) })
      setStatus(next)
      await loadCategoryContext(categorySlug)
    } catch (e) {
      setMsg(e?.message || 'Could not save category yet. You can still choose software, but setup must save before finishing.')
    } finally {
      setSaving(false)
    }
  }

  const saveSoftware = async () => {
    if (!softwareSlug) return window.alert('Select one software')
    setSaving(true); setMsg('')
    try {
      setStep(3)
      const next = await apiFetch('/onboarding/select-software', { method: 'POST', body: JSON.stringify({ software_slug: softwareSlug, confirm_change: true }) })
      setStatus(next)
    } catch (e) {
      setMsg(e?.message || 'Could not save software yet. Please try Continue again before finishing setup.')
    } finally {
      setSaving(false)
    }
  }

  const finish = async () => {
    if (!goals.length) return window.alert('Select at least one goal')
    if (!channelChoice) return window.alert('Select preferred channels')
    setSaving(true); setMsg('')
    try {
      const channels = channelList()
      const workflows = goals.map((workflow_key) => ({
        workflow_key,
        enabled: true,
        channels,
        timing_rules: template?.workflows?.[workflow_key]?.timing_rules || {},
      }))
      await apiFetch('/onboarding/wizard/complete', {
        method: 'POST',
        body: JSON.stringify({
          step: 'simple_onboarding',
          services: template?.default_services || [],
          workflows,
        }),
      })
      nav('/', { replace: true })
    } catch (e) {
      setMsg(e?.message || 'Could not complete onboarding')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <article className="card"><div className="panel-body">Loading setup…</div></article>

  return (
    <>
      <PageHeader
        title="Quick setup"
        description="Answer a few questions so VOXBULK can tailor recovery workflows for your organisation."
        action={<span className="pill">Step {step} / 4</span>}
      />
      {msg ? <article className="card"><div className="panel-body">{msg}</div></article> : null}
      <section className="wizard-shell">
        <aside className="card wizard-sidebar">
          <div className="card-head"><h3>Setup progress</h3></div>
          <div className="wizard-steps">
            {[
              { id: 1, title: 'Category', note: 'Choose one business type.' },
              { id: 2, title: 'Software', note: 'Choose one booking system.' },
              { id: 3, title: 'Goals & channels', note: 'Choose what VOXBULK should help with.' },
              { id: 4, title: 'Review', note: 'Confirm and unlock dashboard.' },
            ].map(item => (
              <button key={item.id} className={`wizard-step ${step === item.id ? 'active' : ''} ${step > item.id ? 'done' : ''}`} onClick={() => setStep(item.id)} type="button">
                <span className="wizard-step-index">{step > item.id ? '✓' : item.id}</span>
                <span><strong>{item.title}</strong><em>{item.note}</em></span>
              </button>
            ))}
          </div>
          <div className="wizard-progress"><div className="wizard-progress-bar"><span style={{ width: `${step * 25}%` }} /></div><p>{step} of 4</p></div>
        </aside>

        <section className="wizard-main">
          {step === 1 && (
            <article className="card wizard-card">
              <div className="card-head"><h3>Select your business category</h3></div>
              <div className="panel-body form-stack">
                <p className="field-hint">Choose one category for this organisation.</p>
                <div className="chip-grid">
                  {categories.map((c) => (
                    <button key={c.slug} type="button" className={`choice-chip ${categorySlug === c.slug ? 'on' : ''}`} onClick={() => { setCategorySlug(c.slug); setSoftwareSlug(''); loadCategoryContext(c.slug) }}>
                      {categoryLabel(c.slug)}
                    </button>
                  ))}
                </div>
              </div>
            </article>
          )}

          {step === 2 && (
            <article className="card wizard-card">
              <div className="card-head"><h3>Select your booking/practice software</h3></div>
              <div className="panel-body form-stack">
                <p className="field-hint">VOXBULK stays an overlay. Your selected software remains the source of truth.</p>
                <div className="list-stack" style={{ padding: 0 }}>
                  {softwareOptions.map((s) => (
                    <button key={s.slug} type="button" className={`ticket-item ${softwareSlug === s.slug ? 'selected' : ''}`} onClick={() => setSoftwareSlug(s.slug)}>
                      <span><strong>{s.display_name}</strong><p>{s.short_description}</p></span>
                      <span className={`status-badge ${s.is_active ? 'recovered' : 'pending'}`}>{s.status}</span>
                    </button>
                  ))}
                </div>
              </div>
            </article>
          )}

          {step === 3 && (
            <article className="card wizard-card">
              <div className="card-head"><h3>What should VOXBULK help with?</h3></div>
              <div className="panel-body form-stack">
                <div>
                  <span>Business goals</span>
                  <p className="field-hint">Select the outcomes you want VOXBULK to support first.</p>
                  <div className="chip-grid">
                    {SIMPLE_GOALS.map((goal) => (
                      <button key={goal.key} type="button" className={`choice-chip ${goals.includes(goal.key) ? 'on' : ''}`} onClick={() => setGoals(toggleInList(goals, goal.key))}>
                        {goal.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <span>Preferred contact channels</span>
                  <p className="field-hint">Detailed workflow channel settings can be changed later.</p>
                  <div className="chip-grid">
                    {[
                      ['whatsapp', 'WhatsApp'],
                      ['ai_call', 'AI phone calls'],
                      ['both', 'Both'],
                    ].map(([key, label]) => (
                      <button key={key} type="button" className={`choice-chip ${channelChoice === key ? 'on' : ''}`} onClick={() => setChannelChoice(key)}>{label}</button>
                    ))}
                  </div>
                </div>
              </div>
            </article>
          )}

          {step === 4 && (
            <article className="card wizard-card">
              <div className="card-head"><h3>Review and finish</h3></div>
              <div className="panel-body wizard-review">
                <div className="review-grid">
                  <div><span>Category</span><strong>{categoryLabel(status?.category_slug || categorySlug)}</strong></div>
                  <div><span>Software</span><strong>{softwareOptions.find((s) => s.slug === (status?.booking_software_slug || softwareSlug))?.display_name || softwareSlug || '—'}</strong></div>
                  <div><span>Goals</span><strong>{goals.map((key) => SIMPLE_GOALS.find((g) => g.key === key)?.label || key).join(', ') || '—'}</strong></div>
                  <div><span>Channels</span><strong>{channelSummary()}</strong></div>
                </div>
                <div className="launch-panel"><h2>Ready to unlock the dashboard</h2><p>Advanced AI identity, compliance wording, timing rules and workflow-specific prompts can be edited later in settings.</p></div>
              </div>
            </article>
          )}

          <div className="wizard-footer-actions">
            <button className="btn btn-secondary" onClick={() => setStep(s => Math.max(1, s - 1))} disabled={step === 1 || saving} type="button">Back</button>
            {step === 1 ? <button className="btn btn-primary" onClick={saveCategory} disabled={saving} type="button">{saving ? 'Saving…' : 'Continue'}</button> : null}
            {step === 2 ? <button className="btn btn-primary" onClick={saveSoftware} disabled={saving} type="button">{saving ? 'Saving…' : 'Continue'}</button> : null}
            {step === 3 ? <button className="btn btn-primary" onClick={() => goals.length ? setStep(4) : window.alert('Select at least one goal')} disabled={saving} type="button">Review</button> : null}
            {step === 4 ? <button className="btn btn-primary" onClick={finish} disabled={saving} type="button">{saving ? 'Finishing…' : 'Finish setup'}</button> : null}
          </div>
        </section>
      </section>
    </>
  )
}

function SetupWizardPage() {
  const nav = useNavigate()
  const [step, setStep] = useState(1)
  const [saving, setSaving] = useState(false)
  const [membershipRole, setDisplayedMembershipRole] = useState(null)
  const [needsRoleFallback, setNeedsRoleFallback] = useState(false)

  const initial = readSetupProfile() || {}
  const prefs = normalizeWizardPrefs(initial)
  const [form, setForm] = useState({
    // Step 1: personal profile (role is chosen on sign-in; fallback here only if missing)
    fullName: initial.fullName || '',
    roleFallback: initial.roleFallback || 'dental',
    phone: initial.phone || '',

    // Step 2: clinic profile
    clinicName: initial.clinicName || '',
    branchName: initial.branchName || '',
    location: initial.location || '',

    // Step 3: business basics
    clinicType: initial.clinicType || 'general_dentistry',
    teamSize: initial.teamSize || '1-5',

    // Step 4: recovery preferences (multi-select; at least one of each)
    recoveryGoals: prefs.recoveryGoals,
    contactChannels: prefs.contactChannels,
  })

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const me = await apiFetch('/auth/me')
        if (cancelled) return
        setDisplayedMembershipRole(me?.role || null)
        setNeedsRoleFallback(!me?.role)
      } catch {
        if (!cancelled) setNeedsRoleFallback(true)
      }
    })()
    return () => { cancelled = true }
  }, [])

  const setField = (key, value) => {
    setForm(prev => ({ ...prev, [key]: value }))
  }

  const validateStep = () => {
    if (step === 1) {
      if (needsRoleFallback && !String(form.roleFallback || '').trim()) return 'Role is required'
      if (!form.fullName.trim()) return 'Full name is required'
      if (!form.phone.trim()) return 'Phone is required'
      return null
    }
    if (step === 2) {
      if (!form.clinicName.trim()) return 'Clinic name is required'
      if (!form.branchName.trim()) return 'Branch name is required'
      if (!form.location.trim()) return 'Location is required'
      return null
    }
    if (step === 4) {
      if (!form.recoveryGoals?.length) return 'Select at least one recovery goal'
      if (!form.contactChannels?.length) return 'Select at least one contact channel'
      return null
    }
    return null
  }

  const next = () => {
    const err = validateStep()
    if (err) {
      window.alert(err)
      return
    }
    writeSetupProfile(form)
    setStep(s => Math.min(5, s + 1))
  }

  const prev = () => setStep(s => Math.max(1, s - 1))

  const finish = async () => {
    const err = validateStep()
    if (err) {
      window.alert(err)
      return
    }
    setSaving(true)
    try {
      // Role should already be set on the public sign-in flow. Only persist here if missing (edge case).
      if (needsRoleFallback) {
        await apiFetch('/auth/me/role', { method: 'POST', body: JSON.stringify({ role: form.roleFallback }) })
        setDisplayedMembershipRole(form.roleFallback)
        setNeedsRoleFallback(false)
      }

      writeSetupProfile({ ...form, completedAt: new Date().toISOString() })
      await apiFetch('/auth/me/dashboard-setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile: { ...form, completedAt: new Date().toISOString() } }),
      })
      setSetupCompleteLocal()
      nav('/', { replace: true })
    } catch (e) {
      window.alert(e?.message || 'Could not complete setup')
    } finally {
      setSaving(false)
    }
  }

  return <>
    <PageHeader
      title="Finish setup"
      description="Complete your first-login profile so the dashboard can be tailored to your clinic."
      action={<span className="pill">Step {step} / 5</span>}
    />

    <section className="wizard-shell">
      <aside className="card wizard-sidebar">
        <div className="card-head"><h3>Setup progress</h3></div>
        <div className="wizard-steps">
          {wizardSteps.map(item => (
            <button
              key={item.id}
              className={`wizard-step ${step === item.id ? 'active' : ''} ${step > item.id ? 'done' : ''}`}
              onClick={() => setStep(item.id)}
              type="button"
            >
              <span className="wizard-step-index">{step > item.id ? '✓' : item.id}</span>
              <span><strong>{item.title}</strong><em>{item.note}</em></span>
            </button>
          ))}
        </div>
        <div className="wizard-progress">
          <div className="wizard-progress-bar"><span style={{ width: `${step * 20}%` }} /></div>
          <p>{step} of 5</p>
        </div>
      </aside>

      <section className="wizard-main">
        {step === 1 && (
          <article className="card wizard-card">
            <div className="card-head"><h3>Personal profile</h3></div>
            <div className="panel-body form-stack">
              {needsRoleFallback ? (
                <label>
                  <span>Role / title</span>
                  <select value={form.roleFallback} onChange={e => setField('roleFallback', e.target.value)}>
                    <option value="dental">Dental</option>
                    <option value="receptionist">Receptionist</option>
                    <option value="owner">Owner</option>
                    <option value="manager">Manager</option>
                  </select>
                </label>
              ) : (
                <div className="info-banner">Role on account: <strong>{membershipRole || '—'}</strong> (set at sign-up)</div>
              )}
              <label>
                <span>Full name</span>
                <input value={form.fullName} onChange={e => setField('fullName', e.target.value)} placeholder="e.g. Sarah Johnson" />
              </label>
              <label>
                <span>Phone</span>
                <input value={form.phone} onChange={e => setField('phone', e.target.value)} placeholder="+44…" />
              </label>
              <div className="info-banner">Completing setup saves to your account — you will not be asked again after logout.</div>
            </div>
          </article>
        )}

        {step === 2 && (
          <article className="card wizard-card">
            <div className="card-head"><h3>Clinic profile</h3></div>
            <div className="panel-body form-stack">
              <label>
                <span>Clinic name</span>
                <input value={form.clinicName} onChange={e => setField('clinicName', e.target.value)} placeholder="e.g. Northgate Dental" />
              </label>
              <label>
                <span>Branch name</span>
                <input value={form.branchName} onChange={e => setField('branchName', e.target.value)} placeholder="e.g. Chelsea" />
              </label>
              <label>
                <span>Location / address</span>
                <input value={form.location} onChange={e => setField('location', e.target.value)} placeholder="City or address" />
              </label>
            </div>
          </article>
        )}

        {step === 3 && (
          <article className="card wizard-card">
            <div className="card-head"><h3>Business basics</h3></div>
            <div className="panel-body form-stack">
              <label>
                <span>Clinic type</span>
                <select value={form.clinicType} onChange={e => setField('clinicType', e.target.value)}>
                  <option value="general_dentistry">General dentistry</option>
                  <option value="cosmetic">Cosmetic</option>
                  <option value="ortho">Orthodontics</option>
                  <option value="mixed">Mixed</option>
                </select>
              </label>
              <label>
                <span>Team size</span>
                <select value={form.teamSize} onChange={e => setField('teamSize', e.target.value)}>
                  <option value="1-5">1–5</option>
                  <option value="6-15">6–15</option>
                  <option value="16-50">16–50</option>
                  <option value="50+">50+</option>
                </select>
              </label>
            </div>
          </article>
        )}

        {step === 4 && (
          <article className="card wizard-card">
            <div className="card-head"><h3>Recovery preferences</h3></div>
            <div className="panel-body form-stack">
              <div>
                <span>Recovery goals</span>
                <p className="field-hint">Select one or more — we will prioritise all of them in your workspace.</p>
                <div className="chip-actions">
                  <button type="button" className="btn btn-secondary btn-compact" onClick={() => setField('recoveryGoals', GOAL_OPTIONS.map((g) => g.id))}>Select all</button>
                  <button type="button" className="btn btn-secondary btn-compact" onClick={() => setField('recoveryGoals', [])}>Clear</button>
                </div>
                <div className="chip-grid" role="group" aria-label="Recovery goals">
                  {GOAL_OPTIONS.map((g) => {
                    const on = form.recoveryGoals.includes(g.id)
                    return (
                      <button
                        key={g.id}
                        type="button"
                        className={`choice-chip ${on ? 'on' : ''}`}
                        aria-pressed={on}
                        onClick={() => setField('recoveryGoals', toggleInList(form.recoveryGoals, g.id))}
                      >
                        {g.label}
                      </button>
                    )
                  })}
                </div>
              </div>
              <div>
                <span>Contact channels</span>
                <p className="field-hint">Enable any combination — you can narrow this later in settings.</p>
                <div className="chip-actions">
                  <button type="button" className="btn btn-secondary btn-compact" onClick={() => setField('contactChannels', CHANNEL_OPTIONS.map((c) => c.id))}>Select all</button>
                  <button type="button" className="btn btn-secondary btn-compact" onClick={() => setField('contactChannels', [])}>Clear</button>
                </div>
                <div className="chip-grid" role="group" aria-label="Contact channels">
                  {CHANNEL_OPTIONS.map((c) => {
                    const on = form.contactChannels.includes(c.id)
                    return (
                      <button
                        key={c.id}
                        type="button"
                        className={`choice-chip ${on ? 'on' : ''}`}
                        aria-pressed={on}
                        onClick={() => setField('contactChannels', toggleInList(form.contactChannels, c.id))}
                      >
                        {c.label}
                      </button>
                    )
                  })}
                </div>
              </div>
            </div>
          </article>
        )}

        {step === 5 && (
          <article className="card wizard-card">
            <div className="card-head"><h3>Review & finish</h3></div>
            <div className="panel-body wizard-review">
              <div className="review-grid">
                <div><span>Name</span><strong>{form.fullName || '—'}</strong></div>
                <div><span>Role</span><strong>{needsRoleFallback ? form.roleFallback : (membershipRole || '—')}</strong></div>
                <div><span>Phone</span><strong>{form.phone || '—'}</strong></div>
                <div><span>Clinic</span><strong>{form.clinicName || '—'}</strong></div>
                <div><span>Branch</span><strong>{form.branchName || '—'}</strong></div>
                <div><span>Location</span><strong>{form.location || '—'}</strong></div>
                <div><span>Clinic type</span><strong>{form.clinicType}</strong></div>
                <div><span>Team size</span><strong>{form.teamSize}</strong></div>
                <div><span>Recovery goals</span><strong>{form.recoveryGoals.map(goalLabel).join(', ') || '—'}</strong></div>
                <div><span>Contact channels</span><strong>{form.contactChannels.map(channelLabel).join(', ') || '—'}</strong></div>
              </div>
              <div className="launch-panel">
                <h2>Ready to enter the dashboard</h2>
                <p>Finish setup to unlock the normal dashboard. Your role is already saved from sign-up unless you used the in-wizard fallback.</p>
              </div>
            </div>
          </article>
        )}

        <div className="wizard-footer-actions">
          <button className="btn btn-secondary" onClick={prev} disabled={step === 1} type="button">Back</button>
          {step < 5 ? (
            <button className="btn btn-primary" onClick={next} type="button">Continue</button>
          ) : (
            <button className="btn btn-primary" onClick={finish} disabled={saving} type="button">
              {saving ? 'Saving…' : 'Finish setup'}
            </button>
          )}
        </div>
      </section>
    </section>
  </>
}

function ReadOnlyCard({ label, value, wide }) { return <article className={`card form-card ${wide ? 'wide' : ''}`}><p className="field-label">{label}</p><p className="field-value">{value}</p></article> }
function EditableCard({ label, value, onChange, disabled }) { return <article className="card form-card"><label><span className="field-label">{label}</span><input value={value} onChange={e => onChange(e.target.value)} disabled={disabled} /></label></article> }

class DashboardRootErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { err: null }
  }
  static getDerivedStateFromError(err) {
    return { err }
  }
  render() {
    if (this.state.err) {
      const e = this.state.err
      return (
        <div style={{ padding: 24, maxWidth: 720, margin: '40px auto', fontFamily: 'Inter, sans-serif', color: '#1e293b' }}>
          <h1 style={{ fontSize: 18 }}>Dashboard UI error</h1>
          <p style={{ color: '#64748b', fontSize: 14 }}>{e?.message || String(e)}</p>
          <pre style={{ overflow: 'auto', background: '#f1f5f9', padding: 12, borderRadius: 8, fontSize: 12 }}>{e?.stack || ''}</pre>
        </div>
      )
    }
    return this.props.children
  }
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <DashboardRootErrorBoundary>
      <App />
    </DashboardRootErrorBoundary>
  </React.StrictMode>
)
