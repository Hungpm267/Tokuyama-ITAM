from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from .models import Contract, ContractLine


class ContractLineInline(admin.TabularInline):
    model = ContractLine
    extra = 1
    fields = ('item_type', 'spec', 'qty_ordered', 'received_progress')
    readonly_fields = ('received_progress',)

    def received_progress(self, obj):
        if not obj.pk:
            return '-'
        color = 'green' if obj.is_fully_received else 'orange'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}/{} ({})</span>',
            color,
            obj.qty_received,
            obj.qty_ordered,
            _('Đã nhận đủ') if obj.is_fully_received else _('Chưa đủ')
        )
    received_progress.short_description = _('Tiến độ nhận hàng')


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ('code', 'delivery_status', 'total_lines', 'created_at')
    list_filter = ('delivery_status',)
    search_fields = ('code',)
    inlines = [ContractLineInline]

    def total_lines(self, obj):
        return obj.lines.count()
    total_lines.short_description = _('Số dòng hàng')


@admin.register(ContractLine)
class ContractLineAdmin(admin.ModelAdmin):
    list_display = ('contract', 'item_type', 'qty_ordered', 'qty_received_display', 'status_badge')
    list_filter = ('contract__delivery_status',)
    search_fields = ('contract__code', 'item_type')

    def qty_received_display(self, obj):
        return f"{obj.qty_received} / {obj.qty_ordered}"
    qty_received_display.short_description = _('Đã nhận / Đặt')

    def status_badge(self, obj):
        if obj.is_fully_received:
            return format_html('<span style="color: green; font-weight: bold;">✔ {}</span>', _('Đã nhận đủ'))
        return format_html('<span style="color: orange; font-weight: bold;">⏳ {}</span>', _('Chưa nhận đủ'))
    status_badge.short_description = _('Trạng thái')
