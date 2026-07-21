from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from bapratustra.config import (
    ConfigurationError,
    load_google_sheets_settings,
    load_ops_alert_settings,
    load_slack_service_settings,
    load_settings,
)
from bapratustra.interactions import serve_socket_mode
from bapratustra.job import run_daily_job, to_recommendation_history
from bapratustra.messaging import (
    add_candidate_reactions,
    build_daily_message,
    get_reaction_counts,
    pin_message,
    post_daily_message,
    post_channel_onboarding,
    post_ops_alert,
)
from bapratustra.recommendation import select_recommendations
from bapratustra.sheets import (
    SheetSchemaError,
    build_readonly_sheets_service,
    build_writable_sheets_service,
    read_lunch_options,
    read_recommendation_log,
)


def run_daily() -> int:
    """Execute the production posting flow once."""
    settings = load_settings()
    sheets_service = build_writable_sheets_service(
        settings.google_service_account_file
    )
    slack_client = WebClient(token=settings.slack_bot_token)
    result = run_daily_job(settings, sheets_service, slack_client)

    if result.outcome == "posted":
        assert result.post is not None
        print(
            "밥라투스트라 게시 완료: "
            f"channel={result.post.channel_id}, ts={result.post.message_ts}"
        )
        return 0
    if result.outcome == "duplicate":
        print("오늘 이 채널의 추천이 이미 게시되어 종료합니다.")
        return 0
    print("밥라투스트라 일일 작업이 완료되지 않았습니다.", file=sys.stderr)
    return 1


def run_dry_run() -> int:
    settings = load_google_sheets_settings()
    service = build_readonly_sheets_service(settings.google_service_account_file)
    result = read_lunch_options(service, settings.google_spreadsheet_id)
    log_entries = read_recommendation_log(service, settings.google_spreadsheet_id)

    print(f"Google Sheets connection is valid: {len(result.options)} active option(s)")
    print(f"Recommendation history is valid: {len(log_entries)} row(s)")
    for issue in result.issues:
        print(f"Excluded row {issue.row_number}: {issue.reason}", file=sys.stderr)

    recommendations = select_recommendations(
        result.options, to_recommendation_history(log_entries)
    )
    if not recommendations:
        print("No valid lunch options are available for preview.", file=sys.stderr)
        return 1

    print()
    print(build_daily_message(recommendations))
    return 0


def run_slack_connection_test() -> int:
    """Post one marked test message without writing recommendation history."""
    settings = load_settings()
    sheets_service = build_readonly_sheets_service(
        settings.google_service_account_file
    )
    result = read_lunch_options(sheets_service, settings.google_spreadsheet_id)
    log_entries = read_recommendation_log(
        sheets_service, settings.google_spreadsheet_id
    )
    for issue in result.issues:
        print(f"Excluded row {issue.row_number}: {issue.reason}", file=sys.stderr)

    recommendations = select_recommendations(
        result.options, to_recommendation_history(log_entries)
    )
    if not recommendations:
        print("No valid lunch options are available for Slack test.", file=sys.stderr)
        return 1

    slack_client = WebClient(token=settings.slack_bot_token)
    post = post_daily_message(
        slack_client,
        settings.lunch_channel_id,
        recommendations,
        candidate_url=settings.candidate_url,
        leaderboard_url=settings.leaderboard_url,
        connection_test=True,
    )
    expected_reactions = add_candidate_reactions(
        slack_client,
        post.channel_id,
        post.message_ts,
        len(recommendations),
    )
    counts = get_reaction_counts(
        slack_client, post.channel_id, post.message_ts
    )
    missing = [name for name in expected_reactions if counts.get(name, 0) < 1]
    if missing:
        raise RuntimeError(
            "Slack did not return the seeded reactions: " + ", ".join(missing)
        )

    print(f"Slack connection test posted: channel={post.channel_id}, ts={post.message_ts}")
    print("Seeded reactions verified: " + ", ".join(expected_reactions))
    print("recommendation_log was not modified.")
    return 0


def post_onboarding() -> int:
    """Post the channel guide once; an admin pins it in Slack afterward."""
    settings = load_settings()
    slack_client = WebClient(token=settings.slack_bot_token)
    post = post_channel_onboarding(
        slack_client,
        settings.lunch_channel_id,
        candidate_url=settings.candidate_url,
        leaderboard_url=settings.leaderboard_url,
    )
    try:
        pin_message(slack_client, post)
    except SlackApiError:
        print(
            "온보딩 게시는 성공했지만 자동 고정에 실패했습니다: "
            f"channel={post.channel_id}, ts={post.message_ts}",
            file=sys.stderr,
        )
        raise
    print(
        "채널 온보딩 게시 및 자동 고정 완료: "
        f"channel={post.channel_id}, ts={post.message_ts}"
    )
    return 0


def run_slack_service() -> int:
    settings = load_slack_service_settings()
    try:
        serve_socket_mode(settings)
    except KeyboardInterrupt:
        print("밥라투스트라 Slack 상호작용 서비스를 종료합니다.")
    return 0


def notify_systemd_failure(unit_name: str) -> int:
    """Post a generic alert when systemd reports that the daily unit failed."""
    settings = load_ops_alert_settings()
    slack_client = WebClient(token=settings.slack_bot_token)
    post_ops_alert(
        slack_client,
        settings.ops_channel_id,
        stage="systemd 일일 작업",
        outcome=f"{unit_name} 실패; journal 확인 필요",
    )
    print(f"systemd failure alert posted: unit={unit_name}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Validate all settings or preview the real Sheet without mutating it."""
    parser = argparse.ArgumentParser(description="밥라투스트라 운영 명령")
    commands = parser.add_mutually_exclusive_group()
    commands.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 Google Sheet를 읽고 추천 메시지만 미리 봅니다.",
    )
    commands.add_argument(
        "--test-slack",
        action="store_true",
        help=(
            "테스트 채널에 표시된 연결 테스트 메시지를 한 번 게시합니다."
        ),
    )
    commands.add_argument(
        "--run-daily",
        action="store_true",
        help="좋아요를 집계하고 오늘의 추천을 실제 채널에 게시합니다.",
    )
    commands.add_argument(
        "--post-onboarding",
        action="store_true",
        help="점심 채널 안내 메시지를 한 번 게시합니다.",
    )
    commands.add_argument(
        "--run-slack-service",
        action="store_true",
        help="Slack 버튼 요청을 처리하는 Socket Mode 서비스를 실행합니다.",
    )
    commands.add_argument(
        "--notify-systemd-failure",
        metavar="UNIT",
        help="systemd 실패 unit을 운영 채널에 알립니다.",
    )
    args = parser.parse_args(argv)

    try:
        if args.dry_run:
            return run_dry_run()
        if args.test_slack:
            return run_slack_connection_test()
        if args.run_daily:
            return run_daily()
        if args.post_onboarding:
            return post_onboarding()
        if args.run_slack_service:
            return run_slack_service()
        if args.notify_systemd_failure:
            return notify_systemd_failure(args.notify_systemd_failure)
        load_settings()
    except (ConfigurationError, SheetSchemaError) as exc:
        print(f"밥라투스트라 검증 실패: {exc}", file=sys.stderr)
        return 2
    except SlackApiError as exc:
        error = exc.response.get("error", "unknown_error")
        print(f"Slack API 실패: {error}", file=sys.stderr)
        return 3

    print(
        "밥라투스트라 설정이 유효합니다. 실제 게시에는 --run-daily를 사용하세요."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
