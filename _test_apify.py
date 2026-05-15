import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config, httpx

resp = httpx.get(
    "https://api.apify.com/v2/users/me",
    headers={"Authorization": f"Bearer {config.APIFY_API_KEY}"},
    timeout=10,
)
if resp.status_code == 200:
    d = resp.json().get("data", {})
    print(f"Conectado como: {d.get('username', d.get('id', 'desconocido'))}")
    plan = d.get("plan", {})
    print(f"Plan: {plan.get('name', 'desconocido')}")
    print(f"Status: HTTP {resp.status_code} OK")
    print("APIFY CONECTADO correctamente.")
else:
    print(f"Error HTTP {resp.status_code}: {resp.text[:200]}")
    sys.exit(1)
