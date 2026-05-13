import React, { useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  Building2,
  ClipboardCheck,
  Activity,
  Megaphone,
  Plug,
  CreditCard,
  LifeBuoy,
  BrainCircuit,
  Shield,
  BarChart3,
  Users,
  Settings,
  ChevronRight,
} from 'lucide-react'

import { filterSidebarNav } from '../../lib/adminPaths'
import { useAdminProfile } from '../../context/AdminProfileContext'

const NAV = [
  [
    'Dashboard',
    LayoutDashboard,
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
    Building2,
    [
      ['All organisations', '/organisations'],
      ['Organisation profile', '/organisations/profile'],
      ['Categories', '/organisations/categories'],
    ],
  ],
  [
    'Onboarding',
    ClipboardCheck,
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
    Activity,
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
    Megaphone,
    [
      ['Lead sources', '/marketing/lead-sources'],
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
    Plug,
    [
      ['Dentally', '/integrations/dentally'],
      ['Telnyx voice agent', '/integrations/telnyx'],
      ['Azure Speech', '/integrations/azure_speech'],
      ['OpenAI', '/integrations/openai'],
      ['DeepSeek', '/integrations/deepseek'],
      ['Groq', '/integrations/groq'],
      ['Deepgram', '/integrations/deepgram'],
      ['Cartesia', '/integrations/cartesia'],
      ['ElevenLabs', '/integrations/elevenlabs'],
      ['Twilio legacy', '/integrations/twilio'],
      ['Vapi', '/integrations/vapi'],
      ['GoCardless', '/integrations/gocardless'],
      ['Webhooks', '/integrations/webhooks'],
      ['Social login', '/integrations/social-login'],
    ],
  ],
  [
    'Services API',
    Plug,
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
    CreditCard,
    [
      ['Mandates', '/billing/mandates'],
      ['Subscriptions', '/billing/subscriptions'],
      ['Invoices', '/billing/invoices'],
      ['Failed payments', '/billing/failed-payments'],
      ['Revenue reports', '/billing/reports'],
      ['Packages & Pricing', '/billing/packages'],
    ],
  ],
  [
    'Support',
    LifeBuoy,
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
    BrainCircuit,
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
    Shield,
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
    BarChart3,
    [
      ['Platform KPIs', '/analytics/kpis'],
      ['Org benchmarks', '/analytics/benchmarks'],
      ['Recovery performance', '/analytics/recovery'],
      ['Cost vs revenue', '/analytics/cost-revenue'],
    ],
  ],
    [
    'Team & roles',
    Users,
    [
      ['Platform admins (list)', '/admin/users'],
      ['Add platform admin', '/admin/users/new'],
      ['Permissions', '/team/permissions'],
      ['Activity logs', '/team/logs'],
    ],
  ],
  [
    'Platform Settings',
    Settings,
    [
      ['Global config', '/settings/global'],
      ['Feature flags', '/settings/flags'],
      ['Email / notification settings', '/settings/email'],
      ['API keys / secrets', '/settings/api-keys'],
    ],
  ],
]

export default function Sidebar() {
  const location = useLocation()
  const navigate = useNavigate()
  const { adminRole } = useAdminProfile()

  const nav = useMemo(() => filterSidebarNav(adminRole, NAV), [adminRole])

  const [open, setOpen] = useState(
    Object.fromEntries(
      NAV.map(([name]) => [
        name,
        ['Dashboard', 'Organisations', 'Integrations', 'Billing & Finance'].includes(name),
      ])
    )
  )

  const handleNavigate = (path) => {
    if (location.pathname !== path) navigate(path)
  }

  return (
    <aside className="sidebar">
      <div className="brandBar">
  <div className="brand brandImageOnly">
    <img
      src="/retoverlogosvg.svg"
      alt="VOXBULK"
      className="brandLogoImage"
    />
  </div>
</div>

      <div className="navWrap">
        {nav.map(([group, Icon, items], idx) => {
          const isGroupActive = items.some(([, path]) => location.pathname === path)

          return (
            <div className="navGroup" key={group}>
              {idx === 0 && <div className="groupTitle">Main</div>}
              {idx === 4 && <div className="groupTitle">Growth & Finance</div>}
              {idx === 7 && <div className="groupTitle">Control</div>}

              <button
                className={`navButton ${open[group] ? 'open' : ''} ${isGroupActive ? 'group-active' : ''}`}
                onClick={() => setOpen((s) => ({ ...s, [group]: !s[group] }))}
              >
                <Icon size={17} />
                <span>{group}</span>
                <ChevronRight
                  size={15}
                  className="chev"
                  style={{ transform: open[group] ? 'rotate(90deg)' : 'none' }}
                />
              </button>

              {open[group] &&
                items.map(([label, path]) => (
                  <button
                    key={`${group}-${path}-${label}`}
                    onClick={() => handleNavigate(path)}
                    className={`subButton ${location.pathname === path ? 'active' : ''}`}
                  >
                    {label}
                  </button>
                ))}
            </div>
          )
        })}
      </div>
    </aside>
  )
}