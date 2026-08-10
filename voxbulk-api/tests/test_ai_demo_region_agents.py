from app.services.ai_demo_service import AiDemoService
from types import SimpleNamespace


def test_infer_visitor_region_from_whatsapp():
    assert AiDemoService.infer_visitor_region(SimpleNamespace(whatsapp_e164="+447700900123", preferred_language="en")) == "GB"
    assert AiDemoService.infer_visitor_region(SimpleNamespace(whatsapp_e164="+61412345678", preferred_language="en")) == "AU"
    assert AiDemoService.infer_visitor_region(SimpleNamespace(whatsapp_e164="+353871234567", preferred_language="en")) == "IE"
    assert AiDemoService.infer_visitor_region(SimpleNamespace(whatsapp_e164="+966501234567", preferred_language="en")) == "SA"
    assert AiDemoService.infer_visitor_region(SimpleNamespace(whatsapp_e164="+201001234567", preferred_language="en")) == "EG"
    assert AiDemoService.infer_visitor_region(SimpleNamespace(whatsapp_e164="+15551234567", preferred_language="en")) == "US"
    assert AiDemoService.infer_visitor_region(SimpleNamespace(whatsapp_e164="", preferred_language="ar")) == "SA"
    assert AiDemoService.infer_visitor_region(SimpleNamespace(whatsapp_e164="", preferred_language="en")) == "GB"
