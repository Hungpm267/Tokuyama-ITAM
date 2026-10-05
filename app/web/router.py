from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Request, Depends, Form, HTTPException, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import get_db
from app.models import (
    User, Asset, Assignment, Person, Department,
    License, LicenseAssignment, AccessCard, CardLoan, Contract
)
from app.services.auth import (
    authenticate_user, create_session_token, verify_session_token
)
from app.services.stats import get_dashboard_stats

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

web_router = APIRouter(include_in_schema=False)

def get_current_user_from_cookie(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    token = request.cookies.get("toku_session")
    if not token:
        return None
    session_data = verify_session_token(token)
    if not session_data:
        return None
    user_id, _ = session_data
    return db.query(User).filter(User.id == user_id, User.is_active == True).first()

@web_router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None}
    )

@web_router.post("/login", response_class=HTMLResponse)
def login_post(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = authenticate_user(db, username, password)
    if not user:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Invalid username or password / Tên đăng nhập hoặc mật khẩu không đúng."}
        )
    token = create_session_token(user.id, user.role)
    redirect = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    redirect.set_cookie(
        key="toku_session",
        value=token,
        max_age=1800,  # 30 minutes
        httponly=True,
        samesite="lax"
    )
    return redirect

@web_router.get("/logout")
def logout(response: Response):
    redirect = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    redirect.delete_cookie("toku_session")
    return redirect

@web_router.get("/set-lang")
def set_language(lang: str, next: str = "/", response: Response = None):
    redirect = RedirectResponse(url=next or "/", status_code=status.HTTP_302_FOUND)
    redirect.set_cookie("toku_lang", lang, max_age=86400 * 30)
    return redirect

@web_router.get("/", response_class=HTMLResponse)
@web_router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(
    request: Request,
    user: Optional[User] = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    stats = get_dashboard_stats(db)
    lang = request.cookies.get("toku_lang", "en")

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": user,
            "lang": lang,
            "asset_stats": stats["asset_stats"],
            "expiring_licenses": stats["expiring_licenses"],
            "active_card_loans": stats["active_card_loans"],
        }
    )

@web_router.get("/search", response_class=HTMLResponse)
def search_page(
    request: Request,
    q: Optional[str] = "",
    user: Optional[User] = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    lang = request.cookies.get("toku_lang", "en")
    query = (q or "").strip()

    assets, persons, contracts, cards = [], [], [], []
    if query:
        assets = db.query(Asset).filter(
            Asset.is_deleted == False,
            (Asset.asset_code.ilike(f"%{query}%")) |
            (Asset.serial.ilike(f"%{query}%")) |
            (Asset.model.ilike(f"%{query}%")) |
            (Asset.mac_address.ilike(f"%{query}%"))
        ).all()

        persons = db.query(Person).filter(
            Person.is_deleted == False,
            (Person.staff_code.ilike(f"%{query}%")) |
            (Person.full_name.ilike(f"%{query}%"))
        ).all()

        contracts = db.query(Contract).filter(
            Contract.is_deleted == False,
            Contract.code.ilike(f"%{query}%")
        ).all()

        cards = db.query(AccessCard).filter(
            AccessCard.is_deleted == False,
            AccessCard.card_no.ilike(f"%{query}%")
        ).all()

    total_count = len(assets) + len(persons) + len(contracts) + len(cards)

    return templates.TemplateResponse(
        request=request,
        name="search.html",
        context={
            "user": user,
            "lang": lang,
            "query": query,
            "assets": assets,
            "persons": persons,
            "contracts": contracts,
            "cards": cards,
            "total_count": total_count,
        }
    )

@web_router.get("/person/{person_id}/profile", response_class=HTMLResponse)
def person_profile_page(
    person_id: int,
    request: Request,
    user: Optional[User] = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    lang = request.cookies.get("toku_lang", "en")

    # 1. Current assets
    current_assignments = [a for a in person.assignments if not a.is_deleted and a.returned_at is None]
    # 2. Past assignments
    past_assignments = [a for a in person.assignments if not a.is_deleted and a.returned_at is not None]
    # 3. Licenses
    current_asset_ids = [a.asset_id for a in current_assignments]
    licenses_assigned = db.query(LicenseAssignment).filter(
        LicenseAssignment.is_deleted == False,
        LicenseAssignment.removed_at == None,
        (LicenseAssignment.person_id == person.id) | (LicenseAssignment.asset_id.in_(current_asset_ids))
    ).all()
    # 4. Card loans
    current_cards = [l for l in person.card_loans if not l.is_deleted and l.returned_at is None]
    past_cards = [l for l in person.card_loans if not l.is_deleted and l.returned_at is not None]

    return templates.TemplateResponse(
        request=request,
        name="person_profile.html",
        context={
            "user": user,
            "lang": lang,
            "person": person,
            "current_assignments": current_assignments,
            "past_assignments": past_assignments,
            "licenses_assigned": licenses_assigned,
            "current_cards": current_cards,
            "past_cards": past_cards,
        }
    )

@web_router.get("/trash", response_class=HTMLResponse)
def trash_page(
    request: Request,
    user: Optional[User] = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    if not user or user.role != "it_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

    lang = request.cookies.get("toku_lang", "en")

    deleted_assets = db.query(Asset).filter(Asset.is_deleted == True).all()
    deleted_persons = db.query(Person).filter(Person.is_deleted == True).all()
    deleted_licenses = db.query(License).filter(License.is_deleted == True).all()
    deleted_cards = db.query(AccessCard).filter(AccessCard.is_deleted == True).all()
    deleted_contracts = db.query(Contract).filter(Contract.is_deleted == True).all()

    items = []
    for a in deleted_assets:
        items.append({"model_name": "asset", "type": "Asset", "name": str(a), "obj": a})
    for p in deleted_persons:
        items.append({"model_name": "person", "type": "Person", "name": str(p), "obj": p})
    for l in deleted_licenses:
        items.append({"model_name": "license", "type": "License", "name": str(l), "obj": l})
    for c in deleted_cards:
        items.append({"model_name": "card", "type": "AccessCard", "name": str(c), "obj": c})
    for ct in deleted_contracts:
        items.append({"model_name": "contract", "type": "Contract", "name": str(ct), "obj": ct})

    return templates.TemplateResponse(
        request=request,
        name="trash.html",
        context={
            "user": user,
            "lang": lang,
            "items": items,
        }
    )

@web_router.post("/trash/restore")
def trash_restore_action(
    request: Request,
    model_name: str = Form(...),
    item_id: int = Form(...),
    user: Optional[User] = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    if not user or user.role != "it_admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    model_map = {
        "asset": Asset,
        "person": Person,
        "license": License,
        "card": AccessCard,
        "contract": Contract,
    }
    model_cls = model_map.get(model_name)
    if model_cls:
        item = db.query(model_cls).filter(model_cls.id == item_id, model_cls.is_deleted == True).first()
        if item:
            item.restore()
            db.commit()

    return RedirectResponse(url="/trash", status_code=status.HTTP_302_FOUND)
