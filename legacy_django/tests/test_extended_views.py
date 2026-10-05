import pytest
from datetime import date, timedelta
from django.urls import reverse
from django.contrib.auth.models import User
from apps.organization.models import Person, Department
from apps.assets.models import Asset, AssetCategory, Assignment
from apps.licenses.models import LicenseProduct, License, LicenseAssignment
from apps.cards.models import AccessCard, Room, CardLoan
from apps.contracts.models import Contract

@pytest.mark.django_db
def test_dashboard_displays_metrics_in_admin_index(client):
    admin_user = User.objects.create_superuser("admin_dashboard", "admin@toku.com", "pass123")
    client.force_login(admin_user)
    
    # Create test data
    cat = AssetCategory.objects.create(name="Laptop")
    Asset.objects.create(asset_code="PC-DASH-1", category=cat, status="in_stock")
    Asset.objects.create(asset_code="PC-DASH-2", category=cat, status="loaned")
    
    # Expiring license
    prod = LicenseProduct.objects.create(name="Office 2026")
    License.objects.create(product=prod, seats=10, expiry_date=date.today() + timedelta(days=15))
    
    # Active card loan
    card = AccessCard.objects.create(card_no="CARD-999")
    CardLoan.objects.create(card=card, external_name="Contractor A", external_company="Cleaning", borrowed_at=date.today())
    
    res = client.get(reverse("admin:index"))
    assert res.status_code == 200
    content = res.content.decode('utf-8')
    assert "PC-DASH" in content or "Laptop" in content or "asset_stats" in res.context
    assert "Office 2026" in content or "expiring_licenses" in res.context
    assert "CARD-999" in content or "unreturned_cards" in res.context

@pytest.mark.django_db
def test_global_search_returns_grouped_results(client):
    admin_user = User.objects.create_superuser("admin_search", "admin@toku.com", "pass123")
    client.force_login(admin_user)
    
    cat = AssetCategory.objects.create(name="Desktop")
    Asset.objects.create(asset_code="TKY-SEARCH-01", serial="SERIAL-XYZ", category=cat)
    dept = Department.objects.create(name_en="IT")
    Person.objects.create(staff_code="TVC999", full_name="Yamada Taro", department=dept)
    Contract.objects.create(code="KHCM-SEARCH-2026")
    
    # Search for serial
    res1 = client.get(reverse("admin:global_search") + "?q=SERIAL-XYZ")
    assert res1.status_code == 200
    assert "TKY-SEARCH-01" in res1.content.decode('utf-8')
    
    # Search for person
    res2 = client.get(reverse("admin:global_search") + "?q=Yamada")
    assert res2.status_code == 200
    assert "TVC999" in res2.content.decode('utf-8')

@pytest.mark.django_db
def test_person_profile_view(client):
    admin_user = User.objects.create_superuser("admin_profile", "admin@toku.com", "pass123")
    client.force_login(admin_user)
    
    dept = Department.objects.create(name_en="IT")
    person = Person.objects.create(staff_code="TVC-PROF", full_name="Nguyen Van Profile", department=dept)
    cat = AssetCategory.objects.create(name="Laptop")
    asset = Asset.objects.create(asset_code="TKY-PROF-01", category=cat)
    Assignment.objects.create(asset=asset, person=person, borrowed_at=date.today())
    
    res = client.get(reverse("admin:person_profile", args=[person.pk]))
    assert res.status_code == 200
    content = res.content.decode('utf-8')
    assert "Nguyen Van Profile" in content
    assert "TKY-PROF-01" in content

@pytest.mark.django_db
def test_trash_restore_action(client):
    admin_user = User.objects.create_superuser("admin_trash_test", "admin@toku.com", "pass123")
    client.force_login(admin_user)
    
    cat = AssetCategory.objects.create(name="Mouse")
    asset = Asset.objects.create(asset_code="TKY-MOUSE-01", category=cat)
    asset.soft_delete(reason="Damaged sensor", user=admin_user)
    assert Asset.objects.count() == 0
    assert Asset.all_objects.count() == 1
    
    # Check trash view lists it
    res_trash = client.get(reverse("admin:trash"))
    assert res_trash.status_code == 200
    assert "TKY-MOUSE-01" in res_trash.content.decode('utf-8')
    
    # Post restore
    res_restore = client.post(reverse("admin:trash"), data={
        'restore_item': '1',
        'model_name': 'asset',
        'item_id': str(asset.pk),
    }, follow=True)
    assert res_restore.status_code == 200
    assert Asset.objects.count() == 1
    asset.refresh_from_db()
    assert asset.is_deleted is False

