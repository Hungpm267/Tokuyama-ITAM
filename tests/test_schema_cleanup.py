"""Schema sau khi thu hẹp app: chỉ còn laptop, nhân sự và phần nền của hệ thống."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app import models as m
from app.enums import Module

KEPT_TABLES = {
    "users", "roles", "role_permissions",
    "departments", "asset_categories", "asset_tags",
    "persons", "person_secrets",
    "assets", "asset_tag_links", "assignments",
    "audit_logs",
}
DROPPED_ENUMS = {
    "card_status", "card_type", "delivery_status",
    "contract_item_kind", "license_type", "phone_device_type",
}


def test_database_keeps_only_the_twelve_tables(db: Session):
    tables = set(inspect(db.connection()).get_table_names()) - {"alembic_version"}
    assert tables == KEPT_TABLES


def test_models_match_the_kept_tables():
    assert set(m.Base.metadata.tables) == KEPT_TABLES


def test_enums_of_dropped_tables_are_gone(db: Session):
    names = set(db.scalars(text("SELECT typname FROM pg_type WHERE typtype = 'e'")))
    assert not names & DROPPED_ENUMS


def test_columns_use_business_names(db: Session):
    insp = inspect(db.connection())
    asset_cols = {c["name"] for c in insp.get_columns("assets")}
    person_cols = {c["name"] for c in insp.get_columns("persons")}
    assert "device_code" in asset_cols
    assert not asset_cols & {"vendor_code", "contract_line_id"}
    assert "user_id" in person_cols
    assert "user_login_id" not in person_cols


def test_renamed_unique_indexes_follow_the_columns(db: Session):
    insp = inspect(db.connection())
    assert "uq_alive_assets_device_code" in {i["name"] for i in insp.get_indexes("assets")}
    assert "uq_alive_persons_user_id" in {i["name"] for i in insp.get_indexes("persons")}


def test_user_role_has_a_foreign_key(db: Session):
    keys = inspect(db.connection()).get_foreign_keys("users")
    assert any(k["constrained_columns"] == ["role_id"] and k["referred_table"] == "roles" for k in keys)


def test_permission_modules_of_dropped_tables_are_gone():
    assert not {x.value for x in Module} & {"licenses", "cards", "contracts", "phones"}


def _cols(db: Session, table: str) -> dict:
    return {c["name"]: c for c in inspect(db.connection()).get_columns(table)}


def test_assets_have_device_code_only(db: Session):
    cols = _cols(db, "assets")
    assert cols["device_code"]["nullable"] is False
    assert not {"asset_code", "pc_name"} & set(cols)


def test_device_code_unique_index_exists(db: Session):
    assert "uq_alive_assets_device_code" in {i["name"] for i in inspect(db.connection()).get_indexes("assets")}


def test_departments_have_no_code(db: Session):
    assert "code" not in _cols(db, "departments")


def test_persons_have_type_and_required_code(db: Session):
    cols = _cols(db, "persons")
    assert cols["person_type"]["nullable"] is False
    assert cols["staff_code"]["nullable"] is False


def test_person_type_enum_values(db: Session):
    values = set(db.scalars(text(
        "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid WHERE t.typname = 'person_type'"
    )))
    assert values == {"EMPLOYEE", "VENDOR", "BUSINESS_TRIP"}
