from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import SoftDeleteModel


class Department(SoftDeleteModel):
    name_en = models.CharField(
        max_length=100,
        verbose_name=_('Tên tiếng Anh / English Name')
    )
    name_ja = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name=_('Tên tiếng Nhật / Japanese Name')
    )

    class Meta:
        verbose_name = _('Phòng ban / Department')
        verbose_name_plural = _('Phòng ban / Departments')
        constraints = [
            models.UniqueConstraint(
                fields=['name_en'],
                condition=models.Q(is_deleted=False),
                name='unique_active_department_name_en'
            )
        ]

    def __str__(self):
        if self.name_ja:
            return f"{self.name_en} ({self.name_ja})"
        return self.name_en


class Person(SoftDeleteModel):
    STATUS_CHOICES = [
        ('active', _('Đang làm việc / Active')),
        ('resigned', _('Đã nghỉ việc / Resigned')),
    ]

    staff_code = models.CharField(
        max_length=50,
        verbose_name=_('Mã nhân viên / Staff Code')
    )
    full_name = models.CharField(
        max_length=100,
        verbose_name=_('Họ tên / Full Name')
    )
    department = models.ForeignKey(
        Department,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='members',
        verbose_name=_('Phòng ban / Department')
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        verbose_name=_('Trạng thái / Status')
    )

    class Meta:
        verbose_name = _('Nhân viên / Person')
        verbose_name_plural = _('Nhân viên / Persons')
        constraints = [
            models.UniqueConstraint(
                fields=['staff_code'],
                condition=models.Q(is_deleted=False),
                name='unique_active_staff_code'
            )
        ]

    def __str__(self):
        return f"{self.staff_code} - {self.full_name}"
