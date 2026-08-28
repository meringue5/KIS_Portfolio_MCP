from datetime import UTC, datetime

from kis_portfolio.modules.exposure import canonical_instrument_id, resolve_instrument_classification


def test_canonical_identity_and_master_type_do_not_invent_exposure():
    assert canonical_instrument_id("krx", "0019k0") == "v1|KRX|0019K0"
    result = resolve_instrument_classification(
        market="KRX", name="TIME 미국혼합", master={"group_code": "E"},
    )
    assert result.asset_type == "etf"
    assert result.economic_exposure == "unknown"
    assert result.source == "kis_instrument_master"


def test_reasoned_owner_override_wins_but_unreasoned_override_is_ignored():
    cutoff = datetime(2026, 8, 28, tzinfo=UTC)
    ignored = resolve_instrument_classification(
        market="KRX", name="fixture", as_of=cutoff, master={"group_code": "E"},
        override={"asset_subtype": "reit", "exposure_type": "domestic_direct", "reason": ""},
    )
    assert ignored.asset_type == "etf"
    chosen = resolve_instrument_classification(
        market="KRX", name="fixture", as_of=cutoff, master={"group_code": "E"},
        override={
            "asset_subtype": "reit", "exposure_type": "domestic_direct", "reason": "owner review",
            "valid_from": "2026-01-01", "valid_to": "2027-01-01",
        },
    )
    assert chosen.asset_type == "reit"
    assert chosen.source == "owner_override"


def test_exact_route_can_establish_etf_type_but_never_economic_exposure():
    result = resolve_instrument_classification(
        market="KRX", name="new instrument", exact_route_profile_id="etf_profile.time-v1",
    )
    assert result.asset_type == "etf"
    assert result.economic_exposure == "unknown"
    unresolved = resolve_instrument_classification(market="NAS", name="Unknown security")
    assert unresolved.asset_type == "unknown"
