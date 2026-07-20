from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from bapratustra.leaderboard import LeaderboardCache, build_leaderboard
from bapratustra.recommendation import LunchOption
from bapratustra.sheets import RecommendationLogEntry


KST = ZoneInfo("Asia/Seoul")


def _entry(
    restaurant: str,
    menu: str,
    likes: int,
    *,
    day: int,
    synced: bool = True,
) -> RecommendationLogEntry:
    timestamp = datetime(2026, 7, day, 11, 0, tzinfo=KST)
    return RecommendationLogEntry(
        recommended_at=timestamp,
        run_date_kst=date(2026, 7, day),
        position=1,
        restaurant=restaurant,
        menu=menu,
        slack_channel_id="C_LUNCH",
        slack_message_ts=f"{day}.000",
        like_count=likes,
        likes_synced_at=timestamp if synced else None,
    )


def test_build_leaderboard_aggregates_all_three_rankings() -> None:
    snapshot = build_leaderboard(
        [
            LunchOption("가게 A", "메뉴 A", recommended_by="민지"),
            LunchOption("가게 A", "메뉴 B", recommended_by="민지"),
            LunchOption("가게 B", "메뉴 C", recommended_by="철수"),
            LunchOption("가게 C", "메뉴 D"),
        ],
        [
            _entry("가게 A", "메뉴 A", 2, day=18),
            _entry("가게 A", "메뉴 A", 1, day=19),
            _entry("가게 B", "메뉴 C", 2, day=20),
        ],
    )

    assert [
        (item.restaurant, item.menu, item.likes, item.appearances)
        for item in snapshot.menus
    ] == [
        ("가게 A", "메뉴 A", 3, 2),
        ("가게 B", "메뉴 C", 2, 1),
    ]
    assert [
        (item.restaurant, item.likes, item.appearances)
        for item in snapshot.restaurants
    ] == [("가게 A", 3, 2), ("가게 B", 2, 1)]
    assert [(item.name, item.options) for item in snapshot.contributors] == [
        ("민지", 2),
        ("철수", 1),
    ]
    assert snapshot.likes_synced_at == datetime(
        2026, 7, 20, 11, 0, tzinfo=KST
    )
    assert snapshot.total_menus == 2
    assert snapshot.total_restaurants == 2
    assert snapshot.total_contributors == 2


def test_build_leaderboard_matches_sheet_tie_order_and_limit() -> None:
    snapshot = build_leaderboard(
        [],
        [
            _entry("나 식당", "메뉴", 1, day=18),
            _entry("가 식당", "후식", 1, day=19),
            _entry("가 식당", "메뉴", 1, day=20),
        ],
        limit=2,
    )

    assert [(item.restaurant, item.menu) for item in snapshot.menus] == [
        ("가 식당", "메뉴"),
        ("가 식당", "후식"),
    ]


def test_build_leaderboard_rejects_non_positive_limit() -> None:
    with pytest.raises(ValueError, match="at least one"):
        build_leaderboard([], [], limit=0)


def test_cache_loads_once_within_ttl_and_refreshes_after_expiry() -> None:
    now = [10.0]
    snapshots = [build_leaderboard([], [])]
    calls = []

    def load():
        calls.append(True)
        return snapshots[0]

    cache = LeaderboardCache(load, ttl_seconds=5, clock=lambda: now[0])

    assert cache.get() is snapshots[0]
    assert cache.get() is snapshots[0]
    now[0] = 15.0
    assert cache.get() is snapshots[0]
    assert len(calls) == 2


def test_cache_serves_previous_snapshot_when_refresh_fails() -> None:
    now = [10.0]
    snapshot = build_leaderboard([], [])
    should_fail = [False]

    def load():
        if should_fail[0]:
            raise RuntimeError("Sheets unavailable")
        return snapshot

    cache = LeaderboardCache(load, ttl_seconds=5, clock=lambda: now[0])
    assert cache.get() is snapshot

    should_fail[0] = True
    now[0] = 15.0
    assert cache.get() is snapshot
