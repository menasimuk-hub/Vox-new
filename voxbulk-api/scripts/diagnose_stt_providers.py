"""One-off STT provider diagnostic for production."""
from app.core.database import get_sessionmaker
from app.services.providers.deepgram_service import DeepgramProviderService
from app.services.providers.deepinfra_service import DeepInfraProviderService
from app.services.voice_transcription_service import stt_provider_order

db = get_sessionmaker()()
try:
    print("stt_provider_order", stt_provider_order())
    print("deepgram_configured", DeepgramProviderService.is_configured(db))
    print("deepinfra_configured", DeepInfraProviderService.is_configured(db))
finally:
    db.close()
