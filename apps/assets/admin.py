from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from .models import AssetCategory, Asset, Assignment


class AssignmentInline(admin.TabularInline):
    model = Assignment
    extra = 0
    fields = ('person', 'borrowed_at', 'returned_at', 'note')


@admin.register(AssetCategory)
class AssetCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'asset_count', 'created_at')
    search_fields = ('name',)

    def asset_count(self, obj):
        return obj.assets.count()
    asset_count.short_description = _('Số thiết bị')


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = (
        'asset_code', 'category', 'model', 'serial', 'status_badge',
        'current_holder', 'contract_line', 'created_at'
    )
    list_filter = ('category', 'status', 'contract_line__contract')
    search_fields = ('asset_code', 'serial', 'hwid', 'mac_address', 'model')
    inlines = [AssignmentInline]

    def status_badge(self, obj):
        colors = {
            'in_stock': 'green',
            'loaned': '#2563eb',
            'lost': 'red',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = _('Trạng thái')

    def current_holder(self, obj):
        active_assignment = obj.assignments.filter(returned_at__isnull=True).select_related('person').first()
        if active_assignment:
            return active_assignment.person.full_name
        return '-'
    current_holder.short_description = _('Người đang giữ')


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('asset', 'person', 'borrowed_at', 'returned_at', 'loan_status')
    list_filter = ('returned_at', 'borrowed_at')
    search_fields = ('asset__asset_code', 'asset__serial', 'person__full_name', 'person__staff_code')

    def loan_status(self, obj):
        if obj.returned_at is None:
            return format_html('<span style="color: blue; font-weight: bold;">{}</span>', _('Đang mượn'))
        return format_html('<span style="color: gray;">{}</span>', _('Đã trả'))
    loan_status.short_description = _('Tình trạng')
