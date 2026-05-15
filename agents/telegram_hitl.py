"""
Telegram HITL — Human-In-The-Loop para Applicator v2.

Exports públicos:
  build_browser_notification(jobs, timeout_min) -> str
  build_email_notification(jobs, email)         -> str
  send_cv_ready_browser(jobs, timeout_min)      -> None
  send_cv_ready_email(jobs)                     -> None
  send_screenshot_for_approval(image_path, job) -> None
  wait_for_approval(timeout_s)                  -> bool
"""
import asyncio
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import telegram  # python-telegram-bot v20

_RAMA_LABEL = {"A": "Consultoría", "B": "Retail", "C": "Paid Media"}


# ── Constructores de mensajes (puros, sin efectos secundarios) ─────────────────

def build_browser_notification(jobs: list[dict], timeout_min: int = 5) -> str:
    """Mensaje Telegram Canal B: navegador abierto esperando acción manual."""
    lines = [
        "⏳ <b>CVs listos para completar envío en browser</b>",
        f"Tienes {timeout_min} minutos para completar:\n",
    ]
    for j in jobs:
        rama  = _RAMA_LABEL.get(j.get("rama", ""), j.get("rama", ""))
        cargo   = j.get("cargo", "")
        empresa = j.get("empresa", "")
        score   = j.get("score", "")
        lines.append(f"  • [{rama}] {cargo} @ {empresa} ({score}%)")
    lines.append("\nEl navegador está abierto. Completa y cierra para continuar.")
    return "\n".join(lines)


def build_email_notification(jobs: list[dict], email: str) -> str:
    """Mensaje Telegram Canal C: draft de correo listo para adjuntar CV."""
    lines = [
        "📧 <b>CVs listos para completar envío en draft</b>",
        f"Cuenta: {email}\n",
    ]
    for j in jobs:
        rama    = _RAMA_LABEL.get(j.get("rama", ""), j.get("rama", ""))
        cargo   = j.get("cargo", "")
        empresa = j.get("empresa", "")
        score   = j.get("score", "")
        lines.append(f"  • [{rama}] {cargo} @ {empresa} ({score}%)")
    lines.append("\nAbre tu cliente de correo, adjunta el CV y envía.")
    return "\n".join(lines)


# ── Envío Telegram ─────────────────────────────────────────────────────────────

def _require_telegram() -> tuple[str, str]:
    token   = config.TELEGRAM_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID
    if not token or str(token).startswith("PEGA_AQUI"):
        raise RuntimeError("Telegram token no configurado")
    if not chat_id or str(chat_id).startswith("PEGA_AQUI"):
        raise RuntimeError("Telegram chat_id no configurado")
    return token, str(chat_id)


async def _send_text_async(token: str, chat_id: str, text: str) -> None:
    bot = telegram.Bot(token=token)
    async with bot:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")


async def _send_photo_async(
    token: str, chat_id: str, image_path: str, caption: str
) -> None:
    bot = telegram.Bot(token=token)
    async with bot:
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as photo:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=caption,
                    parse_mode="HTML",
                )
        else:
            # Sin imagen disponible: enviar sólo el texto
            await bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML")


def send_cv_ready_browser(jobs: list[dict], timeout_min: int = 5) -> None:
    """Notifica a Lorena que hay CVs listos para aplicación manual en browser."""
    token, chat_id = _require_telegram()
    text = build_browser_notification(jobs, timeout_min=timeout_min)
    asyncio.run(_send_text_async(token, chat_id, text))
    print(f"[HITL] Notificación Canal B enviada ({len(jobs)} cargos)")


def send_cv_ready_email(jobs: list[dict]) -> None:
    """Notifica a Lorena que hay borradores de correo listos para adjuntar CV."""
    token, chat_id = _require_telegram()
    text = build_email_notification(jobs, email=config.EMAIL_ACCOUNT)
    asyncio.run(_send_text_async(token, chat_id, text))
    print(f"[HITL] Notificación Canal C enviada ({len(jobs)} cargos)")


def send_email_body(job: dict, body_text: str) -> None:
    """
    Envía el body del correo completo a Telegram.
    Lorena lo copia desde Telegram, abre Gmail y pega.

    Telegram tiene límite de 4096 chars por mensaje. Si el body es más largo,
    se envían dos mensajes.
    """
    token, chat_id = _require_telegram()
    cargo   = job.get("cargo", "")
    empresa = job.get("empresa", "")
    pdf_hint = "📎 Recuerda adjuntar el CV al enviar."

    header = (
        f"✉️ <b>BODY LISTO — {cargo} @ {empresa}</b>\n"
        f"Copia este texto, abre Gmail, crea un correo nuevo y pega.\n"
        f"Asunto: <code>Aplicación: {cargo} — Lorena Ruiz</code>\n"
        f"{pdf_hint}\n\n"
    )

    # Telegram no admite HTML en el body del CV (puede contener símbolos peligrosos)
    # Enviamos el body como mensaje sin parse_mode para que no falle
    full = header + body_text

    async def _send():
        bot = telegram.Bot(token=token)
        async with bot:
            # Header con HTML
            await bot.send_message(chat_id=chat_id, text=header, parse_mode="HTML")
            # Body como texto plano (sin parse_mode para evitar errores con < > &)
            chunk_size = 4000
            for i in range(0, len(body_text), chunk_size):
                await bot.send_message(
                    chat_id=chat_id,
                    text=body_text[i:i + chunk_size],
                )

    asyncio.run(_send())
    print(f"[HITL] Body del correo enviado a Telegram para {cargo} @ {empresa}")


def send_screenshot_for_approval(image_path: str, job: dict) -> None:
    """
    Envía screenshot de la página Review de LinkedIn Easy Apply a Lorena.
    Lorena responde SI o NO para aprobar o rechazar el envío.
    """
    token, chat_id = _require_telegram()
    cargo   = job.get("cargo", "")
    empresa = job.get("empresa", "")
    timeout_min = config.HITL_TIMEOUT_S // 60
    caption = (
        f"⚠️ <b>REVISAR ANTES DE ENVIAR</b>\n\n"
        f"Cargo: {cargo}\n"
        f"Empresa: {empresa}\n\n"
        f"✅ Responde <b>SI</b> para confirmar el envío\n"
        f"❌ Responde <b>NO</b> para cancelar\n"
        f"⏱ Tienes {timeout_min} minutos"
    )
    asyncio.run(_send_photo_async(token, chat_id, image_path, caption))
    print(f"[HITL] Screenshot enviado — esperando respuesta para {cargo} @ {empresa}")


def send_screenshot_for_approval_sync(image_path: str, job: dict,
                                       extra_msg: str = "") -> None:
    """
    Versión sync de send_screenshot_for_approval — usa urllib.request (sin asyncio).
    Seguro para llamar desde dentro del context manager de Playwright sync API.

    Envía sendPhoto si image_path existe, sendMessage si no.
    extra_msg: mensaje adicional a incluir en el caption (ej: instrucciones manuales).
    Nunca propaga excepciones — errores se silencian con print.
    """
    try:
        token, chat_id = _require_telegram()
        cargo       = job.get("cargo", "")
        empresa     = job.get("empresa", "")
        timeout_min = getattr(config, "HITL_TIMEOUT_S", 300) // 60
        caption = (
            f"⚠️ REVISAR ANTES DE ENVIAR\n\n"
            f"Cargo: {cargo}\n"
            f"Empresa: {empresa}\n\n"
            f"Responde SI para confirmar el envio\n"
            f"Responde NO para cancelar\n"
            f"Tienes {timeout_min} minutos"
        )
        if extra_msg:
            caption += f"\n\n{extra_msg}"
        base_url = f"https://api.telegram.org/bot{token}"

        if image_path and os.path.exists(image_path):
            # Enviar foto con multipart/form-data
            boundary = b"----JobAppAgentBoundary"
            with open(image_path, "rb") as img_file:
                img_data = img_file.read()
            body = (
                b"--" + boundary + b"\r\n"
                b'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
                + chat_id.encode() + b"\r\n"
                + b"--" + boundary + b"\r\n"
                b'Content-Disposition: form-data; name="caption"\r\n\r\n'
                + caption.encode("utf-8") + b"\r\n"
                + b"--" + boundary + b"\r\n"
                b'Content-Disposition: form-data; name="photo"; filename="screenshot.png"\r\n'
                b"Content-Type: image/png\r\n\r\n"
                + img_data + b"\r\n"
                + b"--" + boundary + b"--\r\n"
            )
            req = urllib.request.Request(
                f"{base_url}/sendPhoto",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
        else:
            # Sin imagen — enviar solo texto
            data = urllib.parse.urlencode({
                "chat_id": chat_id,
                "text":    caption,
            }).encode()
            req = urllib.request.Request(f"{base_url}/sendMessage", data=data)
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()

        print(f"[HITL] Screenshot sync enviado para {cargo} @ {empresa}")
    except Exception as e:
        print(f"[HITL] send_screenshot_for_approval_sync error: {e}")


# ── Polling HITL ───────────────────────────────────────────────────────────────

def _get_latest_update_id(base_url: str) -> int | None:
    """Retorna update_id+1 del mensaje más reciente para ignorar mensajes anteriores."""
    url = f"{base_url}/getUpdates?limit=1&timeout=0"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        results = data.get("result", [])
        if results:
            return results[-1]["update_id"] + 1
    except Exception:
        pass
    return None


def _fetch_updates(base_url: str, offset: int | None, poll_timeout: int) -> dict:
    """Hace una llamada getUpdates. Función separada para facilitar mocking en tests."""
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

    Retorna True  si Lorena responde 'SI' / 'SÍ' / 'YES' / 'S' / '✅'.
    Retorna False si responde 'NO' / 'N' / 'CANCEL', o si expira el timeout.
    Ignora mensajes de chats distintos al configurado.
    """
    token    = config.TELEGRAM_TOKEN
    chat_id  = str(config.TELEGRAM_CHAT_ID)
    base_url = f"https://api.telegram.org/bot{token}"

    offset   = _get_latest_update_id(base_url)
    deadline = time.time() + timeout_s

    _SI_WORDS = {"SI", "SÍ", "YES", "S", "✅", "OK"}
    _NO_WORDS = {"NO", "N", "CANCEL", "CANCELAR", "❌"}

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
