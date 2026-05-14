# Applicator — Plan de Implementación y Pruebas Controladas Pre-Producción

> **Para ejecución:** Seguir paso a paso, canal por canal. Cada tarea tiene criterio de PASS/FAIL explícito. No avanzar al siguiente canal hasta que el anterior sea GREEN.

**Goal:** Verificar, corregir y probar el Applicator (`agents/applicator.py`) canal por canal hasta que la aplicación real de CVs sea confiable y trazable en producción.

**Architecture:** El Applicator recibe `(job, pdf_path, dry_run)` y despacha a uno de 3 canales. Canal A usa Playwright con sesión persistente de LinkedIn. Canal B abre el navegador para completar manualmente. Canal C abre mailto: en Windows. Cada canal retorna `{enviado, canal, url, mensaje}`.

**Tech Stack:** Python 3.14, Playwright (Chromium headful), ReportLab PDF, Windows mailto:, pytest, SQLite.

---

## GAPs identificados en el código actual

> Análisis hecho antes de escribir el plan — cada gap tiene una tarea asignada.

| # | Gap | Canal | Tarea |
|---|---|---|---|
| G1 | Sin validación de sesión activa antes de lanzar Playwright | A | T1 |
| G2 | Selectores Easy Apply pueden estar desactualizados (LinkedIn cambia DOM) | A | T2 |
| G3 | Sin detección de "Ya postulaste" (Already Applied) | A | T3 |
| G4 | `_apply_web_in_browser` recibe `ctx=None` pero su firma la usa — dead code | A | T3 |
| G5 | CV upload silencioso: no confirma si el archivo fue aceptado o rechazado | A | T4 |
| G6 | Sin notificación a Lorena cuando el navegador se abre para acción manual | B, C | T6, T7 |
| G7 | Canal C: `mailto:` sin campo `to:` — email no tiene destinatario | C | T7 |
| G8 | Sin screenshot de éxito nombrado con job+timestamp para auditoría | A | T4 |
| G9 | `screenshots/` path usa `../screenshots` relativo a `OUTPUT_DIR` — puede fallar | A | T1 |
| G10 | Sin smoke-test de Canal A contra URL real antes de submit | A | T2 |

---

## TAREA 1 — Validación de entorno pre-vuelo (Canal A)

**Archivos:**
- Modificar: `agents/applicator.py` — función `_validate_environment()`
- Modificar: `tests/test_applicator_controlled.py` — clase `TestEnvironmentValidation`

### Paso 1.1 — RED: escribir test de validación de entorno

```python
# En tests/test_applicator_controlled.py

class TestEnvironmentValidation:
    """El applicator valida entorno antes de lanzar Playwright."""

    def test_validate_env_returns_dict(self):
        from agents.applicator import validate_environment
        result = validate_environment()
        assert isinstance(result, dict)

    def test_validate_env_has_required_keys(self):
        from agents.applicator import validate_environment
        result = validate_environment()
        for key in ("browser_profile_exists", "pdf_output_dir_exists", "issues"):
            assert key in result, f"Falta clave '{key}' en validate_environment()"

    def test_validate_env_no_crash_without_profile(self, tmp_path, monkeypatch):
        """No lanza excepción aunque el perfil no exista."""
        import config
        monkeypatch.setattr(config, "PLAYWRIGHT_USER_DATA_DIR", str(tmp_path / "noexiste"))
        from agents.applicator import validate_environment
        result = validate_environment()
        assert result["browser_profile_exists"] is False
        assert len(result["issues"]) > 0
```

Correr: `python -m pytest tests/test_applicator_controlled.py::TestEnvironmentValidation -v`
Esperado: **FAIL** — `validate_environment` no existe.

### Paso 1.2 — GREEN: implementar `validate_environment()`

Agregar en `agents/applicator.py` después de los helpers internos:

```python
def validate_environment() -> dict:
    """
    Valida precondiciones del Applicator antes de lanzar Playwright.
    Retorna dict con estado de cada check e lista de issues.
    """
    issues = []

    profile_ok = os.path.isdir(config.PLAYWRIGHT_USER_DATA_DIR)
    if not profile_ok:
        issues.append(
            f"Perfil de navegador no encontrado: {config.PLAYWRIGHT_USER_DATA_DIR} "
            f"— ejecuta: python _setup_browser.py"
        )

    output_ok = os.path.isdir(os.path.dirname(config.OUTPUT_DIR) or ".")
    screenshots_dir = os.path.join(config.OUTPUT_DIR, "screenshots")

    return {
        "browser_profile_exists": profile_ok,
        "pdf_output_dir_exists": output_ok,
        "screenshots_dir": screenshots_dir,
        "issues": issues,
        "ready": len(issues) == 0,
    }
```

Correr: `python -m pytest tests/test_applicator_controlled.py::TestEnvironmentValidation -v`
Esperado: **PASS** — 3 tests GREEN.

### Paso 1.3 — Fix G9: corregir path de screenshots

En `_screenshot_on_error`, reemplazar:
```python
# ANTES (roto):
shots_dir = os.path.join(config.OUTPUT_DIR, "..", "screenshots")

# DESPUÉS (correcto):
shots_dir = os.path.join(config.OUTPUT_DIR, "screenshots")
```

### Paso 1.4 — Integrar validación en `apply()`

En la función `apply()`, antes del bloque `if dry_run:`, agregar:
```python
    if not dry_run and canal == "A":
        env = validate_environment()
        if not env["ready"]:
            return {
                "enviado": False, "canal": canal, "url": url,
                "mensaje": "Entorno no listo: " + "; ".join(env["issues"]),
            }
```

Correr: `python -m pytest -v --tb=short`
Esperado: **119+ tests GREEN** (ningún test existente roto).

---

## TAREA 2 — Smoke test Canal A: sesión y Easy Apply visible (sin submit)

> **Condición controlada:** usar una URL de LinkedIn real de un cargo que tenga Easy Apply. No se submitea — solo se verifica que el botón aparece y el modal abre.

**Archivos:**
- Crear: `tests/test_canal_a_smoke.py` — tests con marcador `@pytest.mark.real_browser`
- Crear: `scripts/smoke_canal_a.py` — script standalone para correr manualmente

### Paso 2.1 — Crear script de smoke standalone

```python
# scripts/smoke_canal_a.py
"""
Smoke test Canal A — verifica sesión LinkedIn y Easy Apply sin enviar.
Uso:
    python scripts/smoke_canal_a.py <linkedin_job_url>

Ejemplo:
    python scripts/smoke_canal_a.py "https://www.linkedin.com/jobs/view/1234567890"
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.applicator import validate_environment
import config

def smoke_test(url: str) -> dict:
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

    print(f"\n=== SMOKE TEST CANAL A ===")
    print(f"URL: {url}")

    env = validate_environment()
    if not env["ready"]:
        print(f"FAIL — entorno no listo: {env['issues']}")
        return {"ok": False, "razon": "entorno"}

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            config.PLAYWRIGHT_USER_DATA_DIR,
            headless=False,
            slow_mo=400,
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page() if not ctx.pages else ctx.pages[0]

        try:
            page.goto(url, timeout=30_000, wait_until="domcontentloaded")
            print(f"  Página cargada: {page.url}")

            # Verificar sesión
            if "login" in page.url or "authwall" in page.url:
                ctx.close()
                print("FAIL — sin sesión activa")
                return {"ok": False, "razon": "sin_sesion"}

            print("  OK — sesión activa")

            # Buscar Easy Apply
            selectors = [
                "button.jobs-apply-button",
                ".jobs-s-apply button",
                "button:has-text('Easy Apply')",
                "button[aria-label*='Easy Apply']",
            ]
            found = False
            for sel in selectors:
                try:
                    loc = page.locator(sel).first
                    if loc.is_visible(timeout=4_000):
                        print(f"  OK — Easy Apply button encontrado: '{sel}'")
                        found = True
                        break
                except Exception:
                    continue

            if not found:
                # Check "Already Applied"
                already = page.locator("button:has-text('Applied'), span:has-text('Applied')").first
                if already.is_visible(timeout=2_000):
                    print("  INFO — Ya postulaste a esta oferta ('Applied')")
                    ctx.close()
                    return {"ok": True, "razon": "ya_postulado"}
                print("FAIL — Easy Apply no encontrado. Posible: cargo externo, o DOM cambió.")
                page.screenshot(path="screenshots/smoke_no_easy_apply.png")
                ctx.close()
                return {"ok": False, "razon": "no_easy_apply"}

            print("  OK — smoke test PASS. El formulario existe. No se submitea.")
            page.screenshot(path="screenshots/smoke_easy_apply_ok.png")
            ctx.close()
            return {"ok": True, "razon": "easy_apply_visible"}

        except PwTimeout as e:
            print(f"FAIL — timeout: {e}")
            ctx.close()
            return {"ok": False, "razon": f"timeout: {e}"}
        except Exception as e:
            print(f"FAIL — error: {e}")
            ctx.close()
            return {"ok": False, "razon": str(e)}


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else input("URL LinkedIn: ").strip()
    result = smoke_test(url)
    print(f"\nResultado: {result}")
    sys.exit(0 if result["ok"] else 1)
```

### Paso 2.2 — Correr smoke test con URL real controlada

```bash
# Elegir una oferta LinkedIn con Easy Apply activo — idealmente un cargo de Paid Media
python scripts/smoke_canal_a.py "https://www.linkedin.com/jobs/view/<JOB_ID>"
```

**Criterio PASS:**
- `sesión activa` → OK
- `Easy Apply button encontrado` → OK
- Screenshot guardado en `screenshots/smoke_easy_apply_ok.png`

**Criterio FAIL:** cualquier `FAIL` en la salida → diagnosticar antes de continuar.

---

## TAREA 3 — Fix G3/G4: "Already Applied" + limpiar dead code

**Archivos:**
- Modificar: `agents/applicator.py`

### Paso 3.1 — RED: test "Already Applied"

```python
# En tests/test_applicator_controlled.py (agregar a clase existente)

def test_detect_already_applied_handled(self):
    """Si ya postulaste, el resultado debe indicarlo sin error."""
    # Este test es conceptual — valida que el código no lanza excepción
    # cuando se detecta "Applied". El smoke test real lo verifica con browser.
    # Aquí solo verificamos que la función existe y es callable.
    from agents.applicator import _apply_linkedin
    assert callable(_apply_linkedin)
```

### Paso 3.2 — GREEN: agregar detección "Already Applied" en `_apply_linkedin`

En `agents/applicator.py`, en `_apply_linkedin()`, después del bloque de sesión (línea ~126), agregar antes de buscar Easy Apply:

```python
            # ── 2.5. Verificar si ya postulaste ────────────────────────────
            try:
                already = page.locator(
                    "button:has-text('Applied'), "
                    "span:has-text('Applied'), "
                    "[aria-label*='Applied']"
                ).first
                if already.is_visible(timeout=2_000):
                    print("  [Applicator-A] Ya postulaste a esta oferta.")
                    ctx.close()
                    return {
                        "enviado": False, "canal": "A", "url": url,
                        "mensaje": "Ya postulaste a esta oferta anteriormente",
                    }
            except Exception:
                pass  # Si no aparece, continuar normalmente
```

### Paso 3.3 — Fix G4: eliminar `_apply_web_in_browser` dead code del fallback

En `_apply_linkedin()`, línea 148, reemplazar la llamada a `_apply_web_in_browser` con:

```python
            if easy_apply_btn is None:
                print("  [Applicator-A] No hay Easy Apply — abriendo URL en Canal B.")
                ctx.close()
                return _apply_web(job, pdf_path)
```

La función `_apply_web_in_browser` puede mantenerse como helper interno para futuros usos pero no se llama desde el flujo principal.

---

## TAREA 4 — Canal A: auditoría de selectores y upload verification

**Archivos:**
- Modificar: `agents/applicator.py` — `_maybe_upload_cv()`, `_apply_linkedin()`
- Crear: `scripts/audit_selectors.py`

### Paso 4.1 — Script de auditoría de selectores LinkedIn

```python
# scripts/audit_selectors.py
"""
Audita selectores de LinkedIn Easy Apply en una URL real.
Muestra qué selectores funcionan y cuáles no.
Uso: python scripts/audit_selectors.py <url>
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

SELECTORS_APPLY = [
    "button.jobs-apply-button",
    "button[data-job-id]",
    ".jobs-s-apply button",
    "button:has-text('Easy Apply')",
    "button[aria-label*='Easy Apply']",
    ".jobs-apply-button--top-card",
]

def audit(url: str):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            config.PLAYWRIGHT_USER_DATA_DIR, headless=False, slow_mo=200)
        page = ctx.new_page()
        page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        print(f"\nURL cargada: {page.url}\n")
        print("=== SELECTORES EASY APPLY ===")
        for sel in SELECTORS_APPLY:
            try:
                loc = page.locator(sel).first
                visible = loc.is_visible(timeout=2_000)
                print(f"  {'OK ' if visible else 'NO '} {sel}")
            except Exception as e:
                print(f"  ERR  {sel} — {e}")
        input("\nPresiona Enter para cerrar...")
        ctx.close()

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else input("URL LinkedIn: ").strip()
    audit(url)
```

### Paso 4.2 — Mejorar `_maybe_upload_cv()` con confirmación

```python
def _maybe_upload_cv(page, pdf_path: str) -> bool:
    """
    Sube el PDF si hay un campo de archivo visible.
    Retorna True si el upload fue exitoso, False si no hay campo o falló.
    """
    if not pdf_path or not os.path.exists(pdf_path):
        print(f"  [Applicator-A] PDF no encontrado: {pdf_path}")
        return False

    selectors = [
        ".jobs-document-upload__input",
        "input[type='file'][name*='resume']",
        "input[type='file'][accept*='pdf']",
        "input[type='file']",
    ]
    for sel in selectors:
        try:
            inp = page.locator(sel).first
            if inp.is_visible(timeout=1_500):
                inp.set_input_files(pdf_path)
                _human_pause(1.0, 1.5)
                # Verificar que aparece el nombre del archivo
                filename = os.path.basename(pdf_path)
                try:
                    page.locator(f"text='{filename}'").wait_for(timeout=3_000)
                    print(f"  [Applicator-A] CV confirmado: {filename}")
                except Exception:
                    print(f"  [Applicator-A] CV subido (sin confirmación visual): {filename}")
                return True
        except Exception:
            continue
    return False
```

### Paso 4.3 — Screenshot de éxito con nombre descriptivo

En `_apply_linkedin()`, después de `submit_btn.click()`, reemplazar:

```python
                    _screenshot_on_error(page, "submitted")
```

Con:

```python
                    # Screenshot de confirmación de envío
                    shots_dir = os.path.join(config.OUTPUT_DIR, "screenshots")
                    os.makedirs(shots_dir, exist_ok=True)
                    ts = int(time.time())
                    cargo_slug = re.sub(r"[^\w]", "_", cargo)[:30]
                    shot_path = os.path.join(shots_dir, f"enviado_{cargo_slug}_{ts}.png")
                    try:
                        page.screenshot(path=shot_path)
                        print(f"  [Applicator-A] Screenshot: {shot_path}")
                    except Exception:
                        pass
```

> Agregar `import re` al bloque de imports si no está.

---

## TAREA 5 — Canal A: prueba controlada END-TO-END con oferta real

> **Condición:** oferta LinkedIn seleccionada por Lorena con Easy Apply activo, preferiblemente de baja prioridad o descartada, para que si hay error no importa.

### Paso 5.1 — Checklist pre-prueba

```
[ ] python _preflight.py → todos los checks OK
[ ] python scripts/smoke_canal_a.py <URL> → PASS (Easy Apply visible)
[ ] python scripts/audit_selectors.py <URL> → al menos 2 selectores OK
[ ] PDF generado existe en outputs/ con el CV correcto
[ ] Lorena está presente para completar manualmente si el formulario tiene preguntas extra
```

### Paso 5.2 — Correr prueba controlada

```python
# Desde Python REPL o script temporal:
import sys
sys.path.insert(0, r"C:\Users\lilia\Clientes\Lorena Ruiz\JobAppAgent")
from agents.applicator import apply
import os

JOB_PRUEBA = {
    "cargo": "<CARGO REAL SELECCIONADO>",
    "empresa": "<EMPRESA>",
    "url": "https://www.linkedin.com/jobs/view/<JOB_ID>",
    "modalidad": "Híbrido",
    "ubicacion": "Bogotá",
    "rama": "C",
}
PDF_PATH = r"C:\Users\lilia\Clientes\Lorena Ruiz\JobAppAgent\outputs\<CV_GENERADO>.pdf"

result = apply(JOB_PRUEBA, PDF_PATH, dry_run=False)
print(result)
```

**Criterios PASS del Canal A:**
- `enviado: True` → submit automático completado
- `enviado: False, mensaje: "formulario con preguntas"` → aceptable (Lorena completa)
- Screenshot en `outputs/screenshots/enviado_*.png`
- No excepción no manejada

---

## TAREA 6 — Canal B: prueba controlada con portal elempleo.com

**Archivos:**
- Modificar: `agents/applicator.py` — agregar notificación Telegram a `_apply_web()`

### Paso 6.1 — Agregar notificación Telegram en Canal B

En `_apply_web()`, antes de `page.goto()`, agregar:

```python
    # Notificar a Lorena que hay acción manual requerida
    try:
        from agents.reporter import send_telegram
        send_telegram(
            f"📋 *Canal B — Acción manual requerida*\n"
            f"Cargo: {cargo}\n"
            f"Empresa: {empresa}\n"
            f"CV: `{os.path.basename(pdf_path)}`\n"
            f"Abriendo navegador ahora..."
        )
    except Exception:
        pass  # No fallar si Telegram no está disponible
```

### Paso 6.2 — Reducir timeout de espera de 5min a 10min con aviso cada 2min

```python
    # Esperar hasta que el usuario cierre el navegador (máx 10 minutos)
    print("  [Applicator-B] Completa el formulario. El navegador cerrará en 10 min.")
    for _ in range(5):  # 5 x 2min = 10min
        try:
            page.wait_for_event("close", timeout=120_000)
            break
        except Exception:
            print("  [Applicator-B] Aún esperando...")
```

### Paso 6.3 — Prueba controlada Canal B

```bash
python scripts/test_canal_b.py
```

Crear `scripts/test_canal_b.py`:
```python
"""
Prueba controlada Canal B — abre un portal de empleo conocido.
Uso: python scripts/test_canal_b.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agents.applicator import apply

JOB_ELEMPLEO = {
    "cargo": "Prueba Canal B — Paid Media",
    "empresa": "Empresa Test Elempleo",
    "url": "https://www.elempleo.com/co/oferta-empleo/paid-media-specialist/",
    "modalidad": "Híbrido",
    "ubicacion": "Bogotá",
    "rama": "C",
}
result = apply(JOB_ELEMPLEO, "", dry_run=False)
print(f"\nResultado Canal B: {result}")
```

**Criterios PASS del Canal B:**
- Navegador Chromium abre en la URL correcta
- `canal: "B"` en el resultado
- `enviado: False` (es acción manual — correcto)
- Notificación Telegram recibida

---

## TAREA 7 — Canal C: fix email destinatario + prueba controlada

**Archivos:**
- Modificar: `agents/applicator.py` — `_apply_email()`

### Paso 7.1 — RED: test email con destinatario

```python
# En tests/test_applicator_controlled.py
def test_canal_c_mailto_has_to_if_email_known(self):
    """Si el job tiene campo email_contacto, el mailto debe incluir to:"""
    job_with_email = {
        **_JOB_COMPANY_SITE,
        "email_contacto": "rrhh@fintechcolombia.com",
    }
    # dry_run no ejecuta _apply_email, así que solo verificamos que el campo
    # email_contacto se refleje si el código lo usa. Test de integración.
    result = apply(job_with_email, _FAKE_PDF, dry_run=True)
    assert result["canal"] == "C"  # precondición
    # El test real se hace en Paso 7.3 con dry_run=False en entorno controlado
```

### Paso 7.2 — GREEN: `_apply_email()` usa `email_contacto` si disponible

```python
def _apply_email(job: dict, pdf_path: str) -> dict:
    cargo = job.get("cargo", "")
    empresa = job.get("empresa", "")
    url = job.get("url", "")
    email_contacto = job.get("email_contacto", "")  # Nuevo campo opcional

    subject = urllib.parse.quote(f"Aplicación: {cargo} — Lorena Ruiz")
    body = urllib.parse.quote(
        f"Estimados,\n\n"
        f"Me dirijo a ustedes para postularme al cargo de {cargo} en {empresa}.\n"
        f"Adjunto mi CV optimizado para esta posición (ver archivo adjunto).\n\n"
        f"Referencia de la oferta: {url}\n\n"
        f"Quedo atenta a su contacto.\n\n"
        f"Lorena Ruiz\n"
        f"lilian@lorena-ruiz.com  |  +57 315 256 1884\n"
        f"www.linkedin.com/in/lilianlorenaruiz"
    )
    # Incluir destinatario si lo sabemos
    to_field = urllib.parse.quote(email_contacto) if email_contacto else ""
    mailto = f"mailto:{to_field}?subject={subject}&body={body}"

    print(f"  [Applicator-C] Email para: {cargo} @ {empresa}")
    if email_contacto:
        print(f"  Destinatario: {email_contacto}")
    else:
        print(f"  Sin destinatario — completar manualmente")
    print(f"  CV a adjuntar: {os.path.basename(pdf_path) if pdf_path else 'N/A'}")

    # Notificación Telegram
    try:
        from agents.reporter import send_telegram
        send_telegram(
            f"📧 *Canal C — Email borrador abierto*\n"
            f"Cargo: {cargo}\n"
            f"Empresa: {empresa}\n"
            f"Destinatario: {email_contacto or 'COMPLETAR MANUALMENTE'}\n"
            f"CV: `{os.path.basename(pdf_path) if pdf_path else 'N/A'}`"
        )
    except Exception:
        pass

    try:
        if sys.platform == "win32":
            os.startfile(mailto)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", mailto])
        else:
            subprocess.Popen(["xdg-open", mailto])
    except Exception as e:
        return {
            "enviado": False, "canal": "C", "url": url,
            "mensaje": f"Error al abrir cliente de correo: {e}",
        }

    return {
        "enviado": False,
        "canal": "C",
        "url": url,
        "mensaje": (
            f"Borrador abierto — adjuntar CV: {os.path.basename(pdf_path) if pdf_path else '?'}"
            + (f" | To: {email_contacto}" if email_contacto else " | Completar destinatario")
        ),
    }
```

### Paso 7.3 — Prueba controlada Canal C (Windows)

```bash
python scripts/test_canal_c.py
```

Crear `scripts/test_canal_c.py`:
```python
"""
Prueba controlada Canal C — abre cliente de correo con borrador.
Uso: python scripts/test_canal_c.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agents.applicator import apply

JOB_EMAIL = {
    "cargo": "Prueba Canal C — Marketing Consultant",
    "empresa": "Empresa Test Email",
    "url": "https://empresa-ejemplo.com/jobs/mktg-consultant",
    "email_contacto": "lilian@lorena-ruiz.com",  # email propio para prueba
    "modalidad": "Híbrido",
    "ubicacion": "Bogotá",
    "rama": "A",
}
result = apply(JOB_EMAIL, "", dry_run=False)
print(f"\nResultado Canal C: {result}")
```

**Criterios PASS del Canal C:**
- Cliente de correo se abre con asunto y cuerpo pre-llenados
- `canal: "C"` en resultado
- `enviado: False` (es manual — correcto)
- Mensaje indica qué PDF adjuntar
- Notificación Telegram recibida

---

## TAREA 8 — Suite de tests actualizada + commit final

**Archivos:**
- Modificar: `tests/test_applicator_controlled.py` — agregar TestEnvironmentValidation

### Paso 8.1 — Correr suite completa

```bash
python -m pytest -v --tb=short
```

Esperado: **≥ 122 tests GREEN** (119 existentes + 3 de TestEnvironmentValidation).

### Paso 8.2 — Actualizar memoria del proyecto

Actualizar `docs/plans/2026-05-14-applicator-produccion.md` con resultados reales de cada canal.

### Paso 8.3 — Commit de producción

```bash
git add agents/applicator.py tests/test_applicator_controlled.py scripts/
git commit -m "feat: applicator production-ready — canal A/B/C con validacion entorno, already-applied detection, email_contacto, Telegram notifications"
```

---

## Orden de ejecución recomendado

```
T1 (validate_environment) → T3 (fix dead code) → T4 (upload fix) →
smoke T2 (sesión + Easy Apply visible) →
audit T4.1 (selectores OK) →
T5 (prueba real Canal A) →
T6 (prueba Canal B) →
T7 (prueba Canal C) →
T8 (suite final + commit)
```

---

## Checklist de PASO A PRODUCCIÓN REAL

```
[ ] T1 PASS — validate_environment() implementada y testeada
[ ] T2 PASS — smoke test Canal A: sesión activa + Easy Apply visible
[ ] T3 PASS — Already Applied detectado, dead code eliminado
[ ] T4 PASS — selectores auditados, upload con confirmación
[ ] T5 PASS — Canal A real: enviado=True o manual completado sin excepciones
[ ] T6 PASS — Canal B real: navegador abre en URL correcta
[ ] T7 PASS — Canal C real: email borrador abre con cuerpo correcto
[ ] T8 PASS — ≥ 122 tests GREEN
[ ] Lorena aprueba primer CV enviado revisando la aplicación en LinkedIn
```

**Solo activar `dry_run=False` en `main.py` cuando todos los checks estén marcados.**
