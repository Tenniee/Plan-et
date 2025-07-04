# events.py

from fastapi import APIRouter, Query, HTTPException, Depends
from utils.auth import get_current_user, get_current_vendor
from models import Event, VendorResponse, InviteRequest, AcceptInviteRequest, VendorRequest, EditEventRequest, CollaboratorInvite, CollaboratorResponse
from database import get_cursor
from typing import Optional, List
from utils.email_sending import send_collaborator_invite_email 

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



@events_router.put("/edit-event/{event_id}")
def edit_event(
    event_id: int,
    data: EditEventRequest,
    user_id: int = Depends(get_current_user)
):
    conn, cursor = get_cursor()
    try:
        # ✅ Ensure event exists and belongs to the user
        cursor.execute("""
            SELECT id FROM events
            WHERE id=%s AND organizer_id=%s
        """, (event_id, user_id))
        owner = cursor.fetchone()

        if not owner:
            # not the owner – check if user is an accepted collaborator
            cursor.execute("""
                SELECT id FROM event_collaborators
                WHERE event_id=%s AND user_id=%s AND accepted=TRUE
            """, (event_id, user_id))
            if not cursor.fetchone():
                raise HTTPException(status_code=403, detail="No permission to edit this event.")

        # ✅ Prepare SQL update fields
        update_fields = []
        values = []

        for field, value in data.dict(exclude_unset=True).items():
            if field == "budget_breakdown":
                update_fields.append(f"{field} = %s")
                values.append(json.dumps([item.dict() for item in value]))
            elif field != "send_update_email":
                update_fields.append(f"{field} = %s")
                values.append(value)

        if not update_fields:
            raise HTTPException(status_code=400, detail="No fields to update")

        values.append(event_id)
        update_sql = f"UPDATE events SET {', '.join(update_fields)} WHERE id = %s"
        cursor.execute(update_sql, tuple(values))
        conn.commit()

        # ✅ Conditionally send email if requested
        if data.send_update_email:
            cursor.execute("""
                SELECT name, email FROM invitees WHERE event_id = %s
            """, (event_id,))
            invitees = cursor.fetchall()

            for invitee in invitees:
                name = invitee[0] or "Guest"
                email = invitee[1]
                # Call your email utility function here
                send_event_update_email(name, email, event_name=event[1])  # Example call

        return {"message": "Event updated successfully"}

    except Exception as e:
        print("❌ Edit Event Error:", e)
        raise HTTPException(status_code=500, detail="Failed to update event")

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
    request: VendorRequest,
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
        # ✅ Check if participation record exists
        cursor.execute("""
            SELECT * FROM event_service_provider_participation
            WHERE event_id = %s AND service_provider_id = %s
        """, (response.event_id, response.vendor_id))
        record = cursor.fetchone()

        if not record:
            raise HTTPException(status_code=404, detail="Participation request not found")

        # ✅ Update verified and responded
        cursor.execute("""
            UPDATE event_service_provider_participation
            SET verified = %s, responded = TRUE
            WHERE event_id = %s AND service_provider_id = %s
        """, (response.accepted, response.event_id, response.vendor_id))

        # ✅ If accepted, update `has_accepted_vendors` and budget_breakdown
        if response.accepted:
            # Get service type and price from participation table
            cursor.execute("""
                SELECT service_to_be_rendered, price
                FROM event_service_provider_participation
                WHERE event_id = %s AND service_provider_id = %s
            """, (response.event_id, response.vendor_id))
            service_data = cursor.fetchone()

            if service_data:
                service_type, price = service_data

                # Get vendor name
                cursor.execute("SELECT name FROM service_providers WHERE id = %s", (response.vendor_id,))
                vendor_name = cursor.fetchone()[0]

                # Get current budget_breakdown
                cursor.execute("SELECT budget_breakdown FROM events WHERE id = %s", (response.event_id,))
                current_budget = cursor.fetchone()[0]

                # Load and append
                import json
                breakdown = json.loads(current_budget) if current_budget else []
                breakdown.append({
                    "recipient": vendor_name,
                    "amount": price,
                    "category": service_type
                })

                # Update events table
                cursor.execute("""
                    UPDATE events
                    SET has_accepted_vendors = TRUE, budget_breakdown = %s
                    WHERE id = %s
                """, (json.dumps(breakdown), response.event_id))

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



# 🛍️ Fetch all vendors (Public Access)
@events_router.get("/vendors/all")
def get_all_vendors():
    conn, cursor = get_cursor()

    try:
        cursor.execute("""
            SELECT 
                id, name, category, price_small, 
                price_medium, price_large, rating, tags 
            FROM service_providers
        """)
        vendors = cursor.fetchall()

        result = []
        for v in vendors:
            result.append({
                "vendor_id": v[0],
                "company_name": v[1],
                "category": v[2],
                "price_small": v[3],
                "price_medium": v[4],
                "price_large": v[5],
                "rating": v[6],
                "tags": v[7].split(",") if v[7] else []
            })

        return {"vendors": result}

    except Exception as e:
        print("❌ Error fetching vendors:", e)
        raise HTTPException(status_code=500, detail="Failed to fetch vendors")

    finally:
        cursor.close()
        conn.close()



@events_router.post("/events/invite")
def invite_users_to_event(request: InviteRequest, user_id: int = Depends(get_current_user)):
    conn, cursor = get_cursor()
    try:
        # ✅ Check if event belongs to the current user
        cursor.execute("SELECT id FROM events WHERE id = %s AND organizer_id = %s", (request.event_id, user_id))
        event = cursor.fetchone()
        if not event:
            raise HTTPException(status_code=403, detail="You do not have permission to invite users to this event.")

        # ✅ Insert invitees
        for invitee in request.invitees:
            cursor.execute("""
                INSERT INTO event_invitees (event_id, name, email)
                VALUES (%s, %s, %s)
            """, (request.event_id, invitee.name, invitee.email))

        # ✅ Update the event to mark guests as invited
        cursor.execute("""
            UPDATE events SET has_invited_guests = TRUE WHERE id = %s
        """, (request.event_id,))

        conn.commit()
        return {"message": f"{len(request.invitees)} user(s) successfully invited to the event."}

    except Exception as e:
        print("❌ Invite Users Error:", e)
        raise HTTPException(status_code=500, detail="Failed to invite users.")

    finally:
        cursor.close()
        conn.close()



@events_router.post("/invite/accept")
def accept_event_invitation(data: AcceptInviteRequest):
    conn, cursor = get_cursor()

    try:
        # ✅ Check if invitee exists
        cursor.execute("""
            SELECT id, accepted FROM invitees 
            WHERE email = %s AND event_id = %s
        """, (data.email, data.event_id))
        result = cursor.fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="Invitation not found")

        invitee_id, already_accepted = result

        if already_accepted:
            return {"message": "You have already accepted this invitation."}

        # ✅ Mark invitee as accepted
        cursor.execute("""
            UPDATE invitees
            SET accepted = TRUE
            WHERE id = %s
        """, (invitee_id,))

        # ✅ Update event has_invited to True if not already
        cursor.execute("""
            UPDATE events
            SET has_invited = TRUE
            WHERE id = %s AND has_invited = FALSE
        """, (data.event_id,))

        conn.commit()

        return {"message": "Invitation accepted successfully"}

    except Exception as e:
        print("❌ Accept Invitation Error:", e)
        raise HTTPException(status_code=500, detail="Failed to accept invitation")

    finally:
        cursor.close()
        conn.close()



@events_router.post("/collaborators/invite")
def send_collaboration_invite(data: CollaboratorInvite, organizer_id: int = Depends(get_current_user)):
    conn, cursor = get_cursor()
    try:
        # ✅ Confirm the event belongs to the current user
        cursor.execute("SELECT * FROM events WHERE id = %s AND organizer_id = %s", (data.event_id, organizer_id))
        if not cursor.fetchone():
            raise HTTPException(status_code=403, detail="You're not allowed to manage this event")

        # ✅ Find user by email
        cursor.execute("SELECT id FROM users WHERE email = %s", (data.email,))
        user_row = cursor.fetchone()
        if not user_row:
            raise HTTPException(status_code=404, detail="User with that email does not exist")

        user_id = user_row[0]

        # ✅ Check if already invited
        cursor.execute("""
            SELECT * FROM collaborators WHERE event_id = %s AND collaborator_id = %s
        """, (data.event_id, user_id))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="User already invited")

        # ✅ Add collaborator
        cursor.execute("""
            INSERT INTO collaborators (event_id, collaborator_id, invited_by)
            VALUES (%s, %s, %s)
        """, (data.event_id, user_id, organizer_id))

        conn.commit()

        # ✅ Send invitation email (placeholder logic)
        send_collaborator_invite_email(to_email=data.email, event_id=data.event_id)

        return {"message": "Collaboration invite sent successfully"}

    finally:
        cursor.close()
        conn.close()


@events_router.post("/collaborators/respond")
def respond_to_collaborator_invite(response: CollaboratorResponse, user_id: int = Depends(get_current_user)):
    conn, cursor = get_cursor()
    try:
        # ✅ Ensure the invite exists
        cursor.execute("""
            SELECT * FROM collaborators WHERE event_id = %s AND collaborator_id = %s
        """, (response.event_id, user_id))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Invite not found")

        # ✅ Update response with accepted status, responded flag, and timestamp
        cursor.execute("""
            UPDATE collaborators
            SET accepted = %s, accepted = TRUE, responded_at = CURRENT_TIMESTAMP
            WHERE event_id = %s AND collaborator_id = %s
        """, (response.accepted, response.event_id, user_id))

        conn.commit()

        return {
            "message": f"Invite {'accepted' if response.accepted else 'declined'} successfully"
        }

    except Exception as e:
        print("❌ Collaborator Respond Error:", e)
        raise HTTPException(status_code=500, detail="Failed to respond to invite")

    finally:
        cursor.close()
        conn.close()



@events_router.get("/collaborators/{event_id}")
def get_collaborators(event_id: int, organizer_id: int = Depends(get_current_user)):
    conn, cursor = get_cursor()
    try:
        cursor.execute("""
            SELECT u.id, u.name, u.email, c.accepted
            FROM collaborators c
            JOIN users u ON u.id = c.collaborator_id
            WHERE c.event_id = %s
        """, (event_id,))
        rows = cursor.fetchall()

        collaborators = [{
            "id": row[0],
            "name": row[1],
            "email": row[2],
            "accepted": row[3]
        } for row in rows]

        return {"collaborators": collaborators}

    finally:
        cursor.close()
        conn.close()
