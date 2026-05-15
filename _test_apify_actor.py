"""Obtiene el log del último run fallido."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config, httpx, json

KEY = config.APIFY_API_KEY
HEADERS = {"Authorization": f"Bearer {KEY}"}
RUN_ID = "wFrs2vS2S4ret49Bz"

# Estado del run
r = httpx.get(f"https://api.apify.com/v2/actor-runs/{RUN_ID}", headers=HEADERS, timeout=10)
d = r.json().get("data", {})
print(f"Status:     {d.get('status')}")
print(f"exitCode:   {d.get('exitCode')}")
print(f"statusMessage: {d.get('statusMessage')}")
print(f"meta: {json.dumps(d.get('meta', {}), indent=2)}")

# Log del run
print("\n=== LOG (últimas 80 líneas) ===")
log_r = httpx.get(
    f"https://api.apify.com/v2/actor-runs/{RUN_ID}/log",
    headers=HEADERS, timeout=15
)
lines = log_r.text.strip().splitlines()
for line in lines[-80:]:
    print(line)
