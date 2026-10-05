# ITAM System Tokuyama Vietnam Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Xây dựng hoàn chỉnh Hệ thống Quản lý Tài sản IT (ITAM) cho Tokuyama Vietnam bằng Django + PostgreSQL, thay thế toàn bộ Excel với 15 bảng cơ sở dữ liệu, xóa mềm, audit log, RBAC 3 vai trò, đa ngôn ngữ Anh/Nhật, Dashboard, Tra cứu toàn cục và Hồ sơ nhân sự 360.

**Architecture:** Monolith Django với Django Admin Native mở rộng. Các ứng dụng phân rã theo miền nghiệp vụ (`core`, `organization`, `assets`, `licenses`, `cards`, `contracts`). Tự động xử lý xóa mềm và truy vết thay đổi qua Custom Model Manager và Thread-local middleware.

**Tech Stack:** Python 3.14, Django 5.x / LTS, PostgreSQL (psycopg/psycopg2-binary), `django-auditlog`, `python-dotenv`, Django i18n (English / Japanese).

**Spec:** [docs/superpowers/specs/2026-10-06-itam-system-design.md](file:///C:/Users/hungm/OneDrive/M%C3%A1y%20t%C3%ADnh/toku-app/docs/superpowers/specs/2026-10-06-itam-system-design.md)

## Global Constraints

* Python 3.14+ compatibility.
* Database: PostgreSQL (with SQLite support for isolated automated tests).
* Ràng buộc xóa mềm: Mọi bảng nghiệp vụ kế thừa 8 trường của `SoftDeleteModel`.
* Ràng buộc duy nhất: Chỉ áp dụng trên bản ghi chưa xóa (`condition=models.Q(is_deleted=False)`).
* Bảo mật: Không lưu bất kỳ mật khẩu nào của nhân viên; che mờ License Key với vai trò không phải IT Admin.
* Đa ngôn ngữ: Giao diện hỗ trợ tiếng Anh (`en`) và tiếng Nhật (`ja`), switcher ngôn ngữ trên header.

---

### Task 1: Environment Setup, Dependencies & Django Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.env`
- Create: `.gitignore`
- Create: `toku_itam/settings.py`
- Create: `toku_itam/urls.py`
- Create: `toku_itam/wsgi.py`
- Create: `toku_itam/asgi.py`
- Create: `manage.py`

**Interfaces:**
- Consumes: None
- Produces: Working Django project with environment variable support (`DEBUG`, `SECRET_KEY`, `DATABASE_URL`).

- [ ] **Step 1: Create `requirements.txt`**

```txt
Django>=5.0,<6.0
psycopg2-binary>=2.9.9
django-auditlog>=3.0.0
python-dotenv>=1.0.0
pytest>=8.0.0
pytest-django>=4.8.0
```

- [ ] **Step 2: Create `.gitignore` and `.env.example`**

```gitignore
__pycache__/
*.py[cod]
*$py.class
*.sqlite3
.env
.venv/
venv/
staticfiles/
media/
```

- [ ] **Step 3: Setup virtual environment & install requirements**

Run: `python -m venv venv; .\venv\Scripts\pip install -r requirements.txt`

- [ ] **Step 4: Initialize Django project `toku_itam` and configure `settings.py`**

Configure `settings.py` to load `.env`, setup i18n (`en`, `ja`), `SESSION_COOKIE_AGE = 1800`, session save every request, and database routing with fallback to SQLite for tests.

- [ ] **Step 5: Verify Django check passes**

Run: `.\venv\Scripts\python manage.py check`
Expected: System check identified no issues.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .gitignore .env.example toku_itam/ manage.py
git commit -m "chore: scaffold Django project and configure settings"
```

---

### Task 2: Core Infrastructure (`core` app - SoftDelete, Base Models, Middleware)

**Files:**
- Create: `core/models.py`
- Create: `core/middleware.py`
- Create: `core/apps.py`
- Test: `tests/test_core_models.py`

**Interfaces:**
- Consumes: Django auth `User` model, thread-local requests.
- Produces: `TimeStampedModel`, `SoftDeleteModel`, `ActiveManager`, `AllObjectsManager`, `get_current_user()` function.

- [ ] **Step 1: Write failing test for `SoftDeleteModel` and `ActiveManager`**

```python
# tests/test_core_models.py
import pytest
from django.db import models
from django.contrib.auth.models import User
from core.models import SoftDeleteModel

class DummyItem(SoftDeleteModel):
    name = models.CharField(max_length=50)
    class Meta:
        app_label = 'core'

@pytest.mark.django_db
def test_soft_delete_filters_out_deleted_records():
    item = DummyItem.objects.create(name="Item 1")
    item.soft_delete(reason="Testing deletion")
    assert item.is_deleted is True
    assert item.delete_reason == "Testing deletion"
    assert DummyItem.objects.count() == 0
    assert DummyItem.all_objects.count() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\venv\Scripts\pytest tests/test_core_models.py -v`
Expected: FAIL (No module named `core.models`)

- [ ] **Step 3: Implement `core/models.py` and `core/middleware.py`**

Define `TimeStampedModel`, `SoftDeleteModel` with 8 audit fields, `ActiveManager` (`filter(is_deleted=False)`), and `AllObjectsManager`. Implement `CurrentRequestMiddleware` to capture current user in thread-local storage for auto-populating `created_by`, `updated_by`, and `deleted_by`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\venv\Scripts\pytest tests/test_core_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/ tests/test_core_models.py
git commit -m "feat(core): implement SoftDeleteModel, managers, and current user middleware"
```

---

### Task 3: Organization Module (`apps/organization` - Department, Person)

**Files:**
- Create: `apps/organization/models.py`
- Create: `apps/organization/admin.py`
- Create: `apps/organization/apps.py`
- Test: `tests/test_organization.py`

**Interfaces:**
- Consumes: `core.models.SoftDeleteModel`.
- Produces: `Department`, `Person` models with partial unique constraint on `staff_code`.

- [ ] **Step 1: Write failing tests for `Department` and `Person`**

```python
# tests/test_organization.py
import pytest
from apps.organization.models import Department, Person

@pytest.mark.django_db
def test_create_person_and_soft_delete_allows_recreation():
    dept = Department.objects.create(name_en="IT", name_ja="IT部")
    p1 = Person.objects.create(staff_code="TVC001", full_name="Nguyen Van A", department=dept)
    p1.soft_delete(reason="Wrong code")
    
    # Can re-create same staff_code because p1 is soft-deleted
    p2 = Person.objects.create(staff_code="TVC001", full_name="Nguyen Van A Correct", department=dept)
    assert p2.id != p1.id
    assert Person.objects.count() == 1
    assert Person.all_objects.count() == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\venv\Scripts\pytest tests/test_organization.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `apps/organization/models.py` and register in admin**

Implement `Department` (`name_en`, `name_ja`) and `Person` (`staff_code`, `full_name`, `department`, `status`) with partial unique constraint `UniqueConstraint(fields=['staff_code'], condition=Q(is_deleted=False), name='unique_active_staff_code')`.

- [ ] **Step 4: Run migrations and test**

Run: `.\venv\Scripts\python manage.py makemigrations organization; .\venv\Scripts\pytest tests/test_organization.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/organization/ tests/test_organization.py
git commit -m "feat(organization): implement Department and Person with soft delete"
```

---

### Task 4: Contracts Module (`apps/contracts` - Contract, ContractLine)

**Files:**
- Create: `apps/contracts/models.py`
- Create: `apps/contracts/admin.py`
- Create: `apps/contracts/apps.py`
- Test: `tests/test_contracts.py`

**Interfaces:**
- Consumes: `core.models.SoftDeleteModel`.
- Produces: `Contract`, `ContractLine` with computed `qty_received`.

- [ ] **Step 1: Write failing test for `Contract` and `ContractLine`**

```python
# tests/test_contracts.py
import pytest
from apps.contracts.models import Contract, ContractLine

@pytest.mark.django_db
def test_contract_creation_and_line_qty():
    contract = Contract.objects.create(code="KHCM-2408-0113", delivery_status="pending")
    line = ContractLine.objects.create(contract=contract, item_type="PC 16 inch", qty_ordered=5)
    assert contract.lines.count() == 1
    assert line.qty_received == 0
    assert line.is_fully_received is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\venv\Scripts\pytest tests/test_contracts.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `apps/contracts/models.py` and register in admin**

Implement `Contract` (`code`, `delivery_status`) and `ContractLine` (`contract`, `item_type`, `spec`, `qty_ordered`). Implement property `qty_received` using query on `Asset` and property `is_fully_received`.

- [ ] **Step 4: Run migrations and test**

Run: `.\venv\Scripts\python manage.py makemigrations contracts; .\venv\Scripts\pytest tests/test_contracts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/contracts/ tests/test_contracts.py
git commit -m "feat(contracts): implement Contract and ContractLine models"
```

---

### Task 5: Assets Module (`apps/assets` - AssetCategory, Asset, Assignment)

**Files:**
- Create: `apps/assets/models.py`
- Create: `apps/assets/admin.py`
- Create: `apps/assets/apps.py`
- Test: `tests/test_assets.py`

**Interfaces:**
- Consumes: `apps.organization.models.Person`, `apps.contracts.models.ContractLine`.
- Produces: `AssetCategory`, `Asset`, `Assignment`, validation preventing deletion of loaned asset, and auto status transitions.

- [ ] **Step 1: Write failing tests for Asset loaning and soft delete block**

```python
# tests/test_assets.py
import pytest
from datetime import date
from django.core.exceptions import ValidationError
from apps.organization.models import Person
from apps.assets.models import AssetCategory, Asset, Assignment

@pytest.mark.django_db
def test_loan_asset_updates_status_and_blocks_delete():
    cat = AssetCategory.objects.create(name="Laptop")
    person = Person.objects.create(staff_code="TVC002", full_name="Nguyen Van B")
    asset = Asset.objects.create(asset_code="TKY-PC001", category=cat, serial="SN12345", status="in_stock")
    
    # Assign asset to person
    assignment = Assignment.objects.create(asset=asset, person=person, borrowed_at=date.today())
    asset.refresh_from_db()
    assert asset.status == "loaned"
    
    # Attempting to soft-delete loaned asset must raise ValidationError
    with pytest.raises(ValidationError):
        asset.soft_delete(reason="Try delete while loaned")
        
    # Return asset
    assignment.returned_at = date.today()
    assignment.save()
    asset.refresh_from_db()
    assert asset.status == "in_stock"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\venv\Scripts\pytest tests/test_assets.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `apps/assets/models.py` with validation and status auto-update**

Implement `AssetCategory`, `Asset`, and `Assignment`. In `Assignment.save()`, sync `asset.status`. In `Asset.soft_delete()`, raise `ValidationError` if `status == 'loaned'` or has unreturned assignments. Add partial unique indexes for `asset_code` and `serial`.

- [ ] **Step 4: Run migrations and test**

Run: `.\venv\Scripts\python manage.py makemigrations assets; .\venv\Scripts\pytest tests/test_assets.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/assets/ tests/test_assets.py
git commit -m "feat(assets): implement Asset, Category, Assignment with validation and status transitions"
```

---

### Task 6: Licenses Module (`apps/licenses` - LicenseProduct, License, LicenseAssignment)

**Files:**
- Create: `apps/licenses/models.py`
- Create: `apps/licenses/admin.py`
- Create: `apps/licenses/apps.py`
- Test: `tests/test_licenses.py`

**Interfaces:**
- Consumes: `apps.assets.models.Asset`, `apps.organization.models.Person`.
- Produces: `LicenseProduct`, `License`, `LicenseAssignment`, license key masking, and expiry checking.

- [ ] **Step 1: Write failing tests for License assignment and key masking**

```python
# tests/test_licenses.py
import pytest
from datetime import date, timedelta
from django.core.exceptions import ValidationError
from apps.licenses.models import LicenseProduct, License, LicenseAssignment
from apps.assets.models import Asset, AssetCategory

@pytest.mark.django_db
def test_license_assignment_and_active_check():
    product = LicenseProduct.objects.create(name="IJCAD")
    license_obj = License.objects.create(
        product=product, seats=5, license_key="SECRET-KEY-1234",
        expiry_date=date.today() + timedelta(days=30)
    )
    cat = AssetCategory.objects.create(name="Desktop")
    asset = Asset.objects.create(asset_code="TKY-DT001", category=cat)
    
    # Must assign to either asset or person
    with pytest.raises(ValidationError):
        LicenseAssignment.objects.create(license=license_obj, assigned_at=date.today())
        
    assignment = LicenseAssignment.objects.create(license=license_obj, asset=asset, assigned_at=date.today())
    assert license_obj.assigned_seats_count == 1
    assert license_obj.is_expiring_soon(days=60) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\venv\Scripts\pytest tests/test_licenses.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `apps/licenses/models.py` and `apps/licenses/admin.py`**

Implement `LicenseProduct`, `License`, `LicenseAssignment`. Add `clean()` validation ensuring at least one of `asset` or `person` is set. In `admin.py`, mask `license_key` for non-superuser/non-IT Admin users.

- [ ] **Step 4: Run migrations and test**

Run: `.\venv\Scripts\python manage.py makemigrations licenses; .\venv\Scripts\pytest tests/test_licenses.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/licenses/ tests/test_licenses.py
git commit -m "feat(licenses): implement License, Assignment, expiry alerts, and key masking"
```

---

### Task 7: Access Cards Module (`apps/cards` - Room, AccessCard, CardLoan)

**Files:**
- Create: `apps/cards/models.py`
- Create: `apps/cards/admin.py`
- Create: `apps/cards/apps.py`
- Test: `tests/test_cards.py`

**Interfaces:**
- Consumes: `apps.organization.models.Person`.
- Produces: `Room`, `AccessCard`, `AccessCardRoom`, `CardLoan`.

- [ ] **Step 1: Write failing tests for Card loaning and external borrower validation**

```python
# tests/test_cards.py
import pytest
from datetime import date
from django.core.exceptions import ValidationError
from apps.cards.models import Room, AccessCard, CardLoan

@pytest.mark.django_db
def test_card_loan_external_borrower_validation():
    card = AccessCard.objects.create(card_no="CARD-001")
    
    # If person is None, external_name is required
    with pytest.raises(ValidationError):
        CardLoan.objects.create(card=card, borrowed_at=date.today())
        
    loan = CardLoan.objects.create(
        card=card, external_name="John Doe", external_company="Cleaning Corp",
        borrowed_at=date.today()
    )
    assert loan.is_active is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\venv\Scripts\pytest tests/test_cards.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `apps/cards/models.py` and register in admin**

Implement `Room`, `AccessCard`, `AccessCardRoom`, and `CardLoan` with partial unique constraint on `card_no`. Validate external borrower fields when `person` is null.

- [ ] **Step 4: Run migrations and test**

Run: `.\venv\Scripts\python manage.py makemigrations cards; .\venv\Scripts\pytest tests/test_cards.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/cards/ tests/test_cards.py
git commit -m "feat(cards): implement Room, AccessCard, and CardLoan with external borrower support"
```

---

### Task 8: Audit Logging Integration & Immutability

**Files:**
- Modify: `toku_itam/settings.py`
- Create: `core/audit.py`
- Test: `tests/test_audit.py`

**Interfaces:**
- Consumes: `auditlog` library or custom `AuditLog` model.
- Produces: Automated tracking of model changes and read-only history.

- [ ] **Step 1: Write failing test for audit tracking**

```python
# tests/test_audit.py
import pytest
from apps.organization.models import Department
from auditlog.models import LogEntry

@pytest.mark.django_db
def test_audit_logs_creation_and_update():
    dept = Department.objects.create(name_en="Sales", name_ja="営業")
    assert LogEntry.objects.filter(object_id=str(dept.id)).count() >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\venv\Scripts\pytest tests/test_audit.py -v`
Expected: FAIL

- [ ] **Step 3: Register models with `auditlog` and configure read-only admin**

Configure `auditlog` in `INSTALLED_APPS` and register `Person`, `Asset`, `Assignment`, `License`, `LicenseAssignment`, `AccessCard`, `CardLoan`, `Contract`. Ensure log entries cannot be modified or deleted.

- [ ] **Step 4: Run migrations and test**

Run: `.\venv\Scripts\python manage.py migrate; .\venv\Scripts\pytest tests/test_audit.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add toku_itam/settings.py core/audit.py tests/test_audit.py
git commit -m "feat(audit): integrate auditlog with immutable tracking"
```

---

### Task 9: RBAC Matrix & Bootstrap Command (`init_system`)

**Files:**
- Create: `core/management/commands/init_system.py`
- Test: `tests/test_rbac_init.py`

**Interfaces:**
- Consumes: Django auth `Group`, `Permission`.
- Produces: Groups `IT Admin`, `GA Manager`, `Executive` with RBAC permissions per spec, default admin user, and initial seed categories.

- [ ] **Step 1: Write failing test for RBAC groups & permissions**

```python
# tests/test_rbac_init.py
import pytest
from django.core.management import call_command
from django.contrib.auth.models import Group, User

@pytest.mark.django_db
def test_init_system_creates_roles_and_permissions():
    call_command("init_system")
    assert Group.objects.filter(name="IT Admin").exists()
    assert Group.objects.filter(name="GA Manager").exists()
    assert Group.objects.filter(name="Executive").exists()
    
    ga_group = Group.objects.get(name="GA Manager")
    perm_codenames = [p.codename for p in ga_group.permissions.all()]
    # GA has view, add, change for person
    assert "add_person" in perm_codenames
    assert "change_person" in perm_codenames
    # GA does NOT have license permissions
    assert not any("license" in c for c in perm_codenames)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\venv\Scripts\pytest tests/test_rbac_init.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `core/management/commands/init_system.py`**

Create 3 Groups (`IT Admin`, `GA Manager`, `Executive`) with exact permissions matching spec matrix. Create default admin `admin / tokuadmin2026`. Populate initial departments, asset categories, software products, and rooms.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\venv\Scripts\pytest tests/test_rbac_init.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/management/commands/init_system.py tests/test_rbac_init.py
git commit -m "feat(core): implement init_system command with RBAC matrix and seed data"
```

---

### Task 10: Extended Admin Features (Dashboard FR-13, Global Search FR-03, Person Profile FR-08, Trash Management)

**Files:**
- Create: `core/views.py`
- Create: `core/templates/admin/index.html`
- Create: `core/templates/admin/global_search.html`
- Create: `core/templates/admin/person_profile.html`
- Create: `core/templates/admin/trash.html`
- Modify: `core/admin.py`
- Test: `tests/test_extended_views.py`

**Interfaces:**
- Consumes: Django Admin site, Asset, License, CardLoan queries.
- Produces: Integrated Dashboard, Search, Person Profile 360, and Trash restoration view.

- [ ] **Step 1: Write failing test for Dashboard and Global Search views**

```python
# tests/test_extended_views.py
import pytest
from django.urls import reverse
from django.contrib.auth.models import User

@pytest.mark.django_db
def test_dashboard_and_search_views_accessible_to_staff(client):
    admin_user = User.objects.create_superuser("admin_test", "admin@toku.com", "pass123")
    client.force_login(admin_user)
    
    # Test Dashboard metrics in admin index
    res_index = client.get(reverse("admin:index"))
    assert res_index.status_code == 200
    assert b"asset_summary" in res_index.content or b"dashboard" in res_index.content
    
    # Test Global Search
    res_search = client.get(reverse("admin:global_search") + "?q=TVC")
    assert res_search.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\venv\Scripts\pytest tests/test_extended_views.py -v`
Expected: FAIL

- [ ] **Step 3: Implement Dashboard metrics, Global Search view, Person Profile view, and Trash Management in `core/admin.py`**

Override `AdminSite.index` to inject Dashboard statistics (counts by status, 60-day expiring licenses, unreturned cards). Implement `/admin/search/` querying across Asset, Person, Contract, and AccessCard. Implement `/admin/person/<id>/profile/`. Implement `/admin/trash/` with restore action.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\venv\Scripts\pytest tests/test_extended_views.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/admin.py core/templates/ tests/test_extended_views.py
git commit -m "feat(ui): implement Dashboard FR-13, Global Search FR-03, Person Profile FR-08, and Trash"
```

---

### Task 11: Multilingual i18n (English/Japanese), Header Language Switcher, Dark/Light Mode & End-to-End Verification

**Files:**
- Create: `locale/ja/LC_MESSAGES/django.po`
- Create: `locale/en/LC_MESSAGES/django.po`
- Create: `core/templates/admin/base_site.html`
- Modify: `toku_itam/settings.py`
- Test: `tests/test_i18n_and_e2e.py`

**Interfaces:**
- Consumes: Django i18n translation catalogs.
- Produces: Bilingual interface with Japanese/English language switcher and verified end-to-end flows.

- [ ] **Step 1: Write test for language switching and translations**

```python
# tests/test_i18n_and_e2e.py
import pytest
from django.urls import reverse

@pytest.mark.django_db
def test_language_switch_cookie_and_japanese_response(client):
    res = client.post(reverse("set_language"), data={"language": "ja", "next": reverse("admin:index")})
    assert res.status_code == 302
```

- [ ] **Step 2: Compile translation messages and configure Header Language Switcher**

Generate and compile translation catalogs for Japanese and English. Add language switcher form in `admin/base_site.html`.

- [ ] **Step 3: Run all test suites**

Run: `.\venv\Scripts\pytest -v`
Expected: All tests pass (100% test pass rate across core, organization, contracts, assets, licenses, cards, audit, rbac, and extended views).

- [ ] **Step 4: Run `init_system` on PostgreSQL and verify local server starts**

Run: `.\venv\Scripts\python manage.py init_system`
Expected: Roles, permissions, admin user, and seed categories populated successfully.

- [ ] **Step 5: Final Commit**

```bash
git add locale/ core/templates/ toku_itam/ tests/
git commit -m "feat(i18n): finalize Japanese/English translation, theme, and verified e2e test suite"
```
