from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, select

from .config import get_settings
from .database import database_healthy, init_db, session_scope
from .director import DirectorCommandService
from .models import ProcessingRun, Review
from .sandbox_source import SandboxReviewSource

ROOT = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(ROOT / "templates"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, root_path=settings.root_path, docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


def page_context(request: Request, **context):
    return {"request": request, "environment": settings.environment, **context}


@app.get("/", name="sandbox")
def sandbox(request: Request):
    with session_scope() as session:
        reviews = list(session.scalars(select(Review).order_by(desc(Review.created_at)).limit(60)))
        latest_run = session.scalar(select(ProcessingRun).order_by(desc(ProcessingRun.started_at)).limit(1))
    return templates.TemplateResponse(request, "sandbox.html", page_context(request, reviews=reviews, latest_run=latest_run, notice=request.query_params.get("notice")))


@app.post("/reviews", name="create_review")
def create_review(request: Request, author_name: str = Form(..., min_length=2, max_length=160), text: str = Form(..., min_length=3, max_length=5000)):
    with session_scope() as session:
        SandboxReviewSource().create_review(session, author_name=author_name, text=text)
    return RedirectResponse(url=f"{request.url_for('sandbox').path}?notice=review-created", status_code=303)


@app.get("/operator", name="operator")
def operator(request: Request):
    with session_scope() as session:
        director = DirectorCommandService(session)
        context = {"kpi": director.kpi_snapshot(), "upward": director.upward_report(), "summary": director.reputation_summary()}
    return templates.TemplateResponse(request, "operator.html", page_context(request, **context))


@app.get("/api/director/{command}")
def director_command(command: str):
    with session_scope() as session:
        director = DirectorCommandService(session)
        if command == "kpi":
            return director.kpi_snapshot()
        if command == "upward-report":
            return director.upward_report()
        if command == "reputation-summary":
            return director.reputation_summary()
    raise HTTPException(404, "UNKNOWN_COMMAND")


@app.get("/health")
def health():
    healthy = database_healthy()
    return {"status": "healthy" if healthy else "unhealthy", "service": "review-site", "database": "healthy" if healthy else "unhealthy", "credentials": "broker_only"}
