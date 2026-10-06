"""Hạ tầng test.

Mỗi test chạy trong một transaction rồi rollback, nên DB test luôn sạch và
các test không ảnh hưởng nhau.

AN TOÀN: fixture từ chối chạy nếu ITAM_ENV=prod hoặc nếu tên database không
chứa 'test'. Đây là chốt chặn để không bao giờ xoá nhầm dữ liệu thật.
"""

from __future__ import annotations

import datetime as dt
import os
import subprocess

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.enums import PersonStatus, RoleCode

TEST_DB_URL = os.environ.get(
    "ITAM_TEST_DATABASE_URL",
    "postgresql+psycopg://postgres@127.0.0.1:5432/itam_test",
)


def _guard() -> None:
    if os.environ.get("ITAM_ENV") == "prod":
        pytest.exit("Từ chối chạy test khi ITAM_ENV=prod", returncode=2)
    if "test" not in TEST_DB_URL.rsplit("/", 1)[-1]:
        pytest.exit(
            f"Tên database test phải chứa 'test'. Đang là: {TEST_DB_URL}", returncode=2
        )


@pytest.fixture(scope="session")
def engine():
    _guard()
    admin_url = TEST_DB_URL.rsplit("/", 1)[0] + "/postgres"
    db_name = TEST_DB_URL.rsplit("/", 1)[-1]
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    admin.dispose()

    env = {**os.environ, "ITAM_DATABASE_URL": TEST_DB_URL}
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=env)

    eng = create_engine(TEST_DB_URL)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine) -> Session:
    """Session có rollback tự động sau mỗi test."""
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        conn.close()


# --------------------------------------------------------------------------
# Factory: dữ liệu tối thiểu để test các ràng buộc
# --------------------------------------------------------------------------

TODAY = dt.date(2026, 10, 6)


@pytest.fixture
def seed(db: Session):
    from app import models as m

    role = m.Role(code=RoleCode.ADMIN.value, name_en="Administrator")
    db.add(role)
    db.flush()

    user = m.User(
        username="it.admin",
        password_hash="x",
        display_name="IT Admin",
        role_id=role.id,
    )
    dept = m.Department(name_en="Production")
    cat = m.AssetCategory(name_en="Laptop")
    db.add_all([user, dept, cat])
    db.flush()

    person = m.Person(
        staff_code="TVC00001",
        full_name="Nguyen Van A",
        department_id=dept.id,
        status=PersonStatus.ACTIVE,
    )
    person_b = m.Person(
        staff_code="TVC00002", full_name="Tran Thi B", status=PersonStatus.ACTIVE
    )
    db.add_all([person, person_b])
    db.flush()

    asset = m.Asset(asset_code="TVC-E00027", vendor_code="TKY-PC0001",
                    serial="SN-0001", category_id=cat.id)
    db.add(asset)

    product = m.LicenseProduct(name="Trend Micro")
    db.add(product)
    db.flush()

    lic = m.License(product_id=product.id, seats=13)
    card = m.AccessCard(card_no="CARD-001")
    loc = m.Location(building="Office", floor="1F", room_en="Server Room",
                     is_access_controlled=True)
    db.add_all([lic, card, loc])
    db.flush()

    return {
        "role": role, "user": user, "dept": dept, "cat": cat,
        "person": person, "person_b": person_b, "asset": asset,
        "product": product, "license": lic, "card": card, "location": loc,
    }
