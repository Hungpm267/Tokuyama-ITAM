from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import SoftDeleteModel


class Contract(SoftDeleteModel):
    STATUS_CHOICES = [
        ('pending', _('Chưa giao / Pending')),
        ('delivered', _('Đã giao / Delivered')),
    ]

    code = models.CharField(
        max_length=50,
        verbose_name=_('Mã hợp đồng / Contract Code')
    )
    delivery_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name=_('Tình trạng giao hàng / Delivery Status')
    )

    class Meta:
        verbose_name = _('Hợp đồng / Contract')
        verbose_name_plural = _('Hợp đồng / Contracts')
        constraints = [
            models.UniqueConstraint(
                fields=['code'],
                condition=models.Q(is_deleted=False),
                name='unique_active_contract_code'
            )
        ]

    def __str__(self):
        return f"{self.code} ({self.get_delivery_status_display()})"


class ContractLine(SoftDeleteModel):
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name=_('Hợp đồng / Contract')
    )
    item_type = models.CharField(
        max_length=100,
        verbose_name=_('Loại hàng / Item Type')
    )
    spec = models.TextField(
        null=True,
        blank=True,
        verbose_name=_('Cấu hình / Specification')
    )
    qty_ordered = models.PositiveIntegerField(
        verbose_name=_('Số lượng đặt / Ordered Qty')
    )

    class Meta:
        verbose_name = _('Dòng hàng hợp đồng / Contract Line')
        verbose_name_plural = _('Dòng hàng hợp đồng / Contract Lines')

    @property
    def qty_received(self):
        """Count received active assets attached to this line."""
        if hasattr(self, 'assets'):
            return self.assets.filter(is_deleted=False).count()
        return 0

    @property
    def is_fully_received(self):
        return self.qty_received >= self.qty_ordered

    def __str__(self):
        return f"{self.contract.code} - {self.item_type} ({self.qty_received}/{self.qty_ordered})"
