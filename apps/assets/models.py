from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from core.models import SoftDeleteModel
from apps.organization.models import Person
from apps.contracts.models import ContractLine


class AssetCategory(SoftDeleteModel):
    name = models.CharField(
        max_length=50,
        verbose_name=_('Tên loại thiết bị / Category Name')
    )

    class Meta:
        verbose_name = _('Loại thiết bị / Asset Category')
        verbose_name_plural = _('Loại thiết bị / Asset Categories')
        constraints = [
            models.UniqueConstraint(
                fields=['name'],
                condition=models.Q(is_deleted=False),
                name='unique_active_asset_category_name'
            )
        ]

    def __str__(self):
        return self.name


class Asset(SoftDeleteModel):
    STATUS_CHOICES = [
        ('in_stock', _('Trong kho / In Stock')),
        ('loaned', _('Đang mượn / Loaned')),
        ('lost', _('Mất / Lost')),
    ]

    asset_code = models.CharField(
        max_length=50,
        verbose_name=_('Mã tài sản / Asset Code')
    )
    category = models.ForeignKey(
        AssetCategory,
        on_delete=models.PROTECT,
        related_name='assets',
        verbose_name=_('Loại thiết bị / Category')
    )
    contract_line = models.ForeignKey(
        ContractLine,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='assets',
        verbose_name=_('Dòng hợp đồng mua / Contract Line')
    )
    model = models.CharField(
        max_length=150,
        null=True,
        blank=True,
        verbose_name=_('Model thiết bị / Model')
    )
    serial = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name=_('Số Serial / Serial Number')
    )
    hwid = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name=_('Mã phần cứng / HWID')
    )
    mac_address = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name=_('Địa chỉ MAC / MAC Address')
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='in_stock',
        verbose_name=_('Trạng thái / Status')
    )
    note = models.TextField(
        null=True,
        blank=True,
        verbose_name=_('Ghi chú / Note')
    )

    class Meta:
        verbose_name = _('Tài sản / Asset')
        verbose_name_plural = _('Tài sản / Assets')
        constraints = [
            models.UniqueConstraint(
                fields=['asset_code'],
                condition=models.Q(is_deleted=False),
                name='unique_active_asset_code'
            ),
            models.UniqueConstraint(
                fields=['serial'],
                condition=models.Q(is_deleted=False) & ~models.Q(serial=''),
                name='unique_active_asset_serial'
            )
        ]

    def __str__(self):
        label = f"{self.asset_code} ({self.category.name})"
        if self.model:
            label += f" - {self.model}"
        if self.serial:
            label += f" [S/N: {self.serial}]"
        return label

    def soft_delete(self, reason=None, user=None):
        # Prevent deletion if currently loaned or has unreturned assignment
        if self.status == 'loaned' or self.assignments.filter(returned_at__isnull=True, is_deleted=False).exists():
            raise ValidationError(_('Không thể xóa tài sản đang được mượn. Vui lòng thu hồi thiết bị trước khi xóa.'))
        super().soft_delete(reason=reason, user=user)


class Assignment(SoftDeleteModel):
    asset = models.ForeignKey(
        Asset,
        on_delete=models.PROTECT,
        related_name='assignments',
        verbose_name=_('Thiết bị / Asset')
    )
    person = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name='assignments',
        verbose_name=_('Người mượn / Person')
    )
    borrowed_at = models.DateField(
        verbose_name=_('Ngày bắt đầu mượn / Borrowed Date')
    )
    returned_at = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('Ngày trả / Returned Date')
    )
    note = models.TextField(
        null=True,
        blank=True,
        verbose_name=_('Ghi chú / Note')
    )

    class Meta:
        verbose_name = _('Mượn - Trả thiết bị / Asset Assignment')
        verbose_name_plural = _('Lịch sử Mượn - Trả / Asset Assignments')

    def clean(self):
        super().clean()
        if self.returned_at and self.borrowed_at and self.returned_at < self.borrowed_at:
            raise ValidationError({'returned_at': _('Ngày trả không thể trước ngày mượn.')})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
        
        # Synchronize asset status
        if self.returned_at is None:
            if self.asset.status != 'loaned':
                self.asset.status = 'loaned'
                self.asset.save(update_fields=['status'])
        else:
            # Check if there are any other active unreturned assignments
            has_other_active = self.asset.assignments.filter(
                returned_at__isnull=True,
                is_deleted=False
            ).exclude(pk=self.pk).exists()
            if not has_other_active and self.asset.status == 'loaned':
                self.asset.status = 'in_stock'
                self.asset.save(update_fields=['status'])
