from fastapi import FastAPI, Depends, Request
from datetime import timedelta, datetime
from jose import JWTError, jwt
import os


from fastapi.openapi.models import APIKey, APIKeyIn, SecuritySchemeType
from fastapi.openapi.utils import get_openapi
from fastapi.security import APIKeyHeader
from fastapi import FastAPI, Security

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



def get_current_user(request: Request):
    token = request.headers.get("Authorization")
    if not token or not token.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    return decode_jwt(token.split(" ")[1])



# Add global security scheme for Swagger UI
@app.get("/secure-endpoint")
def secure_endpoint(user_data=Depends(get_current_user)):
    return {"msg": "Success", "user": user_data}

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="My API",
        version="1.0.0",
        description="API with custom JWT auth",
        routes=app.routes,
    )

    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    }

    for path in openapi_schema["paths"]:
        for method in openapi_schema["paths"][path]:
            openapi_schema["paths"][path][method]["security"] = [{"BearerAuth": []}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

