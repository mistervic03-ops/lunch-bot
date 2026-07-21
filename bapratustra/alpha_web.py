"""Small Sheet-backed candidate contribution site."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from bapratustra.config import GoogleSheetsSettings, load_google_sheets_settings
from bapratustra.recommendation import LunchOption, normalize_name
from bapratustra.sheets import (
    LunchOptionRow,
    append_lunch_option,
    build_writable_sheets_service,
    read_lunch_option_rows,
)


LOGGER = logging.getLogger(__name__)
PACKAGE_ROOT = Path(__file__).parent
TEMPLATES = Jinja2Templates(directory=PACKAGE_ROOT / "templates")


class CandidateValidationError(ValueError):
    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__("candidate validation failed")
        self.errors = errors


def validate_candidate(values: dict[str, str]) -> LunchOption:
    restaurant = normalize_name(values.get("restaurant", ""))
    menu = normalize_name(values.get("menu", ""))
    errors: dict[str, str] = {}
    if not restaurant:
        errors["restaurant"] = "식당 이름을 입력해 주세요."
    if not menu:
        errors["menu"] = "메뉴 이름을 입력해 주세요."

    price_text = values.get("price", "").strip().replace(",", "")
    price: int | None = None
    if price_text:
        if not price_text.isdigit():
            errors["price"] = "가격은 0 이상의 숫자만 입력할 수 있습니다."
        else:
            price = int(price_text)

    map_url = values.get("map_url", "").strip() or None
    if map_url:
        parsed = urlparse(map_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors["map_url"] = "http 또는 https로 시작하는 링크를 입력해 주세요."

    if errors:
        raise CandidateValidationError(errors)
    return LunchOption(
        restaurant=restaurant,
        menu=menu,
        price=price,
        map_url=map_url,
        recommended_by=normalize_name(values.get("recommended_by", "")) or None,
        note=values.get("note", "").strip() or None,
    )


def find_duplicate(
    rows: tuple[LunchOptionRow, ...], option: LunchOption
) -> LunchOptionRow | None:
    restaurant = normalize_name(option.restaurant).casefold()
    menu = normalize_name(option.menu).casefold()
    return next(
        (
            row
            for row in rows
            if normalize_name(row.option.restaurant).casefold() == restaurant
            and normalize_name(row.option.menu).casefold() == menu
        ),
        None,
    )


async def _form(request: Request) -> dict[str, str]:
    values = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    return {key: items[-1] for key, items in values.items()}


def _safe_post(request: Request) -> bool:
    source = request.headers.get("origin") or request.headers.get("referer")
    if not source:
        return False
    parsed = urlparse(source)
    return parsed.scheme == request.url.scheme and parsed.netloc == request.url.netloc


def create_app(
    *,
    settings: GoogleSheetsSettings | None = None,
    service_factory: Callable[[], Any] | None = None,
) -> FastAPI:
    loaded = settings or load_google_sheets_settings()
    make_service = service_factory or (
        lambda: build_writable_sheets_service(loaded.google_service_account_file)
    )

    app = FastAPI(
        title="식당·메뉴 등록",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.mount("/static", StaticFiles(directory=PACKAGE_ROOT / "static"), name="static")

    def render_form(
        request: Request,
        *,
        values: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
        duplicate: LunchOptionRow | None = None,
        created: bool = False,
        service_error: bool = False,
        status_code: int = 200,
    ) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(
            request=request,
            name="alpha_suggest.html",
            context={
                "values": values or {},
                "errors": errors or {},
                "duplicate": duplicate,
                "created": created,
                "service_error": service_error,
                "sheet_url": loaded.lunch_sheet_url,
            },
            status_code=status_code,
        )

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/suggest", status_code=303)

    @app.get("/suggest", response_class=HTMLResponse)
    def suggest(request: Request, created: int = 0) -> HTMLResponse:
        return render_form(request, created=bool(created))

    @app.post("/suggest", response_class=HTMLResponse)
    async def create(request: Request):
        if not _safe_post(request):
            return HTMLResponse("허용되지 않은 요청입니다.", status_code=403)
        values = await _form(request)
        try:
            option = validate_candidate(values)
        except CandidateValidationError as exc:
            return render_form(request, values=values, errors=exc.errors, status_code=422)

        try:
            service = make_service()
            rows = read_lunch_option_rows(service, loaded.google_spreadsheet_id)
            duplicate = find_duplicate(rows.rows, option)
            if duplicate:
                return render_form(
                    request, values=values, duplicate=duplicate, status_code=409
                )
            append_lunch_option(service, loaded.google_spreadsheet_id, option)
        except Exception as exc:
            LOGGER.error("candidate Sheet write failed: %s", type(exc).__name__)
            return render_form(
                request, values=values, service_error=True, status_code=503
            )
        return RedirectResponse("/suggest?created=1", status_code=303)

    @app.get("/options", response_class=HTMLResponse)
    def options(request: Request, q: str = "") -> HTMLResponse:
        try:
            result = read_lunch_option_rows(
                make_service(), loaded.google_spreadsheet_id
            )
        except Exception as exc:
            LOGGER.error("candidate Sheet read failed: %s", type(exc).__name__)
            return TEMPLATES.TemplateResponse(
                request=request,
                name="alpha_options.html",
                context={
                    "candidates": (),
                    "query": q,
                    "sheet_url": loaded.lunch_sheet_url,
                    "service_error": True,
                },
                status_code=503,
            )
        search = normalize_name(q).casefold()
        candidates = tuple(
            row
            for row in result.rows
            if not search
            or search in normalize_name(row.option.restaurant).casefold()
            or search in normalize_name(row.option.menu).casefold()
        )
        return TEMPLATES.TemplateResponse(
            request=request,
            name="alpha_options.html",
            context={
                "candidates": candidates,
                "query": q,
                "sheet_url": loaded.lunch_sheet_url,
                "service_error": False,
            },
        )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
