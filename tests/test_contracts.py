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
def test_contract_line_counts_attached_assets():
    from apps.assets.models import Asset, AssetCategory
    contract = Contract.objects.create(code="KHCM-2408-9999")
    line = ContractLine.objects.create(contract=contract, item_type="Laptop", qty_ordered=2)
    cat = AssetCategory.objects.create(name="Laptop Category")
    
    assert line.qty_received == 0
    assert line.is_fully_received is False
    
    # Add first asset
    a1 = Asset.objects.create(asset_code="PC-001", category=cat, contract_line=line)
    assert line.qty_received == 1
    assert line.is_fully_received is False
    
    # Add second asset
    a2 = Asset.objects.create(asset_code="PC-002", category=cat, contract_line=line)
    assert line.qty_received == 2
    assert line.is_fully_received is True

