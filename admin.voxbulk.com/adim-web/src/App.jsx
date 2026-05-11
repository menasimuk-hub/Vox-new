import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'
import Dashboard from './pages/Dashboard'
import Organisations from './pages/Organisations'
import OrganisationProfile from './pages/OrganisationProfile'
import Categories from './pages/Categories'
import OperationsQueue from './pages/OperationsQueue'
import Billing from './pages/Billing'
import PackagesPricing from './pages/PackagesPricing'
import Integrations from './pages/Integrations'
import ServicesAPI from './pages/ServicesAPI'
import SupportSLA from './pages/SupportSLA'
import SupportTickets from './pages/SupportTickets'
import SupportTicketDetail from './pages/SupportTicketDetail'
import Permissions from './pages/Permissions'
import GenericPage from './pages/GenericPage'
import EmailSettings from './pages/EmailSettings'
import FAQManagement from './pages/FAQManagement'
import HelpCentreContent from './pages/HelpCentreContent'
import PendingSignups from './pages/PendingSignups'
import AdminUsers from './pages/AdminUsers'
import AdminUserCreate from './pages/AdminUserCreate'
import AdminUserEdit from './pages/AdminUserEdit'
import Agents from './pages/Agents'
import AgentDemo from './pages/AgentDemo'
import { defaultAdminHome } from './lib/adminPaths'
import { useAdminProfile } from './context/AdminProfileContext'

const G = (title) => <GenericPage title={title} />

function HomeRedirect() {
  const { loading, adminRole } = useAdminProfile()
  if (loading) {
    return (
      <div className='card' style={{ maxWidth: 480, margin: '48px auto' }}>
        <div className='cardBody muted'>Loading workspace…</div>
      </div>
    )
  }
  return <Navigate to={defaultAdminHome(adminRole)} replace />
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<HomeRedirect />} />

        <Route path='/dashboard' element={<Navigate to='/dashboard/mrr' replace />} />
        <Route path='/dashboard/mrr' element={<Dashboard title='MRR' />} />
        <Route path='/dashboard/total-organisations' element={<Dashboard title='Total organisations' />} />
        <Route path='/dashboard/trial-conversions' element={<Dashboard title='Trial conversions' />} />
        <Route path='/dashboard/system-health' element={<Dashboard title='System health' />} />
        <Route path='/dashboard/llm-call-spend' element={<Dashboard title='LLM / call spend' />} />

        <Route path='/organisations' element={<Organisations />} />
        <Route path='/organisations/profile' element={<OrganisationProfile />} />
        <Route path='/organisations/categories' element={<Categories />} />

        <Route path='/onboarding/setup' element={G('New customer setup')} />
        <Route path='/onboarding/pending-signups' element={<PendingSignups />} />
        <Route path='/onboarding/dentally' element={G('Dentally connection status')} />
        <Route path='/onboarding/numbers' element={G('Number verification')} />
        <Route path='/onboarding/checklist' element={G('Go-live checklist')} />

        <Route path='/operations/call-queue' element={<OperationsQueue title='Call queue' />} />
        <Route path='/operations/whatsapp-queue' element={<OperationsQueue title='WhatsApp queue' />} />
        <Route path='/operations/failed-jobs' element={<OperationsQueue title='Failed jobs' />} />
        <Route path='/operations/manual-retry' element={<OperationsQueue title='Manual retry' />} />
        <Route path='/operations/recovery-events' element={<OperationsQueue title='Recovery events' />} />

        <Route path='/marketing/lead-sources' element={G('Lead sources')} />
        <Route path='/marketing/apollo' element={G('Apollo leads')} />
        <Route path='/marketing/clay' element={G('Clay enrichment')} />
        <Route path='/marketing/instantly' element={G('Instantly campaigns')} />
        <Route path='/marketing/vapi' element={G('Vapi sales calls')} />
        <Route path='/marketing/calendly' element={G('Calendly bookings')} />
        <Route path='/marketing/funnel' element={G('Ad funnel tracking')} />
        <Route path='/marketing/attribution' element={G('Conversion attribution')} />

        <Route path='/integrations/dentally' element={<Integrations />} />
        <Route path='/integrations/telnyx' element={<Integrations />} />
        <Route path='/integrations/azure_speech' element={<Integrations />} />
        <Route path='/integrations/openai' element={<Integrations />} />
        <Route path='/integrations/deepseek' element={<Integrations />} />
        <Route path='/integrations/elevenlabs' element={<Integrations />} />
        <Route path='/integrations/twilio' element={<Integrations />} />
        <Route path='/integrations/vapi' element={<Integrations />} />
        <Route path='/integrations/gocardless' element={<Integrations />} />
        <Route path='/integrations/webhooks' element={<Integrations />} />
        <Route path='/integrations/social-login' element={<Integrations />} />
        <Route path='/services-api' element={<ServicesAPI />} />
        <Route path='/services-api/dentally' element={<ServicesAPI />} />
        <Route path='/services-api/carestack' element={<ServicesAPI />} />
        <Route path='/services-api/pabau' element={<ServicesAPI />} />
        <Route path='/services-api/cliniko' element={<ServicesAPI />} />
        <Route path='/services-api/optix' element={<ServicesAPI />} />
        <Route path='/services-api/ocuco' element={<ServicesAPI />} />
        <Route path='/services-api/telnyx' element={<ServicesAPI />} />

        <Route path='/billing/mandates' element={<Billing />} />
        <Route path='/billing/subscriptions' element={<Billing />} />
        <Route path='/billing/invoices' element={<Billing />} />
        <Route path='/billing/failed-payments' element={<Billing />} />
        <Route path='/billing/reports' element={<Billing />} />
        <Route path='/billing/packages' element={<PackagesPricing />} />

        <Route path='/support/inbox' element={<SupportTickets />} />
        <Route path='/support/tickets' element={<SupportTickets />} />
        <Route path='/support/tickets/:ticketId' element={<SupportTicketDetail />} />
        <Route path='/support/notes' element={G('Customer notes')} />
        <Route path='/support/escalations' element={G('Escalations')} />
        <Route path='/support/help' element={<HelpCentreContent />} />
        <Route path='/support/faq' element={<FAQManagement />} />
        <Route path='/support/sla' element={<SupportSLA />} />

        <Route path='/ai/scripts' element={G('Call scripts')} />
        <Route path='/ai/agents' element={<Agents />} />
        <Route path='/ai/agents/new' element={<Agents />} />
        <Route path='/ai/agents/:agentId/edit' element={<Agents />} />
        <Route path='/ai/agent-demo' element={<AgentDemo />} />
        <Route path='/ai/prompts' element={G('Prompt templates')} />
        <Route path='/ai/retry' element={G('Retry logic')} />
        <Route path='/ai/voicemail' element={G('Voicemail logic')} />
        <Route path='/ai/cost' element={G('Cost controls')} />

        <Route path='/compliance/audit' element={G('Audit logs')} />
        <Route path='/compliance/consent' element={G('Consent / opt-out')} />
        <Route path='/compliance/recording' element={G('Recording disclosure')} />
        <Route path='/compliance/ofcom' element={G('OFCOM rules')} />
        <Route path='/compliance/gdpr' element={G('GDPR logs')} />

        <Route path='/analytics/kpis' element={G('Platform KPIs')} />
        <Route path='/analytics/benchmarks' element={G('Org benchmarks')} />
        <Route path='/analytics/recovery' element={G('Recovery performance')} />
        <Route path='/analytics/cost-revenue' element={G('Cost vs revenue')} />

        <Route path='/team/users' element={<Navigate to='/admin/users' replace />} />
        <Route path='/admin/users' element={<AdminUsers />} />
        <Route path='/admin/users/new' element={<AdminUserCreate />} />
        <Route path='/admin/users/:id/edit' element={<AdminUserEdit />} />
        <Route path='/admin/admin-users' element={<Navigate to='/admin/users/new' replace />} />
        <Route path='/team/permissions' element={<Permissions />} />
        <Route path='/team/logs' element={G('Activity logs')} />

        <Route path='/settings/global' element={G('Global config')} />
        <Route path='/settings/flags' element={G('Feature flags')} />
        <Route path='/settings/email' element={<EmailSettings />} />
        <Route path='/settings/api-keys' element={G('API keys / secrets')} />

        <Route path='*' element={<HomeRedirect />} />
      </Route>
    </Routes>
  )
}