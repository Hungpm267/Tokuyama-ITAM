import pytest
from datetime import date
from django.core.exceptions import ValidationError
from apps.organization.models import Person
from apps.cards.models import Room, AccessCard, AccessCardRoom, CardLoan

@pytest.mark.django_db
def test_card_loan_external_borrower_validation_and_active_check():
    card = AccessCard.objects.create(card_no="CARD-001")
    
    # If person is None, external_name is required
    invalid_loan = CardLoan(card=card, borrowed_at=date.today())
    with pytest.raises(ValidationError):
        invalid_loan.full_clean()
        
    loan = CardLoan.objects.create(
        card=card,
        external_name="John Doe",
        external_company="Cleaning Corp",
        purpose="Cleaning server room",
        borrowed_at=date.today()
    )
    assert loan.is_active is True
    
    # Block deleting card with active loans
    with pytest.raises(ValidationError):
        card.soft_delete(reason="Deleting card on loan")
        
    loan.returned_at = date.today()
    loan.save()
    assert loan.is_active is False
    
    # Now card can be soft-deleted
    card.soft_delete(reason="Card damaged")
    assert card.is_deleted is True

@pytest.mark.django_db
def test_card_rooms_relationship():
    card = AccessCard.objects.create(card_no="CARD-002")
    r1 = Room.objects.create(name="Server Room")
    r2 = Room.objects.create(name="Document Room")
    
    AccessCardRoom.objects.create(card=card, room=r1)
    AccessCardRoom.objects.create(card=card, room=r2)
    
    assert card.rooms.count() == 2
    assert r1.cards.count() == 1
