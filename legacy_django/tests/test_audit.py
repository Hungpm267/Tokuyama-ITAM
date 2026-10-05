import pytest
from apps.organization.models import Department
from auditlog.models import LogEntry

@pytest.mark.django_db
def test_audit_logs_creation_and_update():
    dept = Department.objects.create(name_en="Sales", name_ja="営業")
    
    # Check that LogEntry was created
    entry = LogEntry.objects.filter(object_id=str(dept.id)).first()
    assert entry is not None
    assert entry.action == LogEntry.Action.CREATE
    
    # Update dept
    dept.name_ja = "営業部"
    dept.save()
    
    entries = LogEntry.objects.filter(object_id=str(dept.id)).order_by('timestamp')
    assert entries.count() >= 2
    assert entries.last().action == LogEntry.Action.UPDATE

@pytest.mark.django_db
def test_audit_log_immutability():
    from django.contrib.admin.sites import site
    from auditlog.models import LogEntry
    from django.contrib.auth.models import User
    
    admin_instance = site._registry[LogEntry]
    user = User.objects.create_superuser("super", "super@test.com", "pass")
    
    class DummyRequest:
        def __init__(self, user):
            self.user = user
            
    req = DummyRequest(user)
    assert admin_instance.has_add_permission(req) is False
    assert admin_instance.has_change_permission(req) is False
    assert admin_instance.has_delete_permission(req) is False

