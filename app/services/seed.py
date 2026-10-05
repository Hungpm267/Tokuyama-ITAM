from sqlalchemy.orm import Session
from app.models.user import User
from app.models.organization import Department
from app.models.assets import AssetCategory
from app.models.licenses import LicenseProduct
from app.models.cards import Room
from app.services.auth import hash_password

def seed_all_data(db: Session):
    """Seed initial RBAC users and system categories."""
    # 1. Users
    users_data = [
        ("admin", "admin@tokuyama.vn", "tokuadmin2026", "IT Administrator", "it_admin"),
        ("ga_manager", "ga@tokuyama.vn", "toku2026ga", "GA Manager", "ga_manager"),
        ("director", "director@tokuyama.vn", "toku2026exec", "Japanese Director", "executive"),
    ]
    for username, email, pwd, full_name, role in users_data:
        existing = db.query(User).filter(User.username == username).first()
        if not existing:
            user = User(
                username=username,
                email=email,
                password_hash=hash_password(pwd),
                full_name=full_name,
                role=role,
                is_active=True
            )
            db.add(user)

    # 2. Departments
    depts = [
        ("General Affairs", "総務部"),
        ("IT", "IT部"),
        ("Sales", "営業部"),
        ("Production", "製造部"),
        ("Finance", "財務部"),
        ("Management", "経営管理部"),
    ]
    for en, ja in depts:
        if not db.query(Department).filter(Department.name_en == en).first():
            db.add(Department(name_en=en, name_ja=ja))

    # 3. Asset Categories
    cats = ["Laptop", "Monitor", "Desktop", "Smartphone", "Mouse", "Adapter", "Headset"]
    for c in cats:
        if not db.query(AssetCategory).filter(AssetCategory.name == c).first():
            db.add(AssetCategory(name=c))

    # 4. License Products
    prods = [
        "IJCAD", "Office LTSC", "Adobe Acrobat PDF", "Trend Micro Apex One",
        "Microsoft 365", "Visio", "Windows Pro"
    ]
    for p in prods:
        if not db.query(LicenseProduct).filter(LicenseProduct.name == p).first():
            db.add(LicenseProduct(name=p))

    # 5. Rooms
    rooms = ["Kho", "Server Room", "Document Room", "Production Area"]
    for r in rooms:
        if not db.query(Room).filter(Room.name == r).first():
            db.add(Room(name=r))

    db.commit()
