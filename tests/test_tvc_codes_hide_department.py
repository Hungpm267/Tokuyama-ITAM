"""Mã thiết bị TKY-PC -> TVC-EC (migration 0008) và ẩn phòng ban khỏi màn hình."""

from __future__ import annotations

import asyncio
import datetime as dt
import importlib.util
from pathlib import Path

from sqlalchemy import select, text

from app.admin import DepartmentAdmin, PersonAdmin
from app.models import Asset
from tests.test_so_tong_edit import admin_client, client, override_db  # noqa: F401

_MIGRATION = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0008_tvc_device_codes.py"


def _migration():
    spec = importlib.util.spec_from_file_location("m0008", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_doi_tky_pc_sang_tvc_ec_giu_so_ke_ca_may_da_xoa(db, seed):
    alive = db.scalars(select(Asset).where(Asset.is_deleted.is_(False))).first()
    alive.device_code = "TKY-PC0042"
    other = Asset(device_code="tky-pc0007", category_id=alive.category_id, status=alive.status,
                  is_deleted=True, delete_reason="test", deleted_at=dt.datetime.now(dt.timezone.utc))
    keep = Asset(device_code="MON-001", category_id=alive.category_id, status=alive.status)
    db.add_all([other, keep])
    db.flush()

    db.execute(text(_migration().UPGRADE_SQL))
    db.expire_all()

    assert db.get(Asset, alive.id).device_code == "TVC-EC0042"
    assert db.get(Asset, other.id).device_code == "TVC-EC0007"
    assert db.get(Asset, keep.id).device_code == "MON-001"

    db.execute(text(_migration().DOWNGRADE_SQL))
    db.expire_all()
    assert db.get(Asset, alive.id).device_code == "TKY-PC0042"


def test_menu_phong_ban_an(db, seed):
    assert DepartmentAdmin().is_visible(None) is False


def test_danh_sach_va_form_nhan_su_khong_co_phong_ban(db, seed):
    def keys(cols):
        return {getattr(c, "key", c) for c in cols}

    assert "department" not in keys(PersonAdmin.column_list)
    assert "department" not in keys(PersonAdmin.column_details_list)
    form_cls = asyncio.run(PersonAdmin().scaffold_form())
    assert "department" not in form_cls().data


def test_so_tong_va_kho_mat_khau_khong_hien_phong_ban(admin_client, db, seed):  # noqa: F811
    ledger = admin_client.get("/admin/so-tong").text
    assert "field: 'department'" not in ledger
    vault = admin_client.get("/admin/person-secret/list").text
    assert "data-department" not in vault
    assert "phòng ban" not in vault.lower()
