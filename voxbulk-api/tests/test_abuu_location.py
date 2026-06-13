from __future__ import annotations

from unittest.mock import patch

from app.core.abuu_database import run_abuu_migrations


def test_abuu_nearest_restaurants_admin(app_client):
    run_abuu_migrations()
    from tests.test_abuu_crud import _mk_superadmin

    headers = _mk_superadmin(app_client)
    resp = app_client.get(
        "/admin/abuu/restaurants/nearest",
        headers=headers,
        params={"lat": 31.9038, "lng": 35.2034},
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) >= 1
    assert "distance_km" in rows[0]
    assert rows[0]["distance_km"] >= 0


@patch("app.abuu.services.location_service.httpx.Client")
def test_abuu_nominatim_reverse_geocode(mock_client):
    from app.abuu.services.location_service import reverse_geocode

    mock_resp = mock_client.return_value.__enter__.return_value.get.return_value
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"display_name": "Ramallah, Palestine"}

    text = reverse_geocode(31.9038, 35.2034)
    assert text == "Ramallah, Palestine"
