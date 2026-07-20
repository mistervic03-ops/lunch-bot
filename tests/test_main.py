from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from bapratustra import __main__
from bapratustra.job import DailyRunResult
from bapratustra.messaging import SlackPost
from bapratustra.recommendation import LunchOption
from bapratustra.sheets import LunchOptionsResult, RowIssue


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


def test_slack_connection_test_posts_reactions_without_writing_log(
    monkeypatch, capsys
) -> None:
    settings = SimpleNamespace(
        google_service_account_file=Path("credential.json"),
        google_spreadsheet_id="sheet-id",
        slack_bot_token="xoxb-test",
        lunch_channel_id="C_TEST",
    )
    result = LunchOptionsResult(
        options=(LunchOption("식당", "메뉴"),), issues=()
    )
    client = object()
    monkeypatch.setattr(__main__, "load_settings", lambda: settings)
    monkeypatch.setattr(
        __main__, "build_readonly_sheets_service", lambda credential: "service"
    )
    monkeypatch.setattr(
        __main__, "read_lunch_options", lambda service, spreadsheet_id: result
    )
    monkeypatch.setattr(
        __main__, "read_recommendation_log", lambda service, spreadsheet_id: ()
    )
    monkeypatch.setattr(__main__, "WebClient", lambda token: client)
    monkeypatch.setattr(
        __main__,
        "post_daily_message",
        lambda slack_client, channel_id, recommendations, connection_test: SlackPost(
            "C_TEST", "123.456"
        ),
    )
    monkeypatch.setattr(
        __main__,
        "add_candidate_reactions",
        lambda slack_client, channel_id, message_ts, count: ("one",),
    )
    monkeypatch.setattr(
        __main__,
        "get_reaction_counts",
        lambda slack_client, channel_id, message_ts: {"one": 1},
    )

    exit_code = __main__.main(["--test-slack"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Slack connection test posted" in captured.out
    assert "recommendation_log was not modified" in captured.out


def test_run_daily_builds_writable_clients_and_reports_success(
    monkeypatch, capsys
) -> None:
    settings = SimpleNamespace(
        google_service_account_file=Path("credential.json"),
        slack_bot_token="xoxb-test",
    )
    slack_client = object()
    monkeypatch.setattr(__main__, "load_settings", lambda: settings)
    monkeypatch.setattr(
        __main__, "build_writable_sheets_service", lambda credential: "sheets"
    )
    monkeypatch.setattr(__main__, "WebClient", lambda token: slack_client)
    monkeypatch.setattr(
        __main__,
        "run_daily_job",
        lambda loaded, sheets, slack: DailyRunResult(
            "posted", SlackPost("C_LUNCH", "123.456")
        ),
    )

    exit_code = __main__.main(["--run-daily"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "밥라투스트라 게시 완료" in captured.out
