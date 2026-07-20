from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from bapratustra.recommendation import LunchOption
from bapratustra.sheets import (
    LUNCH_OPTIONS_HEADERS,
    RECOMMENDATION_LOG_HEADERS,
    RecommendationLogEntry,
    RowIssue,
    SheetSchemaError,
    append_recommendation_log,
    parse_lunch_options,
    parse_recommendation_log,
    read_lunch_options,
    read_recommendation_log,
    update_recommendation_likes,
)


def test_sheet_headers_are_employee_facing_korean_labels() -> None:
    assert LUNCH_OPTIONS_HEADERS == (
        "사용",
        "식당",
        "추천 메뉴",
        "가격(원)",
        "지도 링크",
        "추천인",
        "한줄 메모",
    )
    assert RECOMMENDATION_LOG_HEADERS == (
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


def test_parse_lunch_options_returns_valid_active_rows_and_issues() -> None:
    rows = [
        list(LUNCH_OPTIONS_HEADERS),
        [True, " 마루식당 ", "제육볶음", 10000, "", "철수", " 양이 많음 "],
        [False, "비활성 식당", "메뉴"],
        [True, "", "메뉴"],
        [True, "소바집", "냉소바", -1],
        ["maybe", "분식집", "라면"],
        [],
    ]

    result = parse_lunch_options(rows)

    assert result.options == (
        LunchOption(
            restaurant="마루식당",
            menu="제육볶음",
            price=10000,
            recommended_by="철수",
            note="양이 많음",
        ),
    )
    assert result.issues == (
        RowIssue(4, "restaurant and menu are required"),
        RowIssue(5, "price must be a non-negative integer"),
        RowIssue(6, "active must be TRUE or FALSE"),
    )


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [["restaurant", "menu"]],
        [[*LUNCH_OPTIONS_HEADERS[:-1], "memo"]],
    ],
)
def test_parse_lunch_options_rejects_missing_or_changed_header(rows: list[list[str]]) -> None:
    with pytest.raises(SheetSchemaError):
        parse_lunch_options(rows)


@pytest.mark.parametrize("price", [0, 10000, 10000.0, "10000"])
def test_parse_lunch_options_accepts_non_negative_integer_prices(price: object) -> None:
    result = parse_lunch_options(
        [list(LUNCH_OPTIONS_HEADERS), [True, "식당", "메뉴", price]]
    )

    assert result.options[0].price == int(price)


@pytest.mark.parametrize("url", ["example.com", "ftp://example.com", "not a url"])
def test_parse_lunch_options_rejects_invalid_map_url(url: str) -> None:
    result = parse_lunch_options(
        [list(LUNCH_OPTIONS_HEADERS), [True, "식당", "메뉴", "", url]]
    )

    assert result.options == ()
    assert result.issues == (RowIssue(2, "map_url must be an http or https URL"),)


def test_read_lunch_options_uses_unformatted_row_values() -> None:
    service = MagicMock()
    get_request = service.spreadsheets.return_value.values.return_value.get
    get_request.return_value.execute.return_value = {
        "values": [list(LUNCH_OPTIONS_HEADERS), [True, "식당", "메뉴", 10000]]
    }

    result = read_lunch_options(service, "spreadsheet-id")

    assert result.options == (LunchOption("식당", "메뉴", price=10000),)
    get_request.assert_called_once_with(
        spreadsheetId="spreadsheet-id",
        range="lunch_options!A:G",
        majorDimension="ROWS",
        valueRenderOption="UNFORMATTED_VALUE",
    )


def test_parse_recommendation_log_returns_typed_entries() -> None:
    result = parse_recommendation_log(
        [
            list(RECOMMENDATION_LOG_HEADERS),
            [
                "2026-07-20 11:00:03",
                "2026-07-20",
                1,
                "식당",
                "메뉴",
                "C_LUNCH",
                "123.456",
                2,
                "2026-07-20 12:00:00",
            ],
        ]
    )

    assert result == (
        RecommendationLogEntry(
            recommended_at=datetime(
                2026, 7, 20, 11, 0, 3, tzinfo=ZoneInfo("Asia/Seoul")
            ),
            run_date_kst=date(2026, 7, 20),
            position=1,
            restaurant="식당",
            menu="메뉴",
            slack_channel_id="C_LUNCH",
            slack_message_ts="123.456",
            like_count=2,
            likes_synced_at=datetime(
                2026, 7, 20, 12, 0, 0, tzinfo=ZoneInfo("Asia/Seoul")
            ),
        ),
    )
    assert result[0].sheet_row_number == 2


def test_parse_recommendation_log_rejects_changed_header() -> None:
    with pytest.raises(SheetSchemaError, match="header must exactly match"):
        parse_recommendation_log([["recommended_at", "run_date_kst"]])


@pytest.mark.parametrize(
    "row, message",
    [
        (["invalid", "2026-07-20", 1, "식당", "메뉴", "C", "1", 0], "추천 시각"),
        (
            ["2026-07-20 11:00:00", "invalid", 1, "식당", "메뉴", "C", "1", 0],
            "추천 날짜",
        ),
        (
            ["2026-07-20 11:00:00", "2026-07-20", 4, "식당", "메뉴", "C", "1", 0],
            "순서",
        ),
        (
            ["2026-07-20 11:00:00", "2026-07-20", 1, "", "메뉴", "C", "1", 0],
            "필수값",
        ),
        (
            ["2026-07-20 11:00:00", "2026-07-20", 1, "식당", "메뉴", "C", "1", -1],
            "좋아요 수",
        ),
    ],
)
def test_parse_recommendation_log_rejects_malformed_bot_rows(
    row: list[object], message: str
) -> None:
    with pytest.raises(SheetSchemaError, match=message):
        parse_recommendation_log([list(RECOMMENDATION_LOG_HEADERS), row])


def test_read_recommendation_log_uses_unformatted_row_values() -> None:
    service = MagicMock()
    get_request = service.spreadsheets.return_value.values.return_value.get
    get_request.return_value.execute.return_value = {
        "values": [list(RECOMMENDATION_LOG_HEADERS)]
    }

    result = read_recommendation_log(service, "spreadsheet-id")

    assert result == ()
    get_request.assert_called_once_with(
        spreadsheetId="spreadsheet-id",
        range="recommendation_log!A:I",
        majorDimension="ROWS",
        valueRenderOption="UNFORMATTED_VALUE",
    )


def test_append_recommendation_log_inserts_all_rows_once() -> None:
    service = MagicMock()
    append_request = service.spreadsheets.return_value.values.return_value.append
    append_request.return_value.execute.return_value = {"updates": {"updatedRows": 2}}
    kst = ZoneInfo("Asia/Seoul")
    entries = (
        RecommendationLogEntry(
            recommended_at=datetime(2026, 7, 20, 11, 0, tzinfo=kst),
            run_date_kst=date(2026, 7, 20),
            position=1,
            restaurant="식당 A",
            menu="메뉴 A",
            slack_channel_id="C_LUNCH",
            slack_message_ts="123.456",
        ),
        RecommendationLogEntry(
            recommended_at=datetime(2026, 7, 20, 11, 0, tzinfo=kst),
            run_date_kst=date(2026, 7, 20),
            position=2,
            restaurant="식당 B",
            menu="메뉴 B",
            slack_channel_id="C_LUNCH",
            slack_message_ts="123.456",
        ),
    )

    append_recommendation_log(service, "spreadsheet-id", entries)

    append_request.assert_called_once_with(
        spreadsheetId="spreadsheet-id",
        range="recommendation_log!A:I",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={
            "values": [
                [
                    "2026-07-20 11:00:00",
                    "2026-07-20",
                    1,
                    "식당 A",
                    "메뉴 A",
                    "C_LUNCH",
                    "123.456",
                    0,
                    "",
                ],
                [
                    "2026-07-20 11:00:00",
                    "2026-07-20",
                    2,
                    "식당 B",
                    "메뉴 B",
                    "C_LUNCH",
                    "123.456",
                    0,
                    "",
                ],
            ]
        },
    )


def test_update_recommendation_likes_batches_sheet_rows() -> None:
    service = MagicMock()
    batch_request = service.spreadsheets.return_value.values.return_value.batchUpdate
    batch_request.return_value.execute.return_value = {"totalUpdatedRows": 2}
    kst = ZoneInfo("Asia/Seoul")
    base = dict(
        recommended_at=datetime(2026, 7, 20, 11, 0, tzinfo=kst),
        run_date_kst=date(2026, 7, 20),
        restaurant="식당",
        menu="메뉴",
        slack_channel_id="C_LUNCH",
        slack_message_ts="123.456",
    )
    first = RecommendationLogEntry(position=1, sheet_row_number=2, **base)
    second = RecommendationLogEntry(position=2, sheet_row_number=3, **base)

    update_recommendation_likes(
        service,
        "spreadsheet-id",
        [(first, 3), (second, 0)],
        synced_at=datetime(2026, 7, 21, 11, 0, 5, tzinfo=kst),
    )

    batch_request.assert_called_once_with(
        spreadsheetId="spreadsheet-id",
        body={
            "valueInputOption": "RAW",
            "data": [
                {
                    "range": "recommendation_log!H2:I2",
                    "values": [[3, "2026-07-21 11:00:05"]],
                },
                {
                    "range": "recommendation_log!H3:I3",
                    "values": [[0, "2026-07-21 11:00:05"]],
                },
            ],
        },
    )


def test_update_recommendation_likes_requires_parsed_row_number() -> None:
    entry = RecommendationLogEntry(
        recommended_at=datetime(2026, 7, 20, 11, 0, tzinfo=ZoneInfo("Asia/Seoul")),
        run_date_kst=date(2026, 7, 20),
        position=1,
        restaurant="식당",
        menu="메뉴",
        slack_channel_id="C_LUNCH",
        slack_message_ts="123.456",
    )

    with pytest.raises(ValueError, match="row number"):
        update_recommendation_likes(
            MagicMock(),
            "spreadsheet-id",
            [(entry, 1)],
            synced_at=datetime.now(tz=ZoneInfo("Asia/Seoul")),
        )


def test_update_recommendation_likes_rejects_partial_batch_response() -> None:
    service = MagicMock()
    request = service.spreadsheets.return_value.values.return_value.batchUpdate
    request.return_value.execute.return_value = {"totalUpdatedRows": 0}
    entry = RecommendationLogEntry(
        recommended_at=datetime(2026, 7, 20, 11, 0, tzinfo=ZoneInfo("Asia/Seoul")),
        run_date_kst=date(2026, 7, 20),
        position=1,
        restaurant="식당",
        menu="메뉴",
        slack_channel_id="C_LUNCH",
        slack_message_ts="123.456",
        sheet_row_number=2,
    )

    with pytest.raises(RuntimeError, match="updated 0 rows; expected 1"):
        update_recommendation_likes(
            service,
            "spreadsheet-id",
            [(entry, 1)],
            synced_at=datetime.now(tz=ZoneInfo("Asia/Seoul")),
        )
