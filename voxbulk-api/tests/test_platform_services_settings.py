from app.services.org_enabled_services import (
    DEFAULT_ENABLED_SERVICES,
    org_uses_platform_default_allowed,
    parse_enabled_services,
)


class _Org:
    def __init__(self, allowed_services_json=None):
        self.allowed_services_json = allowed_services_json


def test_parse_uses_platform_default_when_org_override_missing():
    platform = dict(DEFAULT_ENABLED_SERVICES)
    platform["customer_feedback"] = True
    parsed = parse_enabled_services(None, platform_default=platform)
    assert parsed["customer_feedback"] is True


def test_org_uses_platform_default_when_json_null():
    assert org_uses_platform_default_allowed(_Org(None)) is True
    assert org_uses_platform_default_allowed(_Org("")) is True
    assert org_uses_platform_default_allowed(_Org('{"survey": false}')) is False
