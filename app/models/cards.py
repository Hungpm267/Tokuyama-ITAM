from sqlalchemy import Column, Integer, String, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.base import SoftDeleteMixin

class Room(Base, SoftDeleteMixin):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)

    card_accesses = relationship("AccessCardRoom", back_populates="room")

    def __repr__(self):
        return self.name

class AccessCard(Base, SoftDeleteMixin):
    __tablename__ = "access_cards"

    id = Column(Integer, primary_key=True, index=True)
    card_no = Column(String(50), nullable=False, unique=True, index=True)

    room_accesses = relationship("AccessCardRoom", back_populates="card")
    loans = relationship("CardLoan", back_populates="card")

    @property
    def allowed_rooms(self):
        return [ra.room for ra in self.room_accesses if not ra.is_deleted and ra.room and not ra.room.is_deleted]

    @property
    def current_active_loan(self):
        active = [l for l in self.loans if not l.is_deleted and l.returned_at is None]
        return active[0] if active else None

    def __repr__(self):
        return self.card_no

class AccessCardRoom(Base, SoftDeleteMixin):
    __tablename__ = "access_card_rooms"

    id = Column(Integer, primary_key=True, index=True)
    card_id = Column(Integer, ForeignKey("access_cards.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)

    card = relationship("AccessCard", back_populates="room_accesses")
    room = relationship("Room", back_populates="card_accesses")

    def __repr__(self):
        return f"{self.card.card_no} <-> {self.room.name}"

class CardLoan(Base, SoftDeleteMixin):
    __tablename__ = "card_loans"

    id = Column(Integer, primary_key=True, index=True)
    card_id = Column(Integer, ForeignKey("access_cards.id"), nullable=False)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=True)
    external_name = Column(String(100), nullable=True)
    external_company = Column(String(100), nullable=True)
    purpose = Column(String(255), nullable=True)
    borrowed_at = Column(Date, nullable=False)
    returned_at = Column(Date, nullable=True)

    card = relationship("AccessCard", back_populates="loans")
    person = relationship("Person", back_populates="card_loans")

    @property
    def is_active(self) -> bool:
        return self.returned_at is None

    @property
    def borrower_name(self) -> str:
        if self.person:
            return self.person.full_name
        if self.external_name:
            if self.external_company:
                return f"{self.external_name} ({self.external_company})"
            return self.external_name
        return "-"

    def __repr__(self):
        return f"Loan #{self.id}: {self.card.card_no} -> {self.borrower_name}"
