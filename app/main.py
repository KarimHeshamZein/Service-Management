"""Application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from .config import BASE_DIR, settings
from .database import init_db
from .deps import RedirectToLogin, login_redirect
from .helpers import localized_json, render
from .routers import (
    admin,
    auth,
    dashboard,
    general_maintenance,
    installations,
    maintenance,
    pricing,
    records,
    reports,
    settings as settings_router,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="sms_session",
        max_age=settings.session_max_age,
        same_site="lax",
        https_only=settings.session_https_only,
    )

    app.mount(
        "/static",
        StaticFiles(directory=str(BASE_DIR / "app" / "static")),
        name="static",
    )

    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(maintenance.router)
    app.include_router(general_maintenance.router)
    app.include_router(installations.router)
    app.include_router(records.router)
    app.include_router(reports.router)
    app.include_router(pricing.router)
    app.include_router(settings_router.router)
    app.include_router(admin.router)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    @app.exception_handler(RedirectToLogin)
    async def _needs_login(request: Request, exc: RedirectToLogin):
        if request.headers.get("x-requested-with", "").lower() == "xmlhttprequest":
            return localized_json(
                request,
                {"ok": False, "errors": {"form": "Session expired."}},
                status_code=401,
            )
        return login_redirect(exc.next_url)

    # Registered against the Starlette class, which is the parent of FastAPI's:
    # unmatched routes raise the former and would otherwise return raw JSON.
    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        if request.url.path.startswith("/static"):
            return PlainTextResponse(str(exc.detail), status_code=exc.status_code)
        if request.headers.get("x-requested-with", "").lower() == "xmlhttprequest":
            return localized_json(
                request,
                {"ok": False, "errors": {"form": str(exc.detail)}},
                status_code=exc.status_code,
            )

        titles = {
            status.HTTP_403_FORBIDDEN: "You don't have access to this",
            status.HTTP_404_NOT_FOUND: "Page not found",
            status.HTTP_405_METHOD_NOT_ALLOWED: "That action isn't available here",
        }
        return render(
            request,
            "error.html",
            {
                "code": exc.status_code,
                "title": titles.get(exc.status_code, "Something went wrong"),
                "detail": (
                    "Check the address, or head back to the dashboard."
                    if exc.status_code == status.HTTP_404_NOT_FOUND
                    else exc.detail
                    if exc.status_code in titles
                    else "Try again in a moment."
                ),
                "layout": "bare" if not getattr(request.state, "user", None) else "app",
            },
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # Internal detail never reaches the browser.
        return render(
            request,
            "error.html",
            {
                "code": 500,
                "title": "Something went wrong",
                "detail": "The action could not be completed. Try again.",
                "layout": "bare",
            },
            status_code=500,
        )

    return app


app = create_app()
