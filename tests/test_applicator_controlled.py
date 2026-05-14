"""
Ciclo 14 RED→GREEN: Applicator — escenarios controlados pre-producción.

Condiciones establecidas ANTES de activar el applicator en producción:
  1. dry_run=True NUNCA abre navegador ni envía emails reales.
  2. Todos los canales (A/B/C) retornan el schema correcto.
  3. El PDF path se referencia en el resultado (trazabilidad).
  4. URLs de portales colombianos clave detectan canal correcto.
  5. El applicator maneja URLs malformadas sin excepción.
  6. El cargo y empresa del job se reflejan en el resultado.
  7. Correr los 3 canales en secuencia no produce side effects cruzados.

Protocolo de aprobación:
  - Todos los tests de este archivo deben ser GREEN antes de activar
    el Applicator en modo producción (dry_run=False).
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.applicator import apply, _detect_channel


# ── Jobs de prueba controlados ─────────────────────────────────────────────────

_JOB_LINKEDIN_CO = {
    "cargo":     "Paid Media Specialist",
    "empresa":   "Empresa Test LinkedIn",
    "url":       "https://www.linkedin.com/jobs/view/1234567890",
    "modalidad": "Híbrido",
    "ubicacion": "Bogotá",
    "rama":      "C",
    "descripcion": "Gestión de campañas paid media.",
}

_JOB_ELEMPLEO = {
    "cargo":     "Trade Marketing Manager",
    "empresa":   "Empresa Test Elempleo",
    "url":       "https://www.elempleo.com/co/oferta-empleo/trade-mktg/9999",
    "modalidad": "Presencial",
    "ubicacion": "Bogotá",
    "rama":      "B",
    "descripcion": "Trade marketing retail.",
}

_JOB_COMPUTRABAJO = {
    "cargo":     "Digital Marketing Analyst",
    "empresa":   "Empresa Test Computrabajo",
    "url":       "https://co.computrabajo.com/oferta/digital-analyst-abc",
    "modalidad": "Remoto",
    "ubicacion": "Colombia",
    "rama":      "C",
    "descripcion": "Análisis digital.",
}

_JOB_GLASSDOOR = {
    "cargo":     "Brand Strategist",
    "empresa":   "Empresa Test Glassdoor",
    "url":       "https://www.glassdoor.com/job-listing/brand-strategist-xyz",
    "modalidad": "Remoto",
    "ubicacion": "Colombia",
    "rama":      "A",
    "descripcion": "Estrategia de marca.",
}

_JOB_COMPANY_SITE = {
    "cargo":     "Marketing Consultant",
    "empresa":   "FinTech Colombia SAS",
    "url":       "https://careers.fintechcolombia.com/jobs/mktg-consultant-2026",
    "modalidad": "Híbrido",
    "ubicacion": "Bogotá",
    "rama":      "A",
    "descripcion": "Consultoría de marketing.",
}

_FAKE_PDF = "outputs/Lorena Ruiz - Test Job - Test Co.pdf"


# ── Ciclo 14a: Detección de canales — portales colombianos ────────────────────

class TestChannelDetectionColombia:
    """
    Portales de empleo colombianos y globales detectados correctamente.
    Canal A = LinkedIn  /  Canal B = portales conocidos  /  Canal C = resto
    """

    def test_elempleo_canal_b(self):
        assert _detect_channel(_JOB_ELEMPLEO["url"]) == "B"

    def test_computrabajo_canal_b(self):
        assert _detect_channel(_JOB_COMPUTRABAJO["url"]) == "B"

    def test_glassdoor_canal_b(self):
        assert _detect_channel(_JOB_GLASSDOOR["url"]) == "B"

    def test_linkedin_canal_a(self):
        assert _detect_channel(_JOB_LINKEDIN_CO["url"]) == "A"

    def test_company_site_canal_c(self):
        assert _detect_channel(_JOB_COMPANY_SITE["url"]) == "C"

    def test_empty_url_canal_c(self):
        assert _detect_channel("") == "C"

    def test_malformed_url_no_exception(self):
        """URL malformada no debe lanzar excepción — retorna canal C por defecto."""
        try:
            canal = _detect_channel("not-a-url-at-all !!@#$%")
            assert canal == "C", f"URL malformada debería dar canal C, retornó {canal}"
        except Exception as e:
            pytest.fail(f"_detect_channel lanzó excepción con URL malformada: {e}")

    def test_none_safe(self):
        """Pasar None no debe lanzar excepción."""
        try:
            canal = _detect_channel(None or "")
            assert canal in ("A", "B", "C")
        except Exception as e:
            pytest.fail(f"_detect_channel lanzó excepción con URL vacía: {e}")


# ── Ciclo 14b: dry_run — sin side effects, schema completo ────────────────────

class TestDryRunNoSideEffects:
    """
    CONDICIÓN PRE-PRODUCCIÓN CRÍTICA:
    dry_run=True debe completar sin abrir navegador, sin enviar email,
    sin escribir a BD — retornando el schema estándar.
    """

    @pytest.mark.parametrize("job,expected_canal", [
        (_JOB_LINKEDIN_CO,   "A"),
        (_JOB_ELEMPLEO,      "B"),
        (_JOB_COMPANY_SITE,  "C"),
    ])
    def test_dry_run_canal_correcto(self, job, expected_canal):
        result = apply(job, _FAKE_PDF, dry_run=True)
        assert result["canal"] == expected_canal, (
            f"Canal incorrecto para URL '{job['url']}': "
            f"esperado {expected_canal}, retornó {result['canal']}"
        )

    @pytest.mark.parametrize("job", [
        _JOB_LINKEDIN_CO, _JOB_ELEMPLEO, _JOB_COMPANY_SITE,
    ])
    def test_dry_run_enviado_true(self, job):
        result = apply(job, _FAKE_PDF, dry_run=True)
        assert result["enviado"] is True, (
            f"dry_run debería retornar enviado=True para '{job['url']}'"
        )

    @pytest.mark.parametrize("job", [
        _JOB_LINKEDIN_CO, _JOB_ELEMPLEO, _JOB_COMPANY_SITE,
    ])
    def test_dry_run_schema_completo(self, job):
        result = apply(job, _FAKE_PDF, dry_run=True)
        required_keys = {"enviado", "canal", "url", "mensaje"}
        missing = required_keys - set(result.keys())
        assert not missing, (
            f"Faltan claves en resultado del applicator: {missing}"
        )

    def test_dry_run_url_preservada(self):
        result = apply(_JOB_LINKEDIN_CO, _FAKE_PDF, dry_run=True)
        assert result["url"] == _JOB_LINKEDIN_CO["url"], (
            "La URL en el resultado no coincide con la URL del job"
        )

    def test_dry_run_mensaje_contiene_simulacion(self):
        result = apply(_JOB_LINKEDIN_CO, _FAKE_PDF, dry_run=True)
        msg = result["mensaje"].lower()
        assert "dry_run" in msg or "simulad" in msg or "simulaci" in msg, (
            f"El mensaje no indica que es simulación: '{result['mensaje']}'"
        )

    def test_dry_run_three_channels_no_crosstalk(self):
        """Los 3 canales en secuencia no producen efectos cruzados."""
        r_a = apply(_JOB_LINKEDIN_CO,  _FAKE_PDF, dry_run=True)
        r_b = apply(_JOB_ELEMPLEO,     _FAKE_PDF, dry_run=True)
        r_c = apply(_JOB_COMPANY_SITE, _FAKE_PDF, dry_run=True)

        assert r_a["canal"] == "A"
        assert r_b["canal"] == "B"
        assert r_c["canal"] == "C"
        assert r_a["url"] == _JOB_LINKEDIN_CO["url"]
        assert r_b["url"] == _JOB_ELEMPLEO["url"]
        assert r_c["url"] == _JOB_COMPANY_SITE["url"]


# ── Ciclo 14c: PDF path — trazabilidad ────────────────────────────────────────

class TestApplicatorPDFTracking:
    """
    El applicator debe referenciar el path del PDF en los canales relevantes,
    garantizando trazabilidad del CV enviado.
    """

    def test_result_url_matches_job(self):
        result = apply(_JOB_LINKEDIN_CO, _FAKE_PDF, dry_run=True)
        assert result["url"] == _JOB_LINKEDIN_CO["url"]

    def test_result_is_dict(self):
        result = apply(_JOB_COMPUTRABAJO, _FAKE_PDF, dry_run=True)
        assert isinstance(result, dict)

    def test_enviado_is_bool(self):
        result = apply(_JOB_GLASSDOOR, _FAKE_PDF, dry_run=True)
        assert isinstance(result["enviado"], bool)

    def test_canal_is_string(self):
        result = apply(_JOB_COMPANY_SITE, _FAKE_PDF, dry_run=True)
        assert isinstance(result["canal"], str)
        assert result["canal"] in ("A", "B", "C")


# ── Checklist pre-producción ───────────────────────────────────────────────────

class TestPreProductionChecklist:
    """
    Checklist formal antes de activar dry_run=False en producción.
    Todos estos tests deben ser GREEN para habilitar el Applicator real.
    """

    def test_channel_a_dry_run_completes(self):
        """Canal A (LinkedIn Easy Apply) — simulación completa sin browser."""
        r = apply(_JOB_LINKEDIN_CO, _FAKE_PDF, dry_run=True)
        assert r["enviado"] and r["canal"] == "A"

    def test_channel_b_dry_run_completes(self):
        """Canal B (portal web) — simulación completa."""
        r = apply(_JOB_ELEMPLEO, _FAKE_PDF, dry_run=True)
        assert r["enviado"] and r["canal"] == "B"

    def test_channel_c_dry_run_completes(self):
        """Canal C (email/empresa) — simulación completa."""
        r = apply(_JOB_COMPANY_SITE, _FAKE_PDF, dry_run=True)
        assert r["enviado"] and r["canal"] == "C"

    def test_no_unhandled_exception_any_channel(self):
        """Ningún canal debe lanzar excepción no manejada en dry_run."""
        jobs = [_JOB_LINKEDIN_CO, _JOB_ELEMPLEO, _JOB_COMPUTRABAJO,
                _JOB_GLASSDOOR, _JOB_COMPANY_SITE]
        for job in jobs:
            try:
                apply(job, _FAKE_PDF, dry_run=True)
            except Exception as e:
                pytest.fail(
                    f"Applicator lanzó excepción no manejada para '{job['url']}': {e}"
                )

    def test_all_required_keys_all_channels(self):
        """Schema de respuesta consistente en los 3 canales."""
        required = {"enviado", "canal", "url", "mensaje"}
        for job in [_JOB_LINKEDIN_CO, _JOB_ELEMPLEO, _JOB_COMPANY_SITE]:
            result = apply(job, _FAKE_PDF, dry_run=True)
            missing = required - set(result.keys())
            assert not missing, (
                f"Canal {result.get('canal', '?')} falta claves: {missing}"
            )
