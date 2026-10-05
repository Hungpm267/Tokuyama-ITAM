from datetime import date, timedelta
from sqlalchemy import Column, Integer, String, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.base import SoftDeleteMixin

class LicenseProduct(Base, SoftDeleteMixin):
    __tablename__ = "license_products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)

    licenses = relationship("License", back_populates="product")

    def __repr__(self):
        return self.name

class License(Base, SoftDeleteMixin):
    __tablename__ = "licenses"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("license_products.id"), nullable=False)
    seats = Column(Integer, default=1, nullable=False)
    license_key = Column(String(255), nullable=True)
    start_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)  # None = Perpetual

    product = relationship("LicenseProduct", back_populates="licenses")
    assignments = relationship("LicenseAssignment", back_populates="license")

    @property
    def assigned_seats_count(self):
        return len([a for a in self.assignments if not a.is_deleted and a.removed_at is None])

    @property
    def available_seats(self):
        return max(0, self.seats - self.assigned_seats_count)

    def is_expiring_soon(self, days: int = 60) -> bool:
        if not self.expiry_date:
            return False
        today = date.today()
        return today <= self.expiry_date <= (today + timedelta(days=days))

    @property
    def is_expired(self) -> bool:
        if not self.expiry_date:
            return False
        return self.expiry_date < date.today()

    def __repr__(self):
        return f"{self.product.name} ({self.assigned_seats_count}/{self.seats} seats)"

class LicenseAssignment(Base, SoftDeleteMixin):
    __tablename__ = "license_assignments"

    id = Column(Integer, primary_key=True, index=True)
    license_id = Column(Integer, ForeignKey("licenses.id"), nullable=False)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=True)
    assigned_at = Column(Date, nullable=False)
    removed_at = Column(Date, nullable=True)

    license = relationship("License", back_populates="assignments")
    asset = relationship("Asset", back_populates="license_assignments")
    person = relationship("Person", back_populates="license_assignments")

    def __repr__(self):
        target = self.asset.asset_code if self.asset else (self.person.full_name if self.person else "Unknown")
        return f"{self.license.product.name} -> {target}"
