from __future__ import annotations

from pathlib import Path

import pytest

from bapratustra.config import (
    ConfigurationError,
    load_google_sheets_settings,
    load_ops_alert_settings,
    load_slack_service_settings,
    load_settings,
)


REQUIRED_ENV = {
    "SLACK_BOT_TOKEN": "xoxb-test",
    "LUNCH_CHANNEL_ID": "C_LUNCH",
    "OPS_CHANNEL_ID": "C_OPS",
    "BAPRATUSTRA_LEADERBOARD_URL": "http://leaderboard.internal:8030/",
    "BAPRATUSTRA_CANDIDATE_URL": "http://candidate.internal/suggest",
    "GOOGLE_SPREADSHEET_ID": "sheet-id",
}


def _set_required_env(monkeypatch: pytest.MonkeyPatch, credential: Path) -> None:
    for name, value in REQUIRED_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", str(credential))


def test_load_settings_reads_required_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    credential = tmp_path / "service-account.json"
    credential.write_text("{}", encoding="utf-8")
    _set_required_env(monkeypatch, credential)

    settings = load_settings(dotenv_path=tmp_path / "absent.env")

    assert settings.lunch_channel_id == "C_LUNCH"
    assert settings.timezone.key == "Asia/Seoul"
    assert settings.google_service_account_file == credential
    assert settings.leaderboard_url == "http://leaderboard.internal:8030/"
    assert settings.candidate_url == "http://candidate.internal/suggest"
    assert settings.lunch_sheet_url == (
        "https://docs.google.com/spreadsheets/d/sheet-id/edit"
    )


def test_load_settings_uses_only_new_branded_timezone_variable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    credential = tmp_path / "service-account.json"
    credential.write_text("{}", encoding="utf-8")
    _set_required_env(monkeypatch, credential)
    monkeypatch.setenv("BAPRATUSTRA_TIMEZONE", "UTC")
    monkeypatch.setenv("BABGWE_TIMEZONE", "America/New_York")

    settings = load_settings(dotenv_path=tmp_path / "absent.env")

    assert settings.timezone.key == "UTC"


def test_load_settings_rejects_missing_required_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    credential = tmp_path / "service-account.json"
    credential.write_text("{}", encoding="utf-8")
    _set_required_env(monkeypatch, credential)
    monkeypatch.delenv("SLACK_BOT_TOKEN")

    with pytest.raises(ConfigurationError, match="SLACK_BOT_TOKEN is required"):
        load_settings(dotenv_path=tmp_path / "absent.env")


def test_load_settings_rejects_missing_credential_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_required_env(monkeypatch, tmp_path / "missing.json")

    with pytest.raises(ConfigurationError, match="does not exist"):
        load_settings(dotenv_path=tmp_path / "absent.env")


def test_load_google_sheets_settings_does_not_require_slack(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    credential = tmp_path / "service-account.json"
    credential.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", str(credential))
    for name in (
        "SLACK_BOT_TOKEN",
        "LUNCH_CHANNEL_ID",
        "OPS_CHANNEL_ID",
        "BAPRATUSTRA_LEADERBOARD_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = load_google_sheets_settings(dotenv_path=tmp_path / "absent.env")

    assert settings.google_spreadsheet_id == "sheet-id"
    assert settings.google_service_account_file == credential
    assert settings.lunch_sheet_url == (
        "https://docs.google.com/spreadsheets/d/sheet-id/edit"
    )


def test_dotenv_loading_can_be_disabled_for_leaderboard_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "GOOGLE_SPREADSHEET_ID=sheet-id\n"
        f"GOOGLE_SERVICE_ACCOUNT_FILE={tmp_path / 'credential.json'}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.delenv("GOOGLE_SPREADSHEET_ID", raising=False)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_FILE", raising=False)

    with pytest.raises(
        ConfigurationError, match="GOOGLE_SERVICE_ACCOUNT_FILE is required"
    ):
        load_google_sheets_settings(dotenv_path=dotenv)


def test_load_ops_alert_settings_does_not_require_google_or_lunch_channel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("OPS_CHANNEL_ID", "C_OPS")
    for name in (
        "LUNCH_CHANNEL_ID",
        "GOOGLE_SPREADSHEET_ID",
        "GOOGLE_SERVICE_ACCOUNT_FILE",
        "BAPRATUSTRA_LEADERBOARD_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = load_ops_alert_settings(dotenv_path=tmp_path / "absent.env")

    assert settings.slack_bot_token == "xoxb-test"
    assert settings.ops_channel_id == "C_OPS"


def test_load_slack_service_settings_requires_only_slack_tokens(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    for name in (
        "LUNCH_CHANNEL_ID",
        "OPS_CHANNEL_ID",
        "GOOGLE_SPREADSHEET_ID",
        "GOOGLE_SERVICE_ACCOUNT_FILE",
        "BAPRATUSTRA_LEADERBOARD_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = load_slack_service_settings(
        dotenv_path=tmp_path / "absent.env"
    )

    assert settings.slack_app_token == "xapp-test"
    assert settings.slack_bot_token == "xoxb-test"
