from fastapi import FastAPI
from datetime import timedelta, datetime
from jose import JWTError, jwt

from routes.auth import auth_router
from routes.events import events_router
from routes.tickets import tickets_router  
from routes.payments import payments_router
from dotenv import load_dotenv

load_dotenv()


app = FastAPI()

# JWT config
SECRET_KEY = os.environ.get("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Include Routers
app.include_router(auth_router, prefix="/auth")
app.include_router(events_router, prefix="/events")
app.include_router(tickets_router, prefix="/tickets")  # ✅ now registered
app.include_router(payments_router)
