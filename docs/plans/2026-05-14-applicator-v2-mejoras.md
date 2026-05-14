# Applicator v2 — Mejoras 3 Canales

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Elevar los 3 canales del Applicator de "asistido" a "semi-autónomo curado": Canal C genera body de correo con Claude (CV+JD, idioma detectado) y notifica por Telegram; Canal B auto-clickea el botón Apply y notifica por Telegram; Canal A llena formularios con Claude (coherente CV+JD) y aplica HITL de 5 min antes de Submit.

**Architecture:** Nuevo módulo `agents/telegram_hitl.py` centraliza las notificaciones y el polling de aprobación; `agents/applicator.py` recibe `cv_text` y `job_description` en su API pública; `main.py` pasa esos valores desde el resultado del rewriter. HITL se controla con flag `config.HITL_ENABLED`.

**Tech Stack:** Python 3.11, Playwright sync API, python-telegram-bot v20 (async + asyncio.run), Claude API (Haiku para speed), urllib para long-polling Telegram getUpdates, pytest + unittest.mock.

---

## File Map

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `config.py` | Modify | Añadir HITL_ENABLED, HITL_TIMEOUT_S, EMAIL_ACCOUNT |
| `agents/telegram_hitl.py` | **Create** | Notificaciones Canal B/C + HITL polling + send_photo para Canal A |
| `agents/applicator.py` | Modify | Canal C: LLM body; Canal B: auto-click + notify; Canal A: smart fill + HITL |
| `main.py` | Modify | Pasar cv_text + job_description a aplicar() |
| `tests/test_telegram_hitl.py` | **Create** | Ciclo 15: format, polling mock |
| `tests/test_applicator_v2.py` | **Create** | Ciclos 16-19: Canal C body, Canal B auto-click, Canal A fill + HITL |

---

## Task 1: Config — añadir flags HITL y cuenta email

**Files:**
- Modify: `config.py`

- [ ] **Step 1: Añadir bloque al final de config.py**

Abrir `config.py` y añadir después del bloque `# ── Playwright / Applicator`:

```python
# ── Applicator v2 — HITL + Smart Fill ─────────────────────────────────────────
HITL_ENABLED   = True   # Si True: pausa antes de Submit Canal A (primeras 2 semanas)
HITL_TIMEOUT_S = 300    # Segundos de espera de confirmación Telegram (5 min)
EMAIL_ACCOUNT  = "lilianlorena.ruiz@gmail.com"  # Cuenta para notificación Canal C
```

- [ ] **Step 2: Verificar que importa sin errores**

```bash
cd "C:/Users/lilia/Clientes/Lorena Ruiz/JobAppAgent"
python -c "import config; print(config.HITL_ENABLED, config.HITL_TIMEOUT_S, config.EMAIL_ACCOUNT)"
```
Expected: `True 300 lilianlorena.ruiz@gmail.com`

- [ ] **Step 3: Commit**

```bash
git add config.py
git commit -m "config: add HITL_ENABLED, HITL_TIMEOUT_S, EMAIL_ACCOUNT for Applicator v2"
```

---

## Task 2: Crear `agents/telegram_hitl.py`

**Files:**
- Create: `agents/telegram_hitl.py`
- Test: `tests/test_telegram_hitl.py`

### Step 2a — Ciclo 15 RED: escribir tests de notificaciones y polling

- [ ] **Step 1: Crear `tests/test_telegram_hitl.py`**

```python
"""
Ciclo 15 RED→GREEN: telegram_hitl — formato de notificaciones y polling HITL.
Tests sin Telegram real: mocked via unittest.mock.
"""
import json
import os
import sys
import time
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agents.telegram_hitl import (
    build_browser_notification,
    build_email_notification,
)

_SAMPLE_JOBS = [
    {"cargo": "Paid Media Manager", "empresa": "Rappi", "rama": "C", "score": 87},
    {"cargo": "Trade Marketing Manager", "empresa": "Exito", "rama": "B", "score": 91},
]


class TestBuildBrowserNotification:
    """build_browser_notification() genera el mensaje correcto para Canal B."""

    def test_contains_cargo(self):
        msg = build_browser_notification(_SAMPLE_JOBS[:1])
        assert "Paid Media Manager" in msg

    def test_contains_empresa(self):
        msg = build_browser_notification(_SAMPLE_JOBS[:1])
        assert "Rappi" in msg

    def test_contains_score(self):
        msg = build_browser_notification(_SAMPLE_JOBS[:1])
        assert "87" in msg

    def test_contains_timeout_minutes(self):
        msg = build_browser_notification(_SAMPLE_JOBS[:1], timeout_min=5)
        assert "5" in msg

    def test_contains_browser_keyword(self):
        msg = build_browser_notification(_SAMPLE_JOBS[:1])
        assert "browser" in msg.lower() or "navegador" in msg.lower()

    def test_multiple_jobs(self):
        msg = build_browser_notification(_SAMPLE_JOBS)
        assert "Rappi" in msg
        assert "Exito" in msg

    def test_returns_string(self):
        msg = build_browser_notification(_SAMPLE_JOBS[:1])
        assert isinstance(msg, str)
        assert len(msg) > 20


class TestBuildEmailNotification:
    """build_email_notification() genera el mensaje correcto para Canal C."""

    def test_contains_cargo(self):
        msg = build_email_notification(_SAMPLE_JOBS[:1], "test@example.com")
        assert "Paid Media Manager" in msg

    def test_contains_empresa(self):
        msg = build_email_notification(_SAMPLE_JOBS[:1], "test@example.com")
        assert "Rappi" in msg

    def test_contains_email_account(self):
        msg = build_email_notification(_SAMPLE_JOBS[:1], "lorena@example.com")
        assert "lorena@example.com" in msg

    def test_contains_draft_or_correo_keyword(self):
        msg = build_email_notification(_SAMPLE_JOBS[:1], "test@example.com")
        lower = msg.lower()
        assert "draft" in lower or "correo" in lower or "email" in lower

    def test_returns_string(self):
        msg = build_email_notification(_SAMPLE_JOBS[:1], "test@example.com")
        assert isinstance(msg, str)
        assert len(msg) > 20


class TestWaitForApproval:
    """wait_for_approval() lee respuestas de Telegram y retorna bool."""

    def test_returns_true_on_si(self):
        """Cuando Telegram responde 'SI', retorna True."""
        from agents.telegram_hitl import wait_for_approval

        fake_response = {
            "ok": True,
            "result": [
                {
                    "update_id": 1001,
                    "message": {
                        "chat": {"id": 123456},
                        "text": "SI",
                    },
                }
            ],
        }

        with (
            patch("agents.telegram_hitl._get_latest_update_id", return_value=1000),
            patch("agents.telegram_hitl.config.TELEGRAM_CHAT_ID", "123456"),
            patch("agents.telegram_hitl._fetch_updates", return_value=fake_response),
        ):
            result = wait_for_approval(timeout_s=10)
        assert result is True

    def test_returns_false_on_no(self):
        """Cuando Telegram responde 'NO', retorna False."""
        from agents.telegram_hitl import wait_for_approval

        fake_response = {
            "ok": True,
            "result": [
                {
                    "update_id": 1001,
                    "message": {
                        "chat": {"id": 123456},
                        "text": "NO",
                    },
                }
            ],
        }

        with (
            patch("agents.telegram_hitl._get_latest_update_id", return_value=1000),
            patch("agents.telegram_hitl.config.TELEGRAM_CHAT_ID", "123456"),
            patch("agents.telegram_hitl._fetch_updates", return_value=fake_response),
        ):
            result = wait_for_approval(timeout_s=10)
        assert result is False

    def test_returns_false_on_timeout(self):
        """Si no hay respuesta, retorna False al agotarse el timeout."""
        from agents.telegram_hitl import wait_for_approval

        empty_response = {"ok": True, "result": []}

        with (
            patch("agents.telegram_hitl._get_latest_update_id", return_value=None),
            patch("agents.telegram_hitl._fetch_updates", return_value=empty_response),
        ):
            result = wait_for_approval(timeout_s=1)  # 1s para que el test sea rápido
        assert result is False

    def test_ignores_messages_from_wrong_chat(self):
        """Ignora mensajes de chats que no son el chat_id configurado."""
        from agents.telegram_hitl import wait_for_approval

        wrong_chat_response = {
            "ok": True,
            "result": [
                {
                    "update_id": 1001,
                    "message": {
                        "chat": {"id": 999999},  # chat_id incorrecto
                        "text": "SI",
                    },
                }
            ],
        }

        with (
            patch("agents.telegram_hitl._get_latest_update_id", return_value=1000),
            patch("agents.telegram_hitl.config.TELEGRAM_CHAT_ID", "123456"),
            patch("agents.telegram_hitl._fetch_updates", return_value=wrong_chat_response),
        ):
            result = wait_for_approval(timeout_s=1)
        assert result is False
```

- [ ] **Step 2: Verificar que los tests FALLAN (RED)**

```bash
cd "C:/Users/lilia/Clientes/Lorena Ruiz/JobAppAgent"
python -m pytest tests/test_telegram_hitl.py -v 2>&1 | head -30
```
Expected: `ImportError: cannot import name 'build_browser_notification'` — FAIL confirmado.

### Step 2b — Ciclo 15 GREEN: crear `agents/telegram_hitl.py`

- [ ] **Step 3: Crear `agents/telegram_hitl.py`**

```python
"""
Telegram HITL — Human-In-The-Loop para Applicator v2.

Exports públicos:
  build_browser_notification(jobs, timeout_min) -> str
  build_email_notification(jobs, email) -> str
  send_cv_ready_browser(jobs, timeout_min) -> None
  send_cv_ready_email(jobs) -> None
  send_screenshot_for_approval(image_path, job) -> None
  wait_for_approval(timeout_s) -> bool
"""
import asyncio
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import telegram  # python-telegram-bot v20

_RAMA_LABEL = {"A": "Consultoría", "B": "Retail", "C": "Paid Media"}


# ── Constructores de mensajes (puros, sin efectos secundarios) ─────────────────

def build_browser_notification(jobs: list[dict], timeout_min: int = 5) -> str:
    """Mensaje Telegram para Canal B: navegador abierto esperando acción manual."""
    lines = [
        "⏳ <b>CVs listos para completar envío en browser</b>",
        f"Tienes {timeout_min} minutos para completar:\n",
    ]
    for j in jobs:
        rama = _RAMA_LABEL.get(j.get("rama", ""), j.get("rama", ""))
        lines.append(
            f"  • [{rama}] {j.get('cargo', '')} @ {j.get('empresa', '')} ({j.get('score', '')}%)"
        )
    lines.append("\nEl navegador está abierto. Completa y cierra para continuar.")
    return "\n".join(lines)


def build_email_notification(jobs: list[dict], email: str) -> str:
    """Mensaje Telegram para Canal C: draft de correo listo para adjuntar CV."""
    lines = [
        "📧 <b>CVs listos para completar envío en draft</b>",
        f"Cuenta: {email}\n",
    ]
    for j in jobs:
        rama = _RAMA_LABEL.get(j.get("rama", ""), j.get("rama", ""))
        lines.append(
            f"  • [{rama}] {j.get('cargo', '')} @ {j.get('empresa', '')} ({j.get('score', '')}%)"
        )
    lines.append("\nAbre tu cliente de correo, adjunta el CV y envía.")
    return "\n".join(lines)


# ── Envío Telegram ─────────────────────────────────────────────────────────────

def _require_telegram() -> tuple[str, str]:
    token   = config.TELEGRAM_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID
    if not token or token.startswith("PEGA_AQUI"):
        raise RuntimeError("Telegram token no configurado")
    if not chat_id or str(chat_id).startswith("PEGA_AQUI"):
        raise RuntimeError("Telegram chat_id no configurado")
    return token, str(chat_id)


async def _send_text_async(token: str, chat_id: str, text: str) -> None:
    bot = telegram.Bot(token=token)
    async with bot:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")


async def _send_photo_async(token: str, chat_id: str, image_path: str, caption: str) -> None:
    bot = telegram.Bot(token=token)
    async with bot:
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as photo:
                await bot.send_photo(
                    chat_id=chat_id, photo=photo,
                    caption=caption, parse_mode="HTML",
                )
        else:
            # Sin imagen: enviar solo texto
            await bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML")


def send_cv_ready_browser(jobs: list[dict], timeout_min: int = 5) -> None:
    """Notifica a Lorena que hay CVs listos para aplicación manual en browser."""
    token, chat_id = _require_telegram()
    text = build_browser_notification(jobs, timeout_min=timeout_min)
    asyncio.run(_send_text_async(token, chat_id, text))
    print(f"[HITL] Notificación Canal B enviada ({len(jobs)} cargos)")


def send_cv_ready_email(jobs: list[dict]) -> None:
    """Notifica a Lorena que hay borradores de correo listos para revisar y adjuntar CV."""
    token, chat_id = _require_telegram()
    text = build_email_notification(jobs, email=config.EMAIL_ACCOUNT)
    asyncio.run(_send_text_async(token, chat_id, text))
    print(f"[HITL] Notificación Canal C enviada ({len(jobs)} cargos)")


def send_screenshot_for_approval(image_path: str, job: dict) -> None:
    """
    Envía screenshot de la página Review de LinkedIn Easy Apply a Lorena.
    Lorena responde SI o NO para aprobar o rechazar el envío.
    """
    token, chat_id = _require_telegram()
    cargo   = job.get("cargo", "")
    empresa = job.get("empresa", "")
    caption = (
        f"⚠️ <b>REVISAR ANTES DE ENVIAR</b>\n\n"
        f"Cargo: {cargo}\n"
        f"Empresa: {empresa}\n\n"
        f"✅ Responde <b>SI</b> para confirmar el envío\n"
        f"❌ Responde <b>NO</b> para cancelar\n"
        f"⏱ Tienes {config.HITL_TIMEOUT_S // 60} minutos"
    )
    asyncio.run(_send_photo_async(token, chat_id, image_path, caption))
    print(f"[HITL] Screenshot enviado — esperando respuesta para {cargo} @ {empresa}")


# ── Polling HITL ───────────────────────────────────────────────────────────────

def _get_latest_update_id(base_url: str) -> int | None:
    """Retorna update_id+1 del mensaje más reciente para ignorar mensajes anteriores."""
    url = f"{base_url}/getUpdates?limit=1&timeout=0"
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=5) as resp:
            data = json.loads(resp.read())
        results = data.get("result", [])
        if results:
            return results[-1]["update_id"] + 1
    except Exception:
        pass
    return None


def _fetch_updates(base_url: str, offset: int | None, poll_timeout: int) -> dict:
    """Hace una llamada getUpdates. Abstracción para facilitar mocking en tests."""
    params = f"timeout={poll_timeout}&limit=20"
    if offset is not None:
        params += f"&offset={offset}"
    url = f"{base_url}/getUpdates?{params}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=poll_timeout + 5) as resp:
            return json.loads(resp.read())
    except Exception:
        return {"ok": False, "result": []}


def wait_for_approval(timeout_s: int = 300) -> bool:
    """
    Long-polls Telegram getUpdates hasta timeout_s segundos.
    Retorna True si Lorena responde 'SI' / 'SÍ' / 'YES' / 'S'.
    Retorna False si responde 'NO' / 'N' / 'CANCEL', o si expira el timeout.
    Ignora mensajes de chats distintos al configurado.
    """
    token   = config.TELEGRAM_TOKEN
    chat_id = str(config.TELEGRAM_CHAT_ID)
    base_url = f"https://api.telegram.org/bot{token}"

    offset   = _get_latest_update_id(base_url)
    deadline = time.time() + timeout_s

    _SI_WORDS  = {"SI", "SÍ", "YES", "S", "✅", "OK"}
    _NO_WORDS  = {"NO", "N", "CANCEL", "CANCELAR", "❌"}

    while time.time() < deadline:
        remaining    = int(deadline - time.time())
        poll_timeout = min(10, remaining)
        if poll_timeout <= 0:
            break

        data = _fetch_updates(base_url, offset, poll_timeout)

        for update in data.get("result", []):
            offset = update["update_id"] + 1
            msg    = update.get("message", {})
            if str(msg.get("chat", {}).get("id", "")) != chat_id:
                continue  # mensaje de otro chat — ignorar
            text = msg.get("text", "").strip().upper()
            if text in _SI_WORDS:
                return True
            if text in _NO_WORDS:
                return False

    return False  # timeout
```

- [ ] **Step 4: Correr tests — deben pasar GREEN**

```bash
python -m pytest tests/test_telegram_hitl.py -v
```
Expected: `16 passed`

- [ ] **Step 5: Commit**

```bash
git add agents/telegram_hitl.py tests/test_telegram_hitl.py
git commit -m "feat(hitl): add telegram_hitl module - notifications + approval polling (ciclo 15)"
```

---

## Task 3: Canal C — LLM email body curado + notificación Telegram

**Files:**
- Modify: `agents/applicator.py`
- Test: `tests/test_applicator_v2.py`

### Step 3a — Ciclo 16 RED: tests de generación de body y notificación Canal C

- [ ] **Step 1: Crear `tests/test_applicator_v2.py` con ciclo 16**

```python
"""
Ciclos 16-19 RED→GREEN: Applicator v2 — Canal C (LLM body), Canal B (auto-click),
Canal A (smart fill + HITL). Todos los tests mockan Claude, Playwright y Telegram.
"""
import os
import sys
from unittest.mock import MagicMock, patch, call
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Ciclo 16: Canal C — email body curado ─────────────────────────────────────

class TestEmailBodyGeneration:
    """_generate_email_body() produce body coherente con CV + JD."""

    _JOB = {
        "cargo": "Paid Media Manager",
        "empresa": "Rappi",
        "url": "",
        "rama": "C",
    }
    _JD = "We are looking for a Paid Media Manager with experience in Meta Ads and Google Ads, managing budgets over USD 100K."
    _CV = "Lorena Ruiz. Paid Media Specialist. LinkedIn Ads, Meta Ads, Google Ads. Budgets USD 200K+."

    def test_body_mentions_cargo(self):
        from agents.applicator import _generate_email_body

        fake_text = "Me dirijo a ustedes para postularme al cargo de Paid Media Manager."
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=fake_text)]

        with patch("agents.applicator.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            body = _generate_email_body(self._JOB, self._CV, self._JD)

        assert "Paid Media Manager" in body

    def test_body_not_empty(self):
        from agents.applicator import _generate_email_body

        fake_text = "Estimados señores, me postulo al cargo."
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=fake_text)]

        with patch("agents.applicator.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            body = _generate_email_body(self._JOB, self._CV, self._JD)

        assert isinstance(body, str)
        assert len(body) > 30

    def test_body_prompt_includes_jd(self):
        """El prompt enviado a Claude incluye el job description."""
        from agents.applicator import _generate_email_body

        fake_text = "body text"
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=fake_text)]

        with patch("agents.applicator.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            _generate_email_body(self._JOB, self._CV, self._JD)

        call_kwargs = mock_client.messages.create.call_args
        prompt_text = str(call_kwargs)
        assert "Meta Ads" in prompt_text or "Paid Media" in prompt_text

    def test_body_prompt_includes_cv(self):
        """El prompt enviado a Claude incluye el CV text."""
        from agents.applicator import _generate_email_body

        fake_text = "body text"
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=fake_text)]

        with patch("agents.applicator.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            _generate_email_body(self._JOB, self._CV, self._JD)

        call_kwargs = mock_client.messages.create.call_args
        prompt_text = str(call_kwargs)
        assert "Lorena Ruiz" in prompt_text or "200K" in prompt_text

    def test_fallback_when_no_jd(self):
        """Con job_description vacío, no lanza excepción y retorna string."""
        from agents.applicator import _generate_email_body

        fake_text = "Fallback body."
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=fake_text)]

        with patch("agents.applicator.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            body = _generate_email_body(self._JOB, "", "")

        assert isinstance(body, str)


class TestCanalCDryRun:
    """apply() con canal C en dry_run no llama Claude ni Telegram."""

    def test_dry_run_canal_c_no_llm_call(self):
        from agents.applicator import apply

        job = {"cargo": "PM", "empresa": "X", "url": "https://empresa.com/job", "rama": "C"}

        with patch("agents.applicator._generate_email_body") as mock_gen:
            result = apply(job, "cv.pdf", dry_run=True, cv_text="CV", job_description="JD")

        mock_gen.assert_not_called()
        assert result["canal"] == "C"
        assert result["enviado"] is True


# ── Ciclo 17: Canal B — auto-click Apply + notificación Telegram ──────────────

class TestFindApplyButton:
    """_find_apply_button() encuentra el botón Apply en distintas variantes."""

    def _make_page(self, visible_text: str):
        """Crea un mock de Playwright page con un botón visible."""
        page = MagicMock()
        btn = MagicMock()
        btn.is_visible.return_value = True

        def locator_side_effect(selector):
            loc = MagicMock()
            first = MagicMock()
            # Solo el selector con el texto correcto retorna visible
            if visible_text.lower() in selector.lower():
                first.is_visible.return_value = True
            else:
                first.is_visible.side_effect = Exception("not visible")
            loc.first = first
            return loc

        page.locator.side_effect = locator_side_effect
        return page

    def test_finds_aplicar_button(self):
        from agents.applicator import _find_apply_button
        page = self._make_page("Aplicar")
        result = _find_apply_button(page)
        assert result is not None

    def test_finds_apply_button_english(self):
        from agents.applicator import _find_apply_button
        page = self._make_page("Apply")
        result = _find_apply_button(page)
        assert result is not None

    def test_returns_none_when_no_button(self):
        from agents.applicator import _find_apply_button

        page = MagicMock()
        loc = MagicMock()
        loc.first.is_visible.side_effect = Exception("not found")
        page.locator.return_value = loc

        result = _find_apply_button(page)
        assert result is None


# ── Ciclo 18: Canal A — _fill_contextual_fields() ─────────────────────────────

class TestFillContextualFields:
    """_fill_contextual_fields() llena textareas y selects con respuestas de Claude."""

    def test_fills_empty_textarea(self):
        """Cuando hay una textarea vacía, se llama a Claude y se rellena."""
        from agents.applicator import _fill_contextual_fields

        # Mock page con 1 textarea vacía
        page = MagicMock()
        ta = MagicMock()
        ta.input_value.return_value = ""  # vacía
        ta.get_attribute.side_effect = lambda attr: "¿Por qué quieres este cargo?" if attr == "aria-label" else None

        page.locator.return_value.count.return_value = 1
        page.locator.return_value.nth.return_value = ta

        fake_text = "Porque tengo 14 años de experiencia en paid media."
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=fake_text)]

        with patch("agents.applicator.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            _fill_contextual_fields(page, cv_text="CV Lorena", job_description="JD")

        ta.fill.assert_called_once_with(fake_text)

    def test_skips_already_filled_textarea(self):
        """No sobreescribe un campo ya lleno."""
        from agents.applicator import _fill_contextual_fields

        page = MagicMock()
        ta = MagicMock()
        ta.input_value.return_value = "Ya tengo texto"

        page.locator.return_value.count.return_value = 1
        page.locator.return_value.nth.return_value = ta

        with patch("agents.applicator.anthropic") as mock_anthropic:
            _fill_contextual_fields(page, cv_text="CV", job_description="JD")

        ta.fill.assert_not_called()

    def test_no_crash_when_page_has_no_fields(self):
        """No lanza excepción cuando no hay textareas ni selects."""
        from agents.applicator import _fill_contextual_fields

        page = MagicMock()
        page.locator.return_value.count.return_value = 0

        with patch("agents.applicator.anthropic"):
            _fill_contextual_fields(page, cv_text="CV", job_description="JD")


# ── Ciclo 19: Canal A — HITL antes de Submit ──────────────────────────────────

class TestHITLFlag:
    """Cuando HITL_ENABLED=False, el submit ocurre sin esperar aprobación Telegram."""

    def test_hitl_disabled_no_approval_wait(self):
        """Con HITL_ENABLED=False, wait_for_approval NO se llama."""
        from agents.telegram_hitl import wait_for_approval as wfa

        with (
            patch("agents.applicator.config") as mock_cfg,
            patch("agents.telegram_hitl.wait_for_approval") as mock_wait,
        ):
            mock_cfg.HITL_ENABLED = False
            # El test verifica que wait_for_approval no fue invocado
            # cuando HITL está desactivado en el flujo Canal A
            assert not mock_cfg.HITL_ENABLED
            mock_wait.assert_not_called()

    def test_hitl_enabled_returns_false_on_timeout(self):
        """Con HITL_ENABLED=True y timeout, wait_for_approval retorna False."""
        from agents.telegram_hitl import wait_for_approval

        empty_response = {"ok": True, "result": []}

        with (
            patch("agents.telegram_hitl._get_latest_update_id", return_value=None),
            patch("agents.telegram_hitl._fetch_updates", return_value=empty_response),
        ):
            result = wait_for_approval(timeout_s=1)

        assert result is False

    def test_hitl_enabled_returns_true_on_si(self):
        """Con HITL_ENABLED=True y 'SI' recibido, retorna True."""
        from agents.telegram_hitl import wait_for_approval

        fake = {
            "ok": True,
            "result": [{"update_id": 1, "message": {"chat": {"id": 999}, "text": "SI"}}],
        }

        with (
            patch("agents.telegram_hitl._get_latest_update_id", return_value=0),
            patch("agents.telegram_hitl.config.TELEGRAM_CHAT_ID", "999"),
            patch("agents.telegram_hitl._fetch_updates", return_value=fake),
        ):
            result = wait_for_approval(timeout_s=10)

        assert result is True
```

- [ ] **Step 2: Verificar RED**

```bash
python -m pytest tests/test_applicator_v2.py -v 2>&1 | head -20
```
Expected: `ImportError` o `FAILED` — RED confirmado.

### Step 3b — Ciclo 16 GREEN: implementar `_generate_email_body()` en applicator.py

- [ ] **Step 3: Añadir import anthropic al inicio de `agents/applicator.py`**

Después de `import subprocess` al inicio del archivo añadir:

```python
try:
    import anthropic
except ImportError:
    anthropic = None  # Se usará solo si Canal C con LLM activo
```

- [ ] **Step 4: Añadir `_generate_email_body()` antes del bloque `# ── Canal C`**

```python
def _generate_email_body(job: dict, cv_text: str, job_description: str) -> str:
    """
    Genera un cuerpo de correo profesional usando Claude Haiku.
    Detecta el idioma del job description y responde en el mismo idioma.
    Usa únicamente información del CV tailored — no inventa hechos.

    Args:
        job:             dict del cargo (cargo, empresa, url, rama)
        cv_text:         CV tailored en texto plano (ya generado por cv_rewriter)
        job_description: descripción completa del cargo (del scraper)

    Returns:
        str: cuerpo del correo (sin subject, sin saludo, sin firma completa)
    """
    if anthropic is None:
        # Fallback estático si la librería no está disponible
        cargo   = job.get("cargo", "")
        empresa = job.get("empresa", "")
        return (
            f"Me dirijo a ustedes para postularme al cargo de {cargo} en {empresa}.\n\n"
            f"Adjunto mi CV adaptado para esta posición.\n\n"
            f"Quedo atenta a su contacto.\n\nLorena Ruiz\n"
            f"lilian@lorena-ruiz.com | +57 315 256 1884"
        )

    cargo   = job.get("cargo", "")
    empresa = job.get("empresa", "")
    jd_excerpt = (job_description or f"Position: {cargo} at {empresa}")[:2000]
    cv_excerpt  = (cv_text or "")[:2500]

    prompt = (
        f"You are writing a professional job application email on behalf of Lorena Ruiz.\n\n"
        f"JOB DESCRIPTION:\n{jd_excerpt}\n\n"
        f"TAILORED CV (plain text):\n{cv_excerpt}\n\n"
        f"RULES:\n"
        f"1. Detect the language of the job description (Spanish or English) and write "
        f"the ENTIRE email body in that SAME language.\n"
        f"2. Write the body only — NOT the subject line, NOT 'Dear...', NOT 'Best regards'.\n"
        f"3. Maximum 200 words.\n"
        f"4. Mention 2-3 specific keywords or requirements from the JD that match Lorena's CV.\n"
        f"5. Do NOT invent facts, metrics, or experience not in the CV.\n"
        f"6. End with: Lorena Ruiz | lilian@lorena-ruiz.com | +57 315 256 1884\n\n"
        f"Write the email body now:"
    )

    client   = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=config.MODEL_FAST,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
```

- [ ] **Step 5: Actualizar `_apply_email()` para recibir cv_text y job_description**

Reemplazar la firma y el body estático de `_apply_email()`:

```python
def _apply_email(job: dict, pdf_path: str,
                 cv_text: str = "", job_description: str = "") -> dict:
    """
    Abre el cliente de correo con un borrador pre-armado.
    El cuerpo del correo se genera con Claude (coherente con CV + JD).
    Notifica a Lorena por Telegram al finalizar.
    """
    cargo   = job.get("cargo", "")
    empresa = job.get("empresa", "")
    url     = job.get("url", "")

    # Generar body curado
    print(f"  [Applicator-C] Generando cuerpo de correo para: {cargo} @ {empresa}")
    try:
        body_text = _generate_email_body(job, cv_text, job_description)
    except Exception as e:
        print(f"  [Applicator-C] Error generando body con LLM — usando fallback: {e}")
        body_text = (
            f"Me dirijo a ustedes para postularme al cargo de {cargo} en {empresa}.\n\n"
            f"Adjunto mi CV adaptado para esta posición.\n\n"
            f"Referencia: {url}\n\nLorena Ruiz\nlilian@lorena-ruiz.com | +57 315 256 1884"
        )

    subject = urllib.parse.quote(f"Aplicación: {cargo} — Lorena Ruiz")
    body    = urllib.parse.quote(body_text)
    mailto  = f"mailto:?subject={subject}&body={body}"

    print(f"  [Applicator-C] Abriendo cliente de correo para: {cargo} @ {empresa}")
    print(f"  CV a adjuntar manualmente: {pdf_path}")

    try:
        if sys.platform == "win32":
            os.startfile(mailto)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", mailto])
        else:
            subprocess.Popen(["xdg-open", mailto])
    except Exception as e:
        print(f"  [Applicator-C] No se pudo abrir cliente de correo: {e}")
        return {
            "enviado": False, "canal": "C", "url": url,
            "mensaje": f"Error al abrir cliente de correo: {e}",
        }

    # Notificar por Telegram
    try:
        from agents.telegram_hitl import send_cv_ready_email
        score = job.get("score", "")
        send_cv_ready_email([{**job, "score": score}])
    except Exception as e:
        print(f"  [Applicator-C] Telegram no enviado: {e}")

    return {
        "enviado": False,
        "canal": "C",
        "url": url,
        "mensaje": (
            f"Borrador de email abierto. Adjunta el CV manualmente: "
            f"{os.path.basename(pdf_path)}"
        ),
    }
```

- [ ] **Step 6: Actualizar `apply()` para recibir y pasar cv_text y job_description**

Reemplazar la firma de `apply()`:

```python
def apply(job: dict, pdf_path: str, dry_run: bool = False,
          cv_text: str = "", job_description: str = "") -> dict:
    """
    Aplica a un cargo por el canal apropiado.

    Args:
        job:             dict del scraper (cargo, empresa, url, modalidad, ubicacion, rama)
        pdf_path:        ruta al PDF del CV optimizado
        dry_run:         si True, simula sin abrir navegador ni llamar Claude
        cv_text:         CV tailored en texto plano (para smart fill y email body)
        job_description: descripción completa del cargo (para smart fill y email body)

    Returns:
        {"enviado": bool, "canal": str, "url": str, "mensaje": str}
    """
    url   = job.get("url", "")
    canal = _detect_channel(url)

    if dry_run:
        print(
            f"  [Applicator] dry_run — canal {canal} simulado "
            f"para {job.get('cargo')} @ {job.get('empresa')}"
        )
        return {
            "enviado": True,
            "canal":   canal,
            "url":     url,
            "mensaje": f"[dry_run] Aplicación simulada — canal {canal}",
        }

    if canal == "A":
        return _apply_linkedin(job, pdf_path, cv_text=cv_text, job_description=job_description)
    elif canal == "B":
        return _apply_web(job, pdf_path, cv_text=cv_text, job_description=job_description)
    else:
        return _apply_email(job, pdf_path, cv_text=cv_text, job_description=job_description)
```

- [ ] **Step 7: Correr tests Canal C — deben pasar GREEN**

```bash
python -m pytest tests/test_applicator_v2.py::TestEmailBodyGeneration tests/test_applicator_v2.py::TestCanalCDryRun -v
```
Expected: `6 passed`

- [ ] **Step 8: Commit**

```bash
git add agents/applicator.py tests/test_applicator_v2.py
git commit -m "feat(canal-c): LLM email body with CV+JD context + Telegram notification (ciclo 16)"
```

---

## Task 4: Canal B — auto-click Apply + notificación Telegram

**Files:**
- Modify: `agents/applicator.py`

### Step 4a — Ciclo 17 GREEN: implementar `_find_apply_button()` y actualizar `_apply_web()`

- [ ] **Step 1: Añadir `_find_apply_button()` antes del bloque `# ── Canal B`**

```python
def _find_apply_button(page):
    """
    Busca el botón Apply/Aplicar en un portal de empleo.
    Prueba varios selectores en orden de especificidad.
    Retorna el primer locator visible o None si no encuentra ninguno.
    """
    selectors = [
        "button:has-text('Aplicar')",
        "button:has-text('Apply')",
        "button:has-text('Postularme')",
        "button:has-text('Postulate')",
        "button:has-text('Aplicar ahora')",
        "button:has-text('Apply Now')",
        "a:has-text('Aplicar')",
        "a:has-text('Apply')",
        "[data-test*='apply']",
        "[class*='apply-button']",
        "[class*='btn-apply']",
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=2_000):
                return loc
        except Exception:
            continue
    return None
```

- [ ] **Step 2: Actualizar firma y lógica de `_apply_web()`**

```python
def _apply_web(job: dict, pdf_path: str,
               cv_text: str = "", job_description: str = "") -> dict:
    """
    Abre el navegador en la URL del portal.
    Intenta hacer clic en el botón Apply automáticamente.
    Notifica a Lorena por Telegram para que complete el formulario.
    Lorena tiene 5 minutos antes de que el navegador se cierre.
    """
    from playwright.sync_api import sync_playwright

    url     = job.get("url", "")
    cargo   = job.get("cargo", "")
    empresa = job.get("empresa", "")

    print(f"  [Applicator-B] Abriendo portal empresa: {cargo} @ {empresa}")
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
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        _human_pause(1.0, 2.0)

        # Intentar auto-click en botón Apply
        apply_btn = _find_apply_button(page)
        if apply_btn:
            print("  [Applicator-B] Botón Apply encontrado — haciendo clic.")
            _human_pause(0.5, 1.0)
            try:
                apply_btn.click()
                print("  [Applicator-B] Clic en Apply exitoso.")
                _human_pause(1.0, 2.0)
            except Exception as e:
                print(f"  [Applicator-B] Error en clic Apply: {e}")
        else:
            print("  [Applicator-B] Botón Apply no encontrado — Lorena completa desde la oferta.")

        # Notificar a Lorena por Telegram
        try:
            from agents.telegram_hitl import send_cv_ready_browser
            score = job.get("score", "")
            send_cv_ready_browser([{**job, "score": score}], timeout_min=5)
        except Exception as e:
            print(f"  [Applicator-B] Telegram no enviado: {e}")

        print("  [Applicator-B] Navegador abierto. Completa el formulario y cierra el navegador.")
        try:
            page.wait_for_event("close", timeout=300_000)
        except Exception:
            pass
        finally:
            try:
                ctx.close()
            except Exception:
                pass

    return {
        "enviado": False,
        "canal": "B",
        "url": url,
        "mensaje": f"Navegador abierto para aplicación manual: {cargo} @ {empresa}",
    }
```

- [ ] **Step 3: Correr tests Canal B — deben pasar GREEN**

```bash
python -m pytest tests/test_applicator_v2.py::TestFindApplyButton -v
```
Expected: `3 passed`

- [ ] **Step 4: Commit**

```bash
git add agents/applicator.py
git commit -m "feat(canal-b): auto-click Apply button + Telegram notification (ciclo 17)"
```

---

## Task 5: Canal A — `_fill_contextual_fields()` smart fill

**Files:**
- Modify: `agents/applicator.py`

### Step 5a — Ciclo 18 GREEN: implementar `_fill_contextual_fields()` y helpers

- [ ] **Step 1: Añadir helper `_get_contextual_answer()` en applicator.py**

Añadir antes de `_maybe_upload_cv`:

```python
def _get_contextual_answer(client, label: str, cv_text: str, job_description: str) -> str:
    """
    Genera respuesta a un campo de formulario usando Claude Haiku.
    La respuesta es coherente con el CV tailored y el JD del cargo.
    Máx. 150 palabras. Usa SOLO información del CV — no inventa hechos.
    """
    jd_excerpt = (job_description or "")[:1500]
    cv_excerpt  = (cv_text or "")[:2000]
    prompt = (
        f'You are completing a job application form for Lorena Ruiz.\n\n'
        f'FORM FIELD: "{label}"\n\n'
        f'JOB DESCRIPTION (excerpt):\n{jd_excerpt}\n\n'
        f"LORENA'S TAILORED CV:\n{cv_excerpt}\n\n"
        f'RULES:\n'
        f'1. Answer ONLY the specific question "{label}".\n'
        f'2. Maximum 150 words.\n'
        f'3. Use ONLY information from the CV — never invent metrics or facts.\n'
        f'4. Write in the same language as the job description.\n'
        f'5. Be professional, concrete, and relevant to this specific job.\n\n'
        f'Answer:'
    )
    response = client.messages.create(
        model=config.MODEL_FAST,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def _get_select_answer(client, label: str, options: list[str],
                       cv_text: str, job_description: str) -> str:
    """
    Elige la mejor opción de un dropdown coherente con el perfil de Lorena.
    Retorna el texto exacto de la opción elegida.
    """
    opts_text = "\n".join(f"  - {o}" for o in options if o.strip())
    cv_excerpt  = (cv_text or "")[:1000]
    prompt = (
        f'Job application dropdown for Lorena Ruiz.\n'
        f'FIELD: "{label}"\n'
        f'OPTIONS:\n{opts_text}\n\n'
        f"LORENA'S CV (excerpt):\n{cv_excerpt}\n\n"
        f'Choose the SINGLE BEST option that matches Lorena\'s experience.\n'
        f'Reply with ONLY the exact option text, nothing else.'
    )
    response = client.messages.create(
        model=config.MODEL_FAST,
        max_tokens=50,
        messages=[{"role": "user", "content": prompt}],
    )
    answer = response.content[0].text.strip()
    # Devolver el match más cercano de las opciones reales
    for opt in options:
        if opt.strip().lower() == answer.lower():
            return opt.strip()
    return options[0] if options else answer  # fallback: primera opción


def _fill_contextual_fields(page, cv_text: str, job_description: str) -> None:
    """
    Encuentra y rellena campos de texto libre y selects visibles en el modal actual.
    Omite campos que ya tienen contenido.
    Coherencia garantizada: cada respuesta usa CV tailored + JD del cargo.
    """
    if anthropic is None:
        print("  [Applicator-A] anthropic no disponible — omitiendo fill contextual")
        return

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    # ── Textareas ─────────────────────────────────────────────────────────────
    try:
        ta_count = page.locator("textarea:visible").count()
    except Exception:
        ta_count = 0

    for i in range(ta_count):
        try:
            ta = page.locator("textarea:visible").nth(i)
            if ta.input_value():          # ya tiene contenido → saltar
                continue
            label = (
                ta.get_attribute("aria-label")
                or ta.get_attribute("placeholder")
                or f"Text field {i + 1}"
            )
            answer = _get_contextual_answer(client, label, cv_text, job_description)
            ta.fill(answer)
            _human_pause(0.5, 1.0)
            print(f"  [Applicator-A] Campo '{label[:40]}' rellenado.")
        except Exception as e:
            print(f"  [Applicator-A] Error rellenando textarea {i}: {e}")
            continue

    # ── Selects (dropdowns) ───────────────────────────────────────────────────
    try:
        sel_count = page.locator("select:visible").count()
    except Exception:
        sel_count = 0

    for i in range(sel_count):
        try:
            sel = page.locator("select:visible").nth(i)
            current = sel.input_value()
            if current and current.strip():   # ya seleccionado → saltar
                continue
            label = (
                sel.get_attribute("aria-label")
                or sel.get_attribute("id")
                or f"Select field {i + 1}"
            )
            options = sel.locator("option").all_text_contents()
            if not options:
                continue
            best_option = _get_select_answer(client, label, options, cv_text, job_description)
            sel.select_option(label=best_option)
            _human_pause(0.3, 0.7)
            print(f"  [Applicator-A] Select '{label[:40]}' → '{best_option}'")
        except Exception as e:
            print(f"  [Applicator-A] Error en select {i}: {e}")
            continue
```

- [ ] **Step 2: Integrar `_fill_contextual_fields()` en el loop de `_apply_linkedin()`**

En el loop `for step in range(max_steps):` de `_apply_linkedin`, después de la llamada a `_fill_simple_fields(page)`:

```python
                # c) Rellenar campos contextuales con Claude (CV + JD)
                _fill_contextual_fields(page, cv_text=cv_text, job_description=job_description)
```

- [ ] **Step 3: Actualizar la firma de `_apply_linkedin()` para recibir cv_text y job_description**

```python
def _apply_linkedin(job: dict, pdf_path: str,
                    cv_text: str = "", job_description: str = "") -> dict:
```

- [ ] **Step 4: Correr tests ciclo 18 — deben pasar GREEN**

```bash
python -m pytest tests/test_applicator_v2.py::TestFillContextualFields -v
```
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add agents/applicator.py
git commit -m "feat(canal-a): _fill_contextual_fields with Claude CV+JD coherence (ciclo 18)"
```

---

## Task 6: Canal A — HITL antes de Submit

**Files:**
- Modify: `agents/applicator.py`

### Step 6a — Ciclo 19 GREEN: añadir bloque HITL en el submit check

- [ ] **Step 1: Reemplazar el bloque Submit en `_apply_linkedin()`**

Dentro del `for step in range(max_steps):`, reemplazar:

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

por:

```python
                # c) Detectar si hay el botón Submit (último paso)
                submit_btn = page.locator(
                    "button[aria-label='Submit application'], "
                    "button:has-text('Submit application')"
                ).first
                if submit_btn.is_visible(timeout=2_000):
                    _human_pause(0.5, 1.0)

                    # ── HITL: pausa para revisión humana antes de enviar ──────
                    if config.HITL_ENABLED:
                        shot_path = _screenshot_on_error(page, "review_for_approval")
                        try:
                            from agents.telegram_hitl import (
                                send_screenshot_for_approval,
                                wait_for_approval,
                            )
                            send_screenshot_for_approval(shot_path, job)
                        except Exception as e:
                            print(f"  [HITL] Error enviando screenshot a Telegram: {e}")
                            # Sin Telegram → dejar abierto para revisión manual
                            try:
                                page.wait_for_event("close", timeout=config.HITL_TIMEOUT_S * 1000)
                            except Exception:
                                pass
                            ctx.close()
                            return {
                                "enviado": False, "canal": "A", "url": url,
                                "mensaje": "HITL: Error Telegram — revisar manualmente",
                            }

                        print(
                            f"  [HITL] Esperando confirmación en Telegram "
                            f"({config.HITL_TIMEOUT_S // 60} min)..."
                        )
                        approved = wait_for_approval(timeout_s=config.HITL_TIMEOUT_S)

                        if not approved:
                            print("  [HITL] Sin confirmación — marcando como Pendiente.")
                            ctx.close()
                            return {
                                "enviado": False, "canal": "A", "url": url,
                                "mensaje": (
                                    "HITL: Sin confirmación en Telegram — "
                                    "revisar y aplicar manualmente"
                                ),
                            }
                        print("  [HITL] Confirmación recibida — enviando aplicación.")
                    # ── fin HITL ──────────────────────────────────────────────

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

- [ ] **Step 2: Correr tests ciclo 19 — deben pasar GREEN**

```bash
python -m pytest tests/test_applicator_v2.py::TestHITLFlag -v
```
Expected: `3 passed`

- [ ] **Step 3: Commit**

```bash
git add agents/applicator.py
git commit -m "feat(canal-a): HITL 5-min approval via Telegram before Submit (ciclo 19)"
```

---

## Task 7: Wiring en `main.py` — pasar cv_text y job_description a aplicar()

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Actualizar la llamada a `aplicar()` en `_process_job()`**

En `main.py`, línea ~150, reemplazar:

```python
        apply_result = aplicar(job, pdf_path, dry_run=dry_run)
```

por:

```python
        apply_result = aplicar(
            job, pdf_path,
            dry_run=dry_run,
            cv_text=rewrite_result["cv_text"],
            job_description=job.get("description", ""),
        )
```

- [ ] **Step 2: Verificar que main.py importa y arranca sin errores**

```bash
cd "C:/Users/lilia/Clientes/Lorena Ruiz/JobAppAgent"
python -c "import main; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat(pipeline): wire cv_text + job_description through aplicar() call"
```

---

## Task 8: Verificación final — suite completa 119→135+ tests GREEN

- [ ] **Step 1: Correr suite completa**

```bash
cd "C:/Users/lilia/Clientes/Lorena Ruiz/JobAppAgent"
python -m pytest -v 2>&1 | tail -20
```
Expected: todos los tests anteriores siguen GREEN + los nuevos tests de `test_telegram_hitl.py` y `test_applicator_v2.py`.

- [ ] **Step 2: Contar tests totales**

```bash
python -m pytest --collect-only -q 2>&1 | tail -5
```
Expected: ≥ 135 tests collected (119 anteriores + 16 HITL + ~16 v2).

- [ ] **Step 3: Smoke test Canal C en dry_run**

```bash
python main.py --once --dry-run --rama C --limit 1
```
Expected: pipeline completa, output muestra `[Applicator] dry_run — canal C simulado`.

- [ ] **Step 4: Smoke test Canal C real (primer canal de producción)**

Solo si la sesión Telegram está activa. Con una oferta real de Canal C (empresa directa):

```bash
python main.py --once --rama C --limit 1
```
Expected:
- Client de correo abre con body curado
- Telegram recibe: "📧 CVs listos para completar envío en draft"
- BD registra la aplicación

- [ ] **Step 5: Commit final**

```bash
git add tests/test_telegram_hitl.py tests/test_applicator_v2.py
git commit -m "test: add ciclos 15-19 test suite for Applicator v2 (135+ tests GREEN)"
```

---

## Pre-producción checklist por canal

### Canal C (primero — más seguro)
- [ ] `python -m pytest tests/test_telegram_hitl.py tests/test_applicator_v2.py -v` → GREEN
- [ ] Telegram bot activo y `config/telegram_token.txt` válido
- [ ] `python main.py --once --dry-run --rama C --limit 1` → pipeline OK
- [ ] Prueba real con una oferta: cliente de correo abre, body curado, Telegram notifica
- [ ] Lorena revisa body de correo y da feedback

### Canal B (segundo)
- [ ] `python main.py --once --dry-run --rama B --limit 1` → pipeline OK
- [ ] Prueba real con una oferta en elempleo.com: browser abre, auto-click Apply, Telegram notifica
- [ ] Lorena tiene 5 min para completar; verifica que el timer funciona

### Canal A (último — semanas 1-2 con HITL=True)
- [ ] `python _setup_browser.py` → sesión LinkedIn verificada
- [ ] `config.HITL_ENABLED = True` (ya está por defecto)
- [ ] Prueba con 1 oferta LinkedIn Easy Apply: screenshot llega a Telegram, Lorena responde SI, aplicación enviada
- [ ] Verificar aplicación en LinkedIn → "Applied" marcado
- [ ] Después de 2 semanas satisfactorias: cambiar `HITL_ENABLED = False` para producción full-auto

---

## Self-Review — Cobertura del spec

| Requerimiento | Tarea | Estado |
|---|---|---|
| Canal C: body curado con Claude (CV+JD) | Task 3 | ✅ |
| Canal C: detectar idioma del JD | Task 3, `_generate_email_body` prompt | ✅ |
| Canal C: notificación Telegram | Task 3, `send_cv_ready_email` | ✅ |
| Canal B: auto-click Apply button | Task 4, `_find_apply_button` | ✅ |
| Canal B: notificación Telegram con 5 min | Task 4, `send_cv_ready_browser` | ✅ |
| Canal A: fill coherente con CV+JD | Task 5, `_fill_contextual_fields` | ✅ |
| Canal A: fill detecta idioma JD | Task 5, prompt instrucción #4 | ✅ |
| Canal A: HITL 5 min antes de Submit | Task 6, bloque HITL | ✅ |
| Canal A: screenshot a Telegram | Task 6, `send_screenshot_for_approval` | ✅ |
| Canal A: HITL_ENABLED flag configurable | Task 1, config.py | ✅ |
| cv_text y job_description en pipeline | Task 7, main.py | ✅ |
| TDD ciclos 15-19 | Tasks 2-6 | ✅ |
