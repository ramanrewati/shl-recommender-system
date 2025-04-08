import requests

API_URL = "https://shl-assignment-mnp1.onrender.com/ping"

try:
    r = requests.get(API_URL, timeout=10)
    print(f"[{r.status_code}] API is alive: {r.json()}")
except Exception as e:
    print(f"Ping failed: {e}")
