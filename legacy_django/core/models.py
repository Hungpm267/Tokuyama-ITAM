from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from core.middleware import get_current_user


class ActiveManager(models.Manager):
    """Manager that only returns non-deleted records."""
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class AllObjectsManager(models.Manager):
    """Manager that returns all records, including soft-deleted ones."""
    pass


class TimeStampedModel(models.Model):
    """Abstract model providing automatic timestamp and user tracking fields."""
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Thời điểm tạo')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='%(app_label)s_%(class)s_created',
        verbose_name=_('Người tạo')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Lần sửa gần nhất')
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='%(app_label)s_%(class)s_updated',
        verbose_name=_('Người sửa gần nhất')
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        user = get_current_user()
        if user and user.is_authenticated:
            if not self.pk and not self.created_by:
                self.created_by = user
            self.updated_by = user
        super().save(*args, **kwargs)


class SoftDeleteModel(TimeStampedModel):
    """
    Abstract model providing 8 standard fields for audit and soft delete:
    created_at, created_by, updated_at, updated_by,
    is_deleted, deleted_at, deleted_by, delete_reason.
    """
    is_deleted = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_('Đã xóa mềm')
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Thời điểm xóa')
    )
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='%(app_label)s_%(class)s_deleted',
        verbose_name=_('Người xóa')
    )
    delete_reason = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name=_('Lý do xóa')
    )

    objects = ActiveManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def soft_delete(self, reason=None, user=None):
        """Soft delete the instance with reason and tracking."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.delete_reason = reason
        if user:
            self.deleted_by = user
        else:
            current_user = get_current_user()
            if current_user and current_user.is_authenticated:
                self.deleted_by = current_user
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by', 'delete_reason', 'updated_at'])

    def restore(self):
        """Restore a soft-deleted record."""
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.delete_reason = None
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by', 'delete_reason', 'updated_at'])
