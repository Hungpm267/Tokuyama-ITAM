from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

class LicensesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.licenses'
    verbose_name = _('Bản quyền & License phần mềm')
