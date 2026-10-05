from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from .models import LicenseProduct, License, LicenseAssignment


class LicenseAssignmentInline(admin.TabularInline):
    model = LicenseAssignment
    extra = 0
    fields = ('asset', 'person', 'assigned_at', 'removed_at')


@admin.register(LicenseProduct)
class LicenseProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'total_licenses', 'created_at')
    search_fields = ('name',)

    def total_licenses(self, obj):
        return obj.licenses.count()
    total_licenses.short_description = _('Số gói license')


@admin.register(License)
class LicenseAdmin(admin.ModelAdmin):
    list_display = (
        'product', 'seats', 'seats_status', 'masked_license_key',
        'expiry_date', 'expiry_status_badge', 'created_at'
    )
    list_filter = ('product', 'expiry_date')
    search_fields = ('product__name', 'license_key')
    inlines = [LicenseAssignmentInline]

    def seats_status(self, obj):
        return f"{obj.assigned_seats_count} / {obj.seats} (Trống: {obj.available_seats})"
    seats_status.short_description = _('Đã dùng / Tổng')

    def masked_license_key(self, obj):
        if not obj.license_key:
            return '-'
        # Check permissions through current user or show masked
        # Note: In Django admin list_display, request is not passed directly, but we can check if current thread user is IT Admin
        from core.middleware import get_current_user
        user = get_current_user()
        if user and (user.is_superuser or user.groups.filter(name='IT Admin').exists()):
            return obj.license_key
        return '••••••••••••'
    masked_license_key.short_description = _('Mã bản quyền (Key)')

    def expiry_status_badge(self, obj):
        if not obj.expiry_date:
            return format_html('<span style="color: green;">{}</span>', _('Vĩnh viễn'))
        if obj.is_expired:
            return format_html('<span style="color: red; font-weight: bold;">{}</span>', _('Đã quá hạn!'))
        if obj.is_expiring_soon(days=60):
            days_left = (obj.expiry_date - obj.expiry_date.today()).days
            return format_html('<span style="color: #d97706; font-weight: bold;">{} ({} ngày)</span>', _('Sắp hết hạn'), days_left)
        return format_html('<span style="color: green;">{}</span>', obj.expiry_date.strftime('%Y-%m-%d'))
    expiry_status_badge.short_description = _('Tình trạng hạn dùng')


@admin.register(LicenseAssignment)
class LicenseAssignmentAdmin(admin.ModelAdmin):
    list_display = ('license', 'assigned_target', 'assigned_at', 'removed_at', 'status_badge')
    list_filter = ('license__product', 'removed_at')
    search_fields = ('license__product__name', 'asset__asset_code', 'person__full_name')

    def assigned_target(self, obj):
        if obj.asset:
            return f"Thiết bị: {obj.asset}"
        if obj.person:
            return f"Nhân viên: {obj.person}"
        return '-'
    assigned_target.short_description = _('Đối tượng gán')

    def status_badge(self, obj):
        if obj.removed_at is None:
            return format_html('<span style="color: blue; font-weight: bold;">{}</span>', _('Đang sử dụng'))
        return format_html('<span style="color: gray;">{}</span>', _('Đã gỡ'))
    status_badge.short_description = _('Trạng thái')
