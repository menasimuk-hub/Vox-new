"""Tests for Telnyx outbound number routing."""

from __future__ import annotations

from app.services.telnyx_number_routing_service import (
    TelnyxNumberRoutingService,
    normalize_route_list,
    resolve_from_routes,
)


def test_resolve_us_number_for_us_destination():
    routes = normalize_route_list(
        [
            {"number": "+447822002525", "regions": ["gb", "global"]},
            {"number": "+12025550178", "regions": ["us"]},
        ]
    )
    picked = resolve_from_routes(routes, destination_e164="+12025551234", fallback="+440000")
    assert picked == "+12025550178"


def test_resolve_global_fallback():
    routes = normalize_route_list([{"number": "+447822002099", "regions": ["global"]}])
    picked = resolve_from_routes(routes, destination_e164="+61491570156", fallback="+440000")
    assert picked == "+447822002099"


def test_seed_legacy_voice_routes():
    cfg = {"default_outbound_number": "+442012345678"}
    picked = TelnyxNumberRoutingService.resolve_voice_from(destination_e164="+442098765432", config=cfg)
    assert picked == "+442012345678"
