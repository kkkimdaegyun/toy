import random
import string
import socket
import uuid

def generate_room_code() -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

def generate_reconnect_token() -> str:
    return str(uuid.uuid4())

def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def format_money(value: int) -> str:
    return f"${value:,}"
