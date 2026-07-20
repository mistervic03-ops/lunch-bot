"""Pure leaderboard aggregation and a small time-based snapshot cache."""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from threading import Lock

from bapratustra.recommendation import LunchOption, normalize_name
from bapratustra.sheets import RecommendationLogEntry


@dataclass(frozen=True)
class MenuStanding:
    restaurant: str
    menu: str
    likes: int
    appearances: int


@dataclass(frozen=True)
class RestaurantStanding:
    restaurant: str
    likes: int
    appearances: int


@dataclass(frozen=True)
class ContributorStanding:
    name: str
    options: int


@dataclass(frozen=True)
class LeaderboardSnapshot:
    menus: tuple[MenuStanding, ...]
    restaurants: tuple[RestaurantStanding, ...]
    contributors: tuple[ContributorStanding, ...]
    likes_synced_at: datetime | None
    total_menus: int
    total_restaurants: int
    total_contributors: int


def build_leaderboard(
    options: Sequence[LunchOption],
    entries: Sequence[RecommendationLogEntry],
    *,
    limit: int = 10,
) -> LeaderboardSnapshot:
    """Aggregate all-time likes while preserving the documented data meanings."""
    if limit < 1:
        raise ValueError("leaderboard limit must be at least one")

    menu_totals: dict[tuple[str, str], list[int]] = defaultdict(
        lambda: [0, 0]
    )
    restaurant_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for entry in entries:
        restaurant = normalize_name(entry.restaurant)
        menu = normalize_name(entry.menu)
        menu_totals[(restaurant, menu)][0] += entry.like_count
        menu_totals[(restaurant, menu)][1] += 1
        restaurant_totals[restaurant][0] += entry.like_count
        restaurant_totals[restaurant][1] += 1

    menus = sorted(
        (
            MenuStanding(restaurant, menu, totals[0], totals[1])
            for (restaurant, menu), totals in menu_totals.items()
        ),
        key=lambda item: (
            -item.likes,
            item.restaurant.casefold(),
            item.menu.casefold(),
        ),
    )[:limit]
    restaurants = sorted(
        (
            RestaurantStanding(restaurant, totals[0], totals[1])
            for restaurant, totals in restaurant_totals.items()
        ),
        key=lambda item: (-item.likes, item.restaurant.casefold()),
    )[:limit]

    contributor_totals: dict[str, int] = defaultdict(int)
    for option in options:
        if option.recommended_by:
            contributor_totals[normalize_name(option.recommended_by)] += 1
    contributors = sorted(
        (
            ContributorStanding(name, count)
            for name, count in contributor_totals.items()
        ),
        key=lambda item: (-item.options, item.name.casefold()),
    )[:limit]

    synced_values = [
        entry.likes_synced_at
        for entry in entries
        if entry.likes_synced_at is not None
    ]
    return LeaderboardSnapshot(
        menus=tuple(menus),
        restaurants=tuple(restaurants),
        contributors=tuple(contributors),
        likes_synced_at=max(synced_values) if synced_values else None,
        total_menus=len(menu_totals),
        total_restaurants=len(restaurant_totals),
        total_contributors=len(contributor_totals),
    )


class LeaderboardCache:
    """Cache one snapshot and serve it stale if a later refresh fails."""

    def __init__(
        self,
        loader: Callable[[], LeaderboardSnapshot],
        *,
        ttl_seconds: float = 300,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("cache TTL must be positive")
        self._loader = loader
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._snapshot: LeaderboardSnapshot | None = None
        self._expires_at = 0.0
        self._lock = Lock()

    def get(self) -> LeaderboardSnapshot:
        now = self._clock()
        if self._snapshot is not None and now < self._expires_at:
            return self._snapshot

        with self._lock:
            now = self._clock()
            if self._snapshot is not None and now < self._expires_at:
                return self._snapshot
            try:
                snapshot = self._loader()
            except Exception:
                if self._snapshot is None:
                    raise
                self._expires_at = now + self._ttl_seconds
                return self._snapshot
            self._snapshot = snapshot
            self._expires_at = now + self._ttl_seconds
            return snapshot
