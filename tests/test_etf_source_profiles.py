import pytest

from kis_portfolio.platform.etf_source_profiles import (
    load_etf_instrument_routes,
    load_etf_source_profiles,
    production_network_profiles,
)


def test_current_etf_profiles_and_exact_routes_are_fixture_only():
    profiles = load_etf_source_profiles()
    routes = load_etf_instrument_routes()
    assert set(profiles) == {
        "etf_profile.time-v1", "etf_profile.koact-v1", "etf_profile.rise-v1", "etf_profile.plus-v1",
    }
    assert len(routes) == 14
    assert routes["v1|KRX|0185L0"].profile_id == "etf_profile.time-v1"
    assert production_network_profiles() == ()
    with pytest.raises(PermissionError, match="not approved"):
        profiles["etf_profile.time-v1"].require_production_allowed()
    assert all(route.activation_state == "fixture_only" for route in routes.values())
