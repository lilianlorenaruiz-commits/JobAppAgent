"""
Configuración global del JobAppAgent.
Las API keys se leen del env var primero; si no existen, del archivo en config/.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Rutas ──────────────────────────────────────────────────────────────────────
CV_PATH       = r"C:\Users\lilia\CV\Lorena_Ruiz_CV.pdf"
DB_PATH       = os.path.join(BASE_DIR, "database", "job_app.db")
PROFILES_DIR  = os.path.join(BASE_DIR, "profiles")
OUTPUT_DIR    = os.path.join(BASE_DIR, "output", "cv_optimizados")
CONFIG_DIR    = os.path.join(BASE_DIR, "config")

# ── Carga de claves ────────────────────────────────────────────────────────────
def _key(env_var: str, filename: str) -> str:
    val = os.environ.get(env_var, "").strip()
    if val:
        return val
    path = os.path.join(CONFIG_DIR, filename)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    return ""

ANTHROPIC_API_KEY  = _key("ANTHROPIC_API_KEY",  "anthropic_key.txt")
APIFY_API_KEY      = _key("APIFY_API_KEY",       "apify_key.txt")
TELEGRAM_TOKEN     = _key("TELEGRAM_TOKEN",      "telegram_token.txt")
TELEGRAM_CHAT_ID   = _key("TELEGRAM_CHAT_ID",    "telegram_chat_id.txt")

# ── Thresholds globales ────────────────────────────────────────────────────────
THRESHOLD_MATCH = 85   # mínimo para pasar al CV rewriter
THRESHOLD_ATS   = 95   # mínimo para generar PDF

# ── Scraper ────────────────────────────────────────────────────────────────────
LINKEDIN_DIAS_MAX    = 16
LINKEDIN_UBICACIONES = ["Bogotá", "Colombia"]
MODALIDADES          = ["Presencial", "Híbrido", "Remoto"]

# ── Modelo IA ──────────────────────────────────────────────────────────────────
MODEL_FAST = "claude-haiku-4-5-20251001"   # skill matching, scoring rápido
MODEL_MAIN = "claude-sonnet-4-6"           # CV rewriting

# ── Apify ──────────────────────────────────────────────────────────────────────
APIFY_ACTOR_ID   = "bebity/linkedin-jobs-scraper"
APIFY_MAX_WAIT_S = 300    # 5 min máximo por run
APIFY_POLL_S     = 10     # intervalo de polling
