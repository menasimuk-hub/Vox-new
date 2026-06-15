from app.services.org_enabled_services import (
    AtLeastOneServiceRequiredError,
    ServiceNotAllowedError,
    effective_services,
    merge_admin_allowed_services,
    merge_user_enabled_services,
    parse_enabled_services,
)


def test_defaults_interview_and_survey_on():
    services = parse_enabled_services(None)
    assert services["interview"] is True
    assert services["survey"] is True


def test_user_can_hide_survey_when_both_allowed():
    allowed = {"interview": True, "survey": True, "recovery": False, "follow_up": False}
    enabled = {"interview": True, "survey": True, "recovery": False, "follow_up": False}
    next_enabled = merge_user_enabled_services(allowed, enabled, {"survey": False})
    visible = effective_services(allowed, next_enabled)
    assert visible["interview"] is True
    assert visible["survey"] is False


def test_user_cannot_disable_last_visible_service():
    allowed = {"interview": True, "survey": True, "recovery": False, "follow_up": False}
    enabled = {"interview": True, "survey": False, "recovery": False, "follow_up": False}
    try:
        merge_user_enabled_services(allowed, enabled, {"interview": False})
        assert False, "expected AtLeastOneServiceRequiredError"
    except AtLeastOneServiceRequiredError:
        pass


def test_user_cannot_enable_service_not_allowed_by_admin():
    allowed = {"interview": True, "survey": False, "recovery": False, "follow_up": False}
    enabled = {"interview": True, "survey": False, "recovery": False, "follow_up": False}
    try:
        merge_user_enabled_services(allowed, enabled, {"survey": True})
        assert False, "expected ServiceNotAllowedError"
    except ServiceNotAllowedError:
        pass


def test_user_can_enable_campaigns_when_allowed():
    allowed = parse_enabled_services(None)
    allowed["campaigns"] = True
    enabled = parse_enabled_services(None)
    next_enabled = merge_user_enabled_services(allowed, enabled, {"campaigns": True})
    assert next_enabled["campaigns"] is True
    assert effective_services(allowed, next_enabled)["campaigns"] is True


def test_admin_clamp_disables_user_survey_when_removed_from_allowed():
    allowed = {"interview": True, "survey": True, "recovery": False, "follow_up": False}
    enabled = {"interview": True, "survey": True, "recovery": False, "follow_up": False}
    allowed, enabled = merge_admin_allowed_services(allowed, enabled, {"survey": False})
    assert allowed["survey"] is False
    assert enabled["survey"] is False
    assert effective_services(allowed, enabled)["interview"] is True
