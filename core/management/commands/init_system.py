import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType

from apps.organization.models import Department, Person
from apps.assets.models import AssetCategory, Asset, Assignment
from apps.licenses.models import LicenseProduct, License, LicenseAssignment
from apps.cards.models import Room, AccessCard, AccessCardRoom, CardLoan
from apps.contracts.models import Contract, ContractLine
from auditlog.models import LogEntry


class Command(BaseCommand):
    help = 'Khởi tạo 3 nhóm quyền RBAC, tài khoản Admin mặc định và dữ liệu danh mục ban đầu cho ITAM Tokuyama'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("==> Đang khởi tạo hệ thống ITAM Tokuyama Vietnam..."))
        
        # 1. Tạo các Nhóm quyền (Groups)
        it_admin_group, _ = Group.objects.get_or_create(name='IT Admin')
        ga_manager_group, _ = Group.objects.get_or_create(name='GA Manager')
        executive_group, _ = Group.objects.get_or_create(name='Executive')

        # Danh sách ContentTypes của các models nghiệp vụ
        org_types = [ContentType.objects.get_for_model(Department), ContentType.objects.get_for_model(Person)]
        asset_types = [ContentType.objects.get_for_model(AssetCategory), ContentType.objects.get_for_model(Asset), ContentType.objects.get_for_model(Assignment)]
        license_types = [ContentType.objects.get_for_model(LicenseProduct), ContentType.objects.get_for_model(License), ContentType.objects.get_for_model(LicenseAssignment)]
        card_types = [ContentType.objects.get_for_model(Room), ContentType.objects.get_for_model(AccessCard), ContentType.objects.get_for_model(AccessCardRoom), ContentType.objects.get_for_model(CardLoan)]
        contract_types = [ContentType.objects.get_for_model(Contract), ContentType.objects.get_for_model(ContractLine)]
        audit_type = ContentType.objects.get_for_model(LogEntry)
        auth_types = [ContentType.objects.get_for_model(User), ContentType.objects.get_for_model(Group)]

        all_business_types = org_types + asset_types + license_types + card_types + contract_types

        # --- A. IT Admin: Toàn quyền ---
        it_perms = Permission.objects.filter(content_type__in=all_business_types + auth_types)
        view_audit_perm = Permission.objects.filter(content_type=audit_type, codename='view_logentry')
        it_admin_group.permissions.set(list(it_perms) + list(view_audit_perm))

        # --- B. GA Manager ---
        # Nhân sự: Đọc, Ghi, Sửa (view, add, change)
        ga_org_perms = Permission.objects.filter(content_type__in=org_types, codename__in=['view_department', 'add_department', 'change_department', 'view_person', 'add_person', 'change_person'])
        # Thẻ ra vào: Đọc, Ghi, Sửa, Xóa
        ga_card_perms = Permission.objects.filter(content_type__in=card_types)
        # Tài sản & Hợp đồng: Chỉ Đọc (view only)
        ga_asset_perms = Permission.objects.filter(content_type__in=asset_types, codename__startswith='view_')
        ga_contract_perms = Permission.objects.filter(content_type__in=contract_types, codename__startswith='view_')

        ga_all_perms = list(ga_org_perms) + list(ga_card_perms) + list(ga_asset_perms) + list(ga_contract_perms)
        ga_manager_group.permissions.set(ga_all_perms)

        # --- C. Executive (Giám đốc): Chỉ Đọc (View-only) ---
        exec_perms = Permission.objects.filter(content_type__in=all_business_types + [audit_type], codename__startswith='view_')
        executive_group.permissions.set(exec_perms)

        self.stdout.write(self.style.SUCCESS("✔ Đã tạo và cấu hình 3 nhóm quyền: IT Admin, GA Manager, Executive."))

        # 2. Tạo tài khoản Admin mặc định
        admin_username = os.getenv('ADMIN_USERNAME', 'admin')
        admin_email = os.getenv('ADMIN_EMAIL', 'admin@tokuyama.vn')
        admin_password = os.getenv('ADMIN_PASSWORD', 'tokuadmin2026')

        if not User.objects.filter(username=admin_username).exists():
            admin_user = User.objects.create_superuser(
                username=admin_username,
                email=admin_email,
                password=admin_password,
                is_staff=True,
                is_superuser=True
            )
            admin_user.groups.add(it_admin_group)
            self.stdout.write(self.style.SUCCESS(f"✔ Đã tạo Superuser '{admin_username}' (Mật khẩu: {admin_password})."))
        else:
            admin_user = User.objects.get(username=admin_username)
            admin_user.groups.add(it_admin_group)
            self.stdout.write(self.style.NOTICE(f"ℹ Tài khoản '{admin_username}' đã tồn tại, đã gán vào IT Admin."))

        # 3. Nạp danh mục mẫu ban đầu (Seed data)
        # 3.1. Phòng ban
        departments = [
            ("General Affairs", "総務部"),
            ("IT", "IT部"),
            ("Sales", "営業部"),
            ("Production", "製造部"),
            ("Finance", "財務部"),
            ("Management", "経営管理部"),
        ]
        for name_en, name_ja in departments:
            Department.objects.get_or_create(name_en=name_en, defaults={'name_ja': name_ja})

        # 3.2. Loại thiết bị
        categories = [
            "Laptop", "Monitor", "Desktop", "Smartphone", "Mouse", "Adapter", "Headset"
        ]
        for cat_name in categories:
            AssetCategory.objects.get_or_create(name=cat_name)

        # 3.3. Danh mục phần mềm license
        products = [
            "IJCAD", "Office LTSC", "Adobe Acrobat PDF", "Trend Micro Apex One",
            "Microsoft 365", "Visio", "Windows Pro"
        ]
        for prod_name in products:
            LicenseProduct.objects.get_or_create(name=prod_name)

        # 3.4. Phòng kiểm soát thẻ
        rooms = [
            "Kho", "Server Room", "Document Room", "Production Area"
        ]
        for room_name in rooms:
            Room.objects.get_or_create(name=room_name)

        self.stdout.write(self.style.SUCCESS("✔ Đã nạp dữ liệu danh mục ban đầu (Phòng ban, Loại tài sản, License, Phòng thẻ)."))
        self.stdout.write(self.style.SUCCESS("==> Khởi tạo hệ thống ITAM hoàn tất thành công!"))
