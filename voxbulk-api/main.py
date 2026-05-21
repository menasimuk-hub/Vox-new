from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.core.config import get_settings
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
from app.routers.dashboard_help import router as dashboard_help_router
from app.routers.dashboard_scripts import router as dashboard_scripts_router
from app.routers.service_orders import router as service_orders_router
from app.services.lead_sales_scheduler import lead_sales_scheduler_loop


def _ensure_local_demo_admin() -> None:
    with get_sessionmaker()() as db:
        email = "zaghlolno@gmail.com"
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

        # If a previous run created this user as a normal user, "upgrade" it so
        # local dev always has a working superuser for routing/admin testing.
        if user is None:
            user = User(
                email=email,
                password_hash=hash_password("testtest1"),
                is_active=True,
                is_superuser=True,
            )
            db.add(user)
            db.flush()
        else:
            changed = False
            if not user.is_active:
                user.is_active = True
                changed = True
            if not user.is_superuser:
                user.is_superuser = True
                changed = True
            if not user.password_hash:
                user.password_hash = hash_password("testtest1")
                changed = True
            if changed:
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
        except Exception:
            logger.exception("local demo admin bootstrap failed — create a superuser manually")
    logger.info("app_starting", extra={"env": settings.env, "app_name": settings.app_name})
    stop_event = asyncio.Event()
    scheduler_task = asyncio.create_task(lead_sales_scheduler_loop(stop_event))
    yield
    stop_event.set()
    scheduler_task.cancel()
    try:
        await scheduler_task
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


def _migration_hint_from_db_error(exc: BaseException) -> str | None:
    msg = str(exc).lower()
    if "unknown column" in msg or "doesn't exist" in msg or "no such table" in msg or "does not exist" in msg:
        return (
            "Database schema is behind the API code. On the VPS run: "
            "cd /www/voxbulk/voxbulk-api && source .venv/bin/activate && python -m alembic upgrade head && cd /www/voxbulk && ./vox.sh restart"
        )
    return None


@app.exception_handler(OperationalError)
async def db_operational_error_handler(_request: Request, exc: OperationalError):
    hint = _migration_hint_from_db_error(exc)
    detail = hint or "Database error — check API logs and DATABASE_URL."
    return JSONResponse(status_code=503, content={"detail": detail})


@app.exception_handler(ProgrammingError)
async def db_programming_error_handler(_request: Request, exc: ProgrammingError):
    hint = _migration_hint_from_db_error(exc)
    detail = hint or "Database error — check API logs."
    return JSONResponse(status_code=503, content={"detail": detail})


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


@app.get("/health/db", tags=["health"])
def health_db():
    """Quick schema probe — fails with 503 if migrations were not applied."""
    SessionLocal = get_sessionmaker()
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
        # Columns/tables added in recent releases (lead sales + automation)
        db.execute(text("SELECT automation_paused FROM lead_sales_tasks LIMIT 0"))
        db.execute(text("SELECT sales_automation_enabled FROM lead_sales_settings LIMIT 0"))
        db.execute(text("SELECT id FROM sales_conversation_states LIMIT 0"))
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
app.include_router(admin_support_router)
app.include_router(service_orders_router)
app.include_router(admin_platform_services_router)
app.include_router(admin_products_router)
app.include_router(admin_products_router, prefix="/api")
app.include_router(dashboard_help_router)
app.include_router(dashboard_scripts_router)
