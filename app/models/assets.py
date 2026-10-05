from sqlalchemy import Column, Integer, String, Text, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.base import SoftDeleteMixin

class AssetCategory(Base, SoftDeleteMixin):
    __tablename__ = "asset_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False, unique=True)

    assets = relationship("Asset", back_populates="category")

    def __repr__(self):
        return self.name

class Asset(Base, SoftDeleteMixin):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    asset_code = Column(String(50), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("asset_categories.id"), nullable=True)
    contract_line_id = Column(Integer, ForeignKey("contract_lines.id"), nullable=True)
    model = Column(String(150), nullable=True)
    serial = Column(String(100), nullable=True, index=True)
    hwid = Column(String(100), nullable=True)
    mac_address = Column(String(50), nullable=True)
    status = Column(String(20), default="in_stock", nullable=False)  # 'in_stock', 'loaned', 'lost'
    note = Column(Text, nullable=True)

    category = relationship("AssetCategory", back_populates="assets")
    contract_line = relationship("ContractLine", back_populates="assets")
    assignments = relationship("Assignment", back_populates="asset")
    license_assignments = relationship("LicenseAssignment", back_populates="asset")

    @property
    def current_holder(self):
        active = [a for a in self.assignments if not a.is_deleted and a.returned_at is None]
        return active[0].person if active else None

    def __repr__(self):
        return f"{self.asset_code} ({self.category.name if self.category else ''})"

class Assignment(Base, SoftDeleteMixin):
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    borrowed_at = Column(Date, nullable=False)
    returned_at = Column(Date, nullable=True)
    note = Column(Text, nullable=True)

    asset = relationship("Asset", back_populates="assignments")
    person = relationship("Person", back_populates="assignments")

    def __repr__(self):
        return f"Assignment #{self.id}: {self.asset} -> {self.person}"
