from app.services.promo_offer_service import PromoOfferError, PromoOfferService
from app.services.sales_offer_send_service import SalesOfferSendService


def test_normalize_code_strips_and_uppercases():
    assert PromoOfferService.normalize_code(" sale-abc123 ") == "SALEABC123"


def test_normalize_code_rejects_short():
    try:
        PromoOfferService.normalize_code("ab")
        assert False, "expected PromoOfferError"
    except PromoOfferError:
        pass


def test_normalize_offer_type_maps_service_kinds():
    assert PromoOfferService.normalize_offer_type("survey") == "survey_credits"
    assert PromoOfferService.normalize_offer_type("interview") == "interview_credits"
    assert PromoOfferService.is_service_credit_offer("survey_credits")
    assert PromoOfferService.is_subscription_offer("dental_trial")


def test_offer_line_for_survey_promo():
    line = SalesOfferSendService._offer_line(
        offer_type="survey_credits",
        survey_contacts=20,
    )
    assert "20" in line
    assert "survey" in line.lower()


def test_is_wallet_voucher_offer():
    assert PromoOfferService.is_wallet_voucher_offer("sales_wallet_voucher")
    assert not PromoOfferService.is_wallet_voucher_offer("dental_trial")


def test_signup_url_uses_public_origin(monkeypatch):
    class _Settings:
        public_app_origin = "https://app.example.com"

    monkeypatch.setattr("app.services.promo_offer_service.get_settings", lambda: _Settings())
    assert PromoOfferService.signup_url("SALEABC") == "https://app.example.com/signin?promo=SALEABC"
    class _Settings:
        public_app_origin = "https://app.example.com"

    monkeypatch.setattr("app.services.promo_offer_service.get_settings", lambda: _Settings())
    assert PromoOfferService.signup_url("SALEABC") == "https://app.example.com/signin?promo=SALEABC"
