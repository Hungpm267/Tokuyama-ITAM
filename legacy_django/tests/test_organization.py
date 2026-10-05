import pytest
from django.db import IntegrityError
from apps.organization.models import Department, Person

@pytest.mark.django_db
def test_create_person_and_soft_delete_allows_recreation():
    dept = Department.objects.create(name_en="IT", name_ja="IT部")
    p1 = Person.objects.create(staff_code="TVC001", full_name="Nguyen Van A", department=dept)
    
    assert Person.objects.count() == 1
    assert str(p1) == "TVC001 - Nguyen Van A"
    
    # Soft-delete p1
    p1.soft_delete(reason="Wrong code")
    assert Person.objects.count() == 0
    assert Person.all_objects.count() == 1
    
    # Can re-create same staff_code because p1 is soft-deleted
    p2 = Person.objects.create(staff_code="TVC001", full_name="Nguyen Van A Correct", department=dept)
    assert p2.id != p1.id
    assert Person.objects.count() == 1
    assert Person.all_objects.count() == 2

@pytest.mark.django_db
def test_duplicate_active_staff_code_raises_error():
    dept = Department.objects.create(name_en="General Affairs", name_ja="総務部")
    Person.objects.create(staff_code="TVC002", full_name="Tran Van B", department=dept)
    with pytest.raises(IntegrityError):
        Person.objects.create(staff_code="TVC002", full_name="Duplicate Code", department=dept)
