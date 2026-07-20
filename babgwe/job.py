"""Pure helpers for the daily job orchestration boundary."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from zoneinfo import ZoneInfo

from babgwe.recommendation import LunchOption, RecommendationHistory
from babgwe.sheets import RecommendationLogEntry


KST = ZoneInfo("Asia/Seoul")


def build_recommendation_log(
    recommendations: Sequence[LunchOption],
    *,
    published_at: datetime,
    slack_channel_id: str,
    slack_message_ts: str,
) -> tuple[RecommendationLogEntry, ...]:
    """Build immutable log rows after a Slack message has been posted."""
    if published_at.tzinfo is None or published_at.utcoffset() is None:
        raise ValueError("published_at must include timezone information")
    published_at_kst = published_at.astimezone(KST)
    return tuple(
        RecommendationLogEntry(
            recommended_at=published_at_kst,
            run_date_kst=published_at_kst.date(),
            position=position,
            restaurant=option.restaurant,
            menu=option.menu,
            slack_channel_id=slack_channel_id,
            slack_message_ts=slack_message_ts,
        )
        for position, option in enumerate(recommendations, start=1)
    )


def has_completed_run(
    entries: Sequence[RecommendationLogEntry],
    run_date_kst: date,
    slack_channel_id: str,
) -> bool:
    """Return whether this KST date and Slack channel already has a posted run."""
    return any(
        entry.run_date_kst == run_date_kst
        and entry.slack_channel_id == slack_channel_id
        for entry in entries
    )


def to_recommendation_history(
    entries: Sequence[RecommendationLogEntry],
) -> tuple[RecommendationHistory, ...]:
    return tuple(
        RecommendationHistory(
            restaurant=entry.restaurant,
            menu=entry.menu,
            recommended_at=entry.recommended_at,
        )
        for entry in entries
    )
