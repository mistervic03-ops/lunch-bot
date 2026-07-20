from pathlib import Path

from fastapi.testclient import TestClient

from bapratustra.config import GoogleSheetsSettings
from bapratustra.leaderboard import build_leaderboard
from bapratustra.recommendation import LunchOption
from bapratustra.web import create_app


def _settings() -> GoogleSheetsSettings:
    return GoogleSheetsSettings("sheet-id", Path("credential.json"))


def test_leaderboard_page_renders_snapshot_and_sheet_link() -> None:
    snapshot = build_leaderboard(
        [LunchOption("가게", "메뉴", recommended_by="민지")], []
    )
    client = TestClient(
        create_app(settings=_settings(), snapshot_loader=lambda: snapshot)
    )

    response = client.get("/")

    assert response.status_code == 200
    assert "점심 리더보드" in response.text
    assert "인기 메뉴" in response.text
    assert "第一章" not in response.text
    assert "THE LUNCH ARCHIVE" not in response.text
    assert "민지" in response.text
    assert 'href="/static/leaderboard.css"' in response.text
    assert "https://docs.google.com/spreadsheets/d/sheet-id/edit" in response.text


def test_leaderboard_page_returns_branded_503_without_initial_snapshot() -> None:
    def fail():
        raise RuntimeError("private")

    client = TestClient(create_app(settings=_settings(), snapshot_loader=fail))

    response = client.get("/")

    assert response.status_code == 503
    assert "잠시 길을 잃었습니다" in response.text
    assert "private" not in response.text


def test_healthz_does_not_load_google_sheet() -> None:
    def fail_if_called():
        raise AssertionError("health check must not load Sheets")

    client = TestClient(
        create_app(settings=_settings(), snapshot_loader=fail_if_called)
    )

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
