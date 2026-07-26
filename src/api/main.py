from __future__ import annotations

from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.sessions import SessionMiddleware

from src.api.routers import (
    admin,
    auth,
    editorial,
    editorial_admin,
    health,
    papers,
    reports,
    reviews,
    submitter,
    users,
)
from src.core.config import settings
from src.core.email import send_review_assignment_email
from src.core.logging import setup_logging
from src.core.production import production_config_errors
from src.tasks.evaluation_task import dispatch_evaluation_task
from src.tasks.editorial_task import dispatch_editorial_submission


def create_app() -> FastAPI:
    setup_logging()
    if settings.app_env == "production":
        errors = production_config_errors()
        if errors:
            raise RuntimeError("生产配置不完整：" + "；".join(errors))
    app = FastAPI(title="中国自主知识创新（法学论文）评价系统 API", version="0.1.0")
    allowed_origins: list[str] = []
    if settings.app_env != "production":
        allowed_origins.extend(["http://localhost:5173", "http://127.0.0.1:5173"])
    if settings.allowed_origins:
        allowed_origins.extend(
            [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def protect_session_writes(request: Request, call_next):
        unsafe = request.method in {"POST", "PUT", "PATCH", "DELETE"}
        has_session = "socialeval_session" in request.cookies
        if settings.app_env == "production" and unsafe and has_session:
            origin = request.headers.get("origin")
            allowed = {
                item.strip().rstrip("/")
                for item in settings.allowed_origins.split(",")
                if item.strip()
            }
            public_origin = urlparse(settings.public_base_url)
            allowed.add(f"{public_origin.scheme}://{public_origin.netloc}")
            if not origin or origin.rstrip("/") not in allowed:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "写请求来源校验失败，请刷新页面后重试"},
                )
        return await call_next(request)

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        same_site="lax",
        session_cookie="socialeval_session",
        https_only=settings.session_https_only,
        max_age=settings.session_max_age_seconds,
    )
    if settings.allowed_hosts:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=[
                host.strip()
                for host in settings.allowed_hosts.split(",")
                if host.strip()
            ],
        )
    app.state.pipeline_runner = None
    app.state.task_dispatcher = dispatch_evaluation_task
    app.state.email_sender = send_review_assignment_email
    app.state.editorial_pipeline_runner = None
    app.state.editorial_dispatcher = dispatch_editorial_submission
    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(users.router, prefix="/api/users", tags=["users"])
    app.include_router(papers.router, prefix="/api/papers", tags=["papers"])
    app.include_router(reports.router, prefix="/api/papers", tags=["reports"])
    app.include_router(reviews.router, prefix="/api/reviews", tags=["reviews"])
    app.include_router(
        submitter.router,
        prefix="/api/submitter",
        tags=["submitter"],
    )
    app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
    app.include_router(editorial.router, prefix="/api/editorial", tags=["editorial"])
    app.include_router(
        editorial_admin.router,
        prefix="/api/admin/editorial",
        tags=["editorial-admin"],
    )
    return app


app = create_app()
