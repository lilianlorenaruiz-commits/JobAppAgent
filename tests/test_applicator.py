"""
Tests de comportamiento del Applicator — Agente 5.
Verifica detección de canal y modo dry_run. No abre navegador real.
"""
import pytest
from agents.applicator import apply, _detect_channel


# ── Detección de canal ─────────────────────────────────────────────────────────

class TestChannelDetection:
    """_detect_channel asigna el canal correcto según la URL."""

    def test_linkedin_url_is_channel_a(self):
        assert _detect_channel("https://www.linkedin.com/jobs/view/1234567890") == "A"

    def test_linkedin_short_url_is_channel_a(self):
        assert _detect_channel("https://linkedin.com/jobs/view/abc") == "A"

    def test_elempleo_is_channel_b(self):
        assert _detect_channel("https://www.elempleo.com/co/oferta-empleo/abc") == "B"

    def test_computrabajo_is_channel_b(self):
        assert _detect_channel("https://co.computrabajo.com/oferta/abc") == "B"

    def test_indeed_is_channel_b(self):
        assert _detect_channel("https://co.indeed.com/viewjob?jk=abc") == "B"

    def test_company_website_is_channel_c(self):
        assert _detect_channel("https://careers.acmecorp.com/apply/123") == "C"

    def test_empty_url_is_channel_c(self):
        assert _detect_channel("") == "C"

    def test_unknown_url_is_channel_c(self):
        assert _detect_channel("https://some-company.com/jobs/senior-pm") == "C"


# ── dry_run: no abre navegador ────────────────────────────────────────────────

_JOB_LINKEDIN = {
    "cargo":     "Paid Media Manager",
    "empresa":   "Acme Corp",
    "url":       "https://www.linkedin.com/jobs/view/9999999999",
    "modalidad": "Híbrido",
    "ubicacion": "Bogotá",
    "rama":      "C",
}

_JOB_WEB = {
    "cargo":     "Trade Marketing Specialist",
    "empresa":   "Grupo Éxito",
    "url":       "https://www.elempleo.com/co/oferta-empleo/trade/123",
    "modalidad": "Presencial",
    "ubicacion": "Bogotá",
    "rama":      "B",
}

_JOB_EMAIL = {
    "cargo":     "Brand Strategist",
    "empresa":   "Startup XYZ",
    "url":       "https://startupxyz.com/careers/brand-strategist",
    "modalidad": "Remoto",
    "ubicacion": "Colombia",
    "rama":      "A",
}


class TestDryRun:
    """En dry_run=True el applicator simula sin abrir navegador."""

    def test_linkedin_dry_run_returns_enviado(self):
        result = apply(_JOB_LINKEDIN, "", dry_run=True)
        assert result["enviado"] is True

    def test_linkedin_dry_run_canal_a(self):
        result = apply(_JOB_LINKEDIN, "", dry_run=True)
        assert result["canal"] == "A"

    def test_web_dry_run_returns_enviado(self):
        result = apply(_JOB_WEB, "", dry_run=True)
        assert result["enviado"] is True

    def test_web_dry_run_canal_b(self):
        result = apply(_JOB_WEB, "", dry_run=True)
        assert result["canal"] == "B"

    def test_email_dry_run_returns_enviado(self):
        result = apply(_JOB_EMAIL, "", dry_run=True)
        assert result["enviado"] is True

    def test_email_dry_run_canal_c(self):
        result = apply(_JOB_EMAIL, "", dry_run=True)
        assert result["canal"] == "C"

    def test_result_has_required_keys(self):
        result = apply(_JOB_LINKEDIN, "", dry_run=True)
        assert "enviado" in result
        assert "canal" in result
        assert "url" in result
        assert "mensaje" in result

    def test_result_url_matches_job(self):
        result = apply(_JOB_LINKEDIN, "/fake/path.pdf", dry_run=True)
        assert result["url"] == _JOB_LINKEDIN["url"]

    def test_dry_run_mensaje_indicates_simulation(self):
        result = apply(_JOB_LINKEDIN, "", dry_run=True)
        assert "dry_run" in result["mensaje"].lower() or "simulad" in result["mensaje"].lower()
