from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


class ConfigurationError(ValueError):
    """Raised when required runtime configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    slack_bot_token: str
    lunch_channel_id: str
    ops_channel_id: str
    google_spreadsheet_id: str
    google_service_account_file: Path
    timezone: ZoneInfo

    @property
    def lunch_sheet_url(self) -> str:
        return (
            "https://docs.google.com/spreadsheets/d/"
            f"{self.google_spreadsheet_id}/edit"
        )


@dataclass(frozen=True)
class GoogleSheetsSettings:
    google_spreadsheet_id: str
    google_service_account_file: Path


@dataclass(frozen=True)
class OpsAlertSettings:
    slack_bot_token: str
    ops_channel_id: str


@dataclass(frozen=True)
class SlackServiceSettings:
    slack_app_token: str
    slack_bot_token: str


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"{name} is required")
    return value


def _google_sheets_settings() -> GoogleSheetsSettings:
    credential_file = Path(_required("GOOGLE_SERVICE_ACCOUNT_FILE")).expanduser()
    if not credential_file.is_file():
        raise ConfigurationError(
            f"GOOGLE_SERVICE_ACCOUNT_FILE does not exist: {credential_file}"
        )
    return GoogleSheetsSettings(
        google_spreadsheet_id=_required("GOOGLE_SPREADSHEET_ID"),
        google_service_account_file=credential_file,
    )


def load_google_sheets_settings(
    *, dotenv_path: str | Path | None = None
) -> GoogleSheetsSettings:
    """Load only the settings required for a read-only Sheets dry run."""
    load_dotenv(dotenv_path=dotenv_path, override=False)
    return _google_sheets_settings()


def load_ops_alert_settings(
    *, dotenv_path: str | Path | None = None
) -> OpsAlertSettings:
    """Load only the Slack settings required for a systemd failure alert."""
    load_dotenv(dotenv_path=dotenv_path, override=False)
    return OpsAlertSettings(
        slack_bot_token=_required("SLACK_BOT_TOKEN"),
        ops_channel_id=_required("OPS_CHANNEL_ID"),
    )


def load_slack_service_settings(
    *, dotenv_path: str | Path | None = None
) -> SlackServiceSettings:
    """Load only the tokens required by the Socket Mode service."""
    load_dotenv(dotenv_path=dotenv_path, override=False)
    return SlackServiceSettings(
        slack_app_token=_required("SLACK_APP_TOKEN"),
        slack_bot_token=_required("SLACK_BOT_TOKEN"),
    )


def load_settings(*, dotenv_path: str | Path | None = None) -> Settings:
    """Load settings from the environment, optionally preceded by a dotenv file."""
    load_dotenv(dotenv_path=dotenv_path, override=False)
    google = _google_sheets_settings()

    timezone_name = os.getenv("BAPRATUSTRA_TIMEZONE", "Asia/Seoul").strip()
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ConfigurationError(
            f"BAPRATUSTRA_TIMEZONE is not a known timezone: {timezone_name}"
        ) from exc

    return Settings(
        slack_bot_token=_required("SLACK_BOT_TOKEN"),
        lunch_channel_id=_required("LUNCH_CHANNEL_ID"),
        ops_channel_id=_required("OPS_CHANNEL_ID"),
        google_spreadsheet_id=google.google_spreadsheet_id,
        google_service_account_file=google.google_service_account_file,
        timezone=timezone,
    )
