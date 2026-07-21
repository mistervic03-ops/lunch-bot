"""Read-only internal leaderboard web application."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from bapratustra.config import (
    GoogleSheetsSettings,
    load_candidate_url,
    load_google_sheets_settings,
)
from bapratustra.leaderboard import (
    LeaderboardCache,
    LeaderboardSnapshot,
    build_leaderboard,
)
from bapratustra.sheets import (
    build_readonly_sheets_service,
    read_lunch_options,
    read_recommendation_log,
)


LOGGER = logging.getLogger(__name__)
PACKAGE_ROOT = Path(__file__).parent
TEMPLATES = Jinja2Templates(directory=PACKAGE_ROOT / "templates")


def load_leaderboard_snapshot(
    settings: GoogleSheetsSettings,
) -> LeaderboardSnapshot:
    service = build_readonly_sheets_service(
        settings.google_service_account_file
    )
    options = read_lunch_options(service, settings.google_spreadsheet_id)
    entries = read_recommendation_log(service, settings.google_spreadsheet_id)
    return build_leaderboard(options.options, entries)


def create_app(
    *,
    settings: GoogleSheetsSettings | None = None,
    candidate_url: str | None = None,
    snapshot_loader: Callable[[], LeaderboardSnapshot] | None = None,
    cache_seconds: float = 300,
) -> FastAPI:
    loaded_settings = settings or load_google_sheets_settings()
    loaded_candidate_url = candidate_url or load_candidate_url()
    loader = snapshot_loader or (
        lambda: load_leaderboard_snapshot(loaded_settings)
    )
    cache = LeaderboardCache(loader, ttl_seconds=cache_seconds)

    app = FastAPI(
        title="밥라투스트라의 전당",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.mount(
        "/static",
        StaticFiles(directory=PACKAGE_ROOT / "static"),
        name="static",
    )

    @app.get("/", response_class=HTMLResponse)
    def leaderboard(request: Request) -> HTMLResponse:
        try:
            snapshot = cache.get()
        except Exception as exc:
            LOGGER.error("leaderboard refresh failed: %s", type(exc).__name__)
            return TEMPLATES.TemplateResponse(
                request=request,
                name="leaderboard_error.html",
                context={"sheet_url": loaded_settings.lunch_sheet_url},
                status_code=503,
            )
        return TEMPLATES.TemplateResponse(
            request=request,
            name="leaderboard.html",
            context={
                "snapshot": snapshot,
                "candidate_url": loaded_candidate_url,
                "sheet_url": loaded_settings.lunch_sheet_url,
            },
        )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
