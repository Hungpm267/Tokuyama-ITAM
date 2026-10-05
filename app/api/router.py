from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.models import Asset, Person, License, AccessCard, Contract, User
from app.schemas import (
    AssetOut, AssetCreate, PersonOut, LicenseOut, AccessCardOut, ContractOut,
    LoginRequest, LoginResponse
)
from app.services.auth import authenticate_user, create_session_token
from app.services.stats import get_dashboard_stats

api_router = APIRouter(prefix="/api/v1")

@api_router.post("/auth/login", response_model=LoginResponse, tags=["Authentication"])
def api_login(data: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, data.username, data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tên đăng nhập hoặc mật khẩu không chính xác."
        )
    token = create_session_token(user.id, user.role)
    return LoginResponse(
        access_token=token,
        user_id=user.id,
        username=user.username,
        role=user.role
    )

@api_router.get("/stats/dashboard", tags=["Dashboard"])
def api_dashboard_stats(db: Session = Depends(get_db)):
    return get_dashboard_stats(db)

@api_router.get("/assets", response_model=List[AssetOut], tags=["Assets"])
def list_assets(status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Asset).filter(Asset.is_deleted == False)
    if status:
        query = query.filter(Asset.status == status)
    return query.all()

@api_router.post("/assets", response_model=AssetOut, tags=["Assets"])
def create_asset(data: AssetCreate, db: Session = Depends(get_db)):
    asset = Asset(**data.model_dump())
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset

@api_router.get("/persons", response_model=List[PersonOut], tags=["Personnel"])
def list_persons(db: Session = Depends(get_db)):
    return db.query(Person).filter(Person.is_deleted == False).all()

@api_router.get("/licenses", response_model=List[LicenseOut], tags=["Licenses"])
def list_licenses(db: Session = Depends(get_db)):
    return db.query(License).filter(License.is_deleted == False).all()

@api_router.get("/cards", response_model=List[AccessCardOut], tags=["Access Cards"])
def list_cards(db: Session = Depends(get_db)):
    return db.query(AccessCard).filter(AccessCard.is_deleted == False).all()

@api_router.get("/contracts", response_model=List[ContractOut], tags=["Contracts"])
def list_contracts(db: Session = Depends(get_db)):
    return db.query(Contract).filter(Contract.is_deleted == False).all()

@api_router.get("/search", tags=["Global Search"])
def api_global_search(q: str, db: Session = Depends(get_db)):
    assets = db.query(Asset).filter(
        Asset.is_deleted == False,
        (Asset.asset_code.ilike(f"%{q}%")) |
        (Asset.serial.ilike(f"%{q}%")) |
        (Asset.model.ilike(f"%{q}%")) |
        (Asset.mac_address.ilike(f"%{q}%"))
    ).all()

    persons = db.query(Person).filter(
        Person.is_deleted == False,
        (Person.staff_code.ilike(f"%{q}%")) |
        (Person.full_name.ilike(f"%{q}%"))
    ).all()

    contracts = db.query(Contract).filter(
        Contract.is_deleted == False,
        Contract.code.ilike(f"%{q}%")
    ).all()

    cards = db.query(AccessCard).filter(
        AccessCard.is_deleted == False,
        AccessCard.card_no.ilike(f"%{q}%")
    ).all()

    return {
        "query": q,
        "assets": [AssetOut.model_validate(a) for a in assets],
        "persons": [PersonOut.model_validate(p) for p in persons],
        "contracts": [ContractOut.model_validate(c) for c in contracts],
        "cards": [AccessCardOut.model_validate(card) for card in cards],
        "total_results": len(assets) + len(persons) + len(contracts) + len(cards)
    }
