"""Daily recommendation helpers and orchestration."""

from __future__ import annotations

import sys
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal, TypeVar
from zoneinfo import ZoneInfo

from bapratustra.config import Settings
from bapratustra.messaging import (
    NUMBER_REACTIONS,
    SlackPost,
    add_candidate_reactions,
    get_reaction_counts,
    post_daily_message,
    post_ops_alert,
)
from bapratustra.recommendation import (
    LunchOption,
    RecommendationHistory,
    select_recommendations,
)
from bapratustra.sheets import (
    RecommendationLogEntry,
    append_recommendation_log,
    read_lunch_options,
    read_recommendation_log,
    update_recommendation_likes,
)


KST = ZoneInfo("Asia/Seoul")
SAFE_RETRY_ATTEMPTS = 3
SAFE_RETRY_DELAY_SECONDS = 2.0
T = TypeVar("T")


@dataclass(frozen=True)
class DailyRunResult:
    outcome: Literal["posted", "duplicate", "failed"]
    post: SlackPost | None = None


def retry_safe_operation(
    operation: Callable[[], T],
    *,
    stage: str,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Retry an idempotent external operation with a small fixed delay."""
    for attempt in range(1, SAFE_RETRY_ATTEMPTS + 1):
        try:
            return operation()
        except Exception:
            if attempt == SAFE_RETRY_ATTEMPTS:
                raise
            print(
                f"{stage} 일시 실패 ({attempt}/{SAFE_RETRY_ATTEMPTS}); "
                f"{SAFE_RETRY_DELAY_SECONDS:g}초 후 재시도",
                file=sys.stderr,
            )
            sleep(SAFE_RETRY_DELAY_SECONDS)
    raise AssertionError("retry loop must return or raise")


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


def recent_message_entries(
    entries: Sequence[RecommendationLogEntry], *, limit: int = 5
) -> tuple[tuple[RecommendationLogEntry, ...], ...]:
    """Group the newest distinct Slack messages for bounded reaction syncing."""
    if limit < 1:
        return ()

    grouped: dict[tuple[str, str], list[RecommendationLogEntry]] = {}
    for entry in entries:
        key = (entry.slack_channel_id, entry.slack_message_ts)
        grouped.setdefault(key, []).append(entry)

    newest = sorted(
        grouped.values(),
        key=lambda group: max(entry.recommended_at for entry in group),
        reverse=True,
    )[:limit]
    return tuple(tuple(group) for group in newest)


def sync_recent_reactions(
    sheets_service: Any,
    slack_client: Any,
    spreadsheet_id: str,
    entries: Sequence[RecommendationLogEntry],
    *,
    synced_at: datetime,
    limit: int = 5,
) -> int:
    """Read recent Slack counts, then atomically submit their Sheet updates."""
    updates: list[tuple[RecommendationLogEntry, int]] = []
    for group in recent_message_entries(entries, limit=limit):
        first = group[0]
        counts = get_reaction_counts(
            slack_client, first.slack_channel_id, first.slack_message_ts
        )
        for entry in group:
            reaction_name = NUMBER_REACTIONS[entry.position - 1]
            employee_count = max(counts.get(reaction_name, 0) - 1, 0)
            updates.append((entry, employee_count))

    update_recommendation_likes(
        sheets_service,
        spreadsheet_id,
        updates,
        synced_at=synced_at,
    )
    return len(updates)


def _error_id() -> str:
    return uuid.uuid4().hex[:8]


def _alert(
    slack_client: Any,
    ops_channel_id: str,
    *,
    stage: str,
    outcome: str,
    error_id: str | None = None,
) -> None:
    try:
        post_ops_alert(
            slack_client,
            ops_channel_id,
            stage=stage,
            outcome=outcome,
            error_id=error_id,
        )
    except Exception as exc:  # The journal remains available if Slack alerting fails.
        print(
            f"운영 알림 전송 실패: {type(exc).__name__}",
            file=sys.stderr,
        )


def _failed(
    slack_client: Any,
    settings: Settings,
    *,
    stage: str,
    outcome: str,
    exc: Exception | None = None,
    post: SlackPost | None = None,
) -> DailyRunResult:
    error_id = _error_id()
    if exc is not None:
        print(
            f"밥라투스트라 작업 실패 [{error_id}] {stage}: {type(exc).__name__}",
            file=sys.stderr,
        )
    _alert(
        slack_client,
        settings.ops_channel_id,
        stage=stage,
        outcome=outcome,
        error_id=error_id,
    )
    return DailyRunResult("failed", post=post)


def run_daily_job(
    settings: Settings,
    sheets_service: Any,
    slack_client: Any,
    *,
    now: datetime | None = None,
    retry_sleep: Callable[[float], None] = time.sleep,
) -> DailyRunResult:
    """Run one bounded daily recommendation job with operational alerts."""
    run_at = now or datetime.now(tz=KST)
    if run_at.tzinfo is None or run_at.utcoffset() is None:
        raise ValueError("now must include timezone information")
    run_at_kst = run_at.astimezone(KST)

    try:
        options_result, log_entries = retry_safe_operation(
            lambda: (
                read_lunch_options(
                    sheets_service, settings.google_spreadsheet_id
                ),
                read_recommendation_log(
                    sheets_service, settings.google_spreadsheet_id
                ),
            ),
            stage="Google Sheet 읽기",
            sleep=retry_sleep,
        )
    except Exception as exc:
        return _failed(
            slack_client,
            settings,
            stage="Google Sheet 읽기",
            outcome="추천을 게시하지 않음",
            exc=exc,
        )

    try:
        retry_safe_operation(
            lambda: sync_recent_reactions(
                sheets_service,
                slack_client,
                settings.google_spreadsheet_id,
                log_entries,
                synced_at=run_at_kst,
            ),
            stage="최근 좋아요 집계",
            sleep=retry_sleep,
        )
    except Exception as exc:
        error_id = _error_id()
        print(
            f"좋아요 집계 실패 [{error_id}]: {type(exc).__name__}",
            file=sys.stderr,
        )
        _alert(
            slack_client,
            settings.ops_channel_id,
            stage="최근 좋아요 집계",
            outcome="기존 값을 유지하고 당일 추천은 계속함",
            error_id=error_id,
        )

    if has_completed_run(
        log_entries, run_at_kst.date(), settings.lunch_channel_id
    ):
        return DailyRunResult("duplicate")

    if options_result.issues:
        rows = ", ".join(str(issue.row_number) for issue in options_result.issues)
        _alert(
            slack_client,
            settings.ops_channel_id,
            stage="추천 후보 검증",
            outcome=(
                f"유효하지 않은 {len(options_result.issues)}개 행 제외 "
                f"({rows}행)"
            ),
        )

    recommendations = select_recommendations(
        options_result.options, to_recommendation_history(log_entries)
    )
    if not recommendations:
        return _failed(
            slack_client,
            settings,
            stage="추천 후보 선택",
            outcome="유효한 후보가 없어 점심 채널에 게시하지 않음",
        )

    try:
        post = post_daily_message(
            slack_client,
            settings.lunch_channel_id,
            recommendations,
            sheet_url=settings.lunch_sheet_url,
        )
    except Exception as exc:
        return _failed(
            slack_client,
            settings,
            stage="Slack 추천 게시",
            outcome="점심 채널에 게시하지 못함",
            exc=exc,
        )

    new_entries = build_recommendation_log(
        recommendations,
        published_at=run_at_kst,
        slack_channel_id=post.channel_id,
        slack_message_ts=post.message_ts,
    )
    try:
        append_recommendation_log(
            sheets_service, settings.google_spreadsheet_id, new_entries
        )
    except Exception as exc:
        return _failed(
            slack_client,
            settings,
            stage="추천 로그 기록",
            outcome=(
                "메시지는 게시됐지만 로그를 기록하지 못함; "
                "자동 재게시하지 않음"
            ),
            exc=exc,
            post=post,
        )

    try:
        add_candidate_reactions(
            slack_client, post.channel_id, post.message_ts, len(recommendations)
        )
    except Exception as exc:
        return _failed(
            slack_client,
            settings,
            stage="번호 반응 추가",
            outcome="메시지와 로그는 완료됐지만 번호 반응을 추가하지 못함",
            exc=exc,
            post=post,
        )

    return DailyRunResult("posted", post=post)
