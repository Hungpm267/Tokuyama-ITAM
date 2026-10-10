"""Điểm khởi chạy chính của ứng dụng ITAM - Tokuyama Vietnam."""

from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, RedirectResponse, Response

from app.admin import RequestContextMiddleware, setup_admin
from app.config import settings
from app.core.security import SESSION_IDLE_SECONDS, SESSION_SECRET, renew_session_token
from app.db import engine
from app.routers.assets import router as assets_router
from app.routers.auth import router as auth_router
from app.routers.batch_receive import router as batch_receive_router
from app.routers.export import router as export_router
from app.routers.global_search import router as global_search_router
from app.routers.portal import router as portal_router
from app.routers.role_matrix import router as role_matrix_router
from app.routers.secrets import router as secrets_router
from app.routers.software_receive import router as software_receive_router
from app.routers.trash import router as trash_router

BASE_DIR = Path(__file__).resolve().parent.parent

is_prod = settings.env.lower() in ("prod", "production")
app = FastAPI(
    title="Tokuyama Vietnam ITAM",
    version="2.0.0",
    docs_url=None if is_prod else "/docs",
    redoc_url=None if is_prod else "/redoc",
)

# 1. Middlewares (GZip nén dữ liệu mạng, Session và Request Context)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    max_age=settings.session_idle_minutes * 60,
)


@app.middleware("http")
async def cache_headers_middleware(request: Request, call_next) -> Response:
    """Tối ưu tốc độ: gắn Cache-Control cho static assets (CSS, JS, WebFonts, PNG)."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static") or "statics" in path or path.endswith((".css", ".js", ".woff2", ".png", ".ico")):
        response.headers["Cache-Control"] = "public, max-age=86400, stale-while-revalidate=604800"
    return response


@app.middleware("http")
async def sliding_session_middleware(request: Request, call_next) -> Response:
    """Gia hạn cookie phiên khi người dùng còn thao tác.

    BRD yêu cầu tự đăng xuất sau 30 phút KHÔNG thao tác. Token chỉ cấp một lần
    lúc đăng nhập thì người đang làm việc liên tục vẫn bị đá ra ở phút 30 và mất
    dữ liệu form đang nhập.
    """
    response = await call_next(request)
    token = request.cookies.get("itam_session")
    if not token or "/logout" in request.url.path:
        return response
    # Tải trước khi rê chuột (<link rel="prefetch">) không phải là thao tác của người dùng.
    # Gia hạn cho nó còn có thể ghi lại cookie ngay sau khi người dùng vừa đăng xuất.
    purpose = (request.headers.get("sec-purpose") or request.headers.get("purpose") or "").lower()
    if "prefetch" in purpose:
        return response
    # Không ghi đè cookie mà chính endpoint vừa đặt hoặc vừa xoá (đăng nhập/đăng xuất).
    if any(c.startswith("itam_session=") for c in response.headers.getlist("set-cookie")):
        return response
    renewed = renew_session_token(token)
    if renewed:
        response.set_cookie(
            key="itam_session",
            value=renewed,
            httponly=True,
            samesite="lax",
            secure=(request.url.scheme == "https"),
            max_age=SESSION_IDLE_SECONDS,
        )
    return response


# 2. Mount thư mục tĩnh Static (phục vụ logo công ty, stylesheet)
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 3. Mount Routers
app.include_router(auth_router)
app.include_router(portal_router)
app.include_router(role_matrix_router)
app.include_router(secrets_router)
app.include_router(batch_receive_router)
app.include_router(software_receive_router)
app.include_router(global_search_router)
app.include_router(trash_router)
app.include_router(assets_router)
app.include_router(export_router)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    """Phục vụ favicon mặc định của hệ thống."""
    return FileResponse(BASE_DIR / "static" / "img" / "tokuyama-favicon.png", media_type="image/png")


@app.get("/admin/set-lang")
@app.get("/set-lang")
async def set_language(
    request: Request, lang: str = "vi", next: str = "/admin"
) -> Response:
    """Chuyển đổi ngôn ngữ hiển thị giữa Tiếng Việt và Tiếng Anh."""
    from sqlalchemy import select
    from app.core.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES
    from app.db import SessionLocal
    from app.models import User

    chosen_lang = lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    user_id = request.session.get("user_id") if hasattr(request, "session") else None
    if not user_id:
        token = request.cookies.get("itam_session")
        if token:
            from app.core.security import verify_session_token

            payload = verify_session_token(token)
            if payload:
                user_id = payload.get("user_id")

    if user_id:
        try:
            with SessionLocal() as db:
                user = db.scalar(select(User).where(User.id == user_id))
                if user:
                    user.preferred_lang = chosen_lang
                    db.commit()
        except Exception:
            pass

    if hasattr(request, "session"):
        request.session["lang"] = chosen_lang

    redirect_url = (
        next
        if (next and next.startswith("/") and not next.startswith("//"))
        else "/admin"
    )
    response = RedirectResponse(url=redirect_url, status_code=303)
    response.set_cookie(
        key="itam_lang",
        value=chosen_lang,
        max_age=30 * 24 * 3600,
        httponly=False,
        samesite="lax",
    )
    return response


# 4. Gắn kết hệ thống SQLAdmin
admin = setup_admin(app, engine)
app.state.admin = admin

