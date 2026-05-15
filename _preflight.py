"""Pre-flight checklist before connecting to Apify."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

PASS = "  [OK]"
FAIL = "  [MISSING]"

print("=== PRE-FLIGHT CHECKLIST ===\n")

# 1. API Keys
print("1. API KEYS")
keys = [
    ("ANTHROPIC_API_KEY",  config.ANTHROPIC_API_KEY),
    ("APIFY_API_KEY",      config.APIFY_API_KEY),
    ("TELEGRAM_TOKEN",     config.TELEGRAM_TOKEN),
    ("TELEGRAM_CHAT_ID",   config.TELEGRAM_CHAT_ID),
]
key_ok = True
for name, val in keys:
    ok = bool(val and not val.startswith("PEGA"))
    print(f"{PASS if ok else FAIL} {name}")
    if not ok:
        key_ok = False

# 2. Files & dirs
print("\n2. FILES & DIRECTORIES")
paths = [
    ("CV source PDF",      config.CV_PATH),
    ("output dir",         config.OUTPUT_DIR),
    ("database dir",       os.path.dirname(config.DB_PATH)),
    ("narrativas JSON",    os.path.join(os.path.dirname(__file__), "narrativas", "narrativas_lorena.json")),
    ("profiles dir",       config.PROFILES_DIR),
    ("config dir",         config.CONFIG_DIR),
]
paths_ok = True
for name, path in paths:
    ok = os.path.exists(path)
    print(f"{PASS if ok else FAIL} {name}: {path}")
    if not ok:
        paths_ok = False

# 3. DB reachable
print("\n3. DATABASE")
try:
    import sqlite3
    con = sqlite3.connect(config.DB_PATH)
    tables = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    con.close()
    print(f"{PASS} SQLite reachable — tables: {[t[0] for t in tables]}")
    db_ok = True
except Exception as e:
    print(f"{FAIL} SQLite error: {e}")
    db_ok = False

# 4. Agents importable
print("\n4. AGENTS")
agents = [
    "agents.cv_parser",
    "agents.narrative_builder",
    "agents.skill_matcher",
    "agents.cv_rewriter",
    "agents.ats_auditor",
    "agents.pdf_generator",
    "agents.reporter",
    "agents.scraper",
    "agents.applicator",
]
agents_ok = True
for mod in agents:
    try:
        __import__(mod)
        print(f"{PASS} {mod}")
    except Exception as e:
        print(f"{FAIL} {mod}: {e}")
        agents_ok = False

# 5. Output PDF from last dry-run
print("\n5. LAST DRY-RUN OUTPUT")
pdf_dir = config.OUTPUT_DIR
pdfs = [f for f in os.listdir(pdf_dir) if f.endswith(".pdf")] if os.path.isdir(pdf_dir) else []
if pdfs:
    print(f"{PASS} {len(pdfs)} PDF(s) in output dir:")
    for p in pdfs:
        print(f"       {p}")
else:
    print(f"{FAIL} No PDFs found — run dry-run first")

# 6. Playwright / Applicator
print("\n6. PLAYWRIGHT / APPLICATOR")
try:
    from playwright.sync_api import sync_playwright
    print(f"{PASS} playwright importable")
    playwright_ok = True
except Exception as e:
    print(f"{FAIL} playwright: {e} — ejecuta: playwright install chromium")
    playwright_ok = False

profile_dir = config.PLAYWRIGHT_USER_DATA_DIR
profile_exists = os.path.isdir(profile_dir) and bool(os.listdir(profile_dir))
if profile_exists:
    print(f"{PASS} browser_profile: {profile_dir}")
else:
    print(f"  [WARN] browser_profile vacío o inexistente — ejecuta _setup_browser.py para inicializar sesión LinkedIn")
    # No es FAIL — el perfil se crea en el primer run

# 7. Apify config sanity
print("\n7. APIFY CONFIG")
print(f"{PASS} Actor ID:       {config.APIFY_ACTOR_ID}")
print(f"{PASS} Max wait:       {config.APIFY_MAX_WAIT_S}s")
print(f"{PASS} Poll interval:  {config.APIFY_POLL_S}s")

# Summary
print("\n=== SUMMARY ===")
all_ok = key_ok and paths_ok and db_ok and agents_ok and playwright_ok
if all_ok:
    print("ALL CHECKS PASSED — safe to connect Apify.")
else:
    print("ISSUES FOUND — fix above before connecting Apify.")
    sys.exit(1)
