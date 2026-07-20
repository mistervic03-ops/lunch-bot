from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from babgwe.job import (
    build_recommendation_log,
    has_completed_run,
    to_recommendation_history,
)
from babgwe.recommendation import LunchOption


def test_build_recommendation_log_uses_kst_date_and_positions() -> None:
    entries = build_recommendation_log(
        [LunchOption("식당 A", "메뉴 A"), LunchOption("식당 B", "메뉴 B")],
        published_at=datetime(2026, 7, 20, 2, 0, tzinfo=timezone.utc),
        slack_channel_id="C_LUNCH",
        slack_message_ts="123.456",
    )

    assert [entry.position for entry in entries] == [1, 2]
    assert all(entry.run_date_kst == date(2026, 7, 20) for entry in entries)
    assert all(entry.recommended_at.hour == 11 for entry in entries)
    assert all(entry.recommended_at.tzinfo == ZoneInfo("Asia/Seoul") for entry in entries)


def test_has_completed_run_matches_both_date_and_channel() -> None:
    entries = build_recommendation_log(
        [LunchOption("식당", "메뉴")],
        published_at=datetime(2026, 7, 20, 11, 0, tzinfo=ZoneInfo("Asia/Seoul")),
        slack_channel_id="C_LUNCH",
        slack_message_ts="123.456",
    )

    assert has_completed_run(entries, date(2026, 7, 20), "C_LUNCH")
    assert not has_completed_run(entries, date(2026, 7, 21), "C_LUNCH")
    assert not has_completed_run(entries, date(2026, 7, 20), "C_OTHER")

    history = to_recommendation_history(entries)
    assert history[0].restaurant == "식당"
    assert history[0].recommended_at == entries[0].recommended_at


def test_build_recommendation_log_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone"):
        build_recommendation_log(
            [LunchOption("식당", "메뉴")],
            published_at=datetime(2026, 7, 20, 11, 0),
            slack_channel_id="C_LUNCH",
            slack_message_ts="123.456",
        )
