"""Điểm khởi chạy chính của ứng dụng ITAM - Tokuyama Vietnam."""

from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.admin import setup_admin
from app.config import settings
from app.core.security import SESSION_SECRET
from app.db import engine
from app.routers.auth import router as auth_router

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(
    title="Tokuyama Vietnam ITAM",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# 1. Session Middleware (hỗ trợ SQLAdmin và phiên làm việc web)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    max_age=settings.session_idle_minutes * 60,
)

# 2. Mount thư mục tĩnh Static (phục vụ logo công ty, stylesheet)
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 3. Mount Routers
app.include_router(auth_router)

# 4. Gắn kết hệ thống SQLAdmin
setup_admin(app, engine)


@app.get("/")
def root():
    """Endpoint kiểm tra trạng thái hoạt động của hệ thống."""
    return {
        "app": "Tokuyama Vietnam ITAM",
        "version": "2.0.0",
        "status": "operational",
    }
