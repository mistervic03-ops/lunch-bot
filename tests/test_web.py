from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from bapratustra.config import GoogleSheetsSettings
from bapratustra.leaderboard import build_leaderboard
from bapratustra.recommendation import LunchOption
from bapratustra.sheets import RecommendationLogEntry
from bapratustra.web import create_app


def _settings() -> GoogleSheetsSettings:
    return GoogleSheetsSettings("sheet-id", Path("credential.json"))


def test_leaderboard_page_renders_snapshot_and_sheet_link() -> None:
    snapshot = build_leaderboard(
        [
            LunchOption(
                "가게",
                "메뉴",
                map_url="https://map.example/place",
                recommended_by="민지",
            )
        ],
        [
            RecommendationLogEntry(
                recommended_at=datetime(
                    2026, 7, 20, 11, 0, tzinfo=ZoneInfo("Asia/Seoul")
                ),
                run_date_kst=date(2026, 7, 20),
                position=1,
                restaurant="가게",
                menu="메뉴",
                slack_channel_id="C_LUNCH",
                slack_message_ts="20.000",
                like_count=1,
            )
        ],
    )
    client = TestClient(
        create_app(settings=_settings(), snapshot_loader=lambda: snapshot)
    )

    response = client.get("/")

    assert response.status_code == 200
    assert "밥라투스트라의 전당" in response.text
    assert "인기 메뉴" in response.text
    assert '<span class="brand">밥라투스트라</span>' not in response.text
    assert '<p class="hero-kicker">사내 점심 기록</p>' in response.text
    assert "점심의 선택은 기록으로 남는다." in response.text
    assert "第一章" not in response.text
    assert "THE LUNCH ARCHIVE" not in response.text
    assert "민지" in response.text
    assert 'href="/static/leaderboard.css"' in response.text
    assert "https://docs.google.com/spreadsheets/d/sheet-id/edit" in response.text
    assert response.text.count('href="https://map.example/place"') == 2

    font_response = client.get("/static/fonts/PretendardVariable.woff2")
    assert font_response.status_code == 200
    assert font_response.headers["content-type"] == "font/woff2"


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
