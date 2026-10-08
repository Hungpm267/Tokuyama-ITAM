"""Script xuất toàn bộ DDL và Seed Data ra file SQL duy nhất cho Aiven.io."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from argon2 import PasswordHasher

from app.enums import DEFAULT_ROLE_PERMISSIONS, RoleCode

ph = PasswordHasher()

# Sinh hash Argon2id cho các tài khoản mặc định
admin_hash = ph.hash("TokuyamaAdmin2026!@#")
ga_hash = ph.hash("TokuyamaGa2026!@#")
exec_hash = ph.hash("TokuyamaExec2026!@#")

# 1. Chạy Alembic để lấy SQL DDL
cmd = [sys.executable, "-m", "alembic", "upgrade", "base:head", "--sql"]
proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
alembic_sql = proc.stdout

# Bỏ phần INFO log ở stdout nếu có
clean_lines = []
for line in alembic_sql.splitlines():
    if line.startswith("INFO "):
        continue
    clean_lines.append(line)
clean_ddl = "\n".join(clean_lines)

# 2. Xây dựng Seed Data SQL
seed_sql = """
-- =============================================================================
-- SEED DATA: ROLES & DEFAULT PERMISSIONS & INITIAL USERS
-- =============================================================================

-- 1. Roles
INSERT INTO roles (id, code, name_en, name_ja, created_at, updated_at, is_deleted) VALUES
(1, 'ADMIN', 'Administrator', '管理者', now(), now(), false),
(2, 'GA_MANAGER', 'GA Manager', '総務課長', now(), now(), false),
(3, 'EXECUTIVE', 'Executive', '役員', now(), now(), false)
ON CONFLICT (id) DO NOTHING;

SELECT setval('roles_id_seq', (SELECT MAX(id) FROM roles));

-- 2. Role Permissions
INSERT INTO role_permissions (role_id, module, action) VALUES
"""

perm_values = []
role_map = {
    RoleCode.ADMIN: 1,
    RoleCode.GA_MANAGER: 2,
    RoleCode.EXECUTIVE: 3,
}

for role_code, modules in DEFAULT_ROLE_PERMISSIONS.items():
    r_id = role_map[role_code]
    for module, actions in modules.items():
        for action in actions:
            perm_values.append(f"({r_id}, '{module.value}', '{action.value}')")

seed_sql += ",\n".join(perm_values) + "\nON CONFLICT (role_id, module, action) DO NOTHING;\n\n"

seed_sql += f"""-- 3. Initial Users
-- Mật khẩu mặc định:
-- it.admin: TokuyamaAdmin2026!@#
-- ga.manager: TokuyamaGa2026!@#
-- executive: TokuyamaExec2026!@#
INSERT INTO users (id, username, password_hash, display_name, role_id, preferred_lang, is_active, created_at, updated_at, is_deleted) VALUES
(1, 'it.admin', '{admin_hash}', 'IT Administrator', 1, 'vi', true, now(), now(), false),
(2, 'ga.manager', '{ga_hash}', 'Trưởng phòng GA (Tổng vụ)', 2, 'vi', true, now(), now(), false),
(3, 'executive', '{exec_hash}', 'Ban Giám Đốc (Executive)', 3, 'ja', true, now(), now(), false)
ON CONFLICT (id) DO NOTHING;

SELECT setval('users_id_seq', (SELECT MAX(id) FROM users));

-- 4. Initial Asset Categories
INSERT INTO asset_categories (id, code, name_en, name_ja, created_at, updated_at, is_deleted) VALUES
(1, 'LAPTOP', 'Laptop / Notebook', 'ノートパソコン', now(), now(), false),
(2, 'DESKTOP', 'Desktop PC', 'デスクトップパソコン', now(), now(), false),
(3, 'MONITOR', 'Monitor / Display', '液晶モニター', now(), now(), false),
(4, 'SERVER', 'Server Hardware', 'サーバー機器', now(), now(), false),
(5, 'NETWORK', 'Network / Switch / Router', 'ネットワーク機器', now(), now(), false),
(6, 'PRINTER', 'Printer / Copier', 'プリンター・複合機', now(), now(), false),
(7, 'PERIPHERAL', 'Peripherals / Accessories', '周辺機器・アクセサリ', now(), now(), false)
ON CONFLICT (id) DO NOTHING;

SELECT setval('asset_categories_id_seq', (SELECT MAX(id) FROM asset_categories));

-- 5. Initial Departments
INSERT INTO departments (id, code, name_en, name_ja, created_at, updated_at, is_deleted) VALUES
(1, 'BOD', 'Board of Directors', '役員会', now(), now(), false),
(2, 'GA', 'General Affairs', '総務課', now(), now(), false),
(3, 'IT', 'Information Technology', 'IT課', now(), now(), false),
(4, 'ACC', 'Accounting & Finance', '経理課', now(), now(), false),
(5, 'PROD', 'Production & Factory', '製造部', now(), now(), false),
(6, 'QA', 'Quality Assurance', '品質保証課', now(), now(), false),
(7, 'LOG', 'Logistics & Supply', '物流課', now(), now(), false)
ON CONFLICT (id) DO NOTHING;

SELECT setval('departments_id_seq', (SELECT MAX(id) FROM departments));

-- 6. Initial Office Locations
INSERT INTO office_locations (id, building, floor, room_en, room_ja, created_at, updated_at, is_deleted) VALUES
(1, 'Main Building', 1, 'GA & Admin Office', '総務事務所', now(), now(), false),
(2, 'Main Building', 1, 'Server Room', 'サーバー室', now(), now(), false),
(3, 'Main Building', 2, 'Director Office', '役員室', now(), now(), false),
(4, 'Main Building', 2, 'Meeting Room A', '会議室A', now(), now(), false),
(5, 'Factory Plant', 1, 'Control Room', '中央制御室', now(), now(), false)
ON CONFLICT (id) DO NOTHING;

SELECT setval('office_locations_id_seq', (SELECT MAX(id) FROM office_locations));
"""

full_sql = f"""-- =============================================================================
-- TOKUYAMA VIETNAM - IT ASSET MANAGEMENT SYSTEM (ITAM)
-- DATABASE INITIALIZATION SCRIPT FOR POSTGRESQL (AIVEN.IO / CLOUD / ON-PREMISE)
-- =============================================================================
-- Generated automatically from SQLAlchemy 2.x & Alembic Migrations
-- Schema revision: 0002 (Head)
-- Compatible with PostgreSQL 14, 15, 16+
-- =============================================================================

{clean_ddl}

{seed_sql}

-- Hoàn tất khởi tạo cơ sở dữ liệu
COMMIT;
"""

target = Path("init_aiven_database.sql")
target.write_text(full_sql, encoding="utf-8")
print(f"Generated {target} successfully ({len(full_sql)} bytes).")
