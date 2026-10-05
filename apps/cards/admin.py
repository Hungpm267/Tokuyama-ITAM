from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from .models import Room, AccessCard, AccessCardRoom, CardLoan


class AccessCardRoomInline(admin.TabularInline):
    model = AccessCardRoom
    extra = 1


class CardLoanInline(admin.TabularInline):
    model = CardLoan
    extra = 0
    fields = ('person', 'external_name', 'external_company', 'purpose', 'borrowed_at', 'returned_at')


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'cards_count', 'created_at')
    search_fields = ('name',)

    def cards_count(self, obj):
        return obj.cards.count()
    cards_count.short_description = _('Số thẻ được vào')


@admin.register(AccessCard)
class AccessCardAdmin(admin.ModelAdmin):
    list_display = ('card_no', 'allowed_rooms_display', 'current_loan_status', 'created_at')
    search_fields = ('card_no',)
    inlines = [AccessCardRoomInline, CardLoanInline]

    def allowed_rooms_display(self, obj):
        rooms = list(obj.rooms.values_list('name', flat=True))
        return ', '.join(rooms) if rooms else '-'
    allowed_rooms_display.short_description = _('Phòng được phép vào')

    def current_loan_status(self, obj):
        active_loan = obj.loans.filter(returned_at__isnull=True).first()
        if active_loan:
            return format_html(
                '<span style="color: blue; font-weight: bold;">{} ({})</span>',
                _('Đang cho mượn'),
                active_loan.borrower_name
            )
        return format_html('<span style="color: green;">{}</span>', _('Sẵn sàng'))
    current_loan_status.short_description = _('Tình trạng')


@admin.register(CardLoan)
class CardLoanAdmin(admin.ModelAdmin):
    list_display = (
        'card', 'borrower_name', 'external_company',
        'purpose', 'borrowed_at', 'returned_at', 'status_badge'
    )
    list_filter = ('returned_at', 'borrowed_at')
    search_fields = ('card__card_no', 'person__full_name', 'external_name', 'external_company', 'purpose')

    def status_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="color: blue; font-weight: bold;">{}</span>', _('Đang mượn'))
        return format_html('<span style="color: gray;">{}</span>', _('Đã trả'))
    status_badge.short_description = _('Trạng thái')
