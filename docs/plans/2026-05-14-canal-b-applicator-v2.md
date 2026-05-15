# Canal B Applicator v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Actualizar `_apply_web()` para hacer auto-click en el botón Apply de portales de empleo y enviar notificación Telegram HITL a Lorena con cargo, empresa, score y tiempo disponible.

**Architecture:** Dos cambios a `agents/applicator.py`: (1) nueva función `_click_apply_button(page)` que prueba múltiples selectores CSS/texto para encontrar y clickear Apply, retorna bool; (2) `_apply_web()` actualizado que llama al clicker después de cargar la página y luego envía notificación via `send_cv_ready_browser()` ya existente en `telegram_hitl.py`. Para hacer `sync_playwright` mockeable en tests, se mueve a import de módulo con try/except (mismo patrón que `anthropic`).

**Tech Stack:** Python 3.11+, Playwright sync API, python-telegram-bot v20 (via `agents/telegram_hitl.py` ya implementado), pytest + unittest.mock.

---

## Archivos a modificar / crear

| Archivo | Acción | Qué cambia |
|---|---|---|
| `agents/applicator.py` | Modificar | Import `sync_playwright` a nivel módulo; import `send_cv_ready_browser`; nueva función `_click_apply_button(page)`; actualizar `_apply_web()` |
| `tests/test_applicator_canal_b.py` | Crear | Tests TDD ciclos 17-18: `_click_apply_button` y `_apply_web()` v2 |
| `_smoke_canal_b.py` | Crear | Smoke test Nivel 3 Canal B con oferta controlada en elempleo.com |

---

## Task 1: Ciclo 17 RED — Tests para `_click_apply_button()`

**Files:**
- Create: `tests/test_applicator_canal_b.py`

- [ ] **Step 1: Crear el archivo de tests con los 3 casos**

```python
"""
Ciclo 17 RED→GREEN: Canal B _click_apply_button()
  - retorna True y hace click cuando encuentra el botón
  - retorna False cuando no encuentra ningún selector
  - no lanza excepción si el locator falla

Ciclo 18 RED→GREEN: Canal B _apply_web() v2
  - send_cv_ready_browser() se llama con la info del job
  - dry_run no llama Telegram ni Playwright
  - resultado tiene schema correcto (4 claves, canal==B)
  - notificación incluye timeout en minutos
"""
import os
import sys
from unittest.mock import MagicMock, patch, call
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_JOB_B = {
    "cargo":   "Trade Marketing Manager",
    "empresa": "Computrabajo Test",
    "url":     "https://www.computrabajo.com.co/jobs/test-123",
    "rama":    "B",
    "score":   88,
}


# ── helpers ────────────────────────────────────────────────────────────────────

def _mock_playwright_ctx(page=None):
    """Mock completo de sync_playwright context manager."""
    mock_page = page or MagicMock()
    mock_page.wait_for_event.side_effect = Exception("browser closed")
    mock_ctx = MagicMock()
    mock_ctx.pages = [mock_page]
    mock_pw_instance = MagicMock()
    mock_pw_instance.chromium.launch_persistent_context.return_value = mock_ctx
    mock_pw_cm = MagicMock()
    mock_pw_cm.__enter__.return_value = mock_pw_instance
    mock_pw_cm.__exit__.return_value = False
    return mock_pw_cm, mock_ctx, mock_page


# ── Ciclo 17: _click_apply_button ─────────────────────────────────────────────

class TestClickApplyButton:
    """_click_apply_button(page) detecta y clickea el botón Apply."""

    def test_returns_true_when_button_found(self):
        from agents.applicator import _click_apply_button
        mock_page = MagicMock()
        mock_loc = MagicMock()
        mock_loc.first.is_visible.return_value = True
        mock_page.locator.return_value = mock_loc
        result = _click_apply_button(mock_page)
        assert result is True

    def test_clicks_the_button_when_found(self):
        from agents.applicator import _click_apply_button
        mock_page = MagicMock()
        mock_loc = MagicMock()
        mock_loc.first.is_visible.return_value = True
        mock_page.locator.return_value = mock_loc
        _click_apply_button(mock_page)
        mock_loc.first.click.assert_called_once()

    def test_returns_false_when_no_button_found(self):
        from agents.applicator import _click_apply_button
        mock_page = MagicMock()
        mock_loc = MagicMock()
        mock_loc.first.is_visible.side_effect = Exception("timeout")
        mock_page.locator.return_value = mock_loc
        result = _click_apply_button(mock_page)
        assert result is False

    def test_does_not_raise_if_locator_fails(self):
        """Errores de Playwright no deben propagar — siempre retorna bool."""
        from agents.applicator import _click_apply_button
        mock_page = MagicMock()
        mock_page.locator.side_effect = Exception("page crashed")
        result = _click_apply_button(mock_page)
        assert isinstance(result, bool)


# ── Ciclo 18: _apply_web() v2 ─────────────────────────────────────────────────

class TestApplyWebCanalBV2:
    """_apply_web() / apply() Canal B envía Telegram y abre browser."""

    def test_dry_run_no_telegram(self):
        """dry_run=True no llama send_cv_ready_browser."""
        from agents.applicator import apply
        with patch("agents.applicator.send_cv_ready_browser") as mock_tg:
            apply(_JOB_B, "cv.pdf", dry_run=True)
        mock_tg.assert_not_called()

    def test_dry_run_result_canal_b(self):
        """dry_run=True retorna canal==B."""
        from agents.applicator import apply
        result = apply(_JOB_B, "cv.pdf", dry_run=True)
        assert result["canal"] == "B"

    def test_real_sends_telegram_notification(self):
        """Sin dry_run, send_cv_ready_browser se llama exactamente una vez."""
        from agents.applicator import apply
        mock_pw_cm, mock_ctx, mock_page = _mock_playwright_ctx()
        with (
            patch("agents.applicator.sync_playwright", return_value=mock_pw_cm),
            patch("agents.applicator.send_cv_ready_browser") as mock_tg,
        ):
            apply(_JOB_B, "cv.pdf", dry_run=False)
        mock_tg.assert_called_once()

    def test_notification_includes_job_cargo(self):
        """La notificación Telegram recibe el cargo correcto."""
        from agents.applicator import apply
        mock_pw_cm, mock_ctx, mock_page = _mock_playwright_ctx()
        with (
            patch("agents.applicator.sync_playwright", return_value=mock_pw_cm),
            patch("agents.applicator.send_cv_ready_browser") as mock_tg,
        ):
            apply(_JOB_B, "cv.pdf", dry_run=False)
        jobs_arg = mock_tg.call_args[0][0]
        assert jobs_arg[0]["cargo"] == _JOB_B["cargo"]

    def test_notification_includes_timeout_min(self):
        """La notificación Telegram incluye timeout_min derivado de HITL_TIMEOUT_S."""
        from agents.applicator import apply
        import config
        mock_pw_cm, mock_ctx, mock_page = _mock_playwright_ctx()
        with (
            patch("agents.applicator.sync_playwright", return_value=mock_pw_cm),
            patch("agents.applicator.send_cv_ready_browser") as mock_tg,
        ):
            apply(_JOB_B, "cv.pdf", dry_run=False)
        timeout_arg = mock_tg.call_args[1].get("timeout_min") or mock_tg.call_args[0][1]
        assert timeout_arg == config.HITL_TIMEOUT_S // 60

    def test_result_schema(self):
        """Resultado tiene las 4 claves requeridas y canal==B."""
        from agents.applicator import apply
        mock_pw_cm, mock_ctx, mock_page = _mock_playwright_ctx()
        with (
            patch("agents.applicator.sync_playwright", return_value=mock_pw_cm),
            patch("agents.applicator.send_cv_ready_browser"),
        ):
            result = apply(_JOB_B, "cv.pdf", dry_run=False)
        assert all(k in result for k in ("enviado", "canal", "url", "mensaje"))
        assert result["canal"] == "B"

    def test_telegram_failure_does_not_crash(self):
        """Si Telegram falla, _apply_web no lanza excepción."""
        from agents.applicator import apply
        mock_pw_cm, mock_ctx, mock_page = _mock_playwright_ctx()
        with (
            patch("agents.applicator.sync_playwright", return_value=mock_pw_cm),
            patch("agents.applicator.send_cv_ready_browser", side_effect=Exception("red")),
        ):
            result = apply(_JOB_B, "cv.pdf", dry_run=False)
        assert result["canal"] == "B"
```

- [ ] **Step 2: Verificar que los tests fallan (RED)**

```
python -m pytest tests/test_applicator_canal_b.py -v
```

Esperado: FAIL en todos — `_click_apply_button` no existe, `sync_playwright` no está a nivel módulo, `send_cv_ready_browser` no está importado.

---

## Task 2: Ciclo 17+18 GREEN — Implementar cambios en `applicator.py`

**Files:**
- Modify: `agents/applicator.py`

- [ ] **Step 3: Agregar imports de módulo para `sync_playwright` y `send_cv_ready_browser`**

Reemplaza el bloque de imports de `telegram_hitl` (líneas 32-37) con:

```python
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None  # Playwright opcional — dry_run funciona sin él

try:
    from agents.telegram_hitl import (
        send_cv_ready_email,
        send_cv_ready_browser,
        send_email_body,
    )
except ImportError:
    def send_cv_ready_email(jobs):  # noqa: E301
        pass
    def send_cv_ready_browser(jobs, timeout_min=5):  # noqa: E301
        pass
    def send_email_body(job, body_text):  # noqa: E301
        pass
```

- [ ] **Step 4: Agregar `_click_apply_button()` justo antes de `_apply_web()`**

Inserta esta función en la sección `# ── Canal B`:

```python
def _click_apply_button(page) -> bool:
    """
    Intenta hacer click en el botón Apply/Aplicar/Postularme de la página.
    Prueba selectores comunes en portales hispanohablantes y en inglés.
    Retorna True si encontró y clickeó el botón, False si no encontró ninguno.
    Nunca lanza excepción — errores de Playwright se silencian.
    """
    selectors = [
        "button:has-text('Aplicar')",
        "button:has-text('Apply')",
        "button:has-text('Postularme')",
        "button:has-text('Postulate')",
        "button:has-text('Aplicarme')",
        "a:has-text('Aplicar')",
        "a:has-text('Apply')",
        "button[class*='apply']",
        "a[class*='apply']",
        ".apply-button",
        "#apply-button",
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=2_000):
                _human_pause(0.5, 1.0)
                loc.click()
                print(f"  [Applicator-B] Botón clickeado: {sel}")
                return True
        except Exception:
            continue
    print("  [Applicator-B] No se encontró botón Apply — Lorena navega manualmente.")
    return False
```

- [ ] **Step 5: Reemplazar `_apply_web()` completo**

```python
def _apply_web(job: dict, pdf_path: str) -> dict:
    """
    Abre el portal de empleo en browser headful, intenta clickear Apply
    y notifica a Lorena por Telegram para que complete el formulario.

    Lorena tiene HITL_TIMEOUT_S segundos para completar y cerrar el browser.
    Nunca hace submit automático.
    """
    url     = job.get("url", "")
    cargo   = job.get("cargo", "")
    empresa = job.get("empresa", "")
    timeout_min = config.HITL_TIMEOUT_S // 60

    print(f"  [Applicator-B] Abriendo portal: {cargo} @ {empresa}")
    print(f"  URL: {url}")
    print(f"  CV para subir: {pdf_path}")

    with sync_playwright() as p:
        os.makedirs(config.PLAYWRIGHT_USER_DATA_DIR, exist_ok=True)
        ctx = p.chromium.launch_persistent_context(
            config.PLAYWRIGHT_USER_DATA_DIR,
            headless=False,
            slow_mo=200,
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page() if not ctx.pages else ctx.pages[0]
        page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        _human_pause(1.0, 2.0)

        # Intentar click automático en Apply
        clicked = _click_apply_button(page)

        # Notificación Telegram HITL
        try:
            send_cv_ready_browser([{**job}], timeout_min=timeout_min)
        except Exception as e:
            print(f"  [Applicator-B] Telegram no enviado: {e}")

        if clicked:
            msg = f"Botón Apply clickeado. Completa el formulario en {timeout_min} min y cierra el browser."
        else:
            msg = f"Browser abierto. Navega a Apply manualmente, completa en {timeout_min} min y cierra."

        print(f"  [Applicator-B] {msg}")
        print(f"  CV disponible en: {pdf_path}")

        try:
            page.wait_for_event("close", timeout=config.HITL_TIMEOUT_S * 1_000)
        except Exception:
            pass
        finally:
            try:
                ctx.close()
            except Exception:
                pass

    return {
        "enviado": False,
        "canal":   "B",
        "url":     url,
        "mensaje": f"{msg} | CV: {os.path.basename(pdf_path)}",
    }
```

- [ ] **Step 6: Eliminar la import local de `sync_playwright` que quedó dentro de `_apply_linkedin()`**

En `_apply_linkedin()` (línea ~102) hay:
```python
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
```
Reemplazar por:
```python
from playwright.sync_api import TimeoutError as PwTimeout
```
(`sync_playwright` ya está importado a nivel módulo.)

- [ ] **Step 7: Verificar que los tests pasan (GREEN)**

```
python -m pytest tests/test_applicator_canal_b.py -v
```

Esperado: todos PASS.

- [ ] **Step 8: Verificar suite completa sin regresiones**

```
python -m pytest -v
```

Esperado: 158 passed (147 anteriores + 11 nuevos).

- [ ] **Step 9: Commit**

```bash
git add agents/applicator.py tests/test_applicator_canal_b.py
git commit -m "feat: Canal B v2 — auto-click Apply + Telegram HITL notification (ciclos 17-18)"
```

---

## Task 3: Smoke test Nivel 3 — Canal B real

**Files:**
- Create: `_smoke_canal_b.py`

- [ ] **Step 10: Crear el smoke test**

```python
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from agents.applicator import apply

TEST_JOB = {
    "cargo":    "Trade Marketing Specialist",
    "empresa":  "Grupo Nutresa",
    "url":      "https://www.computrabajo.com.co/grupo-nutresa/oferta-de-trabajo-de-trade-marketing-specialist",
    "modalidad": "Presencial",
    "ubicacion": "Bogotá",
    "rama":     "B",
    "score":    86,
}

PDF_PATH = os.path.join(config.OUTPUT_DIR, "Lorena Ruiz - Paid Media Manager - Rappi.pdf")
if not os.path.exists(PDF_PATH):
    import glob
    pdfs = glob.glob(os.path.join(config.OUTPUT_DIR, "*.pdf"))
    PDF_PATH = pdfs[0] if pdfs else "cv_prueba.pdf"

print("=" * 55)
print("SMOKE TEST — CANAL B (real, sin dry_run)")
print("=" * 55)
print(f"Cargo:   {TEST_JOB['cargo']}")
print(f"Empresa: {TEST_JOB['empresa']}")
print(f"URL:     {TEST_JOB['url']}")
print(f"PDF:     {os.path.basename(PDF_PATH)}")
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
```

- [ ] **Step 11: Correr el smoke test real**

```
python _smoke_canal_b.py
```

Verificar las 4 condiciones del checklist impreso al final.

- [ ] **Step 12: Commit final si smoke test aprobado**

```bash
git add _smoke_canal_b.py
git commit -m "test: smoke test Nivel 3 Canal B aprobado"
```

---

## Self-Review

**Spec coverage:**
- ✅ Auto-click Apply/Aplicar — `_click_apply_button()` Task 2
- ✅ Notificación Telegram con cargo, empresa, score, timeout — `send_cv_ready_browser()` Task 2
- ✅ Browser permanece abierto para Lorena — `wait_for_event("close")` Task 2
- ✅ No auto-submit nunca — solo click en Apply, nunca en Submit
- ✅ CV PDF path visible en consola y en mensaje resultado — Task 2
- ✅ `HITL_ENABLED` / `HITL_TIMEOUT_S` de config — timeout_min derivado de config Task 2
- ✅ TDD ciclos 17-18 con tests aislados — Tasks 1-2
- ✅ Smoke test Nivel 3 — Task 3

**Placeholder scan:** ninguno.

**Type consistency:** `_click_apply_button(page) -> bool` usada en `_apply_web()` ✅. `send_cv_ready_browser(jobs: list[dict], timeout_min: int)` ya definida en `telegram_hitl.py` ✅.
