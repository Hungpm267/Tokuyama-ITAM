from datetime import date, timedelta
from sqlalchemy.orm import Session
from app.models.assets import Asset
from app.models.licenses import License
from app.models.cards import CardLoan

def get_dashboard_stats(db: Session):
    today = date.today()
    in_60_days = today + timedelta(days=60)

    # 1. Asset statistics
    total_assets = db.query(Asset).filter(Asset.is_deleted == False).count()
    in_stock = db.query(Asset).filter(Asset.is_deleted == False, Asset.status == 'in_stock').count()
    loaned = db.query(Asset).filter(Asset.is_deleted == False, Asset.status == 'loaned').count()
    lost = db.query(Asset).filter(Asset.is_deleted == False, Asset.status == 'lost').count()

    asset_stats = {
        "total": total_assets,
        "in_stock": in_stock,
        "loaned": loaned,
        "lost": lost,
    }

    # 2. Expiring licenses
    expiring_licenses_query = db.query(License).filter(
        License.is_deleted == False,
        License.expiry_date != None,
        License.expiry_date <= in_60_days
    ).order_by(License.expiry_date).all()

    expiring_licenses = []
    for lic in expiring_licenses_query:
        days_left = (lic.expiry_date - today).days
        expiring_licenses.append({
            "product_name": lic.product.name if lic.product else "Unknown",
            "seats": lic.seats,
            "expiry_date": lic.expiry_date.strftime("%Y-%m-%d"),
            "days_left": days_left,
            "is_expired": days_left < 0,
        })

    # 3. Active card loans
    active_loans_query = db.query(CardLoan).filter(
        CardLoan.is_deleted == False,
        CardLoan.returned_at == None
    ).order_by(CardLoan.borrowed_at.desc()).all()

    active_card_loans = []
    for loan in active_loans_query:
        active_card_loans.append({
            "card_no": loan.card.card_no if loan.card else "Unknown",
            "borrower_name": loan.borrower_name,
            "borrowed_at": loan.borrowed_at.strftime("%Y-%m-%d"),
            "purpose": loan.purpose or "-",
            "rooms": [r.name for r in loan.card.allowed_rooms] if loan.card else [],
        })

    return {
        "asset_stats": asset_stats,
        "expiring_licenses": expiring_licenses,
        "active_card_loans": active_card_loans,
    }
