import pytest
from django.core.management import call_command
from django.contrib.auth.models import Group, User
from apps.organization.models import Department
from apps.assets.models import AssetCategory
from apps.licenses.models import LicenseProduct
from apps.cards.models import Room

@pytest.mark.django_db
def test_init_system_creates_roles_permissions_and_seed_data():
    call_command("init_system")
    
    # Check groups
    assert Group.objects.filter(name="IT Admin").exists()
    assert Group.objects.filter(name="GA Manager").exists()
    assert Group.objects.filter(name="Executive").exists()
    
    # Check GA Manager permissions
    ga_group = Group.objects.get(name="GA Manager")
    ga_perms = [p.codename for p in ga_group.permissions.all()]
    
    # GA has add, change, view for person, but NOT delete
    assert "add_person" in ga_perms
    assert "change_person" in ga_perms
    assert "view_person" in ga_perms
    assert "delete_person" not in ga_perms
    
    # GA has full on cardloan
    assert "add_cardloan" in ga_perms
    assert "delete_cardloan" in ga_perms
    
    # GA has NO license perms
    assert not any("license" in p for p in ga_perms)
    
    # Check Executive permissions (view-only)
    exec_group = Group.objects.get(name="Executive")
    exec_perms = [p.codename for p in exec_group.permissions.all()]
    assert all(p.startswith("view_") for p in exec_perms)
    assert "view_asset" in exec_perms
    assert "view_license" in exec_perms
    assert "view_contract" in exec_perms
    
    # Check admin user
    assert User.objects.filter(username="admin").exists()
    admin_user = User.objects.get(username="admin")
    assert admin_user.is_superuser is True
    
    # Check seed data
    assert Department.objects.filter(name_en="General Affairs").exists()
    assert AssetCategory.objects.filter(name="Laptop").exists()
    assert LicenseProduct.objects.filter(name="IJCAD").exists()
    assert Room.objects.filter(name="Server Room").exists()
