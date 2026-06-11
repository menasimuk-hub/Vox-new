"""SQLAlchemy models.

Importing model modules here ensures Alembic sees them via Base.metadata.
"""

from app.models.membership import OrganisationMembership  # noqa: F401
from app.models.organisation import Organisation  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.branch import Branch  # noqa: F401
from app.models.patient import Patient  # noqa: F401
from app.models.appointment import Appointment  # noqa: F401
from app.models.call_log import CallLog  # noqa: F401
from app.models.whatsapp_log import WhatsAppLog  # noqa: F401
from app.models.plan import Plan  # noqa: F401
from app.models.promo_offer import PromoOffer, PromoRedemption  # noqa: F401
from app.models.org_usage_period import OrgUsagePeriod  # noqa: F401
from app.models.subscription import Subscription  # noqa: F401
from app.models.billing_redirect_flow import BillingRedirectFlow  # noqa: F401
from app.models.webhook_event import WebhookEvent  # noqa: F401
from app.models.frontpage_lead_call import FrontpageLeadCall  # noqa: F401
from app.models.frontpage_call_setting import FrontpageCallSetting  # noqa: F401
from app.models.lead_sales_setting import LeadSalesSetting  # noqa: F401
from app.models.lead_sales_task import LeadSalesTask  # noqa: F401
from app.models.sales_offer_template import SalesOfferTemplate  # noqa: F401
from app.models.sales_conversation_state import SalesConversationState  # noqa: F401
from app.models.recovery_job import RecoveryJob  # noqa: F401
from app.models.provider_config import ProviderConfig  # noqa: F401
from app.models.onboarding_request import OnboardingRequest  # noqa: F401
from app.models.onboarding_setting import OnboardingSetting  # noqa: F401
from app.models.organisation_invite import OrganisationInvite  # noqa: F401
from app.models.org_opt_out import OrganisationOptOut  # noqa: F401
from app.models.org_audit_event import OrganisationAuditEvent  # noqa: F401
from app.models.category import Category  # noqa: F401
from app.models.agent import AgentAssignment, AgentDefinition  # noqa: F401
from app.models.voice_agent_platform_settings import VoiceAgentPlatformSettings  # noqa: F401
from app.models.agent_service_assignment import AgentServiceAssignment  # noqa: F401
from app.models.knowledge_base_file import KnowledgeBaseFile  # noqa: F401
from app.models.agent_knowledge_file import AgentKnowledgeFile  # noqa: F401
from app.models.service_api import SupportedServiceAPI  # noqa: F401
from app.models.organisation_ai_config import (  # noqa: F401
    OrganisationAIIdentity,
    OrganisationComplianceConfig,
    OrganisationServiceCatalogItem,
    OrganisationWorkflowConfig,
)
from app.models.oauth_identity import OAuthIdentity  # noqa: F401
from app.models.smtp_settings import SmtpSettings  # noqa: F401
from app.models.email_template import EmailTemplate  # noqa: F401
from app.models.whatsapp_template import WhatsAppTemplate  # noqa: F401
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate  # noqa: F401
from app.models.industry import Industry  # noqa: F401
from app.models.industry_deletion_tombstone import IndustryDeletionTombstone  # noqa: F401
from app.models.survey_type import SurveyType  # noqa: F401
from app.models.survey_type_template import SurveyTypeTemplate  # noqa: F401
from app.models.survey_template_pack import SurveyTemplatePack  # noqa: F401
from app.models.survey_session import (  # noqa: F401
    SurveySession,
    SurveySessionAnswer,
    SurveySessionDecision,
)
from app.models.survey_voice_note_job import SurveyVoiceNoteJob  # noqa: F401
from app.models.wa_survey_platform_settings import WaSurveyPlatformSettings  # noqa: F401
from app.models.survey_flow import (  # noqa: F401
    SurveyFlowDefinition,
    SurveyFlowEdge,
    SurveyFlowNode,
    SurveyFlowOutcome,
)
from app.models.sms_template import SmsTemplate  # noqa: F401
from app.models.password_reset_token import PasswordResetToken  # noqa: F401
from app.models.admin_user import AdminUser  # noqa: F401
from app.models.payment_event import PaymentEvent  # noqa: F401
from app.models.billing_invoice import BillingInvoice  # noqa: F401
from app.models.country_vat_rate import CountryVatRate  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from app.models.faq import FAQCategory, FAQItem  # noqa: F401
from app.models.legal_page import LegalPage  # noqa: F401
from app.models.support_ticket import (  # noqa: F401
    CannedReply,
    CannedReplyCategory,
    SupportTicket,
    SupportTicketAttachment,
    SupportTicketEvent,
    SupportTicketMessage,
)
from app.models.platform_service import PlatformService, ServicePricingRule  # noqa: F401
from app.models.pricing import OrgCustomPricing, PricingGlobalSettings, TopupTier  # noqa: F401
from app.models.plan_price import PlanPrice, PricingCurrencySettings  # noqa: F401
from app.models.wallet_transaction import WalletTransaction  # noqa: F401
from app.models.billing_settings import BillingSettings  # noqa: F401
from app.models.credit_note import CreditNote  # noqa: F401
from app.models.billing_refund_review import BillingRefundReview  # noqa: F401
from app.models.service_order import ServiceOrder, ServiceOrderRecipient  # noqa: F401
from app.models.interview_booking_token import InterviewBookingToken  # noqa: F401
from app.models.career_mailbox_settings import CareerMailboxSettings  # noqa: F401
from app.models.ai_team_settings import AiTeamSettings  # noqa: F401
from app.models.ai_team_prospect import AiTeamProspect  # noqa: F401
from app.models.ai_team_message import AiTeamMessage  # noqa: F401
from app.models.customer_feedback import (  # noqa: F401
    FeedbackIndustry,
    FeedbackLocation,
    FeedbackPackage,
    FeedbackResponse,
    FeedbackSession,
    FeedbackSurveyType,
    FeedbackUsagePeriod,
    FeedbackWaSender,
    FeedbackWaTemplate,
)
from app.models.platform_services_settings import PlatformServicesSettings  # noqa: F401
