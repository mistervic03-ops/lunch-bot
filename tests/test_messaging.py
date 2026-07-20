import pytest

from babgwe.messaging import build_daily_message
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
