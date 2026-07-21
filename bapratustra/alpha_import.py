"""One-way, read-only snapshot import from the current Google Sheet."""

from __future__ import annotations

from bapratustra.config import AlphaSettings, GoogleSheetsSettings
from bapratustra.database import CandidateDatabase
from bapratustra.sheets import (
    SheetSchemaError,
    build_readonly_sheets_service,
    read_lunch_option_rows,
    read_recommendation_log,
)


def import_sheet_snapshot(
    alpha: AlphaSettings, google: GoogleSheetsSettings
) -> tuple[int, int]:
    database = CandidateDatabase(alpha.database_file)
    database.initialize()
    if not database.is_empty():
        raise RuntimeError("alpha database must be empty before import")

    service = build_readonly_sheets_service(google.google_service_account_file)
    candidates = read_lunch_option_rows(service, google.google_spreadsheet_id)
    if candidates.issues:
        shown = candidates.issues[:10]
        details = "; ".join(
            f"{issue.row_number}행 {issue.reason}" for issue in shown
        )
        if len(candidates.issues) > len(shown):
            details += f"; 그 외 {len(candidates.issues) - len(shown)}행"
        raise SheetSchemaError(f"후보 시트에 제외될 행이 있어 가져오기를 중단합니다: {details}")
    entries = read_recommendation_log(service, google.google_spreadsheet_id)
    database.import_snapshot(
        tuple((row.active, row.option) for row in candidates.rows), entries
    )
    counts = database.counts()
    if counts != (len(candidates.rows), len(entries)):
        raise RuntimeError("imported row counts do not match the Sheet snapshot")
    return counts
