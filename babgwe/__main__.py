from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from babgwe.config import (
    ConfigurationError,
    load_google_sheets_settings,
    load_settings,
)
from babgwe.job import to_recommendation_history
from babgwe.messaging import build_daily_message
from babgwe.recommendation import select_recommendations
from babgwe.sheets import (
    SheetSchemaError,
    build_readonly_sheets_service,
    read_lunch_options,
    read_recommendation_log,
)


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


def main(argv: Sequence[str] | None = None) -> int:
    """Validate all settings or preview the real Sheet without mutating it."""
    parser = argparse.ArgumentParser(description="밥괘 운영 명령")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 Google Sheet를 읽고 추천 메시지만 미리 봅니다.",
    )
    args = parser.parse_args(argv)

    try:
        if args.dry_run:
            return run_dry_run()
        load_settings()
    except (ConfigurationError, SheetSchemaError) as exc:
        print(f"밥괘 검증 실패: {exc}", file=sys.stderr)
        return 2

    print(
        "밥괘 전체 설정이 유효합니다. "
        "Slack 게시 작업은 아직 구현되지 않았습니다."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
