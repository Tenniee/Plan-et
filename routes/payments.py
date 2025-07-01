from fastapi import APIRouter, Depends, HTTPException, Query
from models import InitPaymentRequest
from pydantic import BaseModel
from utils.auth import get_current_user, get_current_vendor
from database import get_cursor
from datetime import datetime
import requests
import uuid
import os
payments_router = APIRouter()


PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY")
PAYSTACK_BASE_URL = "https://api.paystack.co"
HEADERS = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}



@payments_router.post("/payments/initialize")
def initialize_payment(data: InitPaymentRequest, user_id: int = Depends(get_current_user)):
    conn, cursor = get_cursor()

    try:
        # ✅ 1. Get user email
        cursor.execute("SELECT email FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        email = user[0]

        # ✅ 2. Get vendor pricing and subaccount
        cursor.execute("""
            SELECT paystack_subaccount_code, price_small, price_medium, price_large
            FROM service_providers WHERE id = %s
        """, (data.vendor_id,))
        vendor = cursor.fetchone()
        if not vendor:
            raise HTTPException(status_code=404, detail="Vendor not found")

        subaccount_code, price_small, price_medium, price_large = vendor

        if not subaccount_code:
            raise HTTPException(status_code=400, detail="Vendor does not have a subaccount set up")

        # ✅ 3. Determine price from selected package
        if data.package_selected == "small":
            amount = price_small
        elif data.package_selected == "medium":
            amount = price_medium
        elif data.package_selected == "large":
            amount = price_large
        else:
            raise HTTPException(status_code=400, detail="Invalid package selected")

        if amount is None:
            raise HTTPException(status_code=400, detail=f"{data.package_selected.capitalize()} package is not available for this vendor.")

        # ✅ 4. Validate event ID if provided
        if data.event_id:
            cursor.execute("SELECT id FROM events WHERE id = %s", (data.event_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Event not found")

        # ✅ 5. Generate reference
        reference = str(uuid.uuid4())

        # ✅ 6. Build Paystack payload
        payload = {
            "email": email,
            "amount": amount * 100,
            "reference": reference,
            "subaccount": subaccount_code,
            "bearer": "subaccount"
        }

        response = requests.post(
            f"{PAYSTACK_BASE_URL}/transaction/initialize",
            json=payload,
            headers=HEADERS
        )

        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to initialize payment")

        paystack_data = response.json()["data"]
        authorization_url = paystack_data["authorization_url"]

        # ✅ 7. Store full payment record
        cursor.execute("""
            INSERT INTO payments (
                sender_id, receiver_id, event_id, amount, reference, status, paystack_subaccount_code, package_selected
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            data.vendor_id,
            data.event_id,
            amount,
            reference,
            "pending",
            subaccount_code,
            data.package_selected
        ))

        conn.commit()

        return {
            "message": "Payment initialized",
            "authorization_url": authorization_url,
            "reference": reference
        }

    except Exception as e:
        print("❌ Payment init error:", e)
        raise HTTPException(status_code=500, detail="Could not initialize payment")

    finally:
        cursor.close()
        conn.close()






@payments_router.get("/payments/verify")
def verify_payment(reference: str = Query(...), user_id: int = Depends(get_current_user)):
    conn, cursor = get_cursor()

    try:
        # ✅ 1. Call Paystack verify endpoint
        res = requests.get(f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}", headers=HEADERS)

        if res.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to verify transaction")

        result = res.json()["data"]
        if result["status"] != "success":
            raise HTTPException(status_code=400, detail="Payment not completed")

        # ✅ 2. Check DB record
        cursor.execute("SELECT status FROM payments WHERE reference = %s AND user_id = %s", (reference, user_id))
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Payment record not found")
        if row[0] == "success":
            return {"message": "Payment already verified"}

        # ✅ 3. Update payment record
        cursor.execute("""
            UPDATE payments SET status = %s, paid_at = %s
            WHERE reference = %s AND user_id = %s
        """, ("success", datetime.utcnow(), reference, user_id))
        conn.commit()

        return {"message": "Payment verified successfully"}

    except Exception as e:
        print("❌ Payment verification error:", e)
        raise HTTPException(status_code=500, detail="Payment verification failed")

    finally:
        cursor.close()
        conn.close()








@payments_router.get("/payments/history")
def get_transaction_history(user_id: int = Depends(get_current_user)):
    conn, cursor = get_cursor()

    try:
        # ✅ Fetch all payments (left join events since event_id may be null)
        cursor.execute("""
            SELECT 
                p.id,
                p.event_id,
                e.name AS event_name,
                sp.name AS vendor_name,
                p.amount,
                p.reference,
                p.status,
                p.paid_at,
                p.package_selected
            FROM payments p
            LEFT JOIN events e ON p.event_id = e.id
            LEFT JOIN service_providers sp ON p.receiver_id = sp.id
            WHERE p.sender_id = %s
            ORDER BY p.paid_at DESC
        """, (user_id,))

        payments = cursor.fetchall()

        results = []
        for row in payments:
            payment_id, event_id, event_name, vendor_name, amount, reference, status, paid_at, package_selected = row

            results.append({
                "payment_id": payment_id,
                "event_id": event_id,
                "event_name": event_name,
                "vendor_name": vendor_name,
                "amount": amount,
                "reference": reference,
                "status": status,
                "paid_at": paid_at,
                "package_selected": package_selected
            })

        return {
            "user_id": user_id,
            "transactions": results
        }

    except Exception as e:
        print("❌ Error fetching transaction history:", e)
        raise HTTPException(status_code=500, detail="Failed to fetch transaction history")

    finally:
        cursor.close()
        conn.close()


@payments_router.get("/payments/vendor-history")
def get_vendor_transaction_history(vendor_id: int = Depends(get_current_vendor)):
    conn, cursor = get_cursor()

    try:
        cursor.execute("""
            SELECT 
                p.id,
                p.event_id,
                e.name AS event_name,
                u.email AS buyer_email,
                p.amount,
                p.reference,
                p.status,
                p.paid_at,
                p.package_selected
            FROM payments p
            LEFT JOIN events e ON p.event_id = e.id
            LEFT JOIN users u ON p.sender_id = u.id
            WHERE p.receiver_id = %s
            ORDER BY p.paid_at DESC
        """, (vendor_id,))

        payments = cursor.fetchall()

        results = []
        for row in payments:
            results.append({
                "payment_id": row[0],
                "event_id": row[1],
                "event_name": row[2],
                "buyer_email": row[3],
                "amount": row[4],
                "reference": row[5],
                "status": row[6],
                "paid_at": row[7],
                "package_selected": row[8]
            })

        return {
            "vendor_id": vendor_id,
            "transactions": results
        }

    except Exception as e:
        print("❌ Vendor payment history error:", e)
        raise HTTPException(status_code=500, detail="Failed to fetch vendor transactions")

    finally:
        cursor.close()
        conn.close()
