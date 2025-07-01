# events.py

from fastapi import APIRouter, Query, HTTPException, Depends
from utils.auth import get_current_user, get_current_vendor
from models import Event, VendorResponse
from database import get_cursor
from typing import Optional, List

print("✅ events.py loaded successfully")  # Debug

events_router = APIRouter()

# ⛳ Create Event
@events_router.post("/create-event")
def create_event(event: Event):
    conn, cursor = get_cursor()
    try:
        cursor.execute(
            """
            INSERT INTO events (name, date, location, min_guests, max_guests)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (event.name, event.date, event.location, event.min_guests, event.max_guests)
        )
        conn.commit()
        return {"message": "Event created successfully"}

    except Exception as e:
        print("❌ Create Event Error:", e)
        raise HTTPException(status_code=500, detail="Failed to create event")
    
    finally:
        cursor.close()
        conn.close()

# ❌ Delete Event
@events_router.delete("/delete-event")
def delete_event(event_id: int = Query(..., description="The ID of the event to delete")):
    conn, cursor = get_cursor()
    try:
        cursor.execute("SELECT * FROM events WHERE id = %s", (event_id,))
        event = cursor.fetchone()
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        cursor.execute("DELETE FROM events WHERE id = %s", (event_id,))
        conn.commit()
        return {"message": f"Event with ID {event_id} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Delete Event Error:", e)
        raise HTTPException(status_code=500, detail="Failed to delete event")
    
    finally:
        cursor.close()
        conn.close()

# 📦 Get All Events
@events_router.get("/get-all-events")
def get_all_events():
    conn, cursor = get_cursor()
    try:
        cursor.execute("SELECT id, name, date, location, min_guests, max_guests FROM events")
        rows = cursor.fetchall()

        events = [
            {
                "id": row[0],
                "name": row[1],
                "date": row[2],
                "location": row[3],
                "min_guests": row[4],
                "max_guests": row[5]
            }
            for row in rows
        ]

        return {"events": events}

    except Exception as e:
        print("❌ Fetch Events Error:", e)
        raise HTTPException(status_code=500, detail="Failed to fetch events")

    finally:
        cursor.close()
        conn.close()



@events_router.get("/get-user-events")
def get_user_events(user_id: int = Query(..., description="ID of the user")):
    conn, cursor = get_cursor()
    try:
        # 1. Fetch events for this user
        cursor.execute("""
            SELECT id, name, date, location, min_guests, max_guests
            FROM events
            WHERE user_id = %s
        """, (user_id,))
        events = cursor.fetchall()

        result = []

        for event in events:
            event_id = event[0]

            # 2. Fetch vendors linked to this event
            cursor.execute("""
                SELECT sp.id, sp.name, esp.verified, esp.responded
                FROM event_service_provider_participation esp
                JOIN service_providers sp ON esp.service_provider_id = sp.id
                WHERE esp.event_id = %s
            """, (event_id,))
            vendors = cursor.fetchall()

            vendor_list = [
                {
                    "id": v[0],
                    "name": v[1],
                    "verified": v[2],
                    "responded": v[3]
                }
                for v in vendors
            ]

            # 3. Build full event data
            result.append({
                "id": event[0],
                "name": event[1],
                "date": event[2],
                "location": event[3],
                "min_guests": event[4],
                "max_guests": event[5],
                "vendors": vendor_list
            })

        return result

    except Exception as e:
        print("❌ Error fetching user events:", e)
        raise HTTPException(status_code=500, detail="Failed to fetch events")

    finally:
        cursor.close()
        conn.close()





@events_router.get("/recommend")
def recommend_services(
    category: str,
    budget: int,
    event_size: str = Query(..., regex="^(small|medium|large)$"),
    tags: Optional[List[str]] = Query(None)
):
    try:
        conn, cursor = get_cursor()

        # Map event_size to DB column
        price_column = f"price_{event_size}"

        # Base SQL
        sql = f"""
            SELECT * FROM service_providers
            WHERE category = %s AND {price_column} <= %s
        """

        params = [category, budget]

        # Add tag filters
        if tags:
            for tag in tags:
                sql += " AND tags LIKE %s"
                params.append(f"%{tag}%")

        sql += f" ORDER BY rating DESC, {price_column} ASC"

        cursor.execute(sql, params)
        results = cursor.fetchall()

        # If none found under budget, get top-rated above budget
        if not results:
            fallback_sql = f"""
                SELECT * FROM service_providers
                WHERE category = %s
            """
            fallback_params = [category]

            if tags:
                for tag in tags:
                    fallback_sql += " AND tags LIKE %s"
                    fallback_params.append(f"%{tag}%")

            fallback_sql += f" ORDER BY rating DESC LIMIT 3"
            cursor.execute(fallback_sql, fallback_params)
            results = cursor.fetchall()

        # Format results
        service_list = []
        for row in results:
            service = {
                "id": row[0],
                "name": row[1],
                "category": row[2],
                "price_small": row[3],
                "price_medium": row[4],
                "price_large": row[5],
                "rating": row[6],
                "tags": row[7].split(",") if row[7] else []
            }
            service_list.append(service)

        return {"results": service_list}

    except Exception as e:
        return {"error": str(e)}

    finally:
        if conn:
            conn.close()




@events_router.get("/vendor-pending-requests")
def get_pending_requests(vendor_id: int):
    conn, cursor = get_cursor()
    try:
        cursor.execute(
            """
            SELECT esp.event_id, e.name, e.date, e.location
            FROM event_service_provider_participation esp
            JOIN events e ON esp.event_id = e.id
            WHERE esp.service_provider_id = %s AND esp.verified = FALSE AND esp.responded = FALSE
            """,
            (vendor_id,)
        )
        results = cursor.fetchall()
        pending_events = [
            {
                "event_id": row[0],
                "event_name": row[1],
                "event_date": row[2],
                "location": row[3]
            }
            for row in results
        ]
        return {"pending_requests": pending_events}
    except Exception as e:
        print("❌ Fetch Pending Requests Error:", e)
        raise HTTPException(status_code=500, detail="Could not fetch requests")
    finally:
        cursor.close()
        conn.close()


@events_router.post("/vendor-request")
def request_vendor_for_event(
    vendor_id: int = Query(..., description="ID of the vendor"),
    event_id: int = Query(..., description="ID of the event"),
    user_id: int = Depends(get_current_user)
):
    conn, cursor = get_cursor()

    try:
        # ✅ Check that vendor exists
        cursor.execute("SELECT id FROM service_providers WHERE id = %s", (vendor_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Vendor not found")

        # ✅ Check that event belongs to current user
        cursor.execute("SELECT id FROM events WHERE id = %s AND organizer_id = %s", (event_id, user_id))
        if not cursor.fetchone():
            raise HTTPException(status_code=403, detail="You can only request vendors for your own events")

        # ✅ Prevent duplicate requests
        cursor.execute("""
            SELECT * FROM event_service_provider_participation
            WHERE event_id = %s AND service_provider_id = %s
        """, (event_id, vendor_id))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Vendor has already been requested for this event")

        # ✅ Create request
        cursor.execute("""
            INSERT INTO event_service_provider_participation (
                event_id, service_provider_id, verified, responded
            ) VALUES (%s, %s, FALSE, FALSE)
        """, (event_id, vendor_id))
        conn.commit()

        return {
            "message": "Vendor request sent successfully",
            "event_id": event_id,
            "vendor_id": vendor_id
        }

    except Exception as e:
        print("❌ Error sending vendor request:", e)
        raise HTTPException(status_code=500, detail="Failed to send vendor request")

    finally:
        cursor.close()
        conn.close()


@events_router.post("/vendor-respond-to-request")
def respond_to_event_request(response: VendorResponse):
    conn, cursor = get_cursor()
    try:
        # Check if a participation record exists
        cursor.execute(
            """
            SELECT * FROM event_service_provider_participation
            WHERE event_id = %s AND service_provider_id = %s
            """,
            (response.event_id, response.vendor_id)
        )
        record = cursor.fetchone()

        if not record:
            raise HTTPException(status_code=404, detail="Participation request not found")

        # Update verified and responded
        cursor.execute(
            """
            UPDATE event_service_provider_participation
            SET verified = %s, responded = TRUE
            WHERE event_id = %s AND service_provider_id = %s
            """,
            (response.accepted, response.event_id, response.vendor_id)
        )
        conn.commit()

        return {
            "message": f"Participation {'accepted' if response.accepted else 'declined'} successfully"
        }

    except Exception as e:
        print("❌ Respond to Request Error:", e)
        raise HTTPException(status_code=500, detail="Failed to respond to request")
    
    finally:
        cursor.close()
        conn.close()


@events_router.get("/event-requests-status-user")
def get_event_requests_status(event_id: int):
    conn, cursor = get_cursor()
    try:
        cursor.execute("""
            SELECT sp.id, sp.name, esp.verified, esp.responded
            FROM event_service_provider_participation esp
            JOIN service_providers sp ON esp.service_provider_id = sp.id
            WHERE esp.event_id = %s
        """, (event_id,))
        rows = cursor.fetchall()

        results = [
            {
                "service_provider_id": row[0],
                "name": row[1],
                "verified": row[2],
                "responded": row[3]
            }
            for row in rows
        ]

        return {"requests_status": results}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()
