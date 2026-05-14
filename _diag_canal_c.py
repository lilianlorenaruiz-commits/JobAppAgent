"""
Diagnóstico Canal C — traza cada capa sin efectos secundarios reales.
Ejecuta: python _diag_canal_c.py
"""
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

# ── Carga el CV y genera body (mismo que el smoke test) ───────────────────────
print("=== CAPA 1: Generar body con Claude ===")
try:
    from agents.cv_parser import parse_cv
    from agents.cv_rewriter import _cv_to_plain_text
    from agents.applicator import _generate_email_body

    cv = parse_cv()
    cv_text = _cv_to_plain_text(cv, rama="C")

    job = {
        "cargo": "Paid Media Specialist",
        "empresa": "Adsmurai Colombia",
        "url": "https://adsmurai.com/careers/paid-media-specialist-bogota",
    }
    jd = (
        "Adsmurai busca un Paid Media Specialist para gestionar campañas de performance "
        "en Meta Ads, Google Ads y LinkedIn Ads para clientes B2B y B2C en Latinoamérica. "
        "Requisitos: mínimo 3 años de experiencia, presupuestos USD 50K+, ROAS, CTR, CPC."
    )

    body_text = _generate_email_body(job, cv_text, jd)
    print(f"[OK] Body generado: {len(body_text)} caracteres")
    print(f"\n--- BODY GENERADO ---\n{body_text}\n--- FIN BODY ---\n")

except Exception as e:
    print(f"[ERROR] Capa 1 falló: {e}")
    body_text = "Body de prueba para diagnóstico. Lorena Ruiz solicita el cargo."

# ── Capa 2: medir longitud URL ─────────────────────────────────────────────────
print("=== CAPA 2: Longitud de la URL mailto: ===")
subject_raw = "Aplicación: Paid Media Specialist — Lorena Ruiz"
subject_enc = urllib.parse.quote(subject_raw)
body_enc    = urllib.parse.quote(body_text)
mailto      = f"mailto:?subject={subject_enc}&body={body_enc}"

print(f"Body raw:      {len(body_text)} chars")
print(f"Body encoded:  {len(body_enc)} chars")
print(f"URL total:     {len(mailto)} chars")

WINDOWS_LIMIT = 2048
if len(mailto) > WINDOWS_LIMIT:
    print(f"[PROBLEMA] URL demasiado larga: {len(mailto)} > {WINDOWS_LIMIT} chars")
    print("           Windows trunca o ignora mailto: URLs sobre ~2048 chars.")
else:
    print(f"[OK] URL dentro del límite ({len(mailto)} < {WINDOWS_LIMIT})")

# ── Capa 3: probar os.startfile con mailto mínimo ─────────────────────────────
print("\n=== CAPA 3: os.startfile con mailto MÍNIMO (solo subject) ===")
mailto_short = f"mailto:?subject={subject_enc}"
print(f"URL corta: {len(mailto_short)} chars — {mailto_short[:80]}...")
print("Intentando abrir cliente de correo con URL corta...")
try:
    os.startfile(mailto_short)
    print("[OK] os.startfile completó sin excepción")
    print("     → ¿Se abrió el cliente de correo? Mira tu pantalla.")
except Exception as e:
    print(f"[ERROR] os.startfile falló: {type(e).__name__}: {e}")

# ── Capa 4: verificar cliente de correo por defecto ───────────────────────────
print("\n=== CAPA 4: Cliente de correo por defecto en Windows ===")
try:
    import winreg
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\mailto\UserChoice",
    )
    prog_id, _ = winreg.QueryValueEx(key, "ProgId")
    print(f"Default mailto handler: {prog_id}")
    winreg.CloseKey(key)
except Exception as e:
    print(f"[INFO] No se pudo leer el registro: {e}")
    print("       Puede que no haya cliente de correo configurado como default.")

print("\n=== DIAGNÓSTICO COMPLETO ===")
print("Revisa los resultados arriba y reporta:")
print("  1. ¿Cuántos chars tiene la URL total?")
print("  2. ¿Se abrió algo con el mailto mínimo (Capa 3)?")
print("  3. ¿Cuál es el default mailto handler (Capa 4)?")
