from django.contrib import admin
from django.urls import path
from auditlog.models import LogEntry
from core.views import (
    get_dashboard_context,
    global_search_view,
    person_profile_view,
    trash_management_view,
)

# Ensure LogEntry in admin is strictly immutable (no add, no change, no delete)
try:
    admin.site.unregister(LogEntry)
except admin.sites.NotRegistered:
    pass

@admin.register(LogEntry)
class ImmutableLogEntryAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'actor', 'action_display', 'content_type', 'object_repr', 'changes_display')
    list_filter = ('action', 'content_type', 'timestamp')
    search_fields = ('object_repr', 'changes', 'actor__username')
    readonly_fields = [f.name for f in LogEntry._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def action_display(self, obj):
        actions = {
            LogEntry.Action.CREATE: 'Thêm mới (Create)',
            LogEntry.Action.UPDATE: 'Cập nhật (Update)',
            LogEntry.Action.DELETE: 'Xóa (Delete)',
        }
        return actions.get(obj.action, str(obj.action))
    action_display.short_description = 'Hành động'

    def changes_display(self, obj):
        return str(obj.changes)[:80] + '...' if len(str(obj.changes)) > 80 else str(obj.changes)
    changes_display.short_description = 'Thay đổi dữ liệu'


# --- Hook custom URLs & Dashboard into Django Admin Site ---
original_get_urls = admin.site.get_urls

def custom_admin_urls():
    custom_urls = [
        path('search/', admin.site.admin_view(global_search_view), name='global_search'),
        path('person/<int:person_id>/profile/', admin.site.admin_view(person_profile_view), name='person_profile'),
        path('trash/', admin.site.admin_view(trash_management_view), name='trash'),
    ]
    return custom_urls + original_get_urls()

admin.site.get_urls = custom_admin_urls

original_index = admin.site.index

def custom_admin_index(request, extra_context=None):
    if extra_context is None:
        extra_context = {}
    extra_context.update(get_dashboard_context())
    return original_index(request, extra_context=extra_context)

admin.site.index = custom_admin_index

admin.site.site_header = "Tokuyama Vietnam ITAM"
admin.site.site_title = "Tokuyama ITAM Admin"
admin.site.index_title = "Hệ thống Quản lý Tài sản IT - Tokuyama Vietnam"
