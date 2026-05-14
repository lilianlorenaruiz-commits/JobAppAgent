"""
Smoke test Nivel 3 — Canal A real.
Ejecuta apply() sin dry_run con una oferta de LinkedIn controlada.

Verifica:
  1. Browser headful abre LinkedIn con sesión persistente
  2. El agente hace clic en Easy Apply
  3. Por cada paso del modal: sube CV, llena contacto, smart fill con Claude
  4. En la página Review: envía screenshot a Lorena por Telegram
  5. Lorena responde SI o NO en Telegram
  6. SI → submit / NO → browser queda abierto para completar manualmente

Uso:
  python _smoke_canal_a.py
"""
import os
import sys
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from agents.applicator import apply

# ── Job de prueba — LinkedIn Easy Apply (Canal A) ──────────────────────────────
# Reemplazar la URL con una oferta real de LinkedIn que tenga Easy Apply
TEST_JOB = {
    "cargo":     "Por identificar al abrir LinkedIn",
    "empresa":   "Por identificar al abrir LinkedIn",
    "url":       "https://www.linkedin.com/jobs/view/4407519233",
    "modalidad": "Por confirmar",
    "ubicacion": "Por confirmar",
    "rama":      "A",
    "score":     91,
}

# ── CV disponible ──────────────────────────────────────────────────────────────
PDF_PATH = os.path.join(config.OUTPUT_DIR, "Lorena Ruiz - Paid Media Manager - Rappi.pdf")
if not os.path.exists(PDF_PATH):
    pdfs = glob.glob(os.path.join(config.OUTPUT_DIR, "*.pdf"))
    PDF_PATH = pdfs[0] if pdfs else "cv_prueba.pdf"

# ── CV en texto plano (para smart fill) ───────────────────────────────────────
CV_TEXT = (
    "Lorena Ruiz — Paid Media Specialist / AM LinkedIn Ads. "
    "14 años en marketing digital. Meta Ads, Google Ads, Amazon Ads, LinkedIn Ads. "
    "Presupuestos USD 240K mensuales. 300 cuentas B2B enterprise en LinkedIn. "
    "Bogotá D.C. | lilian@lorena-ruiz.com | +57 315 256 1884"
)

# ── Job description de prueba ─────────────────────────────────────────────────
JD_TEXT = (
    "We are looking for a Paid Media Manager with experience in Meta Ads, "
    "Google Ads, and LinkedIn Ads. Budget management of USD 50K+ monthly required."
)

print("=" * 60)
print("SMOKE TEST — CANAL A (real, sin dry_run)")
print("=" * 60)
print(f"Cargo:   {TEST_JOB['cargo']}")
print(f"Empresa: {TEST_JOB['empresa']}")
print(f"URL:     {TEST_JOB['url']}")
print(f"PDF:     {os.path.basename(PDF_PATH)}")
print(f"HITL:    {'ACTIVADO' if config.HITL_ENABLED else 'DESACTIVADO'}")
print(f"Timeout: {config.HITL_TIMEOUT_S // 60} minutos")
print()
print("ANTES DE CONTINUAR:")
print("  1. Asegúrate de haber corrido python _setup_browser.py (sesión LinkedIn)")
print("  2. Reemplaza la URL del TEST_JOB con una oferta real de LinkedIn")
print("     que tenga botón 'Easy Apply'")
print("  3. Si HITL está activo, Telegram recibirá un screenshot para aprobar")
print()

print()

result = apply(TEST_JOB, PDF_PATH, dry_run=False,
               cv_text=CV_TEXT, job_description=JD_TEXT)

print()
print("=" * 60)
print("RESULTADO:")
print(f"  Canal:   {result['canal']}")
print(f"  Enviado: {result['enviado']}")
print(f"  Mensaje: {result['mensaje']}")
print("=" * 60)
print()
print("Verifica ahora:")
print("  [ ] ¿Se abrió el browser en la URL de LinkedIn?")
print("  [ ] ¿El agente hizo clic en Easy Apply?")
print("  [ ] ¿Se llenaron los campos de contacto (teléfono, email)?")
print("  [ ] ¿Claude llenó campos de texto libre del formulario?")
if config.HITL_ENABLED:
    print("  [ ] ¿Telegram recibió screenshot de la página Review?")
    print("  [ ] ¿Lorena respondió SI/NO y el resultado es correcto?")
else:
    print("  [ ] (HITL desactivado) ¿Se hizo submit automático?")
print()
print("Si todo OK -> Canal A aprobado OK")
