from django.contrib import admin
from auditlog.models import LogEntry

# Ensure LogEntry in admin is strictly immutable (no add, no change, no delete)
try:
    admin.site.unregister(LogEntry)
except admin.sites.NotRegistered:
    pass

@admin.register(LogEntry)
class ImmutableLogEntryAdmin(admin.ModelAdmin):
    list_display = ('created', 'actor', 'action_display', 'content_type', 'object_repr', 'changes_display')
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
