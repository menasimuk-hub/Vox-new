from app.services.ai_demo_service import AiDemoService
from types import SimpleNamespace


def test_infer_visitor_region_from_whatsapp():
    assert AiDemoService.infer_visitor_region(SimpleNamespace(whatsapp_e164="+447700900123", preferred_language="en", voice_region=None)) == "GB"
    assert AiDemoService.infer_visitor_region(SimpleNamespace(whatsapp_e164="+61412345678", preferred_language="en", voice_region=None)) == "AU"
    assert AiDemoService.infer_visitor_region(SimpleNamespace(whatsapp_e164="+353871234567", preferred_language="en", voice_region=None)) == "IE"
    assert AiDemoService.infer_visitor_region(SimpleNamespace(whatsapp_e164="+966501234567", preferred_language="en", voice_region=None)) == "SA"
    assert AiDemoService.infer_visitor_region(SimpleNamespace(whatsapp_e164="+201001234567", preferred_language="en", voice_region=None)) == "EG"
    assert AiDemoService.infer_visitor_region(SimpleNamespace(whatsapp_e164="+15551234567", preferred_language="en", voice_region=None)) == "US"
    assert AiDemoService.infer_visitor_region(SimpleNamespace(whatsapp_e164="", preferred_language="ar", voice_region=None)) == "SA"
    assert AiDemoService.infer_visitor_region(SimpleNamespace(whatsapp_e164="", preferred_language="en", voice_region=None)) == "GB"


def test_admin_voice_region_override_beats_phone():
    assert (
        AiDemoService.infer_visitor_region(
            SimpleNamespace(whatsapp_e164="+447700900123", preferred_language="en", voice_region="AU")
        )
        == "AU"
    )
    assert AiDemoService.normalize_voice_region("sa") == "SA"
    assert AiDemoService.normalize_voice_region("") is None
    assert AiDemoService.normalize_voice_region(None) is None
