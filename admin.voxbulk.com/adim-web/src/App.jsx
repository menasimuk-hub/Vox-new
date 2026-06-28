import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'
import * as P from './lib/lazyPages'
import { defaultAdminHome } from './lib/adminPaths'
import { useAdminProfile } from './context/AdminProfileContext'

const G = (title) => <P.GenericPage title={title} />

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

        <Route path='/dashboard' element={<P.Dashboard />} />
        <Route path='/dashboard/mrr' element={<Navigate to='/dashboard' replace />} />
        <Route path='/dashboard/total-organisations' element={<Navigate to='/dashboard' replace />} />
        <Route path='/dashboard/trial-conversions' element={<Navigate to='/dashboard' replace />} />
        <Route path='/dashboard/system-health' element={<Navigate to='/dashboard' replace />} />
        <Route path='/dashboard/llm-call-spend' element={<Navigate to='/dashboard' replace />} />

        <Route path='/organisations' element={<P.Organisations />} />
        <Route path='/organisations/all-users' element={<P.OrgControlCenter />} />
        <Route path='/organisations/profile' element={<P.OrganisationProfile />} />
        <Route path='/organisations/categories' element={<P.Categories />} />
        <Route path='/organisations/zone/:zone' element={<P.ZoneOrganisations />} />
        <Route path='/organisations/:orgId' element={<P.OrganisationDetail />} />

        <Route path='/onboarding/add-customer' element={<P.OnboardingAddCustomer />} />
        <Route path='/onboarding/setup' element={<Navigate to='/onboarding/add-customer' replace />} />
        <Route path='/onboarding/pending-signups' element={<Navigate to='/dashboard' replace />} />
        <Route path='/onboarding/services' element={<P.OnboardingServices />} />
        <Route path='/onboarding/dentally' element={<Navigate to='/integrations/dentally' replace />} />
        <Route path='/onboarding/numbers' element={<Navigate to='/integrations/telnyx' replace />} />
        <Route path='/onboarding/checklist' element={G('Go-live checklist')} />

        <Route path='/customer-feedback' element={<Navigate to='/customer-feedback/industries' replace />} />
        <Route path='/customer-feedback/industries' element={<P.FeedbackIndustriesList />} />
        <Route path='/customer-feedback/industries/:industryId' element={<P.FeedbackIndustryEdit />} />
        <Route path='/customer-feedback/packages' element={<P.FeedbackPackagesPricing />} />
        <Route path='/customer-feedback/survey-types/:typeId' element={<P.FeedbackSurveyTypeEdit />} />
        <Route path='/customer-feedback/:tab' element={<P.CustomerFeedbackHub />} />

        <Route path='/campaigns' element={<P.CampaignsHub />} />
        <Route path='/campaigns/templates' element={<P.CampaignTemplates />} />

        <Route path='/operations/running-surveys' element={<P.RunningSurveys />} />
        <Route path='/operations/wa-survey-insights' element={<P.WaSurveyInsights />} />
        <Route path='/operations/running-interviews' element={<P.RunningInterviews />} />
        <Route path='/operations/running-appointments' element={<P.RunningAppointments />} />
        <Route path='/operations/orders/:orderId' element={<P.ServiceOrderDetail />} />
        <Route path='/operations/script-moderation' element={<P.ScriptModeration />} />
        <Route path='/operations/call-queue' element={<P.OperationsQueue title='Call queue' />} />
        <Route path='/operations/whatsapp-queue' element={<P.OperationsQueue title='WhatsApp queue' />} />
        <Route path='/operations/failed-jobs' element={<P.OperationsQueue title='Failed jobs' />} />
        <Route path='/operations/manual-retry' element={<P.OperationsQueue title='Manual retry' />} />
        <Route path='/operations/recovery-events' element={<P.OperationsQueue title='Recovery events' />} />

        <Route path='/marketing/lead-sources' element={<P.LeadSources />} />
        <Route path='/marketing/lead-sales' element={<P.LeadSales />} />
        <Route path='/marketing/lead-sales/settings' element={<P.LeadSalesSettings />} />
        <Route path='/marketing/lead-sales/offer-templates' element={<P.SalesOfferTemplates />} />
        <Route path='/marketing/salesmen' element={<P.Salesmen />} />
        <Route path='/marketing/lead-sales/:taskId' element={<P.LeadSalesEdit />} />
        <Route path='/marketing/ai-team' element={<P.AiTeam />} />
        <Route path='/marketing/promo-offers' element={<P.PromoOffers />} />
        <Route path='/marketing/promo-offers/new' element={<P.PromoOfferCreate />} />
        <Route path='/marketing/frontpage-call-leads' element={<P.FrontpageCallLeads />} />
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

        <Route path='/integrations' element={<P.Integrations />} />
        <Route path='/integrations/kpi' element={<P.Integrations />} />
        <Route path='/integrations/dentally' element={<P.Integrations />} />
        <Route path='/integrations/telnyx' element={<P.Integrations />} />
        <Route path='/integrations/azure_speech' element={<P.Integrations />} />
        <Route path='/integrations/openai' element={<P.Integrations />} />
        <Route path='/integrations/deepseek' element={<P.Integrations />} />
        <Route path='/integrations/groq' element={<P.Integrations />} />
        <Route path='/integrations/deepinfra' element={<P.Integrations />} />
        <Route path='/integrations/deepgram' element={<P.Integrations />} />
        <Route path='/integrations/cartesia' element={<P.Integrations />} />
        <Route path='/integrations/elevenlabs' element={<P.Integrations />} />
        <Route path='/integrations/vapi' element={<P.Integrations />} />
        <Route path='/integrations/gocardless' element={<P.Integrations />} />
        <Route path='/integrations/stripe' element={<P.Integrations />} />
        <Route path='/integrations/airwallex' element={<P.Integrations />} />
        <Route path='/integrations/calendly' element={<P.Integrations />} />
        <Route path='/integrations/cal_com' element={<P.Integrations />} />
        <Route path='/integrations/google_calendar' element={<P.Integrations />} />
        <Route path='/integrations/microsoft_calendar' element={<P.Integrations />} />
        <Route path='/integrations/hubspot' element={<P.Integrations />} />
        <Route path='/integrations/pipedrive' element={<P.Integrations />} />
        <Route path='/integrations/zoho_crm' element={<P.Integrations />} />
        <Route path='/integrations/zoho_bookings' element={<P.Integrations />} />
        <Route path='/integrations/webhooks' element={<P.Integrations />} />
        <Route path='/integrations/social-login' element={<P.Integrations />} />
        <Route path='/services-api' element={<Navigate to='/integrations/kpi' replace />} />
        <Route path='/services-api/*' element={<Navigate to='/integrations/kpi' replace />} />

        <Route path='/billing/mandates' element={<P.Billing />} />
        <Route path='/billing/subscriptions' element={<P.Billing />} />
        <Route path='/billing/invoices' element={<P.InvoicesAdmin />} />
        <Route path='/billing/failed-payments' element={<P.Billing />} />
        <Route path='/billing/refunds' element={<P.RefundsAdmin />} />
        <Route path='/billing/payment-events' element={<P.PaymentEventsAdmin />} />
        <Route path='/billing/wallet-ledger' element={<P.WalletLedgerAdmin />} />
        <Route path='/billing/tax' element={<P.TaxAdmin />} />
        <Route path='/billing/exceptions' element={<P.BillingExceptions />} />
        <Route path='/billing/reports' element={<P.Billing />} />
        <Route path='/billing/calls-cost' element={<P.CallsCost />} />
        <Route path='/billing/packages' element={<Navigate to='/billing/products?tab=subscription' replace />} />
        <Route path='/billing/products' element={<P.ProductsHub />} />
        <Route path='/billing/products/plan/new' element={<P.ProductPlanEdit />} />
        <Route path='/billing/products/plan/:planId/edit' element={<P.ProductPlanEdit />} />
        <Route path='/billing/service-orders' element={<P.ServiceOrdersAdmin />} />

        <Route path='/pricing/*' element={<P.PricingShell />}>
          <Route index element={<Navigate to='/pricing/plans' replace />} />
          <Route path='plans' element={<P.PricingPlans />} />
          <Route path='connection-fee' element={<P.PricingConnectionFee />} />
          <Route path='services' element={<P.PricingServices />} />
          <Route path='topups' element={<P.PricingTopups />} />
          <Route path='plan-prices' element={<P.PricingPlanPrices />} />
          <Route path='currency-rates' element={<P.PricingCurrencyRates />} />
          <Route path='invoice-settings' element={<P.PricingInvoiceSettings />} />
          <Route path='fx' element={<Navigate to='/pricing/currency-rates' replace />} />
          <Route path='estimator' element={<P.PricingEstimator />} />
          <Route path='custom' element={<P.PricingCustomOrg />} />
        </Route>

        <Route path='/support/inbox' element={<P.SupportTickets />} />
        <Route path='/support/tickets' element={<P.SupportTickets />} />
        <Route path='/support/tickets/:ticketId' element={<P.SupportTicketDetail />} />
        <Route path='/support/notes' element={G('Customer notes')} />
        <Route path='/support/escalations' element={G('Escalations')} />
        <Route path='/support/help' element={<P.HelpCentreContent />} />
        <Route path='/support/faq' element={<P.FAQManagement />} />
        <Route path='/support/sla' element={<P.SupportSLA />} />

        <Route path='/ai/scripts' element={G('Call scripts')} />
        <Route path='/ai/agents' element={<P.Agents />} />
        <Route path='/ai/agents/new' element={<P.Agents />} />
        <Route path='/ai/agents/:agentId/edit' element={<P.Agents />} />
        <Route path='/ai/agent-demo' element={<P.AgentDemo />} />
        <Route path='/ai/prompts' element={G('Prompt templates')} />
        <Route path='/ai/retry' element={G('Retry logic')} />
        <Route path='/ai/voicemail' element={G('Voicemail logic')} />
        <Route path='/ai/cost' element={G('Cost controls')} />

        <Route path='/compliance/audit' element={<P.ComplianceAudit />} />
        <Route path='/compliance/account-deletions' element={<P.AccountDeletionsAdmin />} />
        <Route path='/compliance/consent' element={<P.ComplianceSettings />} />
        <Route path='/compliance/recording' element={G('Recording disclosure')} />
        <Route path='/compliance/ofcom' element={G('OFCOM rules')} />
        <Route path='/compliance/gdpr' element={G('GDPR logs')} />

        <Route path='/analytics/kpis' element={<P.PlatformKpis />} />
        <Route path='/analytics/benchmarks' element={<Navigate to='/analytics/kpis' replace />} />
        <Route path='/analytics/recovery' element={<Navigate to='/analytics/kpis' replace />} />
        <Route path='/analytics/cost-revenue' element={<P.CostRevenue />} />

        <Route path='/team/users' element={<Navigate to='/platform/users' replace />} />
        <Route path='/admin/users' element={<Navigate to='/platform/users' replace />} />
        <Route path='/admin/users/new' element={<Navigate to='/platform/users/new' replace />} />
        <Route path='/admin/users/:id/edit' element={<Navigate to='/platform/users/:id/edit' replace />} />
        <Route path='/admin/admin-users' element={<Navigate to='/platform/users/new' replace />} />
        <Route path='/platform/users' element={<P.AdminUsers />} />
        <Route path='/platform/users/new' element={<P.AdminUserCreate />} />
        <Route path='/platform/users/:id/edit' element={<P.AdminUserEdit />} />
        <Route path='/team/permissions' element={<P.Permissions />} />
        <Route path='/team/logs' element={G('Activity logs')} />

        <Route path='/settings/global' element={G('Global config')} />
        <Route path='/settings/flags' element={G('Feature flags')} />
        <Route path='/settings/email' element={<P.EmailSettings />} />
        <Route path='/settings/email/templates/new' element={<P.EmailTemplateEdit />} />
        <Route path='/settings/email/templates/:templateKey/edit' element={<P.EmailTemplateEdit />} />
        <Route path='/settings/email/whatsapp/new' element={<P.WhatsAppTemplateEdit />} />
        <Route path='/settings/email/whatsapp/:templateKey/edit' element={<P.WhatsAppTemplateEdit />} />
        <Route path='/settings/email/sms/new' element={<P.SmsTemplateEdit />} />
        <Route path='/settings/email/sms/:templateKey/edit' element={<P.SmsTemplateEdit />} />
        <Route path='/settings/wa-survey' element={<P.WaSurveyTypes />} />
        <Route path='/settings/wa-survey/system-templates' element={<P.WaSurveySystemTemplates />} />
        <Route path='/settings/wa-interview' element={<P.WaInterviewTemplates />} />
        <Route path='/settings/wa-appointment' element={<P.WaAppointmentTemplates />} />
        <Route path='/settings/wa-survey/simulator' element={<P.WaSurveyFlowSimulator />} />
        <Route path='/settings/wa-survey/industries/:industryId' element={<P.WaSurveyIndustryEdit />} />
        <Route path='/settings/wa-survey/industries' element={<P.WaSurveyIndustries />} />
        <Route path='/settings/wa-survey/:typeId/flows' element={<P.WaSurveyFlows />} />
        <Route path='/settings/wa-survey/:typeId' element={<P.WaSurveyTypeEdit />} />
        <Route path='/settings/legal' element={<P.LegalPages />} />
        <Route path='/settings/meeting-room' element={<P.MeetingRoomSettings />} />
        <Route path='/settings/legal/:slug/edit' element={<P.LegalPageEdit />} />
        <Route path='/settings/disabled-wa-templates' element={<P.DisabledWaTemplates />} />
        <Route path='/settings/api-keys' element={G('API keys / secrets')} />

        <Route path='*' element={<HomeRedirect />} />
      </Route>
    </Routes>
  )
}
