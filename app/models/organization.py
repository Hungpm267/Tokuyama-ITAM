from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.base import SoftDeleteMixin

class Department(Base, SoftDeleteMixin):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    name_en = Column(String(100), nullable=False)
    name_ja = Column(String(100), nullable=True)

    members = relationship("Person", back_populates="department")

    def __repr__(self):
        return self.name_en

class Person(Base, SoftDeleteMixin):
    __tablename__ = "persons"

    id = Column(Integer, primary_key=True, index=True)
    staff_code = Column(String(50), nullable=False, index=True)
    full_name = Column(String(100), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    status = Column(String(20), default="active", nullable=False)  # 'active', 'resigned'

    department = relationship("Department", back_populates="members")
    assignments = relationship("Assignment", back_populates="person")
    license_assignments = relationship("LicenseAssignment", back_populates="person")
    card_loans = relationship("CardLoan", back_populates="person")

    def __repr__(self):
        return f"{self.staff_code} - {self.full_name}"
