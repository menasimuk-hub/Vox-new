import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'
import Dashboard from './pages/Dashboard'
import Organisations from './pages/Organisations'
import ZoneOrganisations from './pages/ZoneOrganisations'
import OrganisationDetail from './pages/OrganisationDetail'
import OrgControlCenter from './pages/OrgControlCenter'
import OrganisationProfile from './pages/OrganisationProfile'
import Categories from './pages/Categories'
import OperationsQueue from './pages/OperationsQueue'
import Billing from './pages/Billing'
import BillingExceptions from './pages/BillingExceptions'
import InvoicesAdmin from './pages/InvoicesAdmin'
import PaymentEventsAdmin from './pages/PaymentEventsAdmin'
import RefundsAdmin from './pages/RefundsAdmin'
import TaxAdmin from './pages/TaxAdmin'
import WalletLedgerAdmin from './pages/WalletLedgerAdmin'
import ProductsHub from './pages/ProductsHub'
import ProductPlanEdit from './pages/ProductPlanEdit'
import CallsCost from './pages/CallsCost'
import Integrations from './pages/Integrations'
import ServicesAPI from './pages/ServicesAPI'
import SupportSLA from './pages/SupportSLA'
import SupportTickets from './pages/SupportTickets'
import SupportTicketDetail from './pages/SupportTicketDetail'
import Permissions from './pages/Permissions'
import GenericPage from './pages/GenericPage'
import ComplianceSettings from './pages/ComplianceSettings'
import ComplianceAudit from './pages/ComplianceAudit'
import AccountDeletionsAdmin from './pages/AccountDeletionsAdmin'
import EmailSettings from './pages/EmailSettings'
import WaSurveySystemTemplates from './pages/WaSurveySystemTemplates'
import WaInterviewTemplates from './pages/WaInterviewTemplates'
import WaSurveyTypes from './pages/WaSurveyTypes'
import WaSurveyTypeEdit from './pages/WaSurveyTypeEdit'
import WaSurveyIndustries from './pages/WaSurveyIndustries'
import WaSurveyIndustryEdit from './pages/WaSurveyIndustryEdit'
import WaSurveyFlowSimulator from './pages/WaSurveyFlowSimulator'
import WaSurveyFlows from './pages/WaSurveyFlows'
import WaSurveyInsights from './pages/WaSurveyInsights'
import EmailTemplateEdit from './pages/EmailTemplateEdit'
import WhatsAppTemplateEdit from './pages/WhatsAppTemplateEdit'
import SmsTemplateEdit from './pages/SmsTemplateEdit'
import FAQManagement from './pages/FAQManagement'
import LegalPages from './pages/LegalPages'
import LegalPageEdit from './pages/LegalPageEdit'
import HelpCentreContent from './pages/HelpCentreContent'
import OnboardingServices from './pages/OnboardingServices'
import OnboardingAddCustomer from './pages/OnboardingAddCustomer'
import AdminUsers from './pages/AdminUsers'
import AdminUserCreate from './pages/AdminUserCreate'
import AdminUserEdit from './pages/AdminUserEdit'
import Agents from './pages/Agents'
import AgentDemo from './pages/AgentDemo'
import FrontpageCallLeads from './pages/FrontpageCallLeads'
import LeadSources from './pages/LeadSources'
import LeadSales from './pages/LeadSales'
import LeadSalesEdit from './pages/LeadSalesEdit'
import LeadSalesSettings from './pages/LeadSalesSettings'
import SalesOfferTemplates from './pages/SalesOfferTemplates'
import PromoOffers from './pages/PromoOffers'
import PromoOfferCreate from './pages/PromoOfferCreate'
import AiTeam from './pages/AiTeam'
import PricingShell from './pages/pricing/PricingShell'
import PricingPlans from './pages/pricing/PricingPlans'
import PricingConnectionFee from './pages/pricing/PricingConnectionFee'
import PricingServices from './pages/pricing/PricingServices'
import PricingTopups from './pages/pricing/PricingTopups'
import PricingPlanPrices from './pages/pricing/PricingPlanPrices'
import PricingCurrencyRates from './pages/pricing/PricingCurrencyRates'
import PricingInvoiceSettings from './pages/pricing/PricingInvoiceSettings'
import PricingEstimator from './pages/pricing/PricingEstimator'
import PricingCustomOrg from './pages/pricing/PricingCustomOrg'
import ServiceOrdersAdmin from './pages/ServiceOrdersAdmin'
import RunningSurveys from './pages/RunningSurveys'
import RunningInterviews from './pages/RunningInterviews'
import ScriptModeration from './pages/ScriptModeration'
import CustomerFeedbackHub from './pages/customer-feedback/CustomerFeedbackHub'
import FeedbackIndustriesList from './pages/customer-feedback/FeedbackIndustriesList'
import FeedbackIndustryEdit from './pages/customer-feedback/FeedbackIndustryEdit'
import FeedbackPackagesPricing from './pages/customer-feedback/FeedbackPackagesPricing'
import FeedbackSurveyTypeEdit from './pages/customer-feedback/FeedbackSurveyTypeEdit'
import CampaignsHub from './pages/campaigns/CampaignsHub'
import CampaignTemplates from './pages/campaigns/CampaignTemplates'
import PlatformKpis from './pages/analytics/PlatformKpis'
import CostRevenue from './pages/analytics/CostRevenue'
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

        <Route path='/dashboard' element={<Dashboard />} />
        <Route path='/dashboard/mrr' element={<Navigate to='/dashboard' replace />} />
        <Route path='/dashboard/total-organisations' element={<Navigate to='/dashboard' replace />} />
        <Route path='/dashboard/trial-conversions' element={<Navigate to='/dashboard' replace />} />
        <Route path='/dashboard/system-health' element={<Navigate to='/dashboard' replace />} />
        <Route path='/dashboard/llm-call-spend' element={<Navigate to='/dashboard' replace />} />

        <Route path='/organisations' element={<Organisations />} />
        <Route path='/organisations/all-users' element={<OrgControlCenter />} />
        <Route path='/organisations/profile' element={<OrganisationProfile />} />
        <Route path='/organisations/categories' element={<Categories />} />
        <Route path='/organisations/zone/:zone' element={<ZoneOrganisations />} />
        <Route path='/organisations/:orgId' element={<OrganisationDetail />} />

        <Route path='/onboarding/add-customer' element={<OnboardingAddCustomer />} />
        <Route path='/onboarding/setup' element={<Navigate to='/onboarding/add-customer' replace />} />
        <Route path='/onboarding/pending-signups' element={<Navigate to='/dashboard' replace />} />
        <Route path='/onboarding/services' element={<OnboardingServices />} />
        <Route path='/onboarding/dentally' element={<Navigate to='/integrations/dentally' replace />} />
        <Route path='/onboarding/numbers' element={<Navigate to='/integrations/telnyx' replace />} />
        <Route path='/onboarding/checklist' element={G('Go-live checklist')} />

        <Route path='/customer-feedback' element={<Navigate to='/customer-feedback/industries' replace />} />
        <Route path='/customer-feedback/industries' element={<FeedbackIndustriesList />} />
        <Route path='/customer-feedback/industries/:industryId' element={<FeedbackIndustryEdit />} />
        <Route path='/customer-feedback/packages' element={<FeedbackPackagesPricing />} />
        <Route path='/customer-feedback/survey-types/:typeId' element={<FeedbackSurveyTypeEdit />} />
        <Route path='/customer-feedback/:tab' element={<CustomerFeedbackHub />} />

        <Route path='/campaigns' element={<CampaignsHub />} />
        <Route path='/campaigns/templates' element={<CampaignTemplates />} />

        <Route path='/operations/running-surveys' element={<RunningSurveys />} />
        <Route path='/operations/wa-survey-insights' element={<WaSurveyInsights />} />
        <Route path='/operations/running-interviews' element={<RunningInterviews />} />
        <Route path='/operations/script-moderation' element={<ScriptModeration />} />
        <Route path='/operations/call-queue' element={<OperationsQueue title='Call queue' />} />
        <Route path='/operations/whatsapp-queue' element={<OperationsQueue title='WhatsApp queue' />} />
        <Route path='/operations/failed-jobs' element={<OperationsQueue title='Failed jobs' />} />
        <Route path='/operations/manual-retry' element={<OperationsQueue title='Manual retry' />} />
        <Route path='/operations/recovery-events' element={<OperationsQueue title='Recovery events' />} />

        <Route path='/marketing/lead-sources' element={<LeadSources />} />
        <Route path='/marketing/lead-sales' element={<LeadSales />} />
        <Route path='/marketing/lead-sales/settings' element={<LeadSalesSettings />} />
        <Route path='/marketing/lead-sales/offer-templates' element={<SalesOfferTemplates />} />
        <Route path='/marketing/lead-sales/:taskId' element={<LeadSalesEdit />} />
        <Route path='/marketing/ai-team' element={<AiTeam />} />
        <Route path='/marketing/promo-offers' element={<PromoOffers />} />
        <Route path='/marketing/promo-offers/new' element={<PromoOfferCreate />} />
        <Route path='/marketing/frontpage-call-leads' element={<FrontpageCallLeads />} />
        {/* Legacy paths (old admin builds used /ai-marketing/…) */}
        <Route path='/ai-marketing/leads' element={<Navigate to='/marketing/lead-sources' replace />} />
        <Route path='/ai-marketing/lead-sources' element={<Navigate to='/marketing/lead-sources' replace />} />
        <Route path='/ai-marketing/lead-sales' element={<Navigate to='/marketing/lead-sales' replace />} />
        <Route path='/marketing/apollo' element={<Navigate to='/marketing/ai-team' replace />} />
        <Route path='/marketing/clay' element={<Navigate to='/marketing/ai-team' replace />} />
        <Route path='/marketing/instantly' element={<Navigate to='/marketing/ai-team' replace />} />
        <Route path='/marketing/vapi' element={<Navigate to='/marketing/ai-team' replace />} />
        <Route path='/marketing/calendly' element={<Navigate to='/marketing/ai-team' replace />} />
        <Route path='/marketing/funnel' element={<Navigate to='/marketing/ai-team' replace />} />
        <Route path='/marketing/attribution' element={<Navigate to='/marketing/ai-team' replace />} />

        <Route path='/integrations' element={<Integrations />} />
        <Route path='/integrations/kpi' element={<Integrations />} />
        <Route path='/integrations/dentally' element={<Integrations />} />
        <Route path='/integrations/telnyx' element={<Integrations />} />
        <Route path='/integrations/azure_speech' element={<Integrations />} />
        <Route path='/integrations/openai' element={<Integrations />} />
        <Route path='/integrations/deepseek' element={<Integrations />} />
        <Route path='/integrations/groq' element={<Integrations />} />
        <Route path='/integrations/deepinfra' element={<Integrations />} />
        <Route path='/integrations/deepgram' element={<Integrations />} />
        <Route path='/integrations/cartesia' element={<Integrations />} />
        <Route path='/integrations/elevenlabs' element={<Integrations />} />
        <Route path='/integrations/vapi' element={<Integrations />} />
        <Route path='/integrations/gocardless' element={<Integrations />} />
        <Route path='/integrations/stripe' element={<Integrations />} />
        <Route path='/integrations/airwallex' element={<Integrations />} />
        <Route path='/integrations/zoom' element={<Integrations />} />
        <Route path='/integrations/calendly' element={<Integrations />} />
        <Route path='/integrations/cal_com' element={<Integrations />} />
        <Route path='/integrations/google_calendar' element={<Integrations />} />
        <Route path='/integrations/microsoft_calendar' element={<Integrations />} />
        <Route path='/integrations/hubspot' element={<Integrations />} />
        <Route path='/integrations/pipedrive' element={<Integrations />} />
        <Route path='/integrations/zoho_crm' element={<Integrations />} />
        <Route path='/integrations/zoho_bookings' element={<Integrations />} />
        <Route path='/integrations/webhooks' element={<Integrations />} />
        <Route path='/integrations/social-login' element={<Integrations />} />
        <Route path='/services-api' element={<Navigate to='/integrations/kpi' replace />} />
        <Route path='/services-api/*' element={<Navigate to='/integrations/kpi' replace />} />

        <Route path='/billing/mandates' element={<Billing />} />
        <Route path='/billing/subscriptions' element={<Billing />} />
        <Route path='/billing/invoices' element={<InvoicesAdmin />} />
        <Route path='/billing/failed-payments' element={<Billing />} />
        <Route path='/billing/refunds' element={<RefundsAdmin />} />
        <Route path='/billing/payment-events' element={<PaymentEventsAdmin />} />
        <Route path='/billing/wallet-ledger' element={<WalletLedgerAdmin />} />
        <Route path='/billing/tax' element={<TaxAdmin />} />
        <Route path='/billing/exceptions' element={<BillingExceptions />} />
        <Route path='/billing/reports' element={<Billing />} />
        <Route path='/billing/calls-cost' element={<CallsCost />} />
        <Route path='/billing/packages' element={<Navigate to='/billing/products?tab=subscription' replace />} />
        <Route path='/billing/products' element={<ProductsHub />} />
        <Route path='/billing/products/plan/new' element={<ProductPlanEdit />} />
        <Route path='/billing/products/plan/:planId/edit' element={<ProductPlanEdit />} />
        <Route path='/billing/service-orders' element={<ServiceOrdersAdmin />} />

        <Route path='/pricing/*' element={<PricingShell />}>
          <Route index element={<Navigate to='/pricing/plans' replace />} />
          <Route path='plans' element={<PricingPlans />} />
          <Route path='connection-fee' element={<PricingConnectionFee />} />
          <Route path='services' element={<PricingServices />} />
          <Route path='topups' element={<PricingTopups />} />
          <Route path='plan-prices' element={<PricingPlanPrices />} />
          <Route path='currency-rates' element={<PricingCurrencyRates />} />
          <Route path='invoice-settings' element={<PricingInvoiceSettings />} />
          <Route path='fx' element={<Navigate to='/pricing/currency-rates' replace />} />
          <Route path='estimator' element={<PricingEstimator />} />
          <Route path='custom' element={<PricingCustomOrg />} />
        </Route>

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

        <Route path='/compliance/audit' element={<ComplianceAudit />} />
        <Route path='/compliance/account-deletions' element={<AccountDeletionsAdmin />} />
        <Route path='/compliance/consent' element={<ComplianceSettings />} />
        <Route path='/compliance/recording' element={G('Recording disclosure')} />
        <Route path='/compliance/ofcom' element={G('OFCOM rules')} />
        <Route path='/compliance/gdpr' element={G('GDPR logs')} />

        <Route path='/analytics/kpis' element={<PlatformKpis />} />
        <Route path='/analytics/benchmarks' element={<Navigate to='/analytics/kpis' replace />} />
        <Route path='/analytics/recovery' element={<Navigate to='/analytics/kpis' replace />} />
        <Route path='/analytics/cost-revenue' element={<CostRevenue />} />

        <Route path='/team/users' element={<Navigate to='/platform/users' replace />} />
        <Route path='/admin/users' element={<Navigate to='/platform/users' replace />} />
        <Route path='/admin/users/new' element={<Navigate to='/platform/users/new' replace />} />
        <Route path='/admin/users/:id/edit' element={<Navigate to='/platform/users/:id/edit' replace />} />
        <Route path='/admin/admin-users' element={<Navigate to='/platform/users/new' replace />} />
        <Route path='/platform/users' element={<AdminUsers />} />
        <Route path='/platform/users/new' element={<AdminUserCreate />} />
        <Route path='/platform/users/:id/edit' element={<AdminUserEdit />} />
        <Route path='/team/permissions' element={<Permissions />} />
        <Route path='/team/logs' element={G('Activity logs')} />

        <Route path='/settings/global' element={G('Global config')} />
        <Route path='/settings/flags' element={G('Feature flags')} />
        <Route path='/settings/email' element={<EmailSettings />} />
        <Route path='/settings/email/templates/new' element={<EmailTemplateEdit />} />
        <Route path='/settings/email/templates/:templateKey/edit' element={<EmailTemplateEdit />} />
        <Route path='/settings/email/whatsapp/new' element={<WhatsAppTemplateEdit />} />
        <Route path='/settings/email/whatsapp/:templateKey/edit' element={<WhatsAppTemplateEdit />} />
        <Route path='/settings/email/sms/new' element={<SmsTemplateEdit />} />
        <Route path='/settings/email/sms/:templateKey/edit' element={<SmsTemplateEdit />} />
        <Route path='/settings/wa-survey' element={<WaSurveyTypes />} />
        <Route path='/settings/wa-survey/system-templates' element={<WaSurveySystemTemplates />} />
        <Route path='/settings/wa-interview' element={<WaInterviewTemplates />} />
        <Route path='/settings/wa-survey/simulator' element={<WaSurveyFlowSimulator />} />
        <Route path='/settings/wa-survey/industries/:industryId' element={<WaSurveyIndustryEdit />} />
        <Route path='/settings/wa-survey/industries' element={<WaSurveyIndustries />} />
        <Route path='/settings/wa-survey/:typeId/flows' element={<WaSurveyFlows />} />
        <Route path='/settings/wa-survey/:typeId' element={<WaSurveyTypeEdit />} />
        <Route path='/settings/legal' element={<LegalPages />} />
        <Route path='/settings/legal/:slug/edit' element={<LegalPageEdit />} />
        <Route path='/settings/api-keys' element={G('API keys / secrets')} />

        <Route path='*' element={<HomeRedirect />} />
      </Route>
    </Routes>
  )
}