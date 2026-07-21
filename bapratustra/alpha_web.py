"""Isolated candidate-management alpha; it does not affect the live bot."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from bapratustra.config import AlphaSettings, load_alpha_settings
from bapratustra.database import (
    CandidateDatabase,
    CandidateValidationError,
    DuplicateCandidateError,
    StoredCandidate,
    validate_candidate,
)


PACKAGE_ROOT = Path(__file__).parent
TEMPLATES = Jinja2Templates(directory=PACKAGE_ROOT / "templates")


async def _form(request: Request) -> dict[str, str]:
    values = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    return {key: items[-1] for key, items in values.items()}


def _safe_post(request: Request) -> bool:
    source = request.headers.get("origin") or request.headers.get("referer")
    if not source:
        return False
    parsed = urlparse(source)
    return parsed.scheme == request.url.scheme and parsed.netloc == request.url.netloc


def _values(candidate: StoredCandidate | None = None) -> dict[str, str]:
    if candidate is None:
        return {}
    return {
        "restaurant": candidate.restaurant,
        "menu": candidate.menu,
        "price": str(candidate.price) if candidate.price is not None else "",
        "map_url": candidate.map_url or "",
        "recommended_by": candidate.recommended_by or "",
        "note": candidate.note or "",
    }


def create_app(
    *,
    settings: AlphaSettings | None = None,
    database: CandidateDatabase | None = None,
) -> FastAPI:
    loaded = settings or load_alpha_settings()
    store = database or CandidateDatabase(loaded.database_file)
    store.initialize()

    app = FastAPI(
        title="점심 후보 보태기",
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
        duplicate: StoredCandidate | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(
            request=request,
            name="alpha_suggest.html",
            context={
                "values": values or {},
                "errors": errors or {},
                "duplicate": duplicate,
            },
            status_code=status_code,
        )

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/suggest", status_code=303)

    @app.get("/suggest", response_class=HTMLResponse)
    def suggest(request: Request) -> HTMLResponse:
        return render_form(request)

    @app.post("/suggest", response_class=HTMLResponse)
    async def create(request: Request):
        if not _safe_post(request):
            return HTMLResponse("허용되지 않은 요청입니다.", status_code=403)
        values = await _form(request)
        try:
            candidate = validate_candidate(values)
            duplicate = store.find_duplicate(candidate)
            if duplicate:
                raise DuplicateCandidateError(duplicate.id)
            created = store.create_candidate(
                candidate, actor=values.get("recommended_by") or None
            )
        except CandidateValidationError as exc:
            return render_form(request, values=values, errors=exc.errors, status_code=422)
        except DuplicateCandidateError as exc:
            return render_form(
                request,
                values=values,
                duplicate=store.get_candidate(exc.existing_id),
                status_code=409,
            )
        return RedirectResponse(f"/options/{created.id}/edit?created=1", status_code=303)

    @app.get("/options", response_class=HTMLResponse)
    def options(request: Request, q: str = "") -> HTMLResponse:
        return TEMPLATES.TemplateResponse(
            request=request,
            name="alpha_options.html",
            context={"candidates": store.list_candidates(search=q), "query": q},
        )

    @app.get("/options/{candidate_id}/edit", response_class=HTMLResponse)
    def edit(
        request: Request, candidate_id: int, created: int = 0, saved: int = 0
    ) -> HTMLResponse:
        candidate = store.get_candidate(candidate_id)
        if candidate is None:
            return HTMLResponse("후보를 찾지 못했습니다.", status_code=404)
        return TEMPLATES.TemplateResponse(
            request=request,
            name="alpha_edit.html",
            context={
                "candidate": candidate,
                "values": _values(candidate),
                "errors": {},
                "duplicate": None,
                "created": bool(created),
                "saved": bool(saved),
            },
        )

    @app.post("/options/{candidate_id}/edit", response_class=HTMLResponse)
    async def update(request: Request, candidate_id: int):
        if not _safe_post(request):
            return HTMLResponse("허용되지 않은 요청입니다.", status_code=403)
        existing = store.get_candidate(candidate_id)
        if existing is None:
            return HTMLResponse("후보를 찾지 못했습니다.", status_code=404)
        values = await _form(request)
        context = {
            "candidate": existing,
            "values": values,
            "errors": {},
            "duplicate": None,
            "created": False,
            "saved": False,
        }
        try:
            candidate = validate_candidate(values)
            duplicate = store.find_duplicate(candidate)
            if duplicate and duplicate.id != candidate_id:
                raise DuplicateCandidateError(duplicate.id)
            store.update_candidate(
                candidate_id, candidate, actor=values.get("actor") or None
            )
        except CandidateValidationError as exc:
            context["errors"] = exc.errors
            return TEMPLATES.TemplateResponse(
                request=request, name="alpha_edit.html", context=context, status_code=422
            )
        except DuplicateCandidateError as exc:
            context["duplicate"] = store.get_candidate(exc.existing_id)
            return TEMPLATES.TemplateResponse(
                request=request, name="alpha_edit.html", context=context, status_code=409
            )
        return RedirectResponse(f"/options/{candidate_id}/edit?saved=1", status_code=303)

    @app.post("/options/{candidate_id}/active")
    async def set_active(request: Request, candidate_id: int):
        if not _safe_post(request):
            return HTMLResponse("허용되지 않은 요청입니다.", status_code=403)
        if store.get_candidate(candidate_id) is None:
            return HTMLResponse("후보를 찾지 못했습니다.", status_code=404)
        values = await _form(request)
        store.set_active(
            candidate_id,
            values.get("active") == "1",
            actor=values.get("actor") or None,
        )
        return RedirectResponse("/options", status_code=303)

    @app.get("/changes", response_class=HTMLResponse)
    def changes(request: Request) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(
            request=request,
            name="alpha_changes.html",
            context={"changes": store.recent_changes()},
        )

    @app.get("/healthz")
    def healthz() -> dict[str, object]:
        candidate_count, log_count = store.counts()
        return {"status": "ok", "candidates": candidate_count, "logs": log_count}

    return app
