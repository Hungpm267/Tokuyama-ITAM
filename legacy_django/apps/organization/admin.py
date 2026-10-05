from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from .models import Department, Person


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name_en', 'name_ja', 'member_count', 'created_at')
    search_fields = ('name_en', 'name_ja')

    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = _('Số nhân viên')


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ('staff_code', 'full_name', 'department', 'status', 'view_profile_link')
    list_filter = ('status', 'department')
    search_fields = ('staff_code', 'full_name')

    def view_profile_link(self, obj):
        try:
            url = reverse('admin:person_profile', args=[obj.pk])
            return format_html('<a class="button" href="{}">{}</a>', url, _('Xem hồ sơ ITAM'))
        except Exception:
            return format_html('<span>-</span>')
    view_profile_link.short_description = _('Hồ sơ tài sản')
