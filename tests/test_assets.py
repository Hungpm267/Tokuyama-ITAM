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
    
    # Now it can be soft-deleted
    asset.soft_delete(reason="Obsolete model")
    assert asset.is_deleted is True

@pytest.mark.django_db
def test_assignment_date_validation():
    cat = AssetCategory.objects.create(name="Monitor")
    person = Person.objects.create(staff_code="TVC003", full_name="Le Van C")
    asset = Asset.objects.create(asset_code="TKY-MON001", category=cat, status="in_stock")
    
    # Return date cannot be before borrow date
    assignment = Assignment(
        asset=asset,
        person=person,
        borrowed_at=date(2026, 10, 5),
        returned_at=date(2026, 10, 1)
    )
    with pytest.raises(ValidationError):
        assignment.full_clean()
