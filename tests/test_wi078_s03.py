"""A classification reference gap must not erase governed Telegram slots."""

import json
from argparse import Namespace

import pytest

from kis_portfolio.adapters.batch import cli
from kis_portfolio.services.sec_issuer_info import SecIssuerInfoError, SecTickerMappingUnresolved


def _stub_downstream(monkeypatch):
    events = []
    monkeypatch.setenv("KIS_TELEGRAM_CANARY_ENABLED", "false")
    monkeypatch.setenv("KIS_TELEGRAM_REAL_USE_ENABLED", "false")
    monkeypatch.setattr(cli, "get_connection", lambda: object())
    monkeypatch.setattr(cli, "run_owned_portfolio_pipeline", lambda *a, **k: {"status": "succeeded"})

    def stage(name):
        def run(*args, **kwargs):
            events.append(name)
            return {"status": "completed"}
        return run

    monkeypatch.setattr(cli, "run_shadow_signal_evaluation", stage("shadow"))
    monkeypatch.setattr(cli, "refresh_wi029_s05_evidence", stage("shadow_evidence"))
    monkeypatch.setattr(cli, "run_telegram_delivery", stage("delivery"))
    monkeypatch.setattr(cli, "run_total_asset_digest", stage("digest"))
    monkeypatch.setattr(cli, "run_owner_portfolio_report", stage("owner_report"))
    return events


def test_0800_skips_1000_only_classification_and_reaches_reports(monkeypatch, capsys):
    events = _stub_downstream(monkeypatch)
    monkeypatch.setattr(cli, "sync_held_overseas_classifications", lambda *a, **k: pytest.fail("08:00 classification call"))

    exit_code = cli._run_owned_portfolio_v2(Namespace(
        date="20261117", slot="kr-0800", partition_key="all-accounts", requested_run_id=None,
    ))

    assert exit_code == 0
    assert events == ["shadow", "shadow_evidence", "delivery", "digest", "owner_report"]
    assert "overseas_classification" not in json.loads(capsys.readouterr().out)


def test_unresolved_1000_classification_is_deferred_but_reports_continue(monkeypatch, capsys):
    events = _stub_downstream(monkeypatch)

    def unresolved(*args, **kwargs):
        assert kwargs["source_slot"] == "kr-1000"
        raise SecTickerMappingUnresolved("SEC ticker mapping is missing or ambiguous for requested scope")

    monkeypatch.setattr(cli, "sync_held_overseas_classifications", unresolved)
    exit_code = cli._run_owned_portfolio_v2(Namespace(
        date="20261117", slot="kr-1000", partition_key="all-accounts", requested_run_id=None,
    ))

    assert exit_code == 0
    assert events == ["shadow", "shadow_evidence", "delivery", "digest", "owner_report"]
    assert json.loads(capsys.readouterr().out)["overseas_classification"] == {
        "status": "deferred", "reason": "sec_ticker_mapping_unresolved",
    }


@pytest.mark.parametrize("failure", [RuntimeError("warehouse unavailable"), SecIssuerInfoError("SEC response unavailable")])
def test_unexpected_1000_classification_failure_is_not_hidden(monkeypatch, failure):
    events = _stub_downstream(monkeypatch)

    def broken(*args, **kwargs):
        raise failure

    monkeypatch.setattr(cli, "sync_held_overseas_classifications", broken)
    with pytest.raises(type(failure), match=str(failure)):
        cli._run_owned_portfolio_v2(Namespace(
            date="20261117", slot="kr-1000", partition_key="all-accounts", requested_run_id=None,
        ))
    assert events == []
