from pathlib import Path

from fastapi.testclient import TestClient

from bapratustra.alpha_web import create_app
from bapratustra.config import AlphaSettings
from bapratustra.database import CandidateDatabase, CandidateInput


ORIGIN = {"Origin": "http://testserver"}


def _client(tmp_path: Path) -> tuple[TestClient, CandidateDatabase, Path]:
    database = CandidateDatabase(tmp_path / "alpha.sqlite3")
    backups = tmp_path / "backups"
    settings = AlphaSettings(database.path, backups)
    return TestClient(create_app(settings=settings, database=database)), database, backups


def test_contribution_page_is_simple_and_database_starts_empty(tmp_path: Path) -> None:
    client, _, _ = _client(tmp_path)

    response = client.get("/suggest")

    assert response.status_code == 200
    assert "식당과 메뉴만 적으면 끝입니다" in response.text
    assert 'name="restaurant"' in response.text
    assert 'name="menu"' in response.text
    assert client.get("/healthz").json() == {
        "status": "ok",
        "candidates": 0,
        "logs": 0,
    }


def test_create_candidate_redirects_without_per_change_backup(tmp_path: Path) -> None:
    client, database, backups = _client(tmp_path)

    response = client.post(
        "/suggest",
        data={"restaurant": "식당", "menu": "메뉴", "recommended_by": "민지"},
        headers=ORIGIN,
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("?created=1")
    assert database.list_candidates()[0].recommended_by == "민지"
    assert not backups.exists()


def test_validation_and_duplicate_do_not_write_or_backup(tmp_path: Path) -> None:
    client, database, backups = _client(tmp_path)
    database.create_candidate(CandidateInput("식당", "메뉴"))

    invalid = client.post(
        "/suggest", data={"restaurant": "", "menu": ""}, headers=ORIGIN
    )
    duplicate = client.post(
        "/suggest", data={"restaurant": " 식당 ", "menu": "메뉴"}, headers=ORIGIN
    )

    assert invalid.status_code == 422
    assert "식당 이름을 입력해주세요" in invalid.text
    assert duplicate.status_code == 409
    assert "이미 같은 후보가 있습니다" in duplicate.text
    assert len(database.list_candidates()) == 1
    assert not backups.exists()


def test_edit_and_deactivate_are_recorded_without_undo_controls(tmp_path: Path) -> None:
    client, database, backups = _client(tmp_path)
    stored = database.create_candidate(CandidateInput("식당", "메뉴"))

    edited = client.post(
        f"/options/{stored.id}/edit",
        data={"restaurant": "식당", "menu": "새 메뉴", "recommended_by": "수정자"},
        headers=ORIGIN,
        follow_redirects=False,
    )
    deactivated = client.post(
        f"/options/{stored.id}/active",
        data={"active": "0", "actor": "수정자"},
        headers=ORIGIN,
        follow_redirects=False,
    )
    assert edited.status_code == deactivated.status_code == 303
    assert database.get_candidate(stored.id).active is False
    assert database.get_candidate(stored.id).menu == "새 메뉴"
    assert not backups.exists()
    assert "새 메뉴" in client.get("/options").text
    changes = client.get("/changes")
    assert "추천에서 제외" in changes.text
    assert "되돌리기" not in changes.text


def test_browser_mutations_require_same_origin(tmp_path: Path) -> None:
    client, database, _ = _client(tmp_path)

    missing = client.post("/suggest", data={"restaurant": "식당", "menu": "메뉴"})
    foreign = client.post(
        "/suggest",
        data={"restaurant": "식당", "menu": "메뉴"},
        headers={"Origin": "https://foreign.example"},
    )

    assert missing.status_code == 403
    assert foreign.status_code == 403
    assert database.list_candidates() == ()
