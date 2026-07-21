from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from bapratustra import alpha_import
from bapratustra.config import AlphaSettings, GoogleSheetsSettings
from bapratustra.database import CandidateDatabase
from bapratustra.recommendation import LunchOption
from bapratustra.sheets import (
    LunchOptionRow,
    LunchOptionRowsResult,
    RecommendationLogEntry,
    RowIssue,
    SheetSchemaError,
)


def _settings(tmp_path: Path):
    return (
        AlphaSettings(tmp_path / "alpha.db", tmp_path / "backups"),
        GoogleSheetsSettings("sheet-id", tmp_path / "credential.json"),
    )


def test_import_reads_sheet_once_and_preserves_inactive_rows(monkeypatch, tmp_path: Path) -> None:
    alpha, google = _settings(tmp_path)
    rows = LunchOptionRowsResult(
        (
            LunchOptionRow(True, LunchOption("활성", "메뉴")),
            LunchOptionRow(False, LunchOption("비활성", "메뉴")),
        ),
        (),
    )
    log = RecommendationLogEntry(
        datetime(2026, 7, 21, 11, tzinfo=ZoneInfo("Asia/Seoul")),
        date(2026, 7, 21),
        1,
        "활성",
        "메뉴",
        "C",
        "1.0",
    )
    monkeypatch.setattr(alpha_import, "build_readonly_sheets_service", lambda path: "service")
    monkeypatch.setattr(alpha_import, "read_lunch_option_rows", lambda service, sheet: rows)
    monkeypatch.setattr(alpha_import, "read_recommendation_log", lambda service, sheet: (log,))

    assert alpha_import.import_sheet_snapshot(alpha, google) == (2, 1)
    stored = CandidateDatabase(alpha.database_file).list_candidates()
    assert [item.active for item in stored] == [True, False]


def test_import_fails_before_writing_when_sheet_has_invalid_rows(monkeypatch, tmp_path: Path) -> None:
    alpha, google = _settings(tmp_path)
    result = LunchOptionRowsResult((), (RowIssue(3, "invalid"),))
    monkeypatch.setattr(alpha_import, "build_readonly_sheets_service", lambda path: "service")
    monkeypatch.setattr(alpha_import, "read_lunch_option_rows", lambda service, sheet: result)

    with pytest.raises(SheetSchemaError, match="3행"):
        alpha_import.import_sheet_snapshot(alpha, google)

    assert CandidateDatabase(alpha.database_file).is_empty()
