from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import bapratustra.job as job
from bapratustra.config import Settings
from bapratustra.job import (
    DailyRunResult,
    build_recommendation_log,
    has_completed_run,
    recent_message_entries,
    run_daily_job,
    sync_recent_reactions,
    to_recommendation_history,
)
from bapratustra.messaging import SlackPost
from bapratustra.recommendation import LunchOption
from bapratustra.sheets import LunchOptionsResult, RecommendationLogEntry, RowIssue


KST = ZoneInfo("Asia/Seoul")


def _settings() -> Settings:
    return Settings(
        slack_bot_token="xoxb-test",
        lunch_channel_id="C_LUNCH",
        ops_channel_id="C_OPS",
        leaderboard_url="http://leaderboard.internal:8030/",
        google_spreadsheet_id="sheet-id",
        google_service_account_file=Path("credential.json"),
        timezone=KST,
    )


def _entry(day: int, position: int = 1) -> RecommendationLogEntry:
    return RecommendationLogEntry(
        recommended_at=datetime(2026, 7, day, 11, 0, tzinfo=KST),
        run_date_kst=date(2026, 7, day),
        position=position,
        restaurant=f"식당 {day}",
        menu=f"메뉴 {position}",
        slack_channel_id="C_LUNCH",
        slack_message_ts=f"{day}.000",
        sheet_row_number=day,
    )


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


def test_recent_message_entries_returns_only_five_newest_messages() -> None:
    entries = [_entry(day) for day in range(1, 7)]

    groups = recent_message_entries(entries)

    assert [group[0].slack_message_ts for group in groups] == [
        "6.000",
        "5.000",
        "4.000",
        "3.000",
        "2.000",
    ]


def test_sync_recent_reactions_subtracts_seed_and_updates_after_reads(
    monkeypatch,
) -> None:
    entries = [_entry(day) for day in range(1, 7)]
    actions: list[str] = []
    captured_updates = []

    def get_counts(client, channel_id, message_ts):
        actions.append(f"read:{message_ts}")
        return {"one": 3}

    def update_likes(service, spreadsheet_id, updates, synced_at):
        actions.append("update")
        captured_updates.extend(updates)

    monkeypatch.setattr(job, "get_reaction_counts", get_counts)
    monkeypatch.setattr(job, "update_recommendation_likes", update_likes)

    count = sync_recent_reactions(
        "sheets",
        "slack",
        "sheet-id",
        entries,
        synced_at=datetime(2026, 7, 20, 11, 0, tzinfo=KST),
    )

    assert count == 5
    assert actions == [
        "read:6.000",
        "read:5.000",
        "read:4.000",
        "read:3.000",
        "read:2.000",
        "update",
    ]
    assert [like_count for _, like_count in captured_updates] == [2] * 5


def test_sync_recent_reactions_does_not_write_after_partial_read_failure(
    monkeypatch,
) -> None:
    calls = 0

    def get_counts(client, channel_id, message_ts):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("Slack unavailable")
        return {"one": 2}

    monkeypatch.setattr(job, "get_reaction_counts", get_counts)
    monkeypatch.setattr(
        job,
        "update_recommendation_likes",
        lambda *args, **kwargs: pytest.fail("partial counts must not be written"),
    )

    with pytest.raises(RuntimeError, match="Slack unavailable"):
        sync_recent_reactions(
            "sheets",
            "slack",
            "sheet-id",
            [_entry(1), _entry(2)],
            synced_at=datetime(2026, 7, 20, 11, 0, tzinfo=KST),
        )


def test_run_daily_job_posts_logs_then_adds_reactions(monkeypatch) -> None:
    actions: list[str] = []
    options = LunchOptionsResult(
        options=tuple(
            LunchOption(f"식당 {number}", f"메뉴 {number}")
            for number in range(1, 4)
        ),
        issues=(RowIssue(9, "invalid"),),
    )
    alerts: list[tuple[str, str]] = []
    monkeypatch.setattr(job, "read_lunch_options", lambda *args: options)
    monkeypatch.setattr(job, "read_recommendation_log", lambda *args: ())
    monkeypatch.setattr(
        job, "sync_recent_reactions", lambda *args, **kwargs: actions.append("sync")
    )
    monkeypatch.setattr(
        job,
        "post_daily_message",
        lambda *args, **kwargs: actions.append("post")
        or SlackPost("C_LUNCH", "123.456"),
    )
    monkeypatch.setattr(
        job,
        "append_recommendation_log",
        lambda *args: actions.append("append"),
    )
    monkeypatch.setattr(
        job,
        "add_candidate_reactions",
        lambda *args: actions.append("reactions"),
    )
    monkeypatch.setattr(
        job,
        "post_ops_alert",
        lambda client, channel, *, stage, outcome, error_id=None: alerts.append(
            (stage, outcome)
        ),
    )

    result = run_daily_job(
        _settings(),
        "sheets",
        "slack",
        now=datetime(2026, 7, 20, 11, 0, tzinfo=KST),
    )

    assert result == DailyRunResult("posted", SlackPost("C_LUNCH", "123.456"))
    assert actions == ["sync", "post", "append", "reactions"]
    assert alerts == [
        ("추천 후보 검증", "유효하지 않은 1개 행 제외 (9행)")
    ]


def test_run_daily_job_retries_safe_sheet_reads(monkeypatch) -> None:
    read_attempts = 0
    delays: list[float] = []

    def read_options(*args):
        nonlocal read_attempts
        read_attempts += 1
        if read_attempts < 3:
            raise RuntimeError("temporary read failure")
        return LunchOptionsResult((LunchOption("식당", "메뉴"),), ())

    monkeypatch.setattr(job, "read_lunch_options", read_options)
    monkeypatch.setattr(job, "read_recommendation_log", lambda *args: ())
    monkeypatch.setattr(job, "sync_recent_reactions", lambda *args, **kwargs: 0)
    monkeypatch.setattr(
        job,
        "post_daily_message",
        lambda *args, **kwargs: SlackPost("C_LUNCH", "123.456"),
    )
    monkeypatch.setattr(job, "append_recommendation_log", lambda *args: None)
    monkeypatch.setattr(job, "add_candidate_reactions", lambda *args: None)

    result = run_daily_job(
        _settings(),
        "sheets",
        "slack",
        now=datetime(2026, 7, 20, 11, 0, tzinfo=KST),
        retry_sleep=delays.append,
    )

    assert result.outcome == "posted"
    assert read_attempts == 3
    assert delays == [2.0, 2.0]


def test_run_daily_job_sync_failure_alerts_but_continues(monkeypatch) -> None:
    options = LunchOptionsResult((LunchOption("식당", "메뉴"),), ())
    alerts: list[tuple[str, str, str | None]] = []
    sync_attempts = 0
    delays: list[float] = []

    def fail_sync(*args, **kwargs):
        nonlocal sync_attempts
        sync_attempts += 1
        raise RuntimeError("private")

    monkeypatch.setattr(job, "read_lunch_options", lambda *args: options)
    monkeypatch.setattr(job, "read_recommendation_log", lambda *args: ())
    monkeypatch.setattr(job, "sync_recent_reactions", fail_sync)
    monkeypatch.setattr(job, "_error_id", lambda: "sync1234")
    monkeypatch.setattr(
        job,
        "post_daily_message",
        lambda *args, **kwargs: SlackPost("C_LUNCH", "123.456"),
    )
    monkeypatch.setattr(job, "append_recommendation_log", lambda *args: None)
    monkeypatch.setattr(job, "add_candidate_reactions", lambda *args: None)
    monkeypatch.setattr(
        job,
        "post_ops_alert",
        lambda client, channel, *, stage, outcome, error_id=None: alerts.append(
            (stage, outcome, error_id)
        ),
    )

    result = run_daily_job(
        _settings(),
        "sheets",
        "slack",
        now=datetime(2026, 7, 20, 11, 0, tzinfo=KST),
        retry_sleep=delays.append,
    )

    assert result.outcome == "posted"
    assert sync_attempts == 3
    assert delays == [2.0, 2.0]
    assert alerts == [
        (
            "최근 좋아요 집계",
            "기존 값을 유지하고 당일 추천은 계속함",
            "sync1234",
        )
    ]


def test_run_daily_job_duplicate_syncs_likes_without_posting(monkeypatch) -> None:
    actions: list[str] = []
    monkeypatch.setattr(
        job,
        "read_lunch_options",
        lambda *args: LunchOptionsResult((LunchOption("식당", "메뉴"),), ()),
    )
    monkeypatch.setattr(job, "read_recommendation_log", lambda *args: (_entry(20),))
    monkeypatch.setattr(
        job, "sync_recent_reactions", lambda *args, **kwargs: actions.append("sync")
    )
    monkeypatch.setattr(
        job, "post_daily_message", lambda *args, **kwargs: actions.append("post")
    )

    result = run_daily_job(
        _settings(),
        "sheets",
        "slack",
        now=datetime(2026, 7, 20, 11, 5, tzinfo=KST),
    )

    assert result == DailyRunResult("duplicate")
    assert actions == ["sync"]


def test_run_daily_job_log_failure_does_not_add_reactions(monkeypatch) -> None:
    actions: list[str] = []
    alerts: list[str] = []
    monkeypatch.setattr(
        job,
        "read_lunch_options",
        lambda *args: LunchOptionsResult((LunchOption("식당", "메뉴"),), ()),
    )
    monkeypatch.setattr(job, "read_recommendation_log", lambda *args: ())
    monkeypatch.setattr(job, "sync_recent_reactions", lambda *args, **kwargs: 0)
    monkeypatch.setattr(
        job,
        "post_daily_message",
        lambda *args, **kwargs: SlackPost("C_LUNCH", "123.456"),
    )
    monkeypatch.setattr(
        job,
        "append_recommendation_log",
        lambda *args: (_ for _ in ()).throw(RuntimeError("write failed")),
    )
    monkeypatch.setattr(
        job,
        "add_candidate_reactions",
        lambda *args: actions.append("reactions"),
    )
    monkeypatch.setattr(job, "_error_id", lambda: "log12345")
    monkeypatch.setattr(
        job,
        "post_ops_alert",
        lambda client, channel, *, stage, outcome, error_id=None: alerts.append(stage),
    )

    result = run_daily_job(
        _settings(),
        "sheets",
        "slack",
        now=datetime(2026, 7, 20, 11, 0, tzinfo=KST),
    )

    assert result.outcome == "failed"
    assert result.post == SlackPost("C_LUNCH", "123.456")
    assert actions == []
    assert alerts == ["추천 로그 기록"]


def test_run_daily_job_post_failure_alerts_without_log(monkeypatch) -> None:
    actions: list[str] = []
    alerts: list[str] = []
    post_attempts = 0

    def fail_post(*args, **kwargs):
        nonlocal post_attempts
        post_attempts += 1
        raise RuntimeError("post failed")

    monkeypatch.setattr(
        job,
        "read_lunch_options",
        lambda *args: LunchOptionsResult((LunchOption("식당", "메뉴"),), ()),
    )
    monkeypatch.setattr(job, "read_recommendation_log", lambda *args: ())
    monkeypatch.setattr(job, "sync_recent_reactions", lambda *args, **kwargs: 0)
    monkeypatch.setattr(job, "post_daily_message", fail_post)
    monkeypatch.setattr(
        job, "append_recommendation_log", lambda *args: actions.append("append")
    )
    monkeypatch.setattr(job, "_error_id", lambda: "post1234")
    monkeypatch.setattr(
        job,
        "post_ops_alert",
        lambda client, channel, *, stage, outcome, error_id=None: alerts.append(stage),
    )

    result = run_daily_job(
        _settings(),
        "sheets",
        "slack",
        now=datetime(2026, 7, 20, 11, 0, tzinfo=KST),
    )

    assert result == DailyRunResult("failed")
    assert post_attempts == 1
    assert actions == []
    assert alerts == ["Slack 추천 게시"]


def test_run_daily_job_reaction_failure_keeps_post_and_log(monkeypatch) -> None:
    actions: list[str] = []
    alerts: list[str] = []
    monkeypatch.setattr(
        job,
        "read_lunch_options",
        lambda *args: LunchOptionsResult((LunchOption("식당", "메뉴"),), ()),
    )
    monkeypatch.setattr(job, "read_recommendation_log", lambda *args: ())
    monkeypatch.setattr(job, "sync_recent_reactions", lambda *args, **kwargs: 0)
    monkeypatch.setattr(
        job,
        "post_daily_message",
        lambda *args, **kwargs: SlackPost("C_LUNCH", "123.456"),
    )
    monkeypatch.setattr(
        job,
        "append_recommendation_log",
        lambda *args: actions.append("append"),
    )
    monkeypatch.setattr(
        job,
        "add_candidate_reactions",
        lambda *args: (_ for _ in ()).throw(RuntimeError("reaction failed")),
    )
    monkeypatch.setattr(job, "_error_id", lambda: "react123")
    monkeypatch.setattr(
        job,
        "post_ops_alert",
        lambda client, channel, *, stage, outcome, error_id=None: alerts.append(stage),
    )

    result = run_daily_job(
        _settings(),
        "sheets",
        "slack",
        now=datetime(2026, 7, 20, 11, 0, tzinfo=KST),
    )

    assert result == DailyRunResult(
        "failed", SlackPost("C_LUNCH", "123.456")
    )
    assert actions == ["append"]
    assert alerts == ["번호 반응 추가"]


def test_run_daily_job_with_no_candidates_alerts_without_post(monkeypatch) -> None:
    alerts: list[str] = []
    monkeypatch.setattr(
        job, "read_lunch_options", lambda *args: LunchOptionsResult((), ())
    )
    monkeypatch.setattr(job, "read_recommendation_log", lambda *args: ())
    monkeypatch.setattr(job, "sync_recent_reactions", lambda *args, **kwargs: 0)
    monkeypatch.setattr(job, "_error_id", lambda: "empty123")
    monkeypatch.setattr(
        job,
        "post_ops_alert",
        lambda client, channel, *, stage, outcome, error_id=None: alerts.append(stage),
    )

    result = run_daily_job(
        _settings(),
        "sheets",
        "slack",
        now=datetime(2026, 7, 20, 11, 0, tzinfo=KST),
    )

    assert result == DailyRunResult("failed")
    assert alerts == ["추천 후보 선택"]
