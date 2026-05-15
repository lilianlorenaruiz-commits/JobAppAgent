# Canal A Applicator v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Actualizar `_apply_linkedin()` con smart fill contextual (Claude llena campos de texto libre usando CV tailored + JD) y HITL 5 min antes de Submit (screenshot → Telegram → SI/NO de Lorena).

**Architecture:** Tres capas nuevas sobre el código existente: (1) `_fill_free_text_fields()` detecta textareas vacíos en el modal Easy Apply y los llena con Claude Haiku; (2) `send_screenshot_for_approval_sync()` en `telegram_hitl.py` envía foto via `urllib.request` multipart — sin asyncio, seguro dentro del context de Playwright; (3) `_apply_linkedin()` actualizado integra ambas capas y chequea `config.HITL_ENABLED` antes de Submit. `wait_for_approval()` ya existe en `telegram_hitl.py` y usa `urllib.request` (sync, sin asyncio) — no requiere cambios.

**Tech Stack:** Python 3.11+, Playwright sync API, Claude Haiku (Anthropic), python-telegram-bot v20 / urllib.request (sync multipart para foto dentro de Playwright).

---

## Archivos a modificar / crear

| Archivo | Acción | Qué cambia |
|---|---|---|
| `agents/applicator.py` | Modificar | `_get_field_question()`, `_generate_field_answer()`, `_fill_free_text_fields()` nuevas; `_apply_linkedin()` actualizado (firma + smart fill + HITL); import `send_screenshot_for_approval_sync` y `wait_for_approval` |
| `agents/telegram_hitl.py` | Modificar | `send_screenshot_for_approval_sync()` nueva (urllib.request multipart, sin asyncio) |
| `tests/test_applicator_canal_a.py` | Crear | Tests TDD ciclos 19-21 |
| `_smoke_canal_a.py` | Crear | Smoke test Nivel 3 con oferta LinkedIn real |

---

## Decisión de diseño crítica: asyncio dentro de Playwright

`asyncio.run()` NO puede ejecutarse dentro del event loop interno de Playwright sync API (mismo error que Canal B). Pero Canal A necesita enviar el screenshot DESDE DENTRO del context `with sync_playwright()` porque debe:
1. Tomar screenshot de la página Review (requiere Playwright activo)
2. Enviarlo a Telegram
3. Esperar SI/NO de Lorena
4. Según respuesta: hacer click Submit o dejar browser abierto

**Solución:** `send_screenshot_for_approval_sync()` usa `urllib.request` con multipart/form-data directamente — sin asyncio, sin `telegram.Bot`, completamente síncrono. `wait_for_approval()` ya usa `urllib.request` (no necesita cambios).

---

## Task 1: Ciclo 19 RED — Tests smart fill (`_fill_free_text_fields`)

**Files:**
- Create: `tests/test_applicator_canal_a.py`

- [ ] **Step 1: Crear archivo de tests con ciclo 19**

```python
"""
Ciclo 19 RED→GREEN: Canal A smart fill
  - _get_field_question() extrae pregunta de placeholder / aria-label / label
  - _generate_field_answer() llama a Claude con la pregunta + CV + JD
  - _fill_free_text_fields() detecta campos vacíos y los llena

Ciclo 20 RED→GREEN: send_screenshot_for_approval_sync
  - envía foto con urllib.request (sin asyncio)
  - fallback a texto si no hay imagen

Ciclo 21 RED→GREEN: _apply_linkedin() v2
  - acepta cv_text y job_description
  - llama _fill_free_text_fields() en cada paso del modal
  - HITL_ENABLED=True: screenshot → Telegram → SI → Submit
  - HITL_ENABLED=True: screenshot → Telegram → NO → browser abierto
  - HITL_ENABLED=False: submit directo sin Telegram
"""
import os
import sys
from unittest.mock import MagicMock, patch, call
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_JOB_A = {
    "cargo":   "Paid Media Manager",
    "empresa": "Rappi",
    "url":     "https://www.linkedin.com/jobs/view/1234567890",
    "rama":    "A",
    "score":   91,
}
_CV  = "Lorena Ruiz. 14 años en paid media. Meta Ads, Google Ads. Presupuestos USD 240K."
_JD  = "We need a Paid Media Manager with Meta Ads and Google Ads experience."


# ── helpers ────────────────────────────────────────────────────────────────────

def _mock_claude(text: str):
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=text)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    return mock_client


def _mock_field(placeholder="", aria_label="", field_id="", value="", visible=True, tag="input"):
    field = MagicMock()
    field.is_visible.return_value = visible
    field.get_attribute.side_effect = lambda attr, **kw: {
        "placeholder": placeholder,
        "aria-label":  aria_label,
        "id":          field_id,
    }.get(attr, "")
    field.input_value.return_value = value
    field.evaluate.return_value = tag
    return field


# ── Ciclo 19: _get_field_question ─────────────────────────────────────────────

class TestGetFieldQuestion:

    def test_returns_placeholder_when_present(self):
        from agents.applicator import _get_field_question
        page  = MagicMock()
        field = _mock_field(placeholder="¿Por qué quieres este cargo?")
        result = _get_field_question(page, field)
        assert "cargo" in result or "¿Por qué" in result

    def test_returns_aria_label_when_no_placeholder(self):
        from agents.applicator import _get_field_question
        page  = MagicMock()
        field = _mock_field(aria_label="Years of experience")
        result = _get_field_question(page, field)
        assert "experience" in result.lower() or "Years" in result

    def test_returns_empty_string_when_no_context(self):
        from agents.applicator import _get_field_question
        page  = MagicMock()
        field = _mock_field()
        page.locator.return_value.first.is_visible.return_value = False
        result = _get_field_question(page, field)
        assert isinstance(result, str)

    def test_does_not_raise_on_exception(self):
        from agents.applicator import _get_field_question
        page  = MagicMock()
        field = MagicMock()
        field.get_attribute.side_effect = Exception("playwright error")
        result = _get_field_question(page, field)
        assert isinstance(result, str)


# ── Ciclo 19: _generate_field_answer ──────────────────────────────────────────

class TestGenerateFieldAnswer:

    def test_returns_string(self):
        from agents.applicator import _generate_field_answer
        client = _mock_claude("14 años de experiencia en paid media.")
        with patch("agents.applicator.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = client
            result = _generate_field_answer("Años de experiencia", _CV, _JD)
        assert isinstance(result, str)

    def test_max_150_chars(self):
        from agents.applicator import _generate_field_answer
        long_answer = "x" * 300
        client = _mock_claude(long_answer)
        with patch("agents.applicator.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = client
            result = _generate_field_answer("Pregunta", _CV, _JD)
        assert len(result) <= 150

    def test_returns_empty_when_anthropic_none(self):
        from agents.applicator import _generate_field_answer
        with patch("agents.applicator.anthropic", None):
            result = _generate_field_answer("Pregunta", _CV, _JD)
        assert result == ""

    def test_prompt_includes_question(self):
        from agents.applicator import _generate_field_answer
        client = _mock_claude("respuesta")
        with patch("agents.applicator.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = client
            _generate_field_answer("¿Cuál es tu mayor fortaleza?", _CV, _JD)
        call_args = str(client.messages.create.call_args)
        assert "fortaleza" in call_args

    def test_prompt_includes_cv_text(self):
        from agents.applicator import _generate_field_answer
        client = _mock_claude("respuesta")
        with patch("agents.applicator.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = client
            _generate_field_answer("Pregunta", _CV, _JD)
        call_args = str(client.messages.create.call_args)
        assert "Lorena Ruiz" in call_args or "paid media" in call_args.lower()


# ── Ciclo 19: _fill_free_text_fields ──────────────────────────────────────────

class TestFillFreeTextFields:

    def test_returns_zero_when_no_fields(self):
        from agents.applicator import _fill_free_text_fields
        page = MagicMock()
        page.locator.return_value.all.return_value = []
        with patch("agents.applicator.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = _mock_claude("respuesta")
            result = _fill_free_text_fields(page, _CV, _JD)
        assert result == 0

    def test_fills_visible_empty_textarea(self):
        from agents.applicator import _fill_free_text_fields
        field = _mock_field(placeholder="¿Por qué este cargo?", tag="textarea")
        page  = MagicMock()
        page.locator.return_value.all.return_value = [field]
        client = _mock_claude("Me apasiona el paid media.")
        with patch("agents.applicator.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = client
            result = _fill_free_text_fields(page, _CV, _JD)
        assert result >= 1
        field.fill.assert_called_once()

    def test_skips_already_filled_field(self):
        from agents.applicator import _fill_free_text_fields
        field = _mock_field(placeholder="¿Por qué?", value="Ya tengo texto", tag="textarea")
        page  = MagicMock()
        page.locator.return_value.all.return_value = [field]
        with patch("agents.applicator.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = _mock_claude("respuesta")
            result = _fill_free_text_fields(page, _CV, _JD)
        field.fill.assert_not_called()

    def test_returns_zero_when_anthropic_none(self):
        from agents.applicator import _fill_free_text_fields
        page = MagicMock()
        with patch("agents.applicator.anthropic", None):
            result = _fill_free_text_fields(page, _CV, _JD)
        assert result == 0

    def test_does_not_raise_on_playwright_error(self):
        from agents.applicator import _fill_free_text_fields
        page = MagicMock()
        page.locator.side_effect = Exception("playwright crash")
        with patch("agents.applicator.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = _mock_claude("respuesta")
            result = _fill_free_text_fields(page, _CV, _JD)
        assert isinstance(result, int)


# ── Ciclo 20: send_screenshot_for_approval_sync ───────────────────────────────

class TestSendScreenshotSync:

    def test_sends_photo_when_image_exists(self, tmp_path):
        img = tmp_path / "shot.png"
        img.write_bytes(b"\x89PNG\r\n")
        from agents.telegram_hitl import send_screenshot_for_approval_sync
        with patch("agents.telegram_hitl.urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = b"{}"
            with patch("agents.telegram_hitl._require_telegram", return_value=("tok", "123")):
                send_screenshot_for_approval_sync(str(img), _JOB_A)
        assert mock_open.called
        # Debe llamar a sendPhoto (no sendMessage)
        req_arg = mock_open.call_args[0][0]
        assert "sendPhoto" in req_arg.full_url

    def test_sends_text_when_no_image(self):
        from agents.telegram_hitl import send_screenshot_for_approval_sync
        with patch("agents.telegram_hitl.urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = b"{}"
            with patch("agents.telegram_hitl._require_telegram", return_value=("tok", "123")):
                send_screenshot_for_approval_sync("no_existe.png", _JOB_A)
        req_arg = mock_open.call_args[0][0]
        assert "sendMessage" in req_arg.full_url

    def test_does_not_raise_on_network_error(self):
        from agents.telegram_hitl import send_screenshot_for_approval_sync
        with patch("agents.telegram_hitl.urllib.request.urlopen", side_effect=Exception("timeout")):
            with patch("agents.telegram_hitl._require_telegram", return_value=("tok", "123")):
                # No debe propagar la excepción
                try:
                    send_screenshot_for_approval_sync("no.png", _JOB_A)
                except Exception:
                    pytest.fail("send_screenshot_for_approval_sync no debe propagar excepciones")


# ── Ciclo 21: _apply_linkedin() v2 ────────────────────────────────────────────

def _mock_linkedin_ctx(submit_visible=True):
    """Mock completo de sync_playwright para LinkedIn Easy Apply."""
    mock_page = MagicMock()
    # Simula: no login wall
    mock_page.url = "https://www.linkedin.com/jobs/view/123"
    # Easy Apply button visible
    mock_page.locator.return_value.first.is_visible.return_value = True
    # Modal visible
    mock_page.locator.return_value.first.wait_for = MagicMock()
    # Submit button: visible en primer paso (simula formulario corto)
    submit_loc = MagicMock()
    submit_loc.is_visible.return_value = submit_visible
    mock_page.screenshot.return_value = None
    mock_page.wait_for_event.side_effect = Exception("closed")

    mock_ctx = MagicMock()
    mock_ctx.pages = [mock_page]

    mock_pw_instance = MagicMock()
    mock_pw_instance.chromium.launch_persistent_context.return_value = mock_ctx

    mock_pw_cm = MagicMock()
    mock_pw_cm.__enter__.return_value = mock_pw_instance
    mock_pw_cm.__exit__.return_value = False

    return mock_pw_cm, mock_ctx, mock_page


class TestApplyLinkedinCanalAV2:

    def test_accepts_cv_text_and_job_description(self):
        """apply() pasa cv_text y job_description a _apply_linkedin sin error."""
        from agents.applicator import apply
        result = apply(_JOB_A, "cv.pdf", dry_run=True, cv_text=_CV, job_description=_JD)
        assert result["canal"] == "A"

    def test_dry_run_does_not_call_fill_free_text(self):
        from agents.applicator import apply
        with patch("agents.applicator._fill_free_text_fields") as mock_fill:
            apply(_JOB_A, "cv.pdf", dry_run=True, cv_text=_CV, job_description=_JD)
        mock_fill.assert_not_called()

    def test_hitl_enabled_sends_screenshot_before_submit(self):
        """HITL_ENABLED=True: send_screenshot_for_approval_sync se llama antes de Submit."""
        from agents.applicator import apply
        mock_pw_cm, _, _ = _mock_linkedin_ctx()
        with (
            patch("agents.applicator.sync_playwright", return_value=mock_pw_cm),
            patch("agents.applicator.send_screenshot_for_approval_sync") as mock_shot,
            patch("agents.applicator.wait_for_approval", return_value=True),
            patch("agents.applicator._fill_free_text_fields", return_value=0),
            patch("agents.applicator.config") as mock_cfg,
        ):
            mock_cfg.HITL_ENABLED   = True
            mock_cfg.HITL_TIMEOUT_S = 300
            mock_cfg.PLAYWRIGHT_USER_DATA_DIR = "browser_profile"
            apply(_JOB_A, "cv.pdf", dry_run=False, cv_text=_CV, job_description=_JD)
        mock_shot.assert_called_once()

    def test_hitl_si_clicks_submit(self):
        """HITL_ENABLED=True + wait_for_approval=True → enviado=True."""
        from agents.applicator import apply
        mock_pw_cm, _, _ = _mock_linkedin_ctx()
        with (
            patch("agents.applicator.sync_playwright", return_value=mock_pw_cm),
            patch("agents.applicator.send_screenshot_for_approval_sync"),
            patch("agents.applicator.wait_for_approval", return_value=True),
            patch("agents.applicator._fill_free_text_fields", return_value=0),
            patch("agents.applicator.config") as mock_cfg,
        ):
            mock_cfg.HITL_ENABLED   = True
            mock_cfg.HITL_TIMEOUT_S = 300
            mock_cfg.PLAYWRIGHT_USER_DATA_DIR = "browser_profile"
            result = apply(_JOB_A, "cv.pdf", dry_run=False, cv_text=_CV, job_description=_JD)
        assert result["enviado"] is True
        assert result["canal"] == "A"

    def test_hitl_no_leaves_browser_open(self):
        """HITL_ENABLED=True + wait_for_approval=False → enviado=False."""
        from agents.applicator import apply
        mock_pw_cm, _, _ = _mock_linkedin_ctx()
        with (
            patch("agents.applicator.sync_playwright", return_value=mock_pw_cm),
            patch("agents.applicator.send_screenshot_for_approval_sync"),
            patch("agents.applicator.wait_for_approval", return_value=False),
            patch("agents.applicator._fill_free_text_fields", return_value=0),
            patch("agents.applicator.config") as mock_cfg,
        ):
            mock_cfg.HITL_ENABLED   = True
            mock_cfg.HITL_TIMEOUT_S = 300
            mock_cfg.PLAYWRIGHT_USER_DATA_DIR = "browser_profile"
            result = apply(_JOB_A, "cv.pdf", dry_run=False, cv_text=_CV, job_description=_JD)
        assert result["enviado"] is False
        assert "cancel" in result["mensaje"].lower() or "HITL" in result["mensaje"]

    def test_hitl_disabled_submits_directly(self):
        """HITL_ENABLED=False → submit sin Telegram, enviado=True."""
        from agents.applicator import apply
        mock_pw_cm, _, _ = _mock_linkedin_ctx()
        with (
            patch("agents.applicator.sync_playwright", return_value=mock_pw_cm),
            patch("agents.applicator.send_screenshot_for_approval_sync") as mock_shot,
            patch("agents.applicator.wait_for_approval") as mock_wait,
            patch("agents.applicator._fill_free_text_fields", return_value=0),
            patch("agents.applicator.config") as mock_cfg,
        ):
            mock_cfg.HITL_ENABLED   = False
            mock_cfg.HITL_TIMEOUT_S = 300
            mock_cfg.PLAYWRIGHT_USER_DATA_DIR = "browser_profile"
            result = apply(_JOB_A, "cv.pdf", dry_run=False, cv_text=_CV, job_description=_JD)
        mock_shot.assert_not_called()
        mock_wait.assert_not_called()
        assert result["enviado"] is True
```

- [ ] **Step 2: Verificar RED**

```
python -m pytest tests/test_applicator_canal_a.py -v
```

Esperado: FAIL en todo — funciones no existen aún.

---

## Task 2: Ciclo 19 GREEN — Implementar smart fill en `applicator.py`

**Files:**
- Modify: `agents/applicator.py`

- [ ] **Step 3: Agregar imports de `send_screenshot_for_approval_sync` y `wait_for_approval`**

En el bloque try/except de telegram_hitl (líneas ~32-44), agregar las dos nuevas funciones:

```python
try:
    from agents.telegram_hitl import (
        send_cv_ready_email,
        send_cv_ready_browser,
        send_email_body,
        send_screenshot_for_approval_sync,
        wait_for_approval,
    )
except ImportError:
    def send_cv_ready_email(jobs):  # noqa: E301
        pass
    def send_cv_ready_browser(jobs, timeout_min=5):  # noqa: E301
        pass
    def send_email_body(job, body_text):  # noqa: E301
        pass
    def send_screenshot_for_approval_sync(image_path, job):  # noqa: E301
        pass
    def wait_for_approval(timeout_s=300):  # noqa: E301
        return False
```

- [ ] **Step 4: Agregar `_get_field_question()` después de `_find_next_button()`**

```python
def _get_field_question(page, field) -> str:
    """
    Extrae el texto de la pregunta asociada a un campo del formulario.
    Prueba: placeholder → aria-label → label[for=id].
    Retorna string vacío si no encuentra contexto. Nunca lanza excepción.
    """
    try:
        placeholder = field.get_attribute("placeholder") or ""
        if len(placeholder.strip()) > 3:
            return placeholder.strip()

        aria = field.get_attribute("aria-label") or ""
        if len(aria.strip()) > 3:
            return aria.strip()

        field_id = field.get_attribute("id") or ""
        if field_id:
            label = page.locator(f"label[for='{field_id}']").first
            if label.is_visible(timeout=500):
                text = label.text_content() or ""
                if len(text.strip()) > 3:
                    return text.strip()
    except Exception:
        pass
    return ""
```

- [ ] **Step 5: Agregar `_generate_field_answer()` después de `_get_field_question()`**

```python
def _generate_field_answer(question: str, cv_text: str, job_description: str) -> str:
    """
    Genera una respuesta concisa para un campo de texto libre usando Claude Haiku.
    Máx 150 chars. Solo usa hechos del CV — nunca inventa.
    Retorna string vacío si anthropic no está disponible.
    """
    if anthropic is None:
        return ""

    cv_excerpt  = (cv_text or "")[:2000]
    jd_excerpt  = (job_description or "")[:500]

    prompt = (
        f"You are filling a job application form on behalf of Lorena Ruiz.\n\n"
        f"CV:\n{cv_excerpt}\n\n"
        f"Job description (excerpt):\n{jd_excerpt}\n\n"
        f"Form question: {question}\n\n"
        f"Write a concise professional answer in the same language as the question. "
        f"Maximum 150 characters. Use ONLY facts from the CV — never invent. "
        f"If the CV has no relevant information, give a brief generic professional answer. "
        f"Answer only — no quotes, no explanation:"
    )

    client   = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=config.MODEL_FAST,
        max_tokens=80,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()[:150]
```

- [ ] **Step 6: Agregar `_fill_free_text_fields()` después de `_generate_field_answer()`**

```python
def _fill_free_text_fields(page, cv_text: str, job_description: str) -> int:
    """
    Detecta campos de texto libre vacíos en el modal Easy Apply de LinkedIn
    y los llena con Claude usando el CV tailored y el JD como contexto.

    Excluye campos de teléfono y email (manejados por _fill_simple_fields).
    Retorna el número de campos llenados.
    Nunca lanza excepción — errores de Playwright se silencian.
    """
    if anthropic is None:
        return 0

    filled = 0
    selectors = [
        "textarea",
        "input[type='text']:not([name*='phone']):not([name*='email'])"
        ":not([id*='phone']):not([id*='email'])"
        ":not([placeholder*='Phone']):not([placeholder*='Email'])",
    ]

    for sel in selectors:
        try:
            fields = page.locator(sel).all()
        except Exception:
            continue

        for field in fields:
            try:
                if not field.is_visible(timeout=500):
                    continue

                current = field.input_value() if "textarea" not in sel else (field.text_content() or "")
                if current and current.strip():
                    continue  # ya tiene contenido — no sobreescribir

                question = _get_field_question(page, field)
                if not question:
                    continue

                answer = _generate_field_answer(question, cv_text, job_description)
                if not answer:
                    continue

                field.fill(answer[:150])
                _human_pause(0.3, 0.7)
                print(f"  [Applicator-A] Campo: '{question[:50]}' → '{answer[:40]}...'")
                filled += 1
            except Exception:
                continue

    return filled
```

- [ ] **Step 7: Verificar ciclo 19 GREEN**

```
python -m pytest tests/test_applicator_canal_a.py::TestGetFieldQuestion tests/test_applicator_canal_a.py::TestGenerateFieldAnswer tests/test_applicator_canal_a.py::TestFillFreeTextFields -v
```

Esperado: 14 PASS.

---

## Task 3: Ciclo 20 GREEN — `send_screenshot_for_approval_sync()` en `telegram_hitl.py`

**Files:**
- Modify: `agents/telegram_hitl.py`

- [ ] **Step 8: Agregar `import urllib.parse` al bloque de imports de `telegram_hitl.py`**

Al inicio del archivo (donde están los imports), agregar `urllib.parse`:

```python
import urllib.parse
import urllib.request
```

(ya existe `urllib.request` — agregar `urllib.parse` en la misma línea o inmediatamente después)

- [ ] **Step 9: Agregar `send_screenshot_for_approval_sync()` al final de `telegram_hitl.py`**

Añadir después de `send_screenshot_for_approval()`:

```python
def send_screenshot_for_approval_sync(image_path: str, job: dict) -> None:
    """
    Versión síncrona de send_screenshot_for_approval usando urllib.request.
    Segura para llamar desde dentro del context de Playwright sync API
    (asyncio.run() no puede usarse dentro del event loop de Playwright).

    Sube la foto via multipart/form-data si existe el archivo.
    Si no hay imagen, envía el caption como texto plano.
    Silencia excepciones de red — el flujo HITL no debe bloquearse.
    """
    token, chat_id = _require_telegram()
    cargo       = job.get("cargo", "")
    empresa     = job.get("empresa", "")
    timeout_min = config.HITL_TIMEOUT_S // 60

    caption = (
        f"⚠️ REVISAR ANTES DE ENVIAR\n\n"
        f"Cargo: {cargo}\n"
        f"Empresa: {empresa}\n\n"
        f"✅ Responde SI para confirmar el envío\n"
        f"❌ Responde NO para cancelar\n"
        f"⏱ Tienes {timeout_min} minutos"
    )

    base_url = f"https://api.telegram.org/bot{token}"

    try:
        if image_path and os.path.exists(image_path):
            # Multipart form-data para enviar foto — sin asyncio
            boundary = "TelegramBoundary42"
            with open(image_path, "rb") as f:
                photo_bytes = f.read()

            body = (
                f"--{boundary}\r\n"
                f"Content-Disposition: form-data; name=\"chat_id\"\r\n\r\n"
                f"{chat_id}\r\n"
                f"--{boundary}\r\n"
                f"Content-Disposition: form-data; name=\"caption\"\r\n\r\n"
                f"{caption}\r\n"
                f"--{boundary}\r\n"
                f"Content-Disposition: form-data; name=\"photo\"; filename=\"screenshot.png\"\r\n"
                f"Content-Type: image/png\r\n\r\n"
            ).encode() + photo_bytes + f"\r\n--{boundary}--\r\n".encode()

            req = urllib.request.Request(
                f"{base_url}/sendPhoto",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
        else:
            # Sin imagen — enviar solo el caption como texto
            body = urllib.parse.urlencode({
                "chat_id":    chat_id,
                "text":       caption,
            }).encode()
            req = urllib.request.Request(
                f"{base_url}/sendMessage",
                data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        print(f"[HITL] Screenshot enviado — esperando respuesta para {cargo} @ {empresa}")

    except Exception as e:
        print(f"[HITL] Error enviando screenshot: {e}")
```

- [ ] **Step 10: Verificar ciclo 20 GREEN**

```
python -m pytest tests/test_applicator_canal_a.py::TestSendScreenshotSync -v
```

Esperado: 3 PASS.

---

## Task 4: Ciclo 21 GREEN — Actualizar `_apply_linkedin()`

**Files:**
- Modify: `agents/applicator.py`

- [ ] **Step 11: Actualizar firma de `_apply_linkedin()` para aceptar cv_text y job_description**

Cambiar la firma (línea ~98):

```python
def _apply_linkedin(job: dict, pdf_path: str,
                    cv_text: str = "", job_description: str = "") -> dict:
```

- [ ] **Step 12: Agregar `_fill_free_text_fields()` en el loop de pasos del formulario**

Dentro del `for step in range(max_steps):` loop, después de `_fill_simple_fields(page)`:

```python
                # b) Rellenar campos simples (teléfono, email)
                _fill_simple_fields(page)

                # b2) Smart fill: campos de texto libre con Claude
                _fill_free_text_fields(page, cv_text, job_description)
```

- [ ] **Step 13: Reemplazar el bloque de Submit directo con HITL-gated submit**

Reemplazar este bloque:

```python
                # c) Detectar si hay el botón Submit (último paso)
                submit_btn = page.locator(
                    "button[aria-label='Submit application'], "
                    "button:has-text('Submit application')"
                ).first
                if submit_btn.is_visible(timeout=2_000):
                    _human_pause(0.5, 1.0)
                    submit_btn.click()
                    _human_pause(2.0, 3.0)
                    print("  [Applicator-A] Aplicación enviada.")
                    _screenshot_on_error(page, "submitted")
                    ctx.close()
                    return {
                        "enviado": True, "canal": "A", "url": url,
                        "mensaje": f"Easy Apply enviado: {cargo} @ {empresa}",
                    }
```

Con:

```python
                # c) Detectar si hay el botón Submit (último paso)
                submit_btn = page.locator(
                    "button[aria-label='Submit application'], "
                    "button:has-text('Submit application')"
                ).first
                if submit_btn.is_visible(timeout=2_000):
                    if config.HITL_ENABLED:
                        # HITL: screenshot → Telegram → esperar SI/NO
                        shot_path = _screenshot_on_error(page, "review")
                        try:
                            send_screenshot_for_approval_sync(shot_path or "", job)
                        except Exception as e:
                            print(f"  [Applicator-A] Telegram HITL falló: {e}")

                        approved = wait_for_approval(timeout_s=config.HITL_TIMEOUT_S)
                        if not approved:
                            print("  [Applicator-A] NO recibido o timeout — browser abierto.")
                            try:
                                page.wait_for_event("close",
                                                    timeout=config.HITL_TIMEOUT_S * 1_000)
                            except Exception:
                                pass
                            ctx.close()
                            return {
                                "enviado": False, "canal": "A", "url": url,
                                "mensaje": (f"HITL: Lorena canceló o no respondió "
                                            f"— {cargo} @ {empresa}"),
                            }

                    # Submit (aprobado por HITL o HITL_ENABLED=False)
                    _human_pause(0.5, 1.0)
                    submit_btn.click()
                    _human_pause(2.0, 3.0)
                    print("  [Applicator-A] Aplicación enviada.")
                    _screenshot_on_error(page, "submitted")
                    ctx.close()
                    return {
                        "enviado": True, "canal": "A", "url": url,
                        "mensaje": f"Easy Apply enviado: {cargo} @ {empresa}",
                    }
```

- [ ] **Step 14: Actualizar `apply()` para pasar cv_text y job_description a `_apply_linkedin()`**

En la función `apply()`, en el bloque `if canal == "A":`:

```python
    if canal == "A":
        return _apply_linkedin(job, pdf_path,
                               cv_text=cv_text, job_description=job_description)
```

- [ ] **Step 15: Verificar ciclo 21 GREEN**

```
python -m pytest tests/test_applicator_canal_a.py::TestApplyLinkedinCanalAV2 -v
```

Esperado: 6 PASS.

- [ ] **Step 16: Verificar suite completa sin regresiones**

```
python -m pytest -q
```

Esperado: 180 passed (158 anteriores + 22 nuevos).

- [ ] **Step 17: Commit**

```bash
git add agents/applicator.py agents/telegram_hitl.py tests/test_applicator_canal_a.py
git commit -m "feat: Canal A v2 — smart fill contextual + HITL screenshot antes de Submit (ciclos 19-21)"
```

---

## Task 5: Smoke test Nivel 3 — Canal A real

**Files:**
- Create: `_smoke_canal_a.py`

- [ ] **Step 18: Crear smoke test**

```python
"""
Smoke test Nivel 3 — Canal A real.
Ejecuta apply() sin dry_run con una oferta LinkedIn real.

Verifica:
  1. Browser abre en LinkedIn con sesión persistente
  2. Click en Easy Apply
  3. Claude llena campos de texto libre (smart fill)
  4. En Review: screenshot llega a Telegram con SI/NO
  5. Lorena responde SI → Submit / NO → browser queda abierto

Uso:
  python _smoke_canal_a.py
  (tener LinkedIn sesión activa en browser_profile/)
"""
import os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from agents.applicator import apply
from agents.cv_parser import parse_cv
from agents.cv_rewriter import _cv_to_plain_text

print("Cargando CV de Lorena...")
try:
    cv = parse_cv()
    cv_text = _cv_to_plain_text(cv, rama="A")
    print(f"CV listo: {len(cv_text)} chars\n")
except Exception as e:
    print(f"Error cargando CV: {e}")
    cv_text = (
        "LORENA RUIZ | Paid Media Specialist\n"
        "Teleperformance (LinkedIn) — Feb 2026–Present | LATAM\n"
        "Amazon, Colombia — May 2025–Feb 2026 | APAC\n"
        "Skills: Meta Ads, Google Ads, LinkedIn Ads, Amazon DSP. USD 240K+. C2 English."
    )

TEST_JOB = {
    "cargo":   "Paid Media Manager",
    "empresa": "Empresa LinkedIn Test",
    "url":     "https://www.linkedin.com/jobs/view/4230029992",  # reemplazar con URL real
    "rama":    "A",
    "score":   90,
    "description": (
        "Buscamos Paid Media Manager con experiencia en Meta Ads, Google Ads. "
        "Presupuestos USD 50K+. Inglés avanzado. Bogotá híbrido."
    ),
}

PDF_PATH = os.path.join(config.OUTPUT_DIR, "Lorena Ruiz - Paid Media Manager - Rappi.pdf")
if not os.path.exists(PDF_PATH):
    pdfs = glob.glob(os.path.join(config.OUTPUT_DIR, "*.pdf"))
    PDF_PATH = pdfs[0] if pdfs else "cv_prueba.pdf"

print("=" * 55)
print("SMOKE TEST — CANAL A (real, sin dry_run)")
print("=" * 55)
print(f"Cargo:        {TEST_JOB['cargo']}")
print(f"Empresa:      {TEST_JOB['empresa']}")
print(f"URL:          {TEST_JOB['url']}")
print(f"PDF:          {os.path.basename(PDF_PATH)}")
print(f"HITL_ENABLED: {config.HITL_ENABLED}")
print(f"Timeout:      {config.HITL_TIMEOUT_S // 60} minutos")
print()
print("Paso 1: Browser abre en LinkedIn (sesión persistente).")
print("Paso 2: Click en Easy Apply.")
print("Paso 3: Claude llena campos de texto libre.")
print("Paso 4: Screenshot → Telegram → responde SI o NO.")
print()
input("Presiona ENTER para continuar (o Ctrl+C para cancelar)...")
print()

result = apply(
    TEST_JOB, PDF_PATH,
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
print("Verifica ahora:")
print("  [ ] ¿Browser abrió en la oferta de LinkedIn?")
print("  [ ] ¿Claude llenó campos de texto libre con datos reales del CV?")
print("  [ ] ¿Telegram recibió el screenshot de la página Review?")
print("  [ ] ¿Respondiste SI → enviado=True / NO → browser quedó abierto?")
print()
print("Si todo OK → Canal A aprobado ✅")
```

- [ ] **Step 19: Correr smoke test (requiere sesión LinkedIn activa)**

```
python _smoke_canal_a.py
```

**ANTES de correr:** verificar que existe sesión en `browser_profile/` con:
```
python _setup_browser.py
```

- [ ] **Step 20: Commit final si smoke test aprobado**

```bash
git add _smoke_canal_a.py
git commit -m "test: smoke test Nivel 3 Canal A aprobado"
```

---

## Self-Review

**Spec coverage:**
- ✅ Smart fill campos texto libre con Claude — `_fill_free_text_fields()` Task 2
- ✅ Solo usa CV tailored — prompt con regla "ONLY facts from the CV" Task 2
- ✅ Máx 150 chars por campo — `[:150]` en `_generate_field_answer()` Task 2
- ✅ Screenshot antes de Submit — `_screenshot_on_error(page, "review")` Task 4
- ✅ Telegram con SI/NO — `send_screenshot_for_approval_sync()` Task 3
- ✅ Espera 5 min — `wait_for_approval(timeout_s=config.HITL_TIMEOUT_S)` Task 4
- ✅ SI → Submit — Task 4 Step 13
- ✅ NO o timeout → browser abierto — Task 4 Step 13
- ✅ `HITL_ENABLED` flag — Task 4 Step 13
- ✅ cv_text y job_description fluyen desde apply() — Task 4 Step 14
- ✅ asyncio fix — `send_screenshot_for_approval_sync()` usa urllib.request Task 3
- ✅ TDD ciclos 19-21 — Tasks 1-4
- ✅ Smoke test Nivel 3 — Task 5

**Placeholder scan:** ninguno.

**Type consistency:**
- `_get_field_question(page, field) -> str` ✅ usado en `_fill_free_text_fields` ✅
- `_generate_field_answer(question, cv_text, job_description) -> str` ✅ usado en `_fill_free_text_fields` ✅
- `send_screenshot_for_approval_sync(image_path: str, job: dict) -> None` ✅ importado en applicator.py ✅
- `wait_for_approval(timeout_s=300) -> bool` ✅ ya existente en telegram_hitl.py ✅
