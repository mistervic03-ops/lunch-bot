from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from babgwe import __main__
from babgwe.recommendation import LunchOption
from babgwe.sheets import LunchOptionsResult, RowIssue


def _prepare_dry_run(monkeypatch, result: LunchOptionsResult) -> None:
    settings = SimpleNamespace(
        google_service_account_file=Path("credential.json"),
        google_spreadsheet_id="sheet-id",
    )
    monkeypatch.setattr(__main__, "load_google_sheets_settings", lambda: settings)
    monkeypatch.setattr(
        __main__, "build_readonly_sheets_service", lambda credential: "service"
    )
    monkeypatch.setattr(
        __main__, "read_lunch_options", lambda service, spreadsheet_id: result
    )
    monkeypatch.setattr(
        __main__, "read_recommendation_log", lambda service, spreadsheet_id: ()
    )


def test_dry_run_prints_preview_and_row_issues(monkeypatch, capsys) -> None:
    _prepare_dry_run(
        monkeypatch,
        LunchOptionsResult(
            options=(LunchOption("식당", "메뉴"),),
            issues=(RowIssue(3, "invalid row"),),
        ),
    )

    exit_code = __main__.main(["--dry-run"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "1 active option(s)" in captured.out
    assert "1. 식당 — 메뉴" in captured.out
    assert "Excluded row 3: invalid row" in captured.err


def test_dry_run_reports_empty_sheet_without_building_message(
    monkeypatch, capsys
) -> None:
    _prepare_dry_run(monkeypatch, LunchOptionsResult(options=(), issues=()))

    exit_code = __main__.main(["--dry-run"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "0 active option(s)" in captured.out
    assert "No valid lunch options" in captured.err
