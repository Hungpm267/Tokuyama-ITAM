import pytest
from apps.contracts.models import Contract, ContractLine

@pytest.mark.django_db
def test_contract_creation_and_line_qty():
    contract = Contract.objects.create(code="KHCM-2408-0113", delivery_status="pending")
    line = ContractLine.objects.create(contract=contract, item_type="PC 16 inch", qty_ordered=5)
    
    assert contract.lines.count() == 1
    assert str(contract) == "KHCM-2408-0113 (Chưa giao / Pending)"
    assert line.qty_received == 0
    assert line.is_fully_received is False
    assert str(line) == "KHCM-2408-0113 - PC 16 inch (0/5)"

@pytest.mark.django_db
def test_contract_soft_delete_unique_code():
    c1 = Contract.objects.create(code="KHCM-2026-TEST", delivery_status="pending")
    c1.soft_delete(reason="Test soft delete")
    
    # Can re-create same code
    c2 = Contract.objects.create(code="KHCM-2026-TEST", delivery_status="delivered")
    assert c2.id != c1.id
    assert Contract.objects.count() == 1
