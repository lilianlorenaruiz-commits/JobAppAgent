"""
Ciclo 15 RED→GREEN: telegram_hitl — formato de notificaciones y polling HITL.
Tests sin Telegram real: mocked via unittest.mock.
"""
import os
import sys
from unittest.mock import patch
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
            result = wait_for_approval(timeout_s=1)
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
                        "chat": {"id": 999999},
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


# ── send_message_sync ─────────────────────────────────────────────────────────

class TestSendMessageSync:
    """send_message_sync envía texto plano a Telegram vía urllib (sin asyncio).

    Escenario real probado 2026-05-14: Lorena respondió NO en Telegram durante
    el smoke test de Canal A. El agente debe notificar la cancelación de vuelta
    sin propagar excepciones (safe dentro del contexto de Playwright sync).
    """

    def test_calls_sendmessage_endpoint(self):
        """Verifica que se llama al endpoint /sendMessage de Telegram."""
        from agents.telegram_hitl import send_message_sync
        from unittest.mock import MagicMock, patch

        fake_resp = MagicMock()
        fake_resp.__enter__ = lambda s: s
        fake_resp.__exit__ = MagicMock(return_value=False)
        fake_resp.read.return_value = b'{"ok":true}'

        with (
            patch("agents.telegram_hitl.config.TELEGRAM_TOKEN", "tok123"),
            patch("agents.telegram_hitl.config.TELEGRAM_CHAT_ID", "456"),
            patch("agents.telegram_hitl.urllib.request.urlopen", return_value=fake_resp) as mock_open,
        ):
            send_message_sync("❌ Aplicación CANCELADA\nCargo: PM\nEmpresa: Acme")

        called_url = mock_open.call_args[0][0].full_url
        assert "/sendMessage" in called_url

    def test_text_appears_in_request_body(self):
        """El texto del mensaje se incluye en el cuerpo de la petición."""
        from agents.telegram_hitl import send_message_sync
        from unittest.mock import MagicMock, patch

        captured = {}
        fake_resp = MagicMock()
        fake_resp.__enter__ = lambda s: s
        fake_resp.__exit__ = MagicMock(return_value=False)
        fake_resp.read.return_value = b'{"ok":true}'

        def capture_req(req, timeout=None):
            captured["body"] = req.data.decode("utf-8") if req.data else ""
            return fake_resp

        with (
            patch("agents.telegram_hitl.config.TELEGRAM_TOKEN", "tok123"),
            patch("agents.telegram_hitl.config.TELEGRAM_CHAT_ID", "456"),
            patch("agents.telegram_hitl.urllib.request.urlopen", side_effect=capture_req),
        ):
            send_message_sync("Cancelado: Social Analyst @ PGD")

        assert "Cancelado" in captured["body"]

    def test_never_raises_on_network_error(self):
        """send_message_sync silencia errores de red — no propaga excepciones."""
        from agents.telegram_hitl import send_message_sync
        from unittest.mock import patch

        with (
            patch("agents.telegram_hitl.config.TELEGRAM_TOKEN", "tok123"),
            patch("agents.telegram_hitl.config.TELEGRAM_CHAT_ID", "456"),
            patch("agents.telegram_hitl.urllib.request.urlopen",
                  side_effect=OSError("connection refused")),
        ):
            send_message_sync("este mensaje fallará en red")  # no debe lanzar
