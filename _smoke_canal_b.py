"""
Smoke test Nivel 3 — Canal B real.
Ejecuta apply() sin dry_run con una oferta controlada en computrabajo.com.

Verifica:
  1. Browser headful se abre en la URL del portal
  2. El agente intenta clickear el botón Apply/Aplicar
  3. Telegram recibe "⏳ CVs listos para completar envío en browser"
  4. El browser permanece abierto para que Lorena complete manualmente

Uso:
  python _smoke_canal_b.py
"""
import os
import sys
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from agents.applicator import apply

# ── Job de prueba — portal de empleo (Canal B) ─────────────────────────────────
TEST_JOB = {
    "cargo":     "Trade Marketing Specialist",
    "empresa":   "Computrabajo",
    "url":       "https://www.computrabajo.com.co/trabajo-de-trade-marketing",
    "modalidad": "Presencial",
    "ubicacion": "Bogotá",
    "rama":      "B",
    "score":     86,
}

# ── PDF disponible ─────────────────────────────────────────────────────────────
PDF_PATH = os.path.join(config.OUTPUT_DIR, "Lorena Ruiz - Paid Media Manager - Rappi.pdf")
if not os.path.exists(PDF_PATH):
    pdfs = glob.glob(os.path.join(config.OUTPUT_DIR, "*.pdf"))
    PDF_PATH = pdfs[0] if pdfs else "cv_prueba.pdf"

print("=" * 55)
print("SMOKE TEST — CANAL B (real, sin dry_run)")
print("=" * 55)
print(f"Cargo:   {TEST_JOB['cargo']}")
print(f"Empresa: {TEST_JOB['empresa']}")
print(f"URL:     {TEST_JOB['url']}")
print(f"PDF:     {os.path.basename(PDF_PATH)}")
print(f"Timeout: {config.HITL_TIMEOUT_S // 60} minutos")
print()
print("Paso 1: Se abrirá el browser en el portal.")
print("Paso 2: El agente intentará clickear Apply/Aplicar.")
print("Paso 3: Telegram recibirá la notificación con timeout.")
print("Paso 4: Completa el formulario y cierra el browser.")
print()
input("Presiona ENTER para continuar (o Ctrl+C para cancelar)...")
print()

result = apply(TEST_JOB, PDF_PATH, dry_run=False)

print()
print("=" * 55)
print("RESULTADO:")
print(f"  Canal:   {result['canal']}")
print(f"  Enviado: {result['enviado']}")
print(f"  Mensaje: {result['mensaje']}")
print("=" * 55)
print()
print("Verifica ahora:")
print("  [ ] ¿Se abrió el browser en la URL del portal?")
print("  [ ] ¿El agente hizo click en el botón Apply/Aplicar?")
print("  [ ] ¿Telegram recibió '⏳ CVs listos para completar envío en browser'?")
print("  [ ] ¿El mensaje de Telegram incluye cargo, empresa y timeout?")
print()
print("Si el botón Apply no fue encontrado → reportar el portal para agregar el selector.")
print("Si todo OK → Canal B aprobado ✅")
