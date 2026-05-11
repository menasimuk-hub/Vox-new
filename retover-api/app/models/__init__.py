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
from app.models.subscription import Subscription  # noqa: F401
from app.models.billing_redirect_flow import BillingRedirectFlow  # noqa: F401
from app.models.webhook_event import WebhookEvent  # noqa: F401
from app.models.recovery_job import RecoveryJob  # noqa: F401
from app.models.provider_config import ProviderConfig  # noqa: F401
from app.models.onboarding_request import OnboardingRequest  # noqa: F401
from app.models.organisation_invite import OrganisationInvite  # noqa: F401
from app.models.category import Category  # noqa: F401
from app.models.agent import AgentAssignment, AgentDefinition  # noqa: F401
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
from app.models.password_reset_token import PasswordResetToken  # noqa: F401
from app.models.admin_user import AdminUser  # noqa: F401
from app.models.payment_event import PaymentEvent  # noqa: F401
from app.models.billing_invoice import BillingInvoice  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from app.models.faq import FAQCategory, FAQItem  # noqa: F401
from app.models.support_ticket import (  # noqa: F401
    CannedReply,
    CannedReplyCategory,
    SupportTicket,
    SupportTicketAttachment,
    SupportTicketEvent,
    SupportTicketMessage,
)
