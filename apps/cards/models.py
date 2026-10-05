from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from core.models import SoftDeleteModel
from apps.organization.models import Person


class Room(SoftDeleteModel):
    name = models.CharField(
        max_length=100,
        verbose_name=_('Tên phòng / Room Name')
    )

    class Meta:
        verbose_name = _('Phòng kiểm soát / Room')
        verbose_name_plural = _('Danh mục Phòng / Rooms')
        constraints = [
            models.UniqueConstraint(
                fields=['name'],
                condition=models.Q(is_deleted=False),
                name='unique_active_room_name'
            )
        ]

    def __str__(self):
        return self.name


class AccessCard(SoftDeleteModel):
    card_no = models.CharField(
        max_length=50,
        verbose_name=_('Số thẻ in trên thẻ / Card Number')
    )
    rooms = models.ManyToManyField(
        Room,
        through='AccessCardRoom',
        related_name='cards',
        blank=True,
        verbose_name=_('Phòng được phép vào / Allowed Rooms')
    )

    class Meta:
        verbose_name = _('Thẻ ra vào / Access Card')
        verbose_name_plural = _('Thẻ ra vào / Access Cards')
        constraints = [
            models.UniqueConstraint(
                fields=['card_no'],
                condition=models.Q(is_deleted=False),
                name='unique_active_card_no'
            )
        ]

    def __str__(self):
        return self.card_no

    def soft_delete(self, reason=None, user=None):
        if self.loans.filter(returned_at__isnull=True, is_deleted=False).exists():
            raise ValidationError(_('Không thể xóa thẻ đang được cho mượn. Vui lòng nhận trả thẻ trước khi xóa.'))
        super().soft_delete(reason=reason, user=user)


class AccessCardRoom(SoftDeleteModel):
    card = models.ForeignKey(
        AccessCard,
        on_delete=models.CASCADE,
        verbose_name=_('Thẻ / Card')
    )
    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        verbose_name=_('Phòng / Room')
    )

    class Meta:
        verbose_name = _('Quyền phòng thẻ / Card Room Access')
        verbose_name_plural = _('Quyền phòng thẻ / Card Room Accesses')
        constraints = [
            models.UniqueConstraint(
                fields=['card', 'room'],
                condition=models.Q(is_deleted=False),
                name='unique_active_card_room'
            )
        ]

    def __str__(self):
        return f"{self.card.card_no} <-> {self.room.name}"


class CardLoan(SoftDeleteModel):
    card = models.ForeignKey(
        AccessCard,
        on_delete=models.PROTECT,
        related_name='loans',
        verbose_name=_('Thẻ mượn / Card')
    )
    person = models.ForeignKey(
        Person,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='card_loans',
        verbose_name=_('Nhân viên mượn / Employee')
    )
    external_name = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name=_('Tên người ngoài / External Borrower Name')
    )
    external_company = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name=_('Công ty đối tác / External Company')
    )
    purpose = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name=_('Mục đích mượn / Purpose')
    )
    borrowed_at = models.DateField(
        verbose_name=_('Ngày mượn / Borrowed Date')
    )
    returned_at = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('Ngày trả / Returned Date')
    )

    class Meta:
        verbose_name = _('Mượn thẻ / Card Loan')
        verbose_name_plural = _('Lịch sử Mượn thẻ / Card Loans')

    @property
    def is_active(self):
        return self.returned_at is None

    @property
    def borrower_name(self):
        if self.person:
            return self.person.full_name
        if self.external_name:
            if self.external_company:
                return f"{self.external_name} ({self.external_company})"
            return self.external_name
        return '-'

    def clean(self):
        super().clean()
        if not self.person and not self.external_name:
            raise ValidationError(_('Bắt buộc phải chọn nhân viên mượn hoặc nhập họ tên người bên ngoài.'))
        if self.returned_at and self.borrowed_at and self.returned_at < self.borrowed_at:
            raise ValidationError({'returned_at': _('Ngày trả không thể trước ngày mượn.')})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        status = _('Đang mượn') if self.is_active else _('Đã trả')
        return f"Thẻ {self.card.card_no} -> {self.borrower_name} [{status}]"
