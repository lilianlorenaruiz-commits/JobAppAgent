"""
Fixtures compartidos para el test suite de JobAppAgent.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

JOB_GRUPO_RED = {
    "cargo":       "Trafficker Digital Senior Bilingüe",
    "empresa":     "Grupo RED",
    "url":         "https://linkedin.com/jobs/dry-C-grupo-red",
    "modalidad":   "Híbrido",
    "ubicacion":   "Bogotá",
    "rama":        "C",
    "descripcion": (
        "Buscamos Trafficker Digital Senior con experiencia en gestión y optimización "
        "de campañas de paid media en Google Ads, Meta Ads (Facebook e Instagram), "
        "Amazon Ads y LinkedIn Ads. Manejo de programmatic advertising, optimización "
        "de ROAS y ACOS, análisis de métricas de performance (CTR, CPC, DPV, NTB Sales) "
        "y presupuestos superiores a USD 200K. Inglés C1/C2 indispensable. "
        "Experiencia en Amazon DSP, AMC y herramientas de data analysis. "
        "Modalidad híbrida, Bogotá."
    ),
}


@pytest.fixture(scope="session")
def cv():
    from agents.cv_parser import parse_cv
    return parse_cv()


@pytest.fixture(scope="session")
def cv_text_grupo_red(cv):
    """Genera el CV para Grupo RED una sola vez para toda la sesión."""
    from agents.cv_rewriter import rewrite
    result = rewrite(cv, JOB_GRUPO_RED, rama="C")
    assert result["passed_ats"], (
        f"CV no pasó ATS ({result['ats_score']}%) — "
        "si el rewriter no llega a 95% los demás tests no tienen sentido"
    )
    return result["cv_text"]
