from pydantic import BaseModel
from typing import Optional


class Event(BaseModel):
    name: str
    date: str
    location: str
    min_guests: int
    max_guests: int

class UserCreate(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

# ----------------------------
# DEFINE REQUEST BODY STRUCTURE
# ----------------------------
class UserCreate(BaseModel):
    email: str
    password: str
# When client sends JSON → FastAPI will check it matches this model
# e.g., {"email": "user@mail.com", "password": "1234"}

class Token(BaseModel):
    access_token: str
    token_type: str
# When we return a token, it follows this shape
# Example: {"access_token": "abc123", "token_type": "bearer"}

class EventServiceLinkRequest(BaseModel):
    event_id: int
    service_provider_id: int

class VendorResponse(BaseModel):
    event_id: int
    vendor_id: int
    accepted: bool  # True for accept, False for decline

# models.py
class InitPaymentRequest(BaseModel):
    event_id: int

class VendorSignup(BaseModel):
    company_name: str
    email: str
    password: str
    business_name: str
    account_number: str
    bank_name: str
    category: str
    price_small: int
    price_medium: int
    price_large: int
    tags: str


class InitPaymentRequest(BaseModel):
    vendor_id: int               # 👈 required
    event_id: Optional[int] = None  # 👈 optional