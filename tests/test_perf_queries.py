"""Tốc độ: kiểm tra quyền không hỏi lại database mỗi lần, và vẫn đúng khi quyền đổi."""

from __future__ import annotations

from sqlalchemy import event, select

from app.core import permissions
from app.models import Role, RolePermission, User


def _count_queries(db):
    counter = {"n": 0}

    def _inc(*_a, **_k):
        counter["n"] += 1

    event.listen(db.get_bind(), "before_cursor_execute", _inc)
    return counter, lambda: event.remove(db.get_bind(), "before_cursor_execute", _inc)


def _admin(db):
    role = db.scalar(select(Role).where(Role.code == "ADMIN"))
    user = db.scalar(select(User).where(User.role_id == role.id, User.is_deleted.is_(False)))
    return role, user


def test_has_permission_hoi_database_mot_lan_cho_nhieu_lan_kiem(db, seed):
    role, user = _admin(db)
    permissions.invalidate_permission_cache()
    counter, stop = _count_queries(db)
    try:
        for _ in range(10):
            permissions.has_permission(db, user, "assets", "view")
            permissions.has_permission(db, user, "persons", "change")
    finally:
        stop()
    assert counter["n"] == 1


def test_them_quyen_moi_co_hieu_luc_ngay(db, seed):
    role, user = _admin(db)
    permissions.invalidate_permission_cache()
    db.query(RolePermission).filter_by(role_id=role.id, module="assets", action="delete").delete()
    permissions.invalidate_permission_cache()
    assert permissions.has_permission(db, user, "assets", "delete") is False
    db.add(RolePermission(role_id=role.id, module="assets", action="delete"))
    db.flush()
    assert permissions.has_permission(db, user, "assets", "delete") is True


def test_nhat_ky_tra_ten_ca_trang_moi_bang_mot_cau(db, seed):
    from app.admin import _audit_record_labels
    from app.models import Asset, Person

    assets = db.scalars(select(Asset)).all()
    persons = db.scalars(select(Person)).all()
    pairs = [("assets", a.id) for a in assets] + [("persons", p.id) for p in persons] + [("assets", 999999)]
    counter, stop = _count_queries(db)
    try:
        labels = _audit_record_labels(db, pairs)
    finally:
        stop()
    assert counter["n"] == 2
    assert labels[("assets", assets[0].id)] == assets[0].device_code
    assert labels[("persons", persons[0].id)] == f"{persons[0].staff_code} · {persons[0].full_name}"
    assert ("assets", 999999) not in labels
