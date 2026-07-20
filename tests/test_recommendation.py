from __future__ import annotations

import random
from datetime import datetime, timezone

from babgwe.recommendation import (
    LunchOption,
    RecommendationHistory,
    normalize_name,
    select_recommendations,
)


def test_normalize_name_collapses_whitespace() -> None:
    assert normalize_name("  Bob's   Kitchen ") == "Bob's Kitchen"


def test_selects_distinct_restaurants_and_prioritizes_never_seen() -> None:
    options = [
        LunchOption("가게 A", "메뉴 1"),
        LunchOption("가게 A", "메뉴 2"),
        LunchOption("가게 B", "메뉴"),
        LunchOption("가게 C", "메뉴"),
        LunchOption("가게 D", "메뉴"),
    ]
    history = [
        RecommendationHistory(
            "가게 A", "메뉴 1", datetime(2026, 7, 1, tzinfo=timezone.utc)
        )
    ]

    result = select_recommendations(options, history, rng=random.Random(7))

    assert {item.restaurant for item in result} == {"가게 B", "가게 C", "가게 D"}


def test_selects_least_recent_menu_within_restaurant() -> None:
    options = [
        LunchOption("가게 A", "오래된 메뉴"),
        LunchOption("가게 A", "최근 메뉴"),
    ]
    history = [
        RecommendationHistory(
            "가게 A", "오래된 메뉴", datetime(2026, 6, 1, tzinfo=timezone.utc)
        ),
        RecommendationHistory(
            "가게 A", "최근 메뉴", datetime(2026, 7, 1, tzinfo=timezone.utc)
        ),
    ]

    result = select_recommendations(options, history, count=1, rng=random.Random(7))

    assert result == [LunchOption("가게 A", "오래된 메뉴")]


def test_ignores_duplicate_and_blank_candidates() -> None:
    options = [
        LunchOption("가게 A", "메뉴"),
        LunchOption(" 가게  A ", " 메뉴 "),
        LunchOption("", "메뉴"),
    ]

    result = select_recommendations(options, [], rng=random.Random(7))

    assert result == [LunchOption("가게 A", "메뉴")]
