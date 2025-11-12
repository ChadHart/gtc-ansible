import asyncio
import random
import string
import aiohttp

API_URL = "https://api.example.com/devices"

def generate_activation_code():
    return "".join(random.choices(string.digits, k=6))

async def check_key_status(api_key: str):
    """Verify key with remote API."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{API_URL}/validate", params={"key": api_key}, timeout=5) as r:
                if r.status == 200:
                    data = await r.json()
                    if data.get("active"):
                        return True, "API key active ✅"
                    return False, "Key found but not activated."
    except Exception as e:
        return False, f"Network error: {e}"
    return False, "Invalid API key."
