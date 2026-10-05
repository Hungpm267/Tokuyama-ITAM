from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.base import SoftDeleteMixin

class Contract(Base, SoftDeleteMixin):
    __tablename__ = "contracts"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), nullable=False, index=True)
    delivery_status = Column(String(20), default="pending", nullable=False)  # 'pending', 'delivered'

    lines = relationship("ContractLine", back_populates="contract", cascade="all, delete-orphan")

    def __repr__(self):
        return f"{self.code} ({self.delivery_status})"

class ContractLine(Base, SoftDeleteMixin):
    __tablename__ = "contract_lines"

    id = Column(Integer, primary_key=True, index=True)
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=False)
    item_type = Column(String(100), nullable=False)
    spec = Column(Text, nullable=True)
    qty_ordered = Column(Integer, nullable=False, default=1)

    contract = relationship("Contract", back_populates="lines")
    assets = relationship("Asset", back_populates="contract_line")

    @property
    def qty_received(self):
        return len([a for a in self.assets if not a.is_deleted])

    @property
    def is_fully_received(self):
        return self.qty_received >= self.qty_ordered

    def __repr__(self):
        return f"{self.item_type} ({self.qty_received}/{self.qty_ordered})"
