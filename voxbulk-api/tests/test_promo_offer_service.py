from app.services.promo_offer_service import PromoOfferError, PromoOfferService


def test_normalize_code_strips_and_uppercases():
    assert PromoOfferService.normalize_code(" sale-abc123 ") == "SALEABC123"


def test_normalize_code_rejects_short():
    try:
        PromoOfferService.normalize_code("ab")
        assert False, "expected PromoOfferError"
    except PromoOfferError:
        pass


def test_signup_url_uses_public_origin(monkeypatch):
    class _Settings:
        public_app_origin = "https://app.example.com"

    monkeypatch.setattr("app.services.promo_offer_service.get_settings", lambda: _Settings())
    assert PromoOfferService.signup_url("SALEABC") == "https://app.example.com/signin?promo=SALEABC"
