"""Read and validate employee-managed lunch options from Google Sheets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from babgwe.recommendation import LunchOption

LUNCH_OPTIONS_HEADERS = (
    "사용",
    "식당",
    "추천 메뉴",
    "가격(원)",
    "지도 링크",
    "추천인",
    "한줄 메모",
)

RECOMMENDATION_LOG_HEADERS = (
    "추천 시각",
    "추천 날짜",
    "순서",
    "식당",
    "메뉴",
    "Slack 채널 ID",
    "Slack 메시지 ID",
    "좋아요 수",
    "좋아요 집계 시각",
)

LUNCH_OPTIONS_RANGE = "lunch_options!A:G"
RECOMMENDATION_LOG_RANGE = "recommendation_log!A:I"
SHEETS_READONLY_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
KST = ZoneInfo("Asia/Seoul")
LOG_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class SheetSchemaError(ValueError):
    """Raised when a sheet cannot be interpreted safely as the documented schema."""


@dataclass(frozen=True)
class RowIssue:
    row_number: int
    reason: str


@dataclass(frozen=True)
class LunchOptionsResult:
    options: tuple[LunchOption, ...]
    issues: tuple[RowIssue, ...]


@dataclass(frozen=True)
class RecommendationLogEntry:
    recommended_at: datetime
    run_date_kst: date
    position: int
    restaurant: str
    menu: str
    slack_channel_id: str
    slack_message_ts: str
    like_count: int = 0
    likes_synced_at: datetime | None = None


def _build_sheets_service(credential_file: Path, scope: str) -> Any:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credentials = service_account.Credentials.from_service_account_file(
        str(credential_file), scopes=[scope]
    )
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def build_readonly_sheets_service(credential_file: Path) -> Any:
    """Create the official Sheets API client with read-only credentials."""
    return _build_sheets_service(credential_file, SHEETS_READONLY_SCOPE)


def build_writable_sheets_service(credential_file: Path) -> Any:
    """Create the Sheets client used only by the posting job after validation."""
    return _build_sheets_service(credential_file, SHEETS_SCOPE)


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _active(value: object) -> bool | None:
    if value is True or _text(value).casefold() == "true":
        return True
    if value is False or _text(value).casefold() == "false":
        return False
    return None


def _price(value: object) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError("price must be a non-negative integer")
    if isinstance(value, int):
        price = value
    elif isinstance(value, float) and value.is_integer():
        price = int(value)
    else:
        text = _text(value)
        if not text.isdigit():
            raise ValueError("price must be a non-negative integer")
        price = int(text)
    if price < 0:
        raise ValueError("price must be a non-negative integer")
    return price


def _map_url(value: object) -> str | None:
    text = _text(value)
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("map_url must be an http or https URL")
    return text


def parse_lunch_options(rows: Sequence[Sequence[object]]) -> LunchOptionsResult:
    """Validate raw A:G values and return active options plus row-level issues."""
    if not rows:
        raise SheetSchemaError("lunch_options is empty and has no header row")

    header = tuple(_text(value) for value in rows[0])
    if header != LUNCH_OPTIONS_HEADERS:
        raise SheetSchemaError(
            "lunch_options header must exactly match: "
            + ", ".join(LUNCH_OPTIONS_HEADERS)
        )

    options: list[LunchOption] = []
    issues: list[RowIssue] = []
    for row_number, raw_row in enumerate(rows[1:], start=2):
        values = list(raw_row[: len(LUNCH_OPTIONS_HEADERS)])
        values.extend([""] * (len(LUNCH_OPTIONS_HEADERS) - len(values)))

        if not any(_text(value) for value in values):
            continue

        active = _active(values[0])
        if active is False:
            continue
        if active is None:
            issues.append(RowIssue(row_number, "active must be TRUE or FALSE"))
            continue

        restaurant = _text(values[1])
        menu = _text(values[2])
        if not restaurant or not menu:
            issues.append(RowIssue(row_number, "restaurant and menu are required"))
            continue

        try:
            price = _price(values[3])
            map_url = _map_url(values[4])
        except ValueError as exc:
            issues.append(RowIssue(row_number, str(exc)))
            continue

        options.append(
            LunchOption(
                restaurant=restaurant,
                menu=menu,
                price=price,
                map_url=map_url,
                recommended_by=_text(values[5]) or None,
                note=_text(values[6]) or None,
            )
        )

    return LunchOptionsResult(tuple(options), tuple(issues))


def read_lunch_options(service: Any, spreadsheet_id: str) -> LunchOptionsResult:
    """Fetch the lunch_options tab once and parse it without mutating the sheet."""
    response = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=LUNCH_OPTIONS_RANGE,
            majorDimension="ROWS",
            valueRenderOption="UNFORMATTED_VALUE",
        )
        .execute()
    )
    return parse_lunch_options(response.get("values", []))


def _log_error(row_number: int, reason: str) -> SheetSchemaError:
    return SheetSchemaError(f"recommendation_log {row_number}행: {reason}")


def _parse_log_datetime(
    value: object, row_number: int, label: str, *, optional: bool = False
) -> datetime | None:
    text = _text(value)
    if optional and not text:
        return None
    try:
        return datetime.strptime(text, LOG_DATETIME_FORMAT).replace(tzinfo=KST)
    except ValueError as exc:
        raise _log_error(
            row_number, f"{label}은 YYYY-MM-DD HH:MM:SS 형식이어야 합니다"
        ) from exc


def _parse_log_integer(
    value: object, row_number: int, label: str, *, minimum: int, maximum: int | None = None
) -> int:
    if isinstance(value, bool):
        raise _log_error(row_number, f"{label} 값이 올바르지 않습니다")
    if isinstance(value, int):
        result = value
    elif isinstance(value, float) and value.is_integer():
        result = int(value)
    else:
        text = _text(value)
        if not text.isdigit():
            raise _log_error(row_number, f"{label} 값이 올바르지 않습니다")
        result = int(text)
    if result < minimum or (maximum is not None and result > maximum):
        raise _log_error(row_number, f"{label} 값이 올바르지 않습니다")
    return result


def parse_recommendation_log(
    rows: Sequence[Sequence[object]],
) -> tuple[RecommendationLogEntry, ...]:
    """Parse the protected bot log, failing closed on any malformed row."""
    if not rows:
        raise SheetSchemaError("recommendation_log is empty and has no header row")

    header = tuple(_text(value) for value in rows[0])
    if header != RECOMMENDATION_LOG_HEADERS:
        raise SheetSchemaError(
            "recommendation_log header must exactly match: "
            + ", ".join(RECOMMENDATION_LOG_HEADERS)
        )

    entries: list[RecommendationLogEntry] = []
    for row_number, raw_row in enumerate(rows[1:], start=2):
        values = list(raw_row[: len(RECOMMENDATION_LOG_HEADERS)])
        values.extend([""] * (len(RECOMMENDATION_LOG_HEADERS) - len(values)))
        if not any(_text(value) for value in values):
            continue

        recommended_at = _parse_log_datetime(values[0], row_number, "추천 시각")
        try:
            run_date_kst = date.fromisoformat(_text(values[1]))
        except ValueError as exc:
            raise _log_error(
                row_number, "추천 날짜는 YYYY-MM-DD 형식이어야 합니다"
            ) from exc
        position = _parse_log_integer(
            values[2], row_number, "순서", minimum=1, maximum=3
        )
        restaurant = _text(values[3])
        menu = _text(values[4])
        slack_channel_id = _text(values[5])
        slack_message_ts = _text(values[6])
        if not all((restaurant, menu, slack_channel_id, slack_message_ts)):
            raise _log_error(
                row_number,
                "식당, 메뉴, Slack 채널 ID와 Slack 메시지 ID는 필수값입니다",
            )
        like_count = _parse_log_integer(
            values[7], row_number, "좋아요 수", minimum=0
        )
        likes_synced_at = _parse_log_datetime(
            values[8], row_number, "좋아요 집계 시각", optional=True
        )
        assert recommended_at is not None
        if recommended_at.date() != run_date_kst:
            raise _log_error(
                row_number,
                "추천 시각의 KST 날짜와 추천 날짜가 일치해야 합니다",
            )

        entries.append(
            RecommendationLogEntry(
                recommended_at=recommended_at,
                run_date_kst=run_date_kst,
                position=position,
                restaurant=restaurant,
                menu=menu,
                slack_channel_id=slack_channel_id,
                slack_message_ts=slack_message_ts,
                like_count=like_count,
                likes_synced_at=likes_synced_at,
            )
        )

    return tuple(entries)


def read_recommendation_log(
    service: Any, spreadsheet_id: str
) -> tuple[RecommendationLogEntry, ...]:
    """Read and validate all recommendation log rows."""
    response = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=RECOMMENDATION_LOG_RANGE,
            majorDimension="ROWS",
            valueRenderOption="UNFORMATTED_VALUE",
        )
        .execute()
    )
    return parse_recommendation_log(response.get("values", []))


def _log_row(entry: RecommendationLogEntry) -> list[object]:
    return [
        entry.recommended_at.astimezone(KST).strftime(LOG_DATETIME_FORMAT),
        entry.run_date_kst.isoformat(),
        entry.position,
        entry.restaurant,
        entry.menu,
        entry.slack_channel_id,
        entry.slack_message_ts,
        entry.like_count,
        (
            entry.likes_synced_at.astimezone(KST).strftime(LOG_DATETIME_FORMAT)
            if entry.likes_synced_at
            else ""
        ),
    ]


def append_recommendation_log(
    service: Any,
    spreadsheet_id: str,
    entries: Sequence[RecommendationLogEntry],
) -> None:
    """Append one posted message's entries in a single Sheets API request."""
    if not entries:
        return
    response = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=spreadsheet_id,
            range=RECOMMENDATION_LOG_RANGE,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [_log_row(entry) for entry in entries]},
        )
        .execute()
    )
    updated_rows = response.get("updates", {}).get("updatedRows")
    if updated_rows != len(entries):
        raise RuntimeError(
            f"recommendation_log append updated {updated_rows} rows; "
            f"expected {len(entries)}"
        )
