from datetime import datetime
from unittest.mock import MagicMock, call
from zoneinfo import ZoneInfo

import pytest

from babgwe.messaging import (
    SlackPost,
    add_candidate_reactions,
    build_daily_message,
    get_reaction_counts,
    post_daily_message,
    post_ops_alert,
)
from babgwe.recommendation import LunchOption


def test_message_omits_missing_optional_fields() -> None:
    message = build_daily_message([LunchOption("가게", "메뉴")])

    assert message.splitlines()[1] == "1. 가게 — 메뉴"
    assert "지도" not in message
    assert "추천:" not in message


def test_message_includes_present_optional_fields() -> None:
    message = build_daily_message(
        [
            LunchOption(
                "가게",
                "메뉴",
                price=10000,
                map_url="https://example.com",
                recommended_by="민지",
            )
        ]
    )

    assert "메뉴 · 10,000원 · 추천: 민지 <https://example.com|지도>" in message


def test_message_rejects_zero_candidates() -> None:
    with pytest.raises(ValueError, match="at least one"):
        build_daily_message([])


def test_post_daily_message_disables_unfurls_and_marks_connection_test() -> None:
    client = MagicMock()
    client.chat_postMessage.return_value = {"channel": "C_TEST", "ts": "123.456"}
    recommendations = [LunchOption("가게", "메뉴")]

    result = post_daily_message(
        client, "C_TEST", recommendations, connection_test=True
    )

    assert result == SlackPost(channel_id="C_TEST", message_ts="123.456")
    client.chat_postMessage.assert_called_once_with(
        channel="C_TEST",
        text="[밥괘 연결 테스트]\n\n" + build_daily_message(recommendations),
        unfurl_links=False,
        unfurl_media=False,
    )


def test_post_daily_message_rejects_missing_slack_identifiers() -> None:
    client = MagicMock()
    client.chat_postMessage.return_value = {"ok": True}

    with pytest.raises(RuntimeError, match="channel and ts"):
        post_daily_message(client, "C_TEST", [LunchOption("가게", "메뉴")])


def test_add_candidate_reactions_maps_positions_to_number_emoji() -> None:
    client = MagicMock()

    names = add_candidate_reactions(client, "C_TEST", "123.456", 3)

    assert names == ("one", "two", "three")
    assert client.reactions_add.call_args_list == [
        call(channel="C_TEST", timestamp="123.456", name="one"),
        call(channel="C_TEST", timestamp="123.456", name="two"),
        call(channel="C_TEST", timestamp="123.456", name="three"),
    ]


@pytest.mark.parametrize("count", [0, 4])
def test_add_candidate_reactions_rejects_unsupported_count(count: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 3"):
        add_candidate_reactions(MagicMock(), "C_TEST", "123.456", count)


def test_get_reaction_counts_returns_raw_slack_counts() -> None:
    client = MagicMock()
    client.reactions_get.return_value = {
        "message": {
            "reactions": [
                {"name": "one", "count": 2},
                {"name": "two", "count": 1},
                {"name": "eyes", "count": 4},
            ]
        }
    }

    counts = get_reaction_counts(client, "C_TEST", "123.456")

    assert counts == {"one": 2, "two": 1, "eyes": 4}
    client.reactions_get.assert_called_once_with(
        channel="C_TEST", timestamp="123.456", full=True
    )


def test_post_ops_alert_contains_only_operational_context() -> None:
    client = MagicMock()

    post_ops_alert(
        client,
        "C_OPS",
        stage="최근 좋아요 집계",
        outcome="기존 값을 유지함",
        error_id="a1b2c3d4",
        occurred_at=datetime(2026, 7, 20, 11, 0, tzinfo=ZoneInfo("Asia/Seoul")),
    )

    client.chat_postMessage.assert_called_once_with(
        channel="C_OPS",
        text=(
            "밥괘 운영 알림\n"
            "발생 시각: 2026-07-20 11:00:00 KST\n"
            "단계: 최근 좋아요 집계\n"
            "결과: 기존 값을 유지함\n"
            "오류 ID: a1b2c3d4"
        ),
        unfurl_links=False,
        unfurl_media=False,
    )
