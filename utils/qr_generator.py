# utils/qr_generator.py
import qrcode
from io import BytesIO
import base64

def generate_qr_code(ticket_code: str) -> str:
    qr = qrcode.make(ticket_code)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    qr_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return qr_b64