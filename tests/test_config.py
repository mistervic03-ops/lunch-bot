from __future__ import annotations

from pathlib import Path

import pytest

from babgwe.config import (
    ConfigurationError,
    load_google_sheets_settings,
    load_settings,
)


REQUIRED_ENV = {
    "SLACK_BOT_TOKEN": "xoxb-test",
    "LUNCH_CHANNEL_ID": "C_LUNCH",
    "OPS_CHANNEL_ID": "C_OPS",
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
    for name in ("SLACK_BOT_TOKEN", "LUNCH_CHANNEL_ID", "OPS_CHANNEL_ID"):
        monkeypatch.delenv(name, raising=False)

    settings = load_google_sheets_settings(dotenv_path=tmp_path / "absent.env")

    assert settings.google_spreadsheet_id == "sheet-id"
    assert settings.google_service_account_file == credential
