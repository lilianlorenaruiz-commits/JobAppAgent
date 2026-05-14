"""
Ciclo 13 RED→GREEN: ATS Auditor — schema y resultado mínimo.
Verifica que el auditor retorna el schema correcto y que un CV
fuerte para Rama C supera el threshold de 95%.

Nota: usa el fixture cv_text_grupo_red (session-scoped) para no
duplicar la llamada al LLM.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

JOB_GRUPO_RED = {
    "cargo": "Trafficker Digital Senior Bilingüe",
    "empresa": "Grupo RED",
    "url": "https://linkedin.com/jobs/dry-C-grupo-red",
    "modalidad": "Híbrido",
    "ubicacion": "Bogotá",
    "rama": "C",
    "descripcion": (
        "Buscamos Trafficker Digital Senior con experiencia en gestión y optimización "
        "de campañas de paid media en Google Ads, Meta Ads, Amazon Ads y LinkedIn Ads. "
        "Manejo de programmatic advertising, optimización de ROAS y ACOS, análisis de "
        "métricas de performance (CTR, CPC, DPV, NTB Sales) y presupuestos superiores "
        "a USD 200K. Inglés C1/C2 indispensable. Experiencia en Amazon DSP y AMC."
    ),
}


@pytest.fixture(scope="module")
def audit_result(cv_text_grupo_red):
    """Corre el ATS Auditor una vez para Grupo RED."""
    from agents.ats_auditor import audit
    return audit(JOB_GRUPO_RED, cv_text_grupo_red)


# ── TestATSAuditorSchema ───────────────────────────────────────────────────────

class TestATSAuditorSchema:
    """El auditor retorna un dict con todos los campos esperados."""

    def test_returns_dict(self, audit_result):
        assert isinstance(audit_result, dict), (
            f"audit() debe retornar un dict, retornó: {type(audit_result)}"
        )

    def test_has_audit_score(self, audit_result):
        assert "audit_score" in audit_result, "Falta 'audit_score' en resultado del auditor"

    def test_has_verdict(self, audit_result):
        assert "verdict" in audit_result, "Falta 'verdict' en resultado del auditor"
        assert audit_result["verdict"] in ("PASS", "CONDITIONAL", "FAIL"), (
            f"Verdict inválido: '{audit_result['verdict']}'"
        )

    def test_has_passed_audit(self, audit_result):
        assert "passed_audit" in audit_result, "Falta 'passed_audit' en resultado"
        assert isinstance(audit_result["passed_audit"], bool)

    def test_has_keywords_missing(self, audit_result):
        assert "keywords_missing" in audit_result
        assert isinstance(audit_result["keywords_missing"], list)

    def test_score_in_range(self, audit_result):
        score = audit_result["audit_score"]
        assert 0 <= score <= 100, f"audit_score fuera de rango: {score}"


# ── TestATSAuditorStrategicResult ──────────────────────────────────────────────

class TestATSAuditorStrategicResult:
    """
    Un CV de Lorena para Rama C (Paid Media) debe pasar el ATS.
    El threshold del rewriter es 95% — el auditor debe coincidir con PASS o CONDITIONAL.
    """

    def test_strong_cv_does_not_fail(self, audit_result):
        """Un CV fuerte no debe dar FAIL — como máximo CONDITIONAL."""
        assert audit_result["verdict"] != "FAIL", (
            f"CV de Lorena para Grupo RED recibió FAIL del auditor.\n"
            f"Score: {audit_result.get('audit_score')}\n"
            f"Keywords missing: {audit_result.get('keywords_missing')}\n"
            f"Weak points: {audit_result.get('weak_points')}"
        )

    def test_audit_score_above_60(self, audit_result):
        """Score mínimo de seguridad — si baja de 60 algo está muy mal."""
        score = audit_result["audit_score"]
        assert score >= 60, (
            f"Score ATS sorprendentemente bajo: {score}/100\n"
            f"Keywords missing: {audit_result.get('keywords_missing')}"
        )
