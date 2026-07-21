from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from slack_sdk.errors import SlackApiError

from bapratustra import __main__
from bapratustra.config import AlphaSettings
from bapratustra.database import CandidateDatabase
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
        lunch_sheet_url="https://docs.google.com/sheet",
        leaderboard_url="http://leaderboard.internal:8030/",
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
        lambda slack_client, channel_id, recommendations, **kwargs: SlackPost(
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


def test_systemd_failure_notification_uses_only_ops_slack_settings(
    monkeypatch, capsys
) -> None:
    settings = SimpleNamespace(
        slack_bot_token="xoxb-test",
        ops_channel_id="C_OPS",
    )
    client = object()
    alerts = []
    monkeypatch.setattr(__main__, "load_ops_alert_settings", lambda: settings)
    monkeypatch.setattr(__main__, "WebClient", lambda token: client)
    monkeypatch.setattr(
        __main__,
        "post_ops_alert",
        lambda slack_client, channel_id, **kwargs: alerts.append(
            (slack_client, channel_id, kwargs)
        ),
    )

    exit_code = __main__.main(
        ["--notify-systemd-failure", "bapratustra.service"]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert alerts == [
        (
            client,
            "C_OPS",
            {
                "stage": "systemd 일일 작업",
                "outcome": "bapratustra.service 실패; journal 확인 필요",
            },
        )
    ]
    assert "bapratustra.service" in captured.out


def test_alpha_backup_command_keeps_only_30_snapshots(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    database = CandidateDatabase(tmp_path / "alpha.sqlite3")
    database.initialize()
    backup_directory = tmp_path / "backups"
    backup_directory.mkdir()
    for index in range(30):
        (backup_directory / f"bapratustra-202601{index:02d}.sqlite3").touch()
    monkeypatch.setattr(
        __main__,
        "load_alpha_settings",
        lambda: AlphaSettings(database.path, backup_directory),
    )

    exit_code = __main__.main(["--backup-alpha"])

    assert exit_code == 0
    assert len(list(backup_directory.glob("bapratustra-*.sqlite3"))) == 30
    assert "오래된 백업 1개 정리" in capsys.readouterr().out


def test_post_onboarding_uses_configured_channel_and_sheet(monkeypatch, capsys) -> None:
    settings = SimpleNamespace(
        slack_bot_token="xoxb-test",
        lunch_channel_id="C_LUNCH",
        lunch_sheet_url="https://docs.google.com/sheet",
        leaderboard_url="http://leaderboard.internal:8030/",
    )
    client = object()
    calls = []
    pins = []
    monkeypatch.setattr(__main__, "load_settings", lambda: settings)
    monkeypatch.setattr(__main__, "WebClient", lambda token: client)
    monkeypatch.setattr(
        __main__,
        "post_channel_onboarding",
        lambda slack_client, channel_id, **kwargs: calls.append(
            (slack_client, channel_id, kwargs)
        )
        or SlackPost("C_LUNCH", "123.456"),
    )
    monkeypatch.setattr(
        __main__, "pin_message", lambda slack_client, post: pins.append(post)
    )

    exit_code = __main__.main(["--post-onboarding"])

    assert exit_code == 0
    assert calls == [
        (
            client,
            "C_LUNCH",
            {
                "sheet_url": "https://docs.google.com/sheet",
                "leaderboard_url": "http://leaderboard.internal:8030/",
            },
        )
    ]
    assert pins == [SlackPost("C_LUNCH", "123.456")]
    assert "게시 및 자동 고정 완료" in capsys.readouterr().out


def test_post_onboarding_reports_post_location_when_auto_pin_fails(
    monkeypatch, capsys
) -> None:
    settings = SimpleNamespace(
        slack_bot_token="xoxb-test",
        lunch_channel_id="C_LUNCH",
        lunch_sheet_url="https://docs.google.com/sheet",
        leaderboard_url="http://leaderboard.internal:8030/",
    )
    monkeypatch.setattr(__main__, "load_settings", lambda: settings)
    monkeypatch.setattr(__main__, "WebClient", lambda token: object())
    monkeypatch.setattr(
        __main__,
        "post_channel_onboarding",
        lambda *args, **kwargs: SlackPost("C_LUNCH", "123.456"),
    )
    monkeypatch.setattr(
        __main__,
        "pin_message",
        lambda *args: (_ for _ in ()).throw(
            SlackApiError("pin failed", {"error": "restricted_action"})
        ),
    )

    exit_code = __main__.main(["--post-onboarding"])

    captured = capsys.readouterr()
    assert exit_code == 3
    assert "게시는 성공했지만 자동 고정에 실패" in captured.err
    assert "channel=C_LUNCH, ts=123.456" in captured.err
    assert "restricted_action" in captured.err


def test_run_slack_service_uses_minimal_service_settings(monkeypatch) -> None:
    settings = object()
    calls = []
    monkeypatch.setattr(
        __main__, "load_slack_service_settings", lambda: settings
    )
    monkeypatch.setattr(
        __main__, "serve_socket_mode", lambda loaded: calls.append(loaded)
    )

    assert __main__.main(["--run-slack-service"]) == 0
    assert calls == [settings]


def test_run_slack_service_stops_cleanly_on_keyboard_interrupt(
    monkeypatch, capsys
) -> None:
    monkeypatch.setattr(
        __main__, "load_slack_service_settings", lambda: object()
    )
    monkeypatch.setattr(
        __main__,
        "serve_socket_mode",
        lambda settings: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    assert __main__.main(["--run-slack-service"]) == 0
    assert "서비스를 종료" in capsys.readouterr().out
