from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict

class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class DepartmentOut(BaseSchema):
    id: int
    name_en: str
    name_ja: Optional[str] = None

class PersonOut(BaseSchema):
    id: int
    staff_code: str
    full_name: str
    department_id: Optional[int] = None
    status: str

class AssetCategoryOut(BaseSchema):
    id: int
    name: str

class AssetOut(BaseSchema):
    id: int
    asset_code: str
    category_id: Optional[int] = None
    model: Optional[str] = None
    serial: Optional[str] = None
    hwid: Optional[str] = None
    mac_address: Optional[str] = None
    status: str
    note: Optional[str] = None

class AssetCreate(BaseModel):
    asset_code: str
    category_id: Optional[int] = None
    contract_line_id: Optional[int] = None
    model: Optional[str] = None
    serial: Optional[str] = None
    hwid: Optional[str] = None
    mac_address: Optional[str] = None
    status: str = "in_stock"
    note: Optional[str] = None

class LicenseOut(BaseSchema):
    id: int
    product_id: int
    seats: int
    start_date: Optional[date] = None
    expiry_date: Optional[date] = None

class AccessCardOut(BaseSchema):
    id: int
    card_no: str

class ContractOut(BaseSchema):
    id: int
    code: str
    delivery_status: str

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    role: str
