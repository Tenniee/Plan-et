# routes/tickets.py

from utils.qr_generator import generate_qr_code
import uuid
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from database import get_cursor
from jose import JWTError, jwt
import os
from utils.auth import get_current_user


tickets_router = APIRouter()







@tickets_router.post("/generate")
def generate_ticket(event_id: int = Query(...), email: str = Query(...)):
    conn, cursor = get_cursor()
    try:
        # ✅ 1. Validate event exists
        cursor.execute("SELECT id FROM events WHERE id = %s", (event_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Event not found")

        # ✅ 2. Generate unique ticket code
        ticket_code = str(uuid.uuid4())

        # ✅ 3. Insert ticket into DB with just event_id and email
        cursor.execute("""
            INSERT INTO tickets (ticket_code, event_id, email)
            VALUES (%s, %s, %s)
        """, (ticket_code, event_id, email))
        conn.commit()

        # ✅ 4. Generate QR code
        qr_code_b64 = generate_qr_code(ticket_code)

        return {
            "message": "✅ Ticket generated successfully",
            "ticket_code": ticket_code,
            "qr_code_base64": f"data:image/png;base64,{qr_code_b64}"
        }

    except Exception as e:
        print("❌ Ticket Generation Error:", e)
        raise HTTPException(status_code=500, detail="Failed to generate ticket")

    finally:
        cursor.close()
        conn.close()




@tickets_router.post("/validate")
def validate_ticket(ticket_code: str, user_id: int = Depends(get_current_user)):
    conn, cursor = get_cursor()
    try:
        # 1. Look up the ticket
        # Update query to pull event_id and event_name too
        cursor.execute("""
            SELECT t.id AS ticket_id, t.is_scanned, e.id AS event_id, e.name AS event_name, e.organizer_id
            FROM tickets t
            JOIN events e ON t.event_id = e.id
            WHERE t.ticket_code = %s
        """, (ticket_code,))
        ticket = cursor.fetchone()

        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        # 🔐 Verify organizer access
        if ticket["organizer_id"] != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to validate this ticket")

        # 2. Check if already scanned
        if ticket["is_scanned"]:
            return {"status": "invalid", "reason": "Ticket already scanned"}

        # 3. Mark as scanned
        cursor.execute("UPDATE tickets SET is_scanned = TRUE WHERE ticket_code = %s", (ticket_code,))
        conn.commit()

        # ✅ Insert log
        cursor.execute("""
            INSERT INTO ticket_logs (ticket_id, event_id, event_name, scanned_by_user_id)
            VALUES (%s, %s, %s, %s)
        """, (ticket["ticket_id"], ticket["event_id"], ticket["event_name"], user_id))

        return {
            "status": "valid",
            "message": "✅ Ticket is valid and has been marked as scanned",
            "event_id": ticket["event_id"],
            "user_id": ticket["user_id"]
        }

    except Exception as e:
        print("❌ Ticket Validation Error:", e)
        raise HTTPException(status_code=500, detail="Validation failed")

    finally:
        cursor.close()
        conn.close()





@tickets_router.get("/logs")
def get_ticket_logs(event_id: int, user_id: int = Depends(get_current_user)):
    conn, cursor = get_cursor()
    try:
        # ✅ Check if user is the organizer of this event
        cursor.execute("SELECT user_id FROM events WHERE id = %s", (event_id,))
        event = cursor.fetchone()

        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        if event[0] != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to view logs for this event")

        # ✅ Fetch logs
        cursor.execute("""
            SELECT ticket_id, scanned_by_user_id, event_name, scanned_at
            FROM ticket_logs
            WHERE event_id = %s
            ORDER BY scanned_at DESC
        """, (event_id,))
        logs = cursor.fetchall()

        return {
            "event_id": event_id,
            "logs": logs
        }

    except Exception as e:
        print("❌ Fetch Ticket Logs Error:", e)
        raise HTTPException(status_code=500, detail="Failed to fetch logs")

    finally:
        cursor.close()
        conn.close()
