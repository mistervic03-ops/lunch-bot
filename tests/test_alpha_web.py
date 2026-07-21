from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from bapratustra.alpha_web import (
    CandidateValidationError,
    create_app,
    validate_candidate,
)
from bapratustra.config import GoogleSheetsSettings
from bapratustra.recommendation import LunchOption
from bapratustra.sheets import LUNCH_OPTIONS_HEADERS


ORIGIN = {"Origin": "http://testserver"}


def _settings() -> GoogleSheetsSettings:
    return GoogleSheetsSettings("sheet-id", Path("credential.json"))


def _client(rows: list[list[object]]) -> tuple[TestClient, MagicMock]:
    service = MagicMock()
    service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
        "values": [list(LUNCH_OPTIONS_HEADERS), *rows]
    }
    service.spreadsheets.return_value.values.return_value.update.return_value.execute.return_value = {
        "updatedRows": 1
    }
    return (
        TestClient(create_app(settings=_settings(), service_factory=lambda: service)),
        service,
    )


def test_candidate_validation_keeps_only_two_required_fields() -> None:
    option = validate_candidate(
        {
            "restaurant": "  가게   이름 ",
            "menu": " 메뉴 ",
            "price": "10,000",
            "map_url": "https://example.com/map",
            "recommended_by": " 민지 ",
            "note": " 맵지 않음 ",
        }
    )

    assert option == LunchOption(
        restaurant="가게 이름",
        menu="메뉴",
        price=10000,
        map_url="https://example.com/map",
        recommended_by="민지",
        note="맵지 않음",
    )


def test_candidate_validation_returns_field_errors() -> None:
    with pytest.raises(CandidateValidationError) as exc_info:
        validate_candidate(
            {"restaurant": "", "menu": "", "price": "만원", "map_url": "map"}
        )

    assert set(exc_info.value.errors) == {"restaurant", "menu", "price", "map_url"}


def test_contribution_page_is_simple_and_links_to_sheet() -> None:
    client, _ = _client([])

    response = client.get("/suggest")

    assert response.status_code == 200
    assert "식당과 메뉴만 입력하면 바로 등록됩니다" in response.text
    assert "점심의 새 가능성" not in response.text
    assert '<main class="form-page">' in response.text
    assert 'class="form-grid required-fields"' in response.text
    assert 'name="restaurant"' in response.text
    assert 'name="menu"' in response.text
    assert ">후보 등록</button>" in response.text
    assert "https://docs.google.com/spreadsheets/d/sheet-id/edit" in response.text
    assert client.get("/healthz").json() == {"status": "ok"}


def test_create_candidate_writes_to_sheet_and_redirects() -> None:
    client, service = _client([])

    response = client.post(
        "/suggest",
        data={"restaurant": "식당", "menu": "메뉴", "recommended_by": "민지"},
        headers=ORIGIN,
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/suggest?created=1"
    service.spreadsheets.return_value.values.return_value.update.assert_called_once()


def test_validation_and_inactive_duplicate_do_not_write() -> None:
    client, service = _client([[False, "식당", "메뉴"]])

    invalid = client.post(
        "/suggest", data={"restaurant": "", "menu": ""}, headers=ORIGIN
    )
    duplicate = client.post(
        "/suggest", data={"restaurant": " 식당 ", "menu": "메뉴"}, headers=ORIGIN
    )

    assert invalid.status_code == 422
    assert "식당 이름을 입력해 주세요" in invalid.text
    assert duplicate.status_code == 409
    assert "추천에서 제외된 상태입니다" in duplicate.text
    service.spreadsheets.return_value.values.return_value.update.assert_not_called()


def test_options_page_reads_active_and_inactive_sheet_rows() -> None:
    client, _ = _client(
        [
            [True, "활성 식당", "메뉴", 9000, "https://map.example/place", "민지"],
            [False, "쉬는 식당", "다른 메뉴"],
        ]
    )

    response = client.get("/options")

    assert response.status_code == 200
    assert '<main class="options-page">' in response.text
    assert 'class="candidate-labels"' in response.text
    assert "활성 식당" in response.text
    assert "쉬는 식당" in response.text
    assert "추천 중" not in response.text
    assert "쉬는 중" not in response.text
    assert response.text.count("추천 제외") == 1
    assert 'href="https://map.example/place"' in response.text
    assert 'class="quiet-action"' in response.text
    assert "지도 보기" in response.text
    assert 'class="secondary-action"' in response.text
    assert "가격 · 추천인" in response.text
    assert "Google Sheet에서 편집" not in response.text
    assert "Google Sheet 관리" in response.text
    assert "살펴보기" not in response.text


def test_options_page_keeps_missing_metadata_visually_empty() -> None:
    client, _ = _client(
        [
            [True, "추천인만 있는 식당", "메뉴", "", "", "민지"],
            [True, "부가 정보 없는 식당", "메뉴"],
        ]
    )

    response = client.get("/options")

    assert response.status_code == 200
    assert ">민지 추천<" in response.text
    assert "· 민지 추천" not in response.text
    assert '<p class="meta"></p>' in response.text


def test_sheet_failure_returns_friendly_503() -> None:
    service = MagicMock()
    service.spreadsheets.return_value.values.return_value.get.return_value.execute.side_effect = RuntimeError(
        "private"
    )
    client = TestClient(
        create_app(settings=_settings(), service_factory=lambda: service)
    )

    response = client.get("/options")

    assert response.status_code == 503
    assert "후보를 불러올 수 없습니다" in response.text
    assert "private" not in response.text


def test_browser_mutations_require_same_origin() -> None:
    client, service = _client([])

    missing = client.post("/suggest", data={"restaurant": "식당", "menu": "메뉴"})
    foreign = client.post(
        "/suggest",
        data={"restaurant": "식당", "menu": "메뉴"},
        headers={"Origin": "https://foreign.example"},
    )

    assert missing.status_code == 403
    assert foreign.status_code == 403
    service.spreadsheets.return_value.values.return_value.get.assert_not_called()
