from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.core.config import get_settings
from app.core.cors_utils import apply_cors_headers
from app.core.database import get_sessionmaker, init_db
from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.provider_settings import ProviderSettingsService

from app.routers.admin import router as admin_router
from app.routers.admin_email import router as admin_email_router
from app.routers.admin_email_legal import router as admin_email_legal_router
from app.routers.admin_messaging import router as admin_messaging_router
from app.routers.admin_wa_survey import router as admin_wa_survey_router
from app.routers.admin_wa_interview import router as admin_wa_interview_router
from app.routers.admin_compliance import router as admin_compliance_router
from app.routers.admin_support import router as admin_support_router
from app.routers.agents import router as agents_router
from app.routers.knowledge_base import router as knowledge_base_router
from app.routers.legal_pages import router as legal_pages_router
from app.routers.promo_offers import router as promo_offers_router
from app.routers.appointments import router as appointments_router
from app.routers.auth import router as auth_router
from app.routers.billing import router as billing_router
from app.routers.branches import router as branches_router
from app.routers.calls import router as calls_router
from app.routers.dashboard import router as dashboard_router
from app.routers.demo import admin_router as admin_demo_router
from app.routers.demo import router as demo_router
from app.routers.faq import router as faq_router
from app.routers.frontpage import admin_router as admin_frontpage_router
from app.routers.frontpage import router as frontpage_router
from app.routers.notifications import router as notifications_router
from app.routers.onboarding import router as onboarding_router
from app.routers.organisations import router as organisations_router
from app.routers.support import router as support_router
from app.routers.telnyx import router as telnyx_router
from app.routers.users import router as users_router
from app.routers.webhooks import router as webhooks_router
from app.routers.whatsapp import router as whatsapp_router
from app.routers.admin_platform_services import router as admin_platform_services_router
from app.routers.admin_products import router as admin_products_router
from app.routers.admin_pricing import router as admin_pricing_router
from app.routers.assistant import admin_router as admin_assistant_router
from app.routers.assistant import router as assistant_router
from app.routers.dashboard_scripts import router as dashboard_scripts_router
from app.routers.admin_customer_feedback import router as admin_customer_feedback_router
from app.routers.customer_feedback import router as customer_feedback_router
from app.routers.service_orders import router as service_orders_router
from app.routers.interview_booking_public import router as interview_booking_public_router
from app.routers.admin_ai_team import router as admin_ai_team_router
from app.routers.brand_public import router as brand_public_router
from app.services.lead_sales_scheduler import lead_sales_scheduler_loop
from app.services.interview_call_dispatch_service import interview_call_scheduler_loop
from app.services.survey_call_dispatch_service import survey_call_scheduler_loop
from app.services.career_mailbox_scheduler import career_mailbox_scheduler_loop
from app.services.interview_ats_scheduler import interview_ats_scheduler_loop
from app.services.uk_compliance_retention_service import uk_compliance_retention_scheduler_loop


LOCAL_ADMIN_EMAIL = os.getenv("LOCAL_ADMIN_EMAIL", "zaghlolno@gmail.com").strip().lower()
LOCAL_ADMIN_PASSWORD = os.getenv("LOCAL_ADMIN_PASSWORD", "testtest1")
LOCAL_DASHBOARD_EMAIL = os.getenv("LOCAL_DASHBOARD_EMAIL", "user@user.com").strip().lower()
LOCAL_DASHBOARD_PASSWORD = os.getenv("LOCAL_DASHBOARD_PASSWORD", LOCAL_ADMIN_PASSWORD)


def _ensure_local_demo_admin() -> None:
    with get_sessionmaker()() as db:
        email = LOCAL_ADMIN_EMAIL
        pwd_hash = hash_password(LOCAL_ADMIN_PASSWORD)
        user = db.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none()

        if user is None:
            user = User(
                email=email,
                password_hash=pwd_hash,
                is_active=True,
                is_superuser=True,
            )
            db.add(user)
            db.flush()
        else:
            user.password_hash = pwd_hash
            user.is_active = True
            user.is_superuser = True
            db.add(user)
            db.flush()

        mem = db.execute(
            select(OrganisationMembership).where(OrganisationMembership.user_id == user.id)
        ).scalar_one_or_none()
        if mem is None:
            org = Organisation(name="VOXBULK Local Admin")
            db.add(org)
            db.flush()
            db.add(OrganisationMembership(org_id=org.id, user_id=user.id))

        db.commit()


def _ensure_local_demo_user() -> None:
    """Ensure a non-admin dashboard account exists for local sign-in testing."""
    with get_sessionmaker()() as db:
        email = LOCAL_DASHBOARD_EMAIL
        user = db.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none()
        pwd_hash = hash_password(LOCAL_DASHBOARD_PASSWORD)
        if user is None:
            user = User(
                email=email,
                password_hash=pwd_hash,
                is_active=True,
                is_superuser=False,
            )
            db.add(user)
            db.flush()
        else:
            user.password_hash = pwd_hash
            user.is_active = True
            user.is_superuser = False
            db.add(user)
            db.flush()

        mem = db.execute(
            select(OrganisationMembership).where(OrganisationMembership.user_id == user.id)
        ).scalar_one_or_none()
        if mem is None:
            org = Organisation(name="Local Test Org")
            db.add(org)
            db.flush()
            db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
            db.flush()
            mem = db.execute(
                select(OrganisationMembership).where(OrganisationMembership.user_id == user.id)
            ).scalar_one()

        from app.models.plan import Plan
        from app.models.subscription import Subscription
        from app.services.gocardless_service import BillingService
        from app.services.usage_wallet_service import UsageWalletService
        from app.services.voxbulk_pricing_service import VoxbulkPricingService

        VoxbulkPricingService.ensure_seeded(db)
        pro = db.execute(select(Plan).where(Plan.code == "pro")).scalar_one_or_none()
        if pro is not None and mem is not None:
            VoxbulkPricingService.apply_plan_allowances(db, pro)
            db.refresh(pro)
            sub = db.execute(select(Subscription).where(Subscription.org_id == mem.org_id)).scalar_one_or_none()
            if sub is None:
                sub = Subscription(
                    org_id=mem.org_id,
                    plan_id=pro.id,
                    status="active",
                    payment_provider="local",
                )
                db.add(sub)
                db.flush()
            else:
                sub.plan_id = pro.id
                sub.status = "active"
                db.add(sub)
                db.flush()
            if UsageWalletService.get_current(db, mem.org_id) is None:
                UsageWalletService.bootstrap_from_plan(db, org_id=mem.org_id, subscription=sub)
            else:
                UsageWalletService.sync_plan_limits(db, org_id=mem.org_id, plan=pro, subscription=sub)

        db.commit()


def _log_provider_key_status(logger) -> None:
    SessionLocal = get_sessionmaker()
    providers = ["openai", "deepseek", "groq", "elevenlabs", "azure_speech"]
    status = {}
    with SessionLocal() as db:
        for provider in providers:
            try:
                row = ProviderSettingsService.get_platform_config_admin_view(db, provider=provider)
                status[provider] = {
                    "enabled": bool(row.get("is_enabled")),
                    "configured": bool(row.get("configured")),
                    "api_key_set": bool((row.get("secret_set") or {}).get("api_key")),
                    "missing_fields": row.get("missing_fields") or [],
                }
            except Exception as exc:
                status[provider] = {"configured": False, "error": str(exc)}
    logger.info("provider_key_status", extra={"providers": status})


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    logger = get_logger(__name__)
    if str(settings.env).lower() in {"dev", "development", "local"}:
        try:
            init_db()
        except Exception:
            logger.exception("init_db failed — fix DATABASE_URL/migrations; /health still works")
        try:
            _ensure_local_demo_admin()
            _ensure_local_demo_user()
            logger.info(
                "local_demo_accounts",
                extra={
                    "dashboard_email": LOCAL_DASHBOARD_EMAIL,
                    "admin_email": LOCAL_ADMIN_EMAIL,
                },
            )
        except Exception:
            logger.exception("local demo bootstrap failed — create users manually")
    logger.info("app_starting", extra={"env": settings.env, "app_name": settings.app_name})
    # TELNYX_WEBHOOK_BUILD_MARKER_20260606_2250 — boot instrumentation (see runtime_build_info)
    try:
        from app.core.runtime_build_info import WEBHOOK_BUILD_MARKER, log_startup_build_info

        log_startup_build_info(logger)
        logger.info("%s main_lifespan_startup_complete", WEBHOOK_BUILD_MARKER)
    except Exception:
        logger.exception("runtime_build_info_failed")
    try:
        from app.core.database import run_database_migrations

        run_database_migrations()
    except Exception:
        logger.exception("database migrations failed — check alembic upgrade head")
    try:
        from app.core.database import get_sessionmaker
        from app.services.email_template_service import EmailTemplateService

        with get_sessionmaker()() as db:
            EmailTemplateService.ensure_system_templates(db)
    except Exception:
        logger.exception("ensure_system_templates failed")
    try:
        from app.core.database import get_sessionmaker
        from app.services.platform_services_settings_service import ensure_row

        with get_sessionmaker()() as db:
            ensure_row(db)
    except Exception:
        logger.exception("platform_services_settings failed")
    try:
        from app.core.database import get_sessionmaker
        from app.services.customer_feedback.seed_service import FeedbackSeedService

        with get_sessionmaker()() as db:
            FeedbackSeedService.ensure_seeded(db)
    except Exception:
        logger.exception("feedback_seed failed")
    try:
        from app.core.database import get_sessionmaker
        from app.services.sales_offer_template_service import ensure_default_offer_templates

        with get_sessionmaker()() as db:
            if ensure_default_offer_templates(db):
                logger.info("seeded_default_sales_offer_templates")
    except Exception:
        logger.exception("ensure_default_offer_templates failed")
    stop_event = asyncio.Event()
    scheduler_task = asyncio.create_task(lead_sales_scheduler_loop(stop_event))
    survey_scheduler_task = asyncio.create_task(survey_call_scheduler_loop(stop_event))
    interview_scheduler_task = asyncio.create_task(interview_call_scheduler_loop(stop_event))
    career_mailbox_task = asyncio.create_task(career_mailbox_scheduler_loop(stop_event))
    ats_scheduler_task = asyncio.create_task(interview_ats_scheduler_loop(stop_event))
    uk_retention_task = asyncio.create_task(uk_compliance_retention_scheduler_loop())
    yield
    stop_event.set()
    scheduler_task.cancel()
    survey_scheduler_task.cancel()
    interview_scheduler_task.cancel()
    career_mailbox_task.cancel()
    ats_scheduler_task.cancel()
    uk_retention_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    try:
        await survey_scheduler_task
    except asyncio.CancelledError:
        pass
    try:
        await interview_scheduler_task
    except asyncio.CancelledError:
        pass
    try:
        await career_mailbox_task
    except asyncio.CancelledError:
        pass
    try:
        await ats_scheduler_task
    except asyncio.CancelledError:
        pass
    try:
        await uk_retention_task
    except asyncio.CancelledError:
        pass
    logger.info("app_stopped", extra={"env": settings.env, "app_name": settings.app_name})


settings = get_settings()

app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.trusted_hosts,
)

_origins = settings.cors_allow_origins
_cors_kw = dict(
    allow_origins=_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=[
        "Authorization",
        "Accept",
        "Content-Type",
        "Origin",
        "X-Voxbulk-Org-Id",
        "X-Retover-Org-Id",
        "X-Requested-With",
    ],
    expose_headers=["Content-Type", "Content-Length"],
    max_age=600,
)
_reg = settings.cors_allow_origin_regex
if _reg:
    _cors_kw["allow_origin_regex"] = _reg
app.add_middleware(CORSMiddleware, **_cors_kw)


@app.middleware("http")
async def ensure_cors_on_all_responses(request: Request, call_next):
    """CORSMiddleware does not attach ACAO to ServerError 500 responses; fix that here."""
    settings = get_settings()
    try:
        response = await call_next(request)
    except Exception as exc:
        get_logger(__name__).exception(
            "unhandled_exception",
            extra={"path": request.url.path, "error_type": type(exc).__name__},
        )
        detail = str(exc).strip() or type(exc).__name__
        response = JSONResponse(
            status_code=500,
            content={
                "detail": detail,
                "error_type": type(exc).__name__,
                "path": request.url.path,
            },
        )
    return apply_cors_headers(request, response, settings)


def _migration_hint_from_db_error(exc: BaseException) -> str | None:
    msg = str(exc).lower()
    if "unknown column" in msg or "doesn't exist" in msg or "no such table" in msg or "does not exist" in msg:
        try:
            from app.core.database import ensure_pricing_schema

            ensure_pricing_schema()
        except Exception:
            pass
        return "Database schema was updated automatically. Refresh the page and try again."
    return None


@app.exception_handler(OperationalError)
async def db_operational_error_handler(request: Request, exc: OperationalError):
    hint = _migration_hint_from_db_error(exc)
    detail = hint or "Database error — check API logs and DATABASE_URL."
    response = JSONResponse(status_code=503, content={"detail": detail})
    return apply_cors_headers(request, response, get_settings())


@app.exception_handler(ProgrammingError)
async def db_programming_error_handler(request: Request, exc: ProgrammingError):
    hint = _migration_hint_from_db_error(exc)
    detail = hint or "Database error — check API logs."
    response = JSONResponse(status_code=503, content={"detail": detail})
    return apply_cors_headers(request, response, get_settings())


@app.get("/health/pricing", tags=["health"])
def health_pricing():
    from app.core.database import get_engine, _table_columns
    from app.core.pricing_schema import WHATSAPP_SURVEY_FEE_PENCE_COLUMN
    from app.services.pricing_bootstrap_service import get_pricing_bootstrap_status

    engine = get_engine()
    settings_cols = sorted(_table_columns(engine, "pricing_global_settings"))
    custom_cols = sorted(_table_columns(engine, "org_custom_pricing"))
    status = get_pricing_bootstrap_status()
    return {
        "status": "ok" if status.get("ok") else "not_ready",
        "whatsapp_survey_fee_column": WHATSAPP_SURVEY_FEE_PENCE_COLUMN,
        "pricing_global_settings_columns": settings_cols,
        "org_custom_pricing_columns": custom_cols,
        **status,
    }


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


@app.get("/health/build", tags=["health"])
def health_build():
    """Deploy verification — explicit marker flags on disk and in the running process."""
    from app.core.runtime_build_info import WEBHOOK_BUILD_MARKER, get_deploy_verification

    data = get_deploy_verification()
    return {
        "status": "ok" if data.get("deploy_ok") else "stale_or_partial",
        "webhook_build_marker": WEBHOOK_BUILD_MARKER,
        "git_sha": data.get("git_sha"),
        "git_sha_full": data.get("git_sha_full"),
        "git_branch": data.get("git_branch"),
        "built_at": data.get("built_at"),
        "app_version": data.get("app_version"),
        "hostname": data.get("hostname"),
        "pid": data.get("pid"),
        "api_root": data.get("api_root"),
        "repo_root": data.get("repo_root"),
        "wa_test_session_persistence_fix_marker": data.get("wa_test_session_persistence_fix_marker"),
        "session_persistence_fix_on_disk": data.get("session_persistence_fix_on_disk"),
        "session_persistence_fix_loaded": data.get("session_persistence_fix_loaded"),
        "wa_test_session_handler": data.get("wa_test_session_handler"),
        "boot_marker_present_on_disk": data.get("boot_marker_present_on_disk"),
        "router_marker_present_on_disk": data.get("router_marker_present_on_disk"),
        "service_marker_present_on_disk": data.get("service_marker_present_on_disk"),
        "canonical_marker_present_on_disk": data.get("canonical_marker_present_on_disk"),
        "boot_marker_loaded": data.get("boot_marker_loaded"),
        "router_marker_loaded": data.get("router_marker_loaded"),
        "service_marker_loaded": data.get("service_marker_loaded"),
        "boot_marker_executed_in_process": data.get("boot_marker_executed_in_process"),
        "webhook_marker_logged_count": data.get("webhook_marker_logged_count"),
        "session_code_present_on_disk": data.get("session_code_present_on_disk"),
        "session_code_loaded": data.get("session_code_loaded"),
        "final_feedback_yes_no_marker": data.get("final_feedback_yes_no_marker"),
        "final_feedback_yes_no_on_disk": data.get("final_feedback_yes_no_on_disk"),
        "final_feedback_yes_no_loaded": data.get("final_feedback_yes_no_loaded"),
        "final_feedback_system_template_marker": data.get("final_feedback_system_template_marker"),
        "final_feedback_system_template_on_disk": data.get("final_feedback_system_template_on_disk"),
        "final_feedback_system_template_loaded": data.get("final_feedback_system_template_loaded"),
        "deploy_ok": data.get("deploy_ok"),
        "handler_chain": data.get("handler_chain"),
        "marker_site_paths": data.get("marker_site_paths"),
    }


@app.get("/health/db", tags=["health"])
def health_db():
    """Quick schema probe — fails with 503 if migrations were not applied."""
    SessionLocal = get_sessionmaker()
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
        # Columns/tables added in recent releases (lead sales + automation)
        db.execute(text("SELECT automation_paused FROM lead_sales_tasks LIMIT 0"))
        db.execute(text("SELECT sales_automation_enabled FROM lead_sales_settings LIMIT 0"))
        db.execute(text("SELECT telnyx_greeting FROM frontpage_call_settings LIMIT 0"))
        db.execute(text("SELECT telnyx_greeting FROM lead_sales_settings LIMIT 0"))
        db.execute(text("SELECT reference_id FROM service_orders LIMIT 0"))
        db.execute(text("SELECT active_for_interview FROM telnyx_whatsapp_templates LIMIT 0"))
    return {"status": "ok", "schema": "current"}


app.include_router(auth_router)
app.include_router(organisations_router)
app.include_router(branches_router)
app.include_router(users_router)
app.include_router(appointments_router)
app.include_router(calls_router)
app.include_router(whatsapp_router)
app.include_router(webhooks_router)
app.include_router(dashboard_router)
app.include_router(demo_router)
app.include_router(admin_demo_router)
app.include_router(billing_router)
app.include_router(support_router)
app.include_router(telnyx_router)
app.include_router(faq_router)
app.include_router(legal_pages_router)
app.include_router(legal_pages_router, prefix="/api")
app.include_router(promo_offers_router)
app.include_router(promo_offers_router, prefix="/api")
app.include_router(frontpage_router)
app.include_router(frontpage_router, prefix="/api")
app.include_router(admin_frontpage_router)
app.include_router(admin_frontpage_router, prefix="/api")
app.include_router(notifications_router)
app.include_router(onboarding_router)
app.include_router(admin_router)
app.include_router(agents_router)
app.include_router(knowledge_base_router)
app.include_router(knowledge_base_router, prefix="/api")
app.include_router(admin_email_router)
app.include_router(admin_email_legal_router)
app.include_router(admin_messaging_router)
app.include_router(admin_wa_survey_router)
app.include_router(admin_wa_interview_router)
app.include_router(admin_compliance_router)
app.include_router(admin_support_router)
app.include_router(service_orders_router)
app.include_router(interview_booking_public_router)
app.include_router(admin_ai_team_router)
app.include_router(admin_ai_team_router, prefix="/api")
app.include_router(brand_public_router)
app.include_router(admin_platform_services_router)
app.include_router(admin_products_router)
app.include_router(admin_products_router, prefix="/api")
app.include_router(admin_pricing_router)
app.include_router(admin_pricing_router, prefix="/api")
app.include_router(dashboard_help_router)
app.include_router(assistant_router)
app.include_router(admin_assistant_router)
app.include_router(dashboard_scripts_router)
app.include_router(admin_customer_feedback_router)
app.include_router(customer_feedback_router)
