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
    assignment_invalid = LicenseAssignment(license=license_obj, assigned_at=date.today())
    with pytest.raises(ValidationError):
        assignment_invalid.full_clean()
        
    assignment = LicenseAssignment.objects.create(license=license_obj, asset=asset, assigned_at=date.today())
    assert license_obj.assigned_seats_count == 1
    assert license_obj.available_seats == 4
    assert license_obj.is_expiring_soon(days=60) is True

    # Block deleting license with active assignments
    with pytest.raises(ValidationError):
        license_obj.soft_delete(reason="Deleting active license")
        
    # Remove assignment
    assignment.removed_at = date.today()
    assignment.save()
    assert license_obj.assigned_seats_count == 0
    license_obj.soft_delete(reason="No longer used")
    assert license_obj.is_deleted is True
