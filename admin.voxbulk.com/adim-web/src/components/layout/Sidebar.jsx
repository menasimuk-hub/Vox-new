import React, { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { filterSidebarNav } from '../../lib/adminPaths'
import { useAdminProfile } from '../../context/AdminProfileContext'

const GROUP_ICONS = {
  Dashboard: 'ti-dashboard',
  Organisations: 'ti-building',
  Onboarding: 'ti-clipboard-check',
  Operations: 'ti-activity',
  'AI Marketing': 'ti-speakerphone',
  Integrations: 'ti-plug',
  'Services API': 'ti-api',
  'Billing & Finance': 'ti-credit-card',
  Support: 'ti-lifebuoy',
  'AI / LLM Control': 'ti-brain',
  Compliance: 'ti-shield',
  Analytics: 'ti-chart-bar',
  'Team & roles': 'ti-users',
  'Platform Settings': 'ti-settings',
}

const GROUP_SECTION = {
  Dashboard: 'Main',
  Organisations: 'Main',
  Onboarding: 'Main',
  Operations: 'Main',
  'AI Marketing': 'Growth & finance',
  Integrations: 'Growth & finance',
  'Services API': 'Growth & finance',
  'Billing & Finance': 'Growth & finance',
  Support: 'Control',
  'AI / LLM Control': 'Control',
  Compliance: 'Control',
  Analytics: 'Control',
  'Team & roles': 'Control',
  'Platform Settings': 'Control',
}

const NAV = [
  [
    'Dashboard',
    [
      ['MRR', '/dashboard/mrr'],
      ['Total organisations', '/dashboard/total-organisations'],
      ['Trial conversions', '/dashboard/trial-conversions'],
      ['System health', '/dashboard/system-health'],
      ['LLM / call spend', '/dashboard/llm-call-spend'],
    ],
  ],
  [
    'Organisations',
    [
      ['All organisations', '/organisations'],
      ['Organisation profile', '/organisations/profile'],
      ['Categories', '/organisations/categories'],
    ],
  ],
  [
    'Onboarding',
    [
      ['New customer setup', '/onboarding/setup'],
      ['Pending signups', '/onboarding/pending-signups'],
      ['Dentally connection status', '/onboarding/dentally'],
      ['Number verification', '/onboarding/numbers'],
      ['Go-live checklist', '/onboarding/checklist'],
    ],
  ],
  [
    'Operations',
    [
      ['Call queue', '/operations/call-queue'],
      ['WhatsApp queue', '/operations/whatsapp-queue'],
      ['Failed jobs', '/operations/failed-jobs'],
      ['Manual retry', '/operations/manual-retry'],
      ['Recovery events', '/operations/recovery-events'],
    ],
  ],
  [
    'AI Marketing',
    [
      ['Lead sources', '/marketing/lead-sources'],
      ['Lead sales', '/marketing/lead-sales'],
      ['Promo offers', '/marketing/promo-offers'],
      ['Sales setup (AI + KB)', '/marketing/lead-sales/settings'],
      ['Offer templates', '/marketing/lead-sales/offer-templates'],
      ['Front page call leads', '/marketing/frontpage-call-leads'],
      ['Apollo leads', '/marketing/apollo'],
      ['Clay enrichment', '/marketing/clay'],
      ['Instantly campaigns', '/marketing/instantly'],
      ['Vapi sales calls', '/marketing/vapi'],
      ['Calendly bookings', '/marketing/calendly'],
      ['Ad funnel tracking', '/marketing/funnel'],
      ['Conversion attribution', '/marketing/attribution'],
    ],
  ],
  [
    'Integrations',
    [
      ['KPI overview', '/integrations/kpi'],
      ['Dentally', '/integrations/dentally'],
      ['Telnyx voice agent', '/integrations/telnyx'],
      ['Azure Speech', '/integrations/azure_speech'],
      ['OpenAI', '/integrations/openai'],
      ['DeepSeek', '/integrations/deepseek'],
      ['Groq', '/integrations/groq'],
      ['Deepgram', '/integrations/deepgram'],
      ['Cartesia', '/integrations/cartesia'],
      ['ElevenLabs', '/integrations/elevenlabs'],
      ['Vapi', '/integrations/vapi'],
      ['GoCardless', '/integrations/gocardless'],
      ['Zoom', '/integrations/zoom'],
      ['Webhooks', '/integrations/webhooks'],
      ['Social login', '/integrations/social-login'],
    ],
  ],
  [
    'Services API',
    [
      ['Dentally', '/services-api/dentally'],
      ['CareStack', '/services-api/carestack'],
      ['Pabau', '/services-api/pabau'],
      ['Cliniko', '/services-api/cliniko'],
      ['Optix', '/services-api/optix'],
      ['Ocuco', '/services-api/ocuco'],
      ['Telnyx', '/services-api/telnyx'],
    ],
  ],
  [
    'Billing & Finance',
    [
      ['Mandates', '/billing/mandates'],
      ['Subscriptions', '/billing/subscriptions'],
      ['Invoices', '/billing/invoices'],
      ['Failed payments', '/billing/failed-payments'],
      ['Revenue reports', '/billing/reports'],
      ['Calls cost', '/billing/calls-cost'],
      ['Products hub', '/billing/products'],
      ['Services & pricing', '/billing/services-pricing'],
      ['Service orders (cash)', '/billing/service-orders'],
    ],
  ],
  [
    'Support',
    [
      ['Support inbox', '/support/inbox'],
      ['Open tickets', '/support/tickets'],
      ['Customer notes', '/support/notes'],
      ['Escalations', '/support/escalations'],
      ['Help centre content', '/support/help'],
      ['FAQ management', '/support/faq'],
      ['SLA tracking', '/support/sla'],
    ],
  ],
  [
    'AI / LLM Control',
    [
      ['Call scripts', '/ai/scripts'],
      ['Agents', '/ai/agents'],
      ['Vox Sales demo', '/ai/agent-demo'],
      ['Prompt templates', '/ai/prompts'],
      ['Retry logic', '/ai/retry'],
      ['Voicemail logic', '/ai/voicemail'],
      ['Cost controls', '/ai/cost'],
    ],
  ],
  [
    'Compliance',
    [
      ['Audit logs', '/compliance/audit'],
      ['Consent / opt-out', '/compliance/consent'],
      ['Recording disclosure', '/compliance/recording'],
      ['OFCOM rules', '/compliance/ofcom'],
      ['GDPR logs', '/compliance/gdpr'],
    ],
  ],
  [
    'Analytics',
    [
      ['Platform KPIs', '/analytics/kpis'],
      ['Org benchmarks', '/analytics/benchmarks'],
      ['Recovery performance', '/analytics/recovery'],
      ['Cost vs revenue', '/analytics/cost-revenue'],
    ],
  ],
  [
    'Team & roles',
    [
      ['Platform admins (list)', '/platform/users'],
      ['Add platform admin', '/platform/users/new'],
      ['Permissions', '/team/permissions'],
      ['Activity logs', '/team/logs'],
    ],
  ],
  [
    'Platform Settings',
    [
      ['Global config', '/settings/global'],
      ['Feature flags', '/settings/flags'],
      ['Email / notification settings', '/settings/email'],
      ['Legal pages', '/settings/legal'],
      ['API keys / secrets', '/settings/api-keys'],
    ],
  ],
]

function findGroupForPath(pathname, tree) {
  for (const [group, items] of tree) {
    if (items.some(([, path]) => path === pathname)) return group
  }
  return null
}

function buildInitialOpen(pathname) {
  const activeGroup = findGroupForPath(pathname, NAV) || 'Dashboard'
  return Object.fromEntries(NAV.map(([name]) => [name, name === activeGroup]))
}

export default function Sidebar({ collapsed, mobileOpen, onToggleCollapse, onNavigate }) {
  const location = useLocation()
  const navigate = useNavigate()
  const { adminRole } = useAdminProfile()

  const nav = useMemo(() => filterSidebarNav(adminRole, NAV), [adminRole])

  const [open, setOpen] = useState(() => buildInitialOpen(location.pathname))

  useEffect(() => {
    const activeGroup = findGroupForPath(location.pathname, nav)
    if (!activeGroup) return
    setOpen((prev) => ({ ...prev, [activeGroup]: true }))
  }, [location.pathname, nav])

  const toggleGroup = (group) => {
    setOpen((prev) => {
      const willOpen = !prev[group]
      if (!willOpen) return { ...prev, [group]: false }
      const next = Object.fromEntries(NAV.map(([name]) => [name, name === group]))
      return next
    })
  }

  const handleNavigate = (path) => {
    if (location.pathname !== path) navigate(path)
    onNavigate?.()
  }

  let lastSection = ''

  return (
    <aside className={`sb ${collapsed ? 'collapsed' : ''} ${mobileOpen ? 'mobile-open' : ''}`} id='sb'>
      <div className='sb-logo'>
        <button
          type='button'
          className='sb-logo-btn'
          onClick={collapsed ? onToggleCollapse : undefined}
          aria-label={collapsed ? 'Expand sidebar' : 'VOXBULK Admin'}
          title={collapsed ? 'Show menu' : 'VOXBULK Admin'}
        >
          <img src='/logo-dark.svg' alt='VOXBULK' className='sb-logo-img logo-light sb-logo-full' />
          <img src='/logo-light.svg' alt='VOXBULK' className='sb-logo-img logo-dark sb-logo-full' />
          <span className='sb-logo-icon' aria-hidden={!collapsed}>
            <img src='/favicon.png' alt='' />
          </span>
        </button>
        {!collapsed ? (
          <button type='button' className='sb-toggle' onClick={onToggleCollapse} aria-label='Collapse sidebar'>
            <i className='ti ti-chevrons-left' />
          </button>
        ) : null}
      </div>

      <div className='sb-nav'>
        {nav.map(([group, items]) => {
          const isGroupActive = items.some(([, path]) => location.pathname === path)
          const icon = GROUP_ICONS[group] || 'ti-circle-dot'
          const section = GROUP_SECTION[group] || ''
          const showSection = section && section !== lastSection
          if (showSection) lastSection = section

          return (
            <div className='nav-group' key={group}>
              {showSection ? <div className='nav-sec'>{section}</div> : null}

              <button
                type='button'
                className={`ni ni-group ${open[group] ? 'open' : ''} ${isGroupActive ? 'has-active' : ''}`}
                onClick={() => toggleGroup(group)}
                aria-expanded={Boolean(open[group])}
              >
                <i className={`ti ${icon} nav-ic`} />
                <span className='ni-label'>{group}</span>
                <i className={`ti ti-chevron-down nav-chev ${open[group] ? 'open' : ''}`} />
                <span className='ni-tip'>{group}</span>
              </button>

              {open[group] ? (
                <div className='nav-children'>
                  {items.map(([label, path]) => {
                    const active = location.pathname === path
                    return (
                      <button
                        type='button'
                        key={`${group}-${path}-${label}`}
                        className={`ni ni-sub ${active ? 'on' : ''}`}
                        onClick={() => handleNavigate(path)}
                      >
                        <span className='ni-sub-dot' aria-hidden='true' />
                        <span className='ni-label'>{label}</span>
                        <span className='ni-tip'>{label}</span>
                      </button>
                    )
                  })}
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
    </aside>
  )
}
