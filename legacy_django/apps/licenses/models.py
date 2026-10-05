from datetime import date, timedelta
from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from core.models import SoftDeleteModel
from apps.assets.models import Asset
from apps.organization.models import Person


class LicenseProduct(SoftDeleteModel):
    name = models.CharField(
        max_length=100,
        verbose_name=_('Tên phần mềm / Software Product')
    )

    class Meta:
        verbose_name = _('Phần mềm bản quyền / License Product')
        verbose_name_plural = _('Danh mục Phần mềm / License Products')
        constraints = [
            models.UniqueConstraint(
                fields=['name'],
                condition=models.Q(is_deleted=False),
                name='unique_active_license_product_name'
            )
        ]

    def __str__(self):
        return self.name


class License(SoftDeleteModel):
    product = models.ForeignKey(
        LicenseProduct,
        on_delete=models.PROTECT,
        related_name='licenses',
        verbose_name=_('Phần mềm / Product')
    )
    seats = models.PositiveIntegerField(
        default=1,
        verbose_name=_('Số lượng bản quyền (Seats) / Total Seats')
    )
    license_key = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name=_('Mã bản quyền / License Key')
    )
    start_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('Ngày bắt đầu / Start Date')
    )
    expiry_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('Ngày hết hạn / Expiry Date (Để trống nếu Vĩnh viễn)')
    )

    class Meta:
        verbose_name = _('Gói License / License')
        verbose_name_plural = _('Gói License / Licenses')

    @property
    def assigned_seats_count(self):
        return self.assignments.filter(removed_at__isnull=True, is_deleted=False).count()

    @property
    def available_seats(self):
        return max(0, self.seats - self.assigned_seats_count)

    def is_expiring_soon(self, days=60):
        if not self.expiry_date:
            return False
        today = date.today()
        return today <= self.expiry_date <= (today + timedelta(days=days))

    @property
    def is_expired(self):
        if not self.expiry_date:
            return False
        return self.expiry_date < date.today()

    def __str__(self):
        expiry_info = self.expiry_date.strftime('%Y-%m-%d') if self.expiry_date else _('Vĩnh viễn / Perpetual')
        return f"{self.product.name} ({self.assigned_seats_count}/{self.seats} seats - Hạn: {expiry_info})"

    def soft_delete(self, reason=None, user=None):
        if self.assigned_seats_count > 0:
            raise ValidationError(_('Không thể xóa license đang được gán. Vui lòng thu hồi trước khi xóa.'))
        super().soft_delete(reason=reason, user=user)


class LicenseAssignment(SoftDeleteModel):
    license = models.ForeignKey(
        License,
        on_delete=models.PROTECT,
        related_name='assignments',
        verbose_name=_('Gói License / License')
    )
    asset = models.ForeignKey(
        Asset,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='license_assignments',
        verbose_name=_('Thiết bị / Asset')
    )
    person = models.ForeignKey(
        Person,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='license_assignments',
        verbose_name=_('Người dùng / Person')
    )
    assigned_at = models.DateField(
        verbose_name=_('Ngày gán / Assigned Date')
    )
    removed_at = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('Ngày gỡ / Removed Date')
    )

    class Meta:
        verbose_name = _('Gán License / License Assignment')
        verbose_name_plural = _('Lịch sử Gán License / License Assignments')

    def clean(self):
        super().clean()
        if not self.asset and not self.person:
            raise ValidationError(_('Phải chọn ít nhất một đối tượng: Thiết bị hoặc Người dùng để gán license.'))
        if self.removed_at and self.assigned_at and self.removed_at < self.assigned_at:
            raise ValidationError({'removed_at': _('Ngày gỡ license không thể trước ngày gán.')})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        target = self.asset.asset_code if self.asset else self.person.full_name
        return f"{self.license.product.name} -> {target}"
