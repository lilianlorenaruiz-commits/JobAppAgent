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
from unittest.mock import MagicMock, patch
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

def _mock_playwright_ctx():
    """Mock completo de sync_playwright context manager."""
    mock_page = MagicMock()
    mock_page.wait_for_event.side_effect = Exception("browser closed")
    mock_ctx = MagicMock()
    mock_ctx.pages = [mock_page]
    mock_pw_instance = MagicMock()
    mock_pw_instance.chromium.launch_persistent_context.return_value = mock_ctx
    mock_pw_cm = MagicMock()
    mock_pw_cm.__enter__.return_value = mock_pw_instance
    mock_pw_cm.__exit__.return_value = False
    return mock_pw_cm


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
        mock_pw_cm = _mock_playwright_ctx()
        with (
            patch("agents.applicator.sync_playwright", return_value=mock_pw_cm),
            patch("agents.applicator.send_cv_ready_browser") as mock_tg,
        ):
            apply(_JOB_B, "cv.pdf", dry_run=False)
        mock_tg.assert_called_once()

    def test_notification_includes_job_cargo(self):
        """La notificación Telegram recibe el cargo correcto."""
        from agents.applicator import apply
        mock_pw_cm = _mock_playwright_ctx()
        with (
            patch("agents.applicator.sync_playwright", return_value=mock_pw_cm),
            patch("agents.applicator.send_cv_ready_browser") as mock_tg,
        ):
            apply(_JOB_B, "cv.pdf", dry_run=False)
        jobs_arg = mock_tg.call_args[0][0]
        assert jobs_arg[0]["cargo"] == _JOB_B["cargo"]

    def test_notification_includes_timeout_min(self):
        """La notificación incluye timeout_min derivado de HITL_TIMEOUT_S."""
        from agents.applicator import apply
        import config
        mock_pw_cm = _mock_playwright_ctx()
        with (
            patch("agents.applicator.sync_playwright", return_value=mock_pw_cm),
            patch("agents.applicator.send_cv_ready_browser") as mock_tg,
        ):
            apply(_JOB_B, "cv.pdf", dry_run=False)
        timeout_arg = mock_tg.call_args[1].get("timeout_min")
        assert timeout_arg == config.HITL_TIMEOUT_S // 60

    def test_result_schema(self):
        """Resultado tiene las 4 claves requeridas y canal==B."""
        from agents.applicator import apply
        mock_pw_cm = _mock_playwright_ctx()
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
        mock_pw_cm = _mock_playwright_ctx()
        with (
            patch("agents.applicator.sync_playwright", return_value=mock_pw_cm),
            patch("agents.applicator.send_cv_ready_browser", side_effect=Exception("red")),
        ):
            result = apply(_JOB_B, "cv.pdf", dry_run=False)
        assert result["canal"] == "B"
