from datetime import datetime, timezone
from pathlib import Path

import pytest

from bapratustra.database import (
    CandidateDatabase,
    CandidateInput,
    CandidateValidationError,
    DuplicateCandidateError,
    validate_candidate,
)


NOW = datetime(2026, 7, 21, 1, 0, tzinfo=timezone.utc)


def _database(tmp_path: Path) -> CandidateDatabase:
    database = CandidateDatabase(tmp_path / "alpha.sqlite3")
    database.initialize()
    return database


def test_validate_candidate_keeps_only_two_required_fields() -> None:
    candidate = validate_candidate(
        {
            "restaurant": "  가게   이름 ",
            "menu": " 메뉴 ",
            "price": "10,000",
            "map_url": "https://example.com/map",
            "recommended_by": " 민지 ",
            "note": " 맵지 않음 ",
        }
    )

    assert candidate == CandidateInput(
        restaurant="가게 이름",
        menu="메뉴",
        price=10000,
        map_url="https://example.com/map",
        recommended_by="민지",
        note="맵지 않음",
    )


def test_validate_candidate_returns_field_errors() -> None:
    with pytest.raises(CandidateValidationError) as exc_info:
        validate_candidate(
            {"restaurant": "", "menu": "", "price": "만원", "map_url": "map"}
        )

    assert set(exc_info.value.errors) == {"restaurant", "menu", "price", "map_url"}


def test_candidate_lifecycle_records_changes(tmp_path: Path) -> None:
    database = _database(tmp_path)
    created = database.create_candidate(
        CandidateInput("가게", "메뉴"), actor="민지", now=NOW
    )
    updated = database.update_candidate(
        created.id,
        CandidateInput("가게", "새 메뉴", price=9000),
        actor="민지",
        now=NOW,
    )
    assert updated.menu == "새 메뉴"
    assert updated.price == 9000

    change = database.recent_changes()[0]
    assert change.action == "update"
    assert change.actor == "민지"
    assert change.before is not None
    assert change.before["menu"] == "메뉴"
    assert change.after["menu"] == "새 메뉴"


def test_candidate_duplicates_are_normalized_and_inactive_rows_are_kept(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    created = database.create_candidate(CandidateInput("가게 이름", "메뉴"), now=NOW)
    database.set_active(created.id, False, now=NOW)

    with pytest.raises(DuplicateCandidateError) as exc_info:
        database.create_candidate(CandidateInput(" 가게   이름 ", "메뉴"), now=NOW)

    assert exc_info.value.existing_id == created.id
    assert database.list_candidates()[0].active is False
    assert database.list_candidates(include_inactive=False) == ()


def test_database_backup_is_a_readable_snapshot(tmp_path: Path) -> None:
    database = _database(tmp_path)
    database.create_candidate(CandidateInput("가게", "메뉴"), now=NOW)

    backup = database.backup(tmp_path / "backups", now=NOW)
    restored = CandidateDatabase(backup)

    assert backup.name == "bapratustra-20260721T010000000000Z.sqlite3"
    assert restored.counts() == (1, 0)


def test_backup_pruning_keeps_newest_30_and_ignores_other_files(tmp_path: Path) -> None:
    database = _database(tmp_path)
    backup_directory = tmp_path / "backups"
    backup_directory.mkdir()
    for index in range(32):
        (backup_directory / f"bapratustra-202607{index:02d}.sqlite3").touch()
    unrelated = backup_directory / "manual-copy.sqlite3"
    unrelated.touch()

    removed = database.prune_backups(backup_directory, keep=30)

    assert [path.name for path in removed] == [
        "bapratustra-20260701.sqlite3",
        "bapratustra-20260700.sqlite3",
    ]
    assert len(list(backup_directory.glob("bapratustra-*.sqlite3"))) == 30
    assert unrelated.exists()
