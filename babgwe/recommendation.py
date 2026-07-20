from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Sequence


@dataclass(frozen=True)
class LunchOption:
    restaurant: str
    menu: str
    price: int | None = None
    map_url: str | None = None
    recommended_by: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class RecommendationHistory:
    restaurant: str
    menu: str
    recommended_at: datetime


def normalize_name(value: str) -> str:
    """Normalize employee-entered names for fair-rotation comparisons."""
    return " ".join(value.split())


def _utc_timestamp(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).timestamp()


def _pick_oldest(
    keys: Iterable[str],
    last_seen: dict[str, datetime],
    count: int,
    rng: random.Random,
) -> list[str]:
    ranked = list(keys)
    rng.shuffle(ranked)
    ranked.sort(
        key=lambda key: (
            key in last_seen,
            _utc_timestamp(last_seen[key]) if key in last_seen else 0.0,
        )
    )
    return ranked[:count]


def select_recommendations(
    options: Sequence[LunchOption],
    history: Sequence[RecommendationHistory],
    *,
    count: int = 3,
    rng: random.Random | None = None,
) -> list[LunchOption]:
    """Select distinct restaurants, favoring never/least-recently recommended items."""
    if count < 1:
        return []

    random_source = rng or random.Random()
    by_restaurant: dict[str, list[LunchOption]] = defaultdict(list)
    seen_options: set[tuple[str, str]] = set()

    for option in options:
        restaurant_key = normalize_name(option.restaurant)
        menu_key = normalize_name(option.menu)
        if not restaurant_key or not menu_key:
            continue
        option_key = (restaurant_key, menu_key)
        if option_key in seen_options:
            continue
        seen_options.add(option_key)
        by_restaurant[restaurant_key].append(option)

    restaurant_last_seen: dict[str, datetime] = {}
    menu_last_seen: dict[tuple[str, str], datetime] = {}
    for entry in history:
        restaurant_key = normalize_name(entry.restaurant)
        menu_key = normalize_name(entry.menu)
        current_restaurant = restaurant_last_seen.get(restaurant_key)
        if current_restaurant is None or _utc_timestamp(
            entry.recommended_at
        ) > _utc_timestamp(current_restaurant):
            restaurant_last_seen[restaurant_key] = entry.recommended_at
        menu_history_key = (restaurant_key, menu_key)
        current_menu = menu_last_seen.get(menu_history_key)
        if current_menu is None or _utc_timestamp(entry.recommended_at) > _utc_timestamp(
            current_menu
        ):
            menu_last_seen[menu_history_key] = entry.recommended_at

    selected_restaurants = _pick_oldest(
        by_restaurant,
        restaurant_last_seen,
        min(count, len(by_restaurant)),
        random_source,
    )

    selected: list[LunchOption] = []
    for restaurant_key in selected_restaurants:
        menu_keys = {
            normalize_name(option.menu): option
            for option in by_restaurant[restaurant_key]
        }
        last_seen = {
            menu_key: menu_last_seen[(restaurant_key, menu_key)]
            for menu_key in menu_keys
            if (restaurant_key, menu_key) in menu_last_seen
        }
        selected_menu = _pick_oldest(menu_keys, last_seen, 1, random_source)[0]
        selected.append(menu_keys[selected_menu])

    return selected
