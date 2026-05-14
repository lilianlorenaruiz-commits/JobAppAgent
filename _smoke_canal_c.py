"""
Smoke test Nivel 3 — Canal C real.
Ejecuta apply() sin dry_run con una oferta controlada.

Verifica:
  1. Claude genera el body del correo (coherente con CV + JD)
  2. El cliente de correo abre con el body curado
  3. Telegram recibe la notificación "📧 CVs listos..."

Uso:
  python _smoke_canal_c.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from agents.applicator import apply
from agents.cv_rewriter import _cv_to_plain_text
from agents.cv_parser import parse_cv

# ── Job de prueba — empresa directa (Canal C) ──────────────────────────────────
# URL sin linkedin.com ni portales → detectado como Canal C
TEST_JOB = {
    "cargo":    "Paid Media Specialist",
    "empresa":  "Adsmurai Colombia",
    "url":      "https://adsmurai.com/careers/paid-media-specialist-bogota",
    "modalidad": "Híbrido",
    "ubicacion": "Bogotá",
    "rama":     "C",
    "score":    89,
    "description": (
        "Adsmurai busca un Paid Media Specialist para gestionar campañas de performance "
        "en Meta Ads, Google Ads y LinkedIn Ads para clientes B2B y B2C en Latinoamérica. "
        "Requisitos: mínimo 3 años de experiencia en paid media, manejo de presupuestos "
        "superiores a USD 50K mensuales, conocimiento de ROAS, CPC, CTR y optimización "
        "de campañas full-funnel. Deseable experiencia con Amazon Ads o DSP. "
        "Inglés intermedio-avanzado. Modalidad híbrida en Bogotá."
    ),
}

# ── CV tailored — tomamos el texto plano del cv_rewriter ──────────────────────
print("Cargando CV de Lorena...")
try:
    cv = parse_cv()
    cv_text = _cv_to_plain_text(cv, rama="C")
    print(f"CV listo: {len(cv_text)} caracteres\n")
except Exception as e:
    print(f"Error cargando CV: {e}")
    # Fallback mínimo
    cv_text = (
        "LORENA RUIZ\n"
        "Paid Media Specialist / Account Manager LinkedIn Ads\n"
        "Teleperformance (LinkedIn) — February 2026 – Present | Latin America\n"
        "Campaign Planner Contractor — Amazon, Colombia | May 2025 – Feb 2026 | APAC\n"
        "Skills: Meta Ads, Google Ads, LinkedIn Ads, Amazon DSP, ROAS, CTR, CPC. "
        "Budgets USD 200K+. C2 English."
    )

# ── Ruta del PDF ya generado ───────────────────────────────────────────────────
PDF_PATH = os.path.join(
    config.OUTPUT_DIR, "Lorena Ruiz - Paid Media Manager - Rappi.pdf"
)
if not os.path.exists(PDF_PATH):
    # Cualquier PDF existente sirve para la prueba
    pdfs = [
        f for f in os.listdir(config.OUTPUT_DIR) if f.endswith(".pdf")
    ]
    PDF_PATH = os.path.join(config.OUTPUT_DIR, pdfs[0]) if pdfs else "cv_prueba.pdf"

print("=" * 55)
print("SMOKE TEST — CANAL C (real, sin dry_run)")
print("=" * 55)
print(f"Cargo:   {TEST_JOB['cargo']}")
print(f"Empresa: {TEST_JOB['empresa']}")
print(f"URL:     {TEST_JOB['url']}")
print(f"PDF:     {os.path.basename(PDF_PATH)}")
print()
print("Paso 1: Claude generará el body del correo...")
print("Paso 2: Se abrirá tu cliente de correo con el body curado.")
print("Paso 3: Telegram recibirá la notificación.")
print()
input("Presiona ENTER para continuar (o Ctrl+C para cancelar)...")
print()

# ── Ejecutar apply() real ─────────────────────────────────────────────────────
result = apply(
    TEST_JOB,
    PDF_PATH,
    dry_run=False,
    cv_text=cv_text,
    job_description=TEST_JOB["description"],
)

print()
print("=" * 55)
print("RESULTADO:")
print(f"  Canal:   {result['canal']}")
print(f"  Enviado: {result['enviado']}")
print(f"  Mensaje: {result['mensaje']}")
print("=" * 55)
print()

# Mostrar body guardado si existe
import glob
body_files = glob.glob(
    os.path.join(config.OUTPUT_DIR, "email_body_Paid Media Specialist*.txt")
)
if body_files:
    latest = max(body_files, key=os.path.getmtime)
    print(f"Body guardado en: {latest}")
    print()
    with open(latest, encoding="utf-8") as f:
        print("--- BODY GENERADO ---")
        print(f.read())
        print("--- FIN BODY ---")
    print()

print("Verifica ahora:")
print("  [ ] ¿Se abrió Gmail en Chrome con el compose pre-llenado?")
print("  [ ] ¿El idioma del body coincide con el JD (español)?")
print("  [ ] ¿El body menciona keywords del JD (Meta Ads, ROAS, full-funnel)?")
print("  [ ] ¿Telegram recibió '📧 CVs listos para completar envío en draft'?")
print()
print("Si algo no abrió → el body está en el archivo mostrado arriba.")
print()
print("Si todo OK → Canal C aprobado ✅")
print("Si hay ajustes → reportar para afinar el prompt.")
