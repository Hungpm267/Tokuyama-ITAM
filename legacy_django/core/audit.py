from auditlog.registry import auditlog

def register_auditlog():
    from apps.organization.models import Department, Person
    from apps.assets.models import AssetCategory, Asset, Assignment
    from apps.licenses.models import LicenseProduct, License, LicenseAssignment
    from apps.cards.models import Room, AccessCard, AccessCardRoom, CardLoan
    from apps.contracts.models import Contract, ContractLine

    models_to_audit = [
        Department,
        Person,
        AssetCategory,
        Asset,
        Assignment,
        LicenseProduct,
        License,
        LicenseAssignment,
        Room,
        AccessCard,
        AccessCardRoom,
        CardLoan,
        Contract,
        ContractLine,
    ]

    for model in models_to_audit:
        if not auditlog.contains(model):
            auditlog.register(model)
