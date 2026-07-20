import React, { useEffect, useMemo, useState } from 'react'

import { useLocation, useNavigate } from 'react-router-dom'



import { filterSidebarNav } from '../../lib/adminPaths'

import { brandAssets } from '../../lib/brand'

import { useAdminProfile } from '../../context/AdminProfileContext'



const GROUP_ICONS = {

  Dashboard: 'ti-dashboard',

  Organisations: 'ti-building',

  Onboarding: 'ti-clipboard-check',

  Operations: 'ti-activity',

  'Customer feedback': 'ti-message-circle',

  Campaigns: 'ti-ad-2',

  'WA Survey': 'ti-brand-whatsapp',

  'AI Interview': 'ti-phone-call',

  'AI Marketing': 'ti-speakerphone',

  Integrations: 'ti-plug',

  Partners: 'ti-heart-handshake',

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

  'Customer feedback': 'Products',

  Campaigns: 'Products',

  'WA Survey': 'Products',

  'AI Interview': 'Products',

  'AI Marketing': 'Growth & finance',

  Integrations: 'Growth & finance',

  Partners: 'Growth & finance',

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

    [['Overview', '/dashboard']],

  ],

  [

    'Organisations',

    [

      ['All organisations', '/organisations'],

      ['All users', '/organisations/all-users'],

      ['GB users', '/organisations/zone/gb'],

      ['USA users', '/organisations/zone/us'],

      ['Canada users', '/organisations/zone/ca'],

      ['Australia users', '/organisations/zone/au'],

      ['Organisation profile', '/organisations/profile'],

      ['Categories', '/organisations/categories'],

    ],

  ],

  [

    'Onboarding',

    [

      ['Add customer', '/onboarding/add-customer'],

      ['Dashboard modules', '/onboarding/services'],

    ],

  ],

  [

    'Customer feedback',

    [

      ['Overview', '/customer-feedback/overview'],

      ['Packages & pricing', '/customer-feedback/packages'],

      ['Subscriptions', '/customer-feedback/subscriptions'],

      ['Locations', '/customer-feedback/locations'],

      ['Results', '/customer-feedback/results'],

    ],

  ],

  [

    'Campaigns',

    [

      ['Overview', '/campaigns'],

      ['Template library', '/campaigns/templates'],

    ],

  ],

  [

    'WA Survey',

    [

      ['Running surveys', '/operations/running-surveys'],

      ['WA Survey insights', '/operations/wa-survey-insights'],

    ],

  ],

  [

    'Appointment Manager',

    [

      ['Running appointments', '/operations/running-appointments'],

    ],

  ],

  [

    'AI Interview',

    [

      ['Running interviews', '/operations/running-interviews'],

      ['Script moderation', '/operations/script-moderation'],

      ['Call queue', '/operations/call-queue'],

      ['WhatsApp queue', '/operations/whatsapp-queue'],

    ],

  ],

  [

    'Operations',

    [

      ['Custom Org', '/operations/custom-org'],

      ['Failed jobs', '/operations/failed-jobs'],

      ['Manual retry', '/operations/manual-retry'],

      ['Recovery events', '/operations/recovery-events'],

    ],

  ],

  [

    'AI Marketing',

    [

      ['AI Team', '/marketing/ai-team'],

      ['Lead sources', '/marketing/lead-sources'],

      ['Lead sales', '/marketing/lead-sales'],

      ['Salesmen', '/marketing/salesmen'],

      ['Promo offers', '/marketing/promo-offers'],

      ['Sales setup (AI + KB)', '/marketing/lead-sales/settings'],

      ['Offer templates', '/marketing/lead-sales/offer-templates'],

      ['Front page call leads', '/marketing/frontpage-call-leads'],

      ['News & Blog', '/marketing/news-blog'],

      ['SEO Control', '/marketing/seo-control'],

    ],

  ],

  [

    'Integrations',

    [

      ['KPI overview', '/integrations/kpi'],

      ['Dentally', '/integrations/dentally'],

      ['Telnyx voice agent', '/integrations/telnyx'],
      ['Meta WhatsApp', '/integrations/meta_whatsapp'],

      ['Azure Speech', '/integrations/azure_speech'],

      ['OpenAI', '/integrations/openai'],

      ['DeepSeek', '/integrations/deepseek'],

      ['Groq', '/integrations/groq'],

      ['DeepInfra', '/integrations/deepinfra'],

      ['Deepgram', '/integrations/deepgram'],

      ['Cartesia', '/integrations/cartesia'],

      ['ElevenLabs', '/integrations/elevenlabs'],

      ['Vapi', '/integrations/vapi'],

      ['GoCardless', '/integrations/gocardless'],

      ['Stripe', '/integrations/stripe'],

      ['Airwallex', '/integrations/airwallex'],

      ['Calendly', '/integrations/calendly'],

      ['Cal.com', '/integrations/cal_com'],

      ['Google Calendar', '/integrations/google_calendar'],

      ['Google Search Console', '/integrations/google_search_console'],

      ['Microsoft 365 Calendar', '/integrations/microsoft_calendar'],

      ['HubSpot', '/integrations/hubspot'],

      ['Pipedrive', '/integrations/pipedrive'],

      ['Zoho CRM', '/integrations/zoho_crm'],

      ['Zoho Bookings', '/integrations/zoho_bookings'],

      ['Webhooks', '/integrations/webhooks'],

      ['Social login', '/integrations/social-login'],

    ],

  ],

  [

    'Partners',

    [

      ['Provider Dashboard', '/partners/dashboard'],

      ['Zoho Marketplace', '/partners/zoho'],

      ['Breezy HR', '/partners/breezy'],

      ['Workable', '/partners/workable'],

      ['Bullhorn Marketplace', '/partners/bullhorn'],

      ['Zapier', '/partners/zapier'],

    ],

  ],

  [

    'Billing & Finance',

    [

      ['Mandates', '/billing/mandates'],

      ['Subscriptions', '/billing/subscriptions'],

      ['Invoices', '/billing/invoices'],

      ['Failed payments', '/billing/failed-payments'],

      ['Refunds', '/billing/refunds'],

      ['Payment events', '/billing/payment-events'],

      ['Wallet ledger', '/billing/wallet-ledger'],

      ['Tax & VAT', '/billing/tax'],

      ['Billing exceptions', '/billing/exceptions'],

      ['Calls cost', '/billing/calls-cost'],

      ['Products hub', '/billing/products'],

      ['Core platform pricing', '/pricing/plans'],

      ['Service orders (cash)', '/billing/service-orders'],

    ],

  ],

  [

    'Support',

    [

      ['Support inbox', '/support/inbox'],

      ['Open tickets', '/support/tickets'],

      ['Help centre content', '/support/help'],

      ['FAQ management', '/support/faq'],

      ['SLA tracking', '/support/sla'],

    ],

  ],

  [

    'AI / LLM Control',

    [

      ['WA Templates', '/ai/wa-templates'],

      ['Connection Profiles', '/ai/connection-profiles'],

      ['Call scripts', '/ai/scripts'],

      ['Agents', '/ai/agents'],

      ['Vox Sales demo', '/ai/agent-demo'],

    ],

  ],

  [

    'Compliance',

    [

      ['Audit logs', '/compliance/audit'],

      ['Account deletions', '/compliance/account-deletions'],

      ['Consent / opt-out', '/compliance/consent'],

      ['STOP opt-out list', '/compliance/opt-outs'],

      ['Recording disclosure', '/compliance/recording'],

      ['OFCOM rules', '/compliance/ofcom'],

      ['GDPR logs', '/compliance/gdpr'],

    ],

  ],

  [

    'Analytics',

    [

      ['Platform KPIs', '/analytics/kpis'],

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

      ['Email / notification settings', '/settings/email'],

      ['Meeting room', '/settings/meeting-room'],

      ['Legal pages', '/settings/legal'],

    ],

  ],

]



function findGroupForPath(pathname, tree) {

  for (const [group, items] of tree) {

    if (items.some(([, path]) => path === pathname || (pathname.startsWith(`${path}/`) && path !== '/'))) {

      return group

    }

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

          <img src={brandAssets.logoBlack} alt='VOXBULK' className='sb-logo-img logo-light sb-logo-full' />

          <img src={brandAssets.logoWhite} alt='VOXBULK' className='sb-logo-img logo-dark sb-logo-full' />

          <span className='sb-logo-icon' aria-hidden={!collapsed}>

            <img src={brandAssets.iconBlack} alt='' className='icon-light' />

            <img src={brandAssets.iconWhite} alt='' className='icon-dark' />

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

          const isGroupActive = items.some(([, path]) => location.pathname === path || location.pathname.startsWith(`${path}/`))

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

                    const active = location.pathname === path || (path !== '/' && location.pathname.startsWith(`${path}/`))

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


