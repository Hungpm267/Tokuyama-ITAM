import pytest
from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from core.models import SoftDeleteModel

class DummySampleItem(SoftDeleteModel):
    name = models.CharField(max_length=50)

    class Meta:
        app_label = 'core'

@pytest.mark.django_db
def test_soft_delete_and_restore_cycle():
    user = User.objects.create_user(username="testuser", password="password")
    item = DummySampleItem.objects.create(name="Item 1", created_by=user)
    
    assert item.is_deleted is False
    assert DummySampleItem.objects.count() == 1
    assert DummySampleItem.all_objects.count() == 1

    # Soft delete
    item.soft_delete(reason="Typo in record", user=user)
    assert item.is_deleted is True
    assert item.delete_reason == "Typo in record"
    assert item.deleted_by == user
    assert item.deleted_at is not None

    # Manager filtering
    assert DummySampleItem.objects.count() == 0
    assert DummySampleItem.all_objects.count() == 1

    # Restore
    item.restore()
    assert item.is_deleted is False
    assert item.delete_reason is None
    assert DummySampleItem.objects.count() == 1
