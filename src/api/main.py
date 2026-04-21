from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from src.api.routers import admin, auth, health, papers, reports, reviews, users
from src.core.config import settings
from src.core.email import send_review_assignment_email
from src.tasks.evaluation_task import dispatch_evaluation_task


def create_app() -> FastAPI:
    app = FastAPI(title="SocialEval API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        same_site="lax",
        session_cookie="socialeval_session",
        https_only=False,
    )
    app.state.pipeline_runner = None
    app.state.task_dispatcher = dispatch_evaluation_task
    app.state.email_sender = send_review_assignment_email
    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(users.router, prefix="/api/users", tags=["users"])
    app.include_router(papers.router, prefix="/api/papers", tags=["papers"])
    app.include_router(reports.router, prefix="/api/papers", tags=["reports"])
    app.include_router(reviews.router, prefix="/api/reviews", tags=["reviews"])
    app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
    return app


app = create_app()
