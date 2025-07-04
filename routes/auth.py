# auth.py

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from typing import Optional
from utils.auth import get_current_user, get_current_vendor

from database import get_cursor  # Import DB function
from models import UserCreate, Token, VendorSignup, OrganizerUpdate, VendorUpdate
import os

# Configuration
SECRET_KEY = os.environ.get("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# Router setup
auth_router = APIRouter()

# Helper Functions
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# ⛳ Signup Endpoint
@auth_router.post("/signup", response_model=Token)
def signup_user(user: UserCreate):
    conn, cursor = get_cursor()
    try:
        cursor.execute(
            "INSERT INTO users (email, password, role) VALUES (%s, %s, %s)",
            (user.email, hashed_pw, "organizer")
        )
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already registered")

        hashed_pw = hash_password(user.password)
        cursor.execute("INSERT INTO users (email, password) VALUES (%s, %s)", (user.email, hashed_pw))
        conn.commit()

        access_token = create_access_token({"sub": user.email})
        return {"access_token": access_token, "token_type": "bearer"}

    except Exception as e:
        print("❌ Organizer Signup Error:", e)
        raise HTTPException(status_code=500, detail="Signup failed")
    finally:
        cursor.close()
        conn.close()



@auth_router.post("/signup/vendor", response_model=Token)
def signup_vendor(data: VendorSignup):
    conn, cursor = get_cursor()

    try:
        # ✅ Check if email already exists
        cursor.execute("SELECT id FROM service_providers WHERE email = %s", (data.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Vendor email already registered")

        # ✅ Call Paystack to create subaccount
        payload = {
            "business_name": data.business_name,
            "settlement_bank": data.bank_name,
            "account_number": data.account_number,
            "percentage_charge": 100,
            "email": data.email
        }

        response = requests.post(
            f"{PAYSTACK_BASE_URL}/subaccount",
            headers=HEADERS,
            json=payload
        )

        if response.status_code != 200:
            print("⚠️ Paystack error:", response.text)
            raise HTTPException(status_code=500, detail="Failed to create Paystack subaccount")

        subaccount_code = response.json()["data"]["subaccount_code"]

        # ✅ Hash password
        hashed_pw = hash_password(data.password)

        # ✅ Insert vendor data including Paystack subaccount code
        cursor.execute("""
            INSERT INTO service_providers (
                name, email, password, business_name, 
                account_number, bank_name, category, 
                price_small, price_medium, price_large, tags,
                role, paystack_subaccount_code
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data.company_name,
            data.email,
            hashed_pw,
            data.business_name,
            data.account_number,
            data.bank_name,
            data.category,
            data.price_small,
            data.price_medium,
            data.price_large,
            data.tags,
            "vendor",
            subaccount_code
        ))

        conn.commit()

        # ✅ Return access token
        access_token = create_access_token({"sub": data.email})
        return {"access_token": access_token, "token_type": "bearer"}

    except Exception as e:
        print("❌ Vendor Signup Error:", e)
        raise HTTPException(status_code=500, detail="Vendor signup failed")

    finally:
        cursor.close()
        conn.close()



@auth_router.get("/auth/fetch-user-details")
def get_current_user_info(user_id: int = Depends(get_current_user)):
    conn, cursor = get_cursor()

    try:
        cursor.execute("""
            SELECT id, email, role FROM users WHERE id = %s
        """, (user_id,))
        user = cursor.fetchone()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "id": user[0],
            "email": user[1],
            "role": user[2]
        }

    finally:
        cursor.close()
        conn.close()


@auth_router.get("/auth/vendor/fetch-vendor-details")
def get_current_vendor_info(vendor_id: int = Depends(get_current_vendor)):
    conn, cursor = get_cursor()

    try:
        cursor.execute("""
            SELECT id, email, business_name, role FROM service_providers WHERE id = %s
        """, (vendor_id,))
        vendor = cursor.fetchone()

        if not vendor:
            raise HTTPException(status_code=404, detail="Vendor not found")

        return {
            "id": vendor[0],
            "email": vendor[1],
            "business_name": vendor[2],
            "role": vendor[3]
        }

    finally:
        cursor.close()
        conn.close()



# ⛳ Login Endpoint
@auth_router.post("/login", response_model=Token)
def login_user(user: UserCreate):
    conn, cursor = get_cursor()
    try:
        cursor.execute("SELECT email, password FROM users WHERE email = %s", (user.email,))
        result = cursor.fetchone()
        if not result:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        db_email, db_password = result
        if not verify_password(user.password, db_password):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        access_token = create_access_token({"sub": db_email})
        return {"access_token": access_token, "token_type": "bearer"}

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Login error:", e)
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        cursor.close()
        conn.close()

# 🔐 Protected Route
@auth_router.get("/protected")
def protected_user_route(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"message": f"Welcome {email}, you are authorized!"}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@auth_router.patch("/profile/update")
def update_organizer_profile(
    data: OrganizerUpdate,
    user_id: int = Depends(get_current_user)
):
    conn, cursor = get_cursor()
    try:
        # Check if user exists
        cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="User not found")

        updates = []
        values = []

        if data.email:
            updates.append("email = %s")
            values.append(data.email)
        if data.password:
            hashed_pw = hash_password(data.password)
            updates.append("password = %s")
            values.append(hashed_pw)

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        values.append(user_id)

        cursor.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = %s",
            tuple(values)
        )
        conn.commit()

        return {"message": "Organizer profile updated successfully"}

    except Exception as e:
        print("❌ Organizer profile update error:", e)
        raise HTTPException(status_code=500, detail="Failed to update profile")

    finally:
        cursor.close()
        conn.close()







@auth_router.patch("/profile/vendor/update")
def update_vendor_profile(
    data: VendorUpdate,
    vendor_id: int = Depends(get_current_user)  # assuming token is for vendor
):
    conn, cursor = get_cursor()
    try:
        # Check if vendor exists
        cursor.execute("SELECT id FROM service_providers WHERE id = %s", (vendor_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Vendor not found")

        updates = []
        values = []

        if data.business_name:
            updates.append("business_name = %s")
            values.append(data.business_name)
        if data.account_number:
            updates.append("account_number = %s")
            values.append(data.account_number)
        if data.bank_name:
            updates.append("bank_name = %s")
            values.append(data.bank_name)
        if data.tags:
            updates.append("tags = %s")
            values.append(data.tags)
        if data.price_small is not None:
            updates.append("price_small = %s")
            values.append(data.price_small)
        if data.price_medium is not None:
            updates.append("price_medium = %s")
            values.append(data.price_medium)
        if data.price_large is not None:
            updates.append("price_large = %s")
            values.append(data.price_large)

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        values.append(vendor_id)

        cursor.execute(
            f"UPDATE service_providers SET {', '.join(updates)} WHERE id = %s",
            tuple(values)
        )
        conn.commit()

        return {"message": "Vendor profile updated successfully"}

    except Exception as e:
        print("❌ Vendor profile update error:", e)
        raise HTTPException(status_code=500, detail="Failed to update vendor profile")

    finally:
        cursor.close()
        conn.close()
