"""
Ciclo 16 RED→GREEN: Applicator v2 Canal C.
  - _generate_email_body() produce body coherente con CV + JD
  - detect idioma del JD y responde en ese idioma (via prompt)
  - apply() dry_run no llama Claude ni Telegram

Todos los tests mockan Claude y Telegram — sin efectos reales.
"""
import os
import sys
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_JOB = {
    "cargo":   "Paid Media Manager",
    "empresa": "Rappi",
    "url":     "https://rappi.com/jobs/123",
    "rama":    "C",
    "score":   87,
}
_JD = (
    "We are looking for a Paid Media Manager with experience in Meta Ads and Google Ads, "
    "managing budgets over USD 100K."
)
_CV = (
    "Lorena Ruiz. Paid Media Specialist. LinkedIn Ads, Meta Ads, Google Ads. "
    "Budgets USD 200K+. 14 years experience."
)


# ── helpers ────────────────────────────────────────────────────────────────────

def _mock_claude(text: str):
    """Devuelve un mock de anthropic client que retorna `text` como respuesta."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=text)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    return mock_client


# ── Ciclo 16: _generate_email_body ────────────────────────────────────────────

class TestEmailBodyGeneration:
    """_generate_email_body() produce body coherente con CV + JD."""

    def test_returns_non_empty_string(self):
        from agents.applicator import _generate_email_body
        client = _mock_claude("Me postulo al cargo de Paid Media Manager.")
        with patch("agents.applicator.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = client
            body = _generate_email_body(_JOB, _CV, _JD)
        assert isinstance(body, str) and len(body) > 10

    def test_prompt_includes_job_description(self):
        """El prompt enviado a Claude incluye keywords del JD."""
        from agents.applicator import _generate_email_body
        client = _mock_claude("body")
        with patch("agents.applicator.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = client
            _generate_email_body(_JOB, _CV, _JD)
        call_args = str(client.messages.create.call_args)
        assert "Meta Ads" in call_args or "Google Ads" in call_args or "100K" in call_args

    def test_prompt_includes_cv_text(self):
        """El prompt enviado a Claude incluye información del CV tailored."""
        from agents.applicator import _generate_email_body
        client = _mock_claude("body")
        with patch("agents.applicator.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = client
            _generate_email_body(_JOB, _CV, _JD)
        call_args = str(client.messages.create.call_args)
        assert "Lorena Ruiz" in call_args or "200K" in call_args

    def test_prompt_instructs_language_detection(self):
        """El prompt instruye a Claude a detectar el idioma del JD."""
        from agents.applicator import _generate_email_body
        client = _mock_claude("body")
        with patch("agents.applicator.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = client
            _generate_email_body(_JOB, _CV, _JD)
        call_args = str(client.messages.create.call_args)
        assert "language" in call_args.lower() or "idioma" in call_args.lower()

    def test_prompt_instructs_max_200_words(self):
        """El prompt impone límite de 200 palabras."""
        from agents.applicator import _generate_email_body
        client = _mock_claude("body")
        with patch("agents.applicator.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = client
            _generate_email_body(_JOB, _CV, _JD)
        call_args = str(client.messages.create.call_args)
        assert "200" in call_args

    def test_fallback_when_anthropic_unavailable(self):
        """Si anthropic es None (no instalado), retorna body estático sin lanzar excepción."""
        from agents.applicator import _generate_email_body
        with patch("agents.applicator.anthropic", None):
            body = _generate_email_body(_JOB, _CV, _JD)
        assert isinstance(body, str)
        assert len(body) > 20
        assert "Paid Media Manager" in body or "Rappi" in body

    def test_fallback_when_empty_jd(self):
        """Con job_description vacío, no lanza excepción."""
        from agents.applicator import _generate_email_body
        client = _mock_claude("Fallback body.")
        with patch("agents.applicator.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = client
            body = _generate_email_body(_JOB, "", "")
        assert isinstance(body, str)


# ── Ciclo 16: apply() signature actualizada ───────────────────────────────────

class TestApplySignatureCanalC:
    """apply() acepta cv_text y job_description sin errores."""

    def test_dry_run_canal_c_accepts_new_params(self):
        """dry_run=True acepta cv_text y job_description sin llamar Claude."""
        from agents.applicator import apply
        with patch("agents.applicator._generate_email_body") as mock_gen:
            result = apply(
                _JOB, "cv.pdf",
                dry_run=True,
                cv_text=_CV,
                job_description=_JD,
            )
        mock_gen.assert_not_called()
        assert result["canal"] == "C"
        assert result["enviado"] is True

    def test_dry_run_no_telegram_call(self):
        """dry_run=True no envía notificación Telegram."""
        from agents.applicator import apply
        with (
            patch("agents.applicator._generate_email_body"),
            patch("agents.telegram_hitl.send_cv_ready_email") as mock_tg,
        ):
            apply(_JOB, "cv.pdf", dry_run=True, cv_text=_CV, job_description=_JD)
        mock_tg.assert_not_called()

    def test_canal_c_real_calls_generate_body(self):
        """Sin dry_run, _apply_email llama a _generate_email_body."""
        from agents.applicator import apply

        mock_body = "Estimados, me postulo al cargo de Paid Media Manager."
        mock_client = _mock_claude(mock_body)

        with (
            patch("agents.applicator.anthropic") as mock_ant,
            patch("agents.applicator.os.startfile"),
            patch("agents.applicator.send_cv_ready_email"),  # no Telegram real
            patch("agents.applicator.send_email_body"),       # no Telegram real
            patch("agents.applicator.webbrowser"),
        ):
            mock_ant.Anthropic.return_value = mock_client
            result = apply(
                _JOB, "cv.pdf",
                dry_run=False,
                cv_text=_CV,
                job_description=_JD,
            )
        assert result["canal"] == "C"
        mock_client.messages.create.assert_called_once()

    def test_canal_c_real_sends_telegram_notification(self):
        """Sin dry_run, _apply_email llama a send_cv_ready_email y send_email_body."""
        from agents.applicator import apply
        mock_client = _mock_claude("Estimados, me postulo.")
        with (
            patch("agents.applicator.anthropic") as mock_ant,
            patch("agents.applicator.os.startfile"),
            patch("agents.applicator.webbrowser"),
            patch("agents.applicator.send_cv_ready_email") as mock_notify,
            patch("agents.applicator.send_email_body") as mock_body_tg,
        ):
            mock_ant.Anthropic.return_value = mock_client
            apply(_JOB, "cv.pdf", dry_run=False, cv_text=_CV, job_description=_JD)
        mock_notify.assert_called_once()
        mock_body_tg.assert_called_once()

    def test_canal_c_result_schema(self):
        """El resultado tiene las 4 claves requeridas."""
        from agents.applicator import apply
        mock_client = _mock_claude("Estimados, me postulo.")
        with (
            patch("agents.applicator.anthropic") as mock_ant,
            patch("agents.applicator.os.startfile"),
            patch("agents.applicator.webbrowser"),
            patch("agents.applicator.send_cv_ready_email"),
            patch("agents.applicator.send_email_body"),
        ):
            mock_ant.Anthropic.return_value = mock_client
            result = apply(_JOB, "cv.pdf", dry_run=False, cv_text=_CV, job_description=_JD)
        assert all(k in result for k in ("enviado", "canal", "url", "mensaje"))
        assert result["canal"] == "C"
