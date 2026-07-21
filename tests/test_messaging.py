from datetime import date, datetime
from unittest.mock import MagicMock, call
from zoneinfo import ZoneInfo

import pytest

from bapratustra.messaging import (
    SlackPost,
    add_candidate_reactions,
    build_daily_message,
    build_onboarding_message,
    get_reaction_counts,
    pin_message,
    post_channel_onboarding,
    post_daily_message,
    post_ops_alert,
)
from bapratustra.recommendation import LunchOption


def test_message_omits_missing_optional_fields() -> None:
    message = build_daily_message([LunchOption("가게", "메뉴")])

    assert "1. 가게 — 메뉴" in message.splitlines()
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


def test_three_candidate_message_uses_strong_character_opening() -> None:
    message = build_daily_message(
        [
            LunchOption("식당 1", "메뉴 1"),
            LunchOption("식당 2", "메뉴 2"),
            LunchOption("식당 3", "메뉴 3"),
        ],
        run_date_kst=date(2026, 7, 20),
    )

    assert message == (
        "📜 밥라투스트라는 이렇게 말했다.\n\n"
        "점심은 스스로 정해지지 않는다. 선택되어야 한다.\n"
        "오늘 그대들 앞에는 세 갈래의 길이 놓여 있다.\n\n"
        "1. 식당 1 — 메뉴 1\n"
        "2. 식당 2 — 메뉴 2\n"
        "3. 식당 3 — 메뉴 3\n\n"
        "먹고 싶은 후보 번호에 반응해 주세요."
    )


def test_three_candidate_declarations_rotate_across_weekdays() -> None:
    recommendations = [
        LunchOption("식당 1", "메뉴 1"),
        LunchOption("식당 2", "메뉴 2"),
        LunchOption("식당 3", "메뉴 3"),
    ]
    weekdays = [
        date(2026, 7, 20),
        date(2026, 7, 21),
        date(2026, 7, 22),
        date(2026, 7, 23),
        date(2026, 7, 24),
        date(2026, 7, 27),
        date(2026, 7, 28),
    ]

    declarations = [
        build_daily_message(recommendations, run_date_kst=day).split("\n\n")[1]
        for day in weekdays
    ]

    assert declarations == [
        "점심은 스스로 정해지지 않는다. 선택되어야 한다.\n"
        "오늘 그대들 앞에는 세 갈래의 길이 놓여 있다.",
        "오늘의 점심은 아직 정해지지 않았다.\n다만 세 가지 가능성이 여기 있다.",
        "정오는 다가오고, 결단의 시간도 함께 온다.\n오늘의 길은 셋이다.",
        "배고픔 앞에서 망설임은 길어지고 점심시간은 짧아진다.\n"
        "오늘의 후보는 셋이다.",
        "오늘의 깨달음은 멀리 있지 않다.\n점심은 이 세 곳 중 하나에 있다.",
        "무엇을 먹을 것인가. 그것이 오늘의 가장 현실적인 물음이다.\n"
        "세 가지 답을 가져왔다.",
        "허기는 매일 돌아오지만, 같은 선택을 반복할 이유는 없다.\n"
        "오늘의 세 갈래 길을 보라.",
    ]
    assert len(set(declarations)) == 7


@pytest.mark.parametrize(
    "recommendations, introduction",
    [
        (
            [LunchOption("식당 1", "메뉴 1")],
            "오늘 확인된 점심의 운명은 하나뿐이다.",
        ),
        (
            [
                LunchOption("식당 1", "메뉴 1"),
                LunchOption("식당 2", "메뉴 2"),
            ],
            "오늘 보이는 점심의 길은 둘뿐이다.",
        ),
    ],
)
def test_shortage_message_keeps_character_but_uses_plain_guidance(
    recommendations, introduction
) -> None:
    message = build_daily_message(recommendations)

    assert introduction in message
    assert message.endswith("새 후보는 아래 버튼에서 등록할 수 있습니다.")
    assert "먹고 싶은 후보 번호" not in message


def test_post_daily_message_disables_unfurls_and_marks_connection_test() -> None:
    client = MagicMock()
    client.chat_postMessage.return_value = {"channel": "C_TEST", "ts": "123.456"}
    recommendations = [LunchOption("가게", "메뉴")]

    result = post_daily_message(
        client,
        "C_TEST",
        recommendations,
        candidate_url="http://candidate.internal/suggest",
        leaderboard_url="http://leaderboard.internal:8030/",
        connection_test=True,
    )

    assert result == SlackPost(channel_id="C_TEST", message_ts="123.456")
    client.chat_postMessage.assert_called_once_with(
        channel="C_TEST",
        text="[밥라투스트라 연결 테스트]\n\n"
        + build_daily_message(recommendations),
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "[밥라투스트라 연결 테스트]\n\n"
                    + build_daily_message(recommendations),
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "식당·메뉴 등록",
                            "emoji": True,
                        },
                        "url": "http://candidate.internal/suggest",
                        "action_id": "open_candidate_web",
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "전당 보기",
                            "emoji": True,
                        },
                        "url": "http://leaderboard.internal:8030/",
                        "action_id": "open_leaderboard",
                    }
                ],
            },
        ],
        unfurl_links=False,
        unfurl_media=False,
    )


def test_post_daily_message_rejects_missing_slack_identifiers() -> None:
    client = MagicMock()
    client.chat_postMessage.return_value = {"ok": True}

    with pytest.raises(RuntimeError, match="channel and ts"):
        post_daily_message(
            client,
            "C_TEST",
            [LunchOption("가게", "메뉴")],
            candidate_url="http://candidate.internal/suggest",
            leaderboard_url="http://leaderboard.internal:8030/",
        )


def test_post_channel_onboarding_explains_schedule_reactions_and_sheet() -> None:
    client = MagicMock()
    client.chat_postMessage.return_value = {"channel": "C_TEST", "ts": "1.2"}

    post = post_channel_onboarding(
        client,
        "C_TEST",
        candidate_url="http://candidate.internal/suggest",
        leaderboard_url="http://leaderboard.internal:8030/",
    )

    text = build_onboarding_message()
    assert post == SlackPost("C_TEST", "1.2")
    assert "평일 오전 11시(KST)" in text
    assert "여러 곳을 골라도" in text
    assert "‘밥라투스트라의 전당’" in text
    blocks = client.chat_postMessage.call_args.kwargs["blocks"]
    assert blocks[1]["elements"][0]["url"] == "http://candidate.internal/suggest"
    assert blocks[1]["elements"][1] == {
        "type": "button",
        "text": {
            "type": "plain_text",
            "text": "전당 보기",
            "emoji": True,
        },
        "url": "http://leaderboard.internal:8030/",
        "action_id": "open_leaderboard",
    }


def test_pin_message_uses_posted_channel_and_timestamp() -> None:
    client = MagicMock()

    pin_message(client, SlackPost("C_TEST", "123.456"))

    client.pins_add.assert_called_once_with(
        channel="C_TEST", timestamp="123.456"
    )


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
            "밥라투스트라 운영 알림\n"
            "발생 시각: 2026-07-20 11:00:00 KST\n"
            "단계: 최근 좋아요 집계\n"
            "결과: 기존 값을 유지함\n"
            "오류 ID: a1b2c3d4"
        ),
        unfurl_links=False,
        unfurl_media=False,
    )
