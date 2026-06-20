import os

import pytest
from fastapi.testclient import TestClient


os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///./.pytest.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
# Valid Fernet key (32 url-safe base64-encoded bytes)
os.environ.setdefault("ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "twilio-test-auth-token")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "")
os.environ.setdefault("TWILIO_API_KEY", "")
os.environ.setdefault("TWILIO_API_SECRET", "")
os.environ.setdefault("TWILIO_FROM_NUMBER", "")
os.environ.setdefault("TWILIO_TWIML_URL", "")
os.environ.setdefault("TWILIO_WHATSAPP_FROM", "")
os.environ.setdefault("VAPI_WEBHOOK_SECRET", "vapi-test")
os.environ.setdefault("VAPI_API_KEY", "")
os.environ.setdefault("GOCARDLESS_WEBHOOK_SECRET", "gc-test")
os.environ.setdefault("BOOTSTRAP_TOKEN", "bootstrap-test-token")
os.environ.setdefault("ENABLE_TEST_CASH_BILLING", "true")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")
os.environ.setdefault("DENTALLY_BASE_URL", "https://dentally.test")
os.environ.setdefault("DENTALLY_API_KEY", "")


@pytest.fixture(autouse=True)
def _ensure_db_schema():
    """Create any missing tables for tests that use get_sessionmaker() directly."""
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())
    yield


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def _cleanup_db():
    yield
    try:
        os.remove(".pytest.db")
    except FileNotFoundError:
        pass
    except PermissionError:
        # On Windows, the SQLite file may still be locked by the driver at teardown.
        pass


@pytest.fixture()
def app_client():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Force Celery to run tasks synchronously in tests.
    from app.workers.celery_app import celery_app

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    celery_app.conf.task_store_eager_result = True

    from main import app

    return TestClient(app)
