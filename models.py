from pydantic import BaseModel
from typing import Optional, List


class Event(BaseModel):
    name: str
    date: str
    location: str
    min_guests: int
    max_guests: int

class BudgetItem(BaseModel):
    vendor_name: str
    amount: int
    service: str

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


class VendorRequest(BaseModel):
    event_id: int
    vendor_id: int
    service_to_be_rendered: str
    price: int



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
    vendor_id: int               
    event_id: Optional[int] = None  

class OrganizerUpdate(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None

class VendorUpdate(BaseModel):
    business_name: Optional[str] = None
    account_number: Optional[str] = None
    bank_name: Optional[str] = None
    tags: Optional[str] = None
    price_small: Optional[int] = None
    price_medium: Optional[int] = None
    price_large: Optional[int] = None

class Invitee(BaseModel):
    name: Optional[str] = None
    email: str

class InviteRequest(BaseModel):
    event_id: int
    invitees: List[Invitee]

class AcceptInviteRequest(BaseModel):
    email: str
    event_id: int




class EditEventRequest(BaseModel):
    name: Optional[str] = None
    date: Optional[str] = None
    location: Optional[str] = None
    min_guests: Optional[int] = None
    max_guests: Optional[int] = None
    description: Optional[str] = None
    total_budget: Optional[int] = None
    ticket_price: Optional[int] = None
    is_public: Optional[bool] = None
    budget_breakdown: Optional[List[BudgetItem]] = None
    send_update_email: Optional[bool] = False


class CollaboratorInvite(BaseModel):
    event_id: int
    email: str

class CollaboratorResponse(BaseModel):
    event_id: int
    accepted: bool
